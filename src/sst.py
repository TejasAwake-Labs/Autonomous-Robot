"""
sst.py - Speech-to-text listener for the Autonomous Robot project.

Listens on the laptop microphone, detects when you start and stop talking,
transcribes the speech offline with faster-whisper, and passes the text to a
callback (main.py sends it to the LLM).

Optional .env values:
    STT_MODEL=base.en        tiny.en | base.en | small.en  (bigger = more accurate, slower)
    STT_LANGUAGE=en          language code, or empty for auto-detect (use a non-.en model then)
    STT_DEVICE=              microphone index (run: python sst.py --devices)
    STT_THRESHOLD=           fixed loudness threshold; empty = auto-calibrate

Standalone test:
    python sst.py            prints what you say
    python sst.py --devices  lists microphones
"""

import collections
import logging
import os
import queue
import sys
import threading
import time

import numpy as np
import sounddevice as sd
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = logging.getLogger(__name__)

# Set by tts.py while the robot is talking, so it doesn't transcribe itself.
try:
    from tts import speaking
except ImportError:
    speaking = threading.Event()

MODEL_SIZE = os.environ.get("STT_MODEL", "base.en")
LANGUAGE = os.environ.get("STT_LANGUAGE", "en").strip() or None
_dev = os.environ.get("STT_DEVICE", "").strip()
INPUT_DEVICE = int(_dev) if _dev.isdigit() else None
_thr = os.environ.get("STT_THRESHOLD", "").strip()
FIXED_THRESHOLD = float(_thr) if _thr else None

SAMPLE_RATE = 16_000
BLOCK_SECONDS = 0.03
BLOCK = int(SAMPLE_RATE * BLOCK_SECONDS)              # 480 samples
PRE_ROLL_BLOCKS = 10                                  # keep 0.3 s before speech starts
SILENCE_END_BLOCKS = int(0.8 / BLOCK_SECONDS)         # 0.8 s of quiet ends an utterance
MIN_SPEECH_BLOCKS = int(0.3 / BLOCK_SECONDS)          # ignore clicks shorter than 0.3 s
MAX_UTTERANCE_BLOCKS = int(15 / BLOCK_SECONDS)        # hard cap: 15 s
COOLDOWN_AFTER_SPEAKING = 0.6                         # seconds of deafness after the robot stops talking

# Whisper sometimes "hears" these in pure noise
_HALLUCINATIONS = {"you", "thank you", "thanks for watching", "bye", "the end"}


def list_devices():
    print(sd.query_devices())


def _rms(block):
    return float(np.sqrt(np.mean(block ** 2)))


def _calibrate(q):
    """Measure ambient noise for ~1 s and derive a speech threshold."""
    levels = []
    end = time.time() + 1.0
    while time.time() < end:
        try:
            levels.append(_rms(q.get(timeout=0.2)))
        except queue.Empty:
            pass
    ambient = float(np.median(levels)) if levels else 0.005
    return max(0.012, ambient * 3.0)


def _transcribe(model, audio):
    segments, _ = model.transcribe(
        audio,
        language=LANGUAGE,
        beam_size=1,
        vad_filter=True,
        condition_on_previous_text=False,
    )
    parts = [s.text.strip() for s in segments if s.no_speech_prob < 0.6]
    text = " ".join(p for p in parts if p).strip()
    if text.lower().strip(" .!?,") in _HALLUCINATIONS:
        return ""
    return text


def stt_listener(on_text, stop_event, enabled_event=None):
    """
    Background thread body.

    on_text(text)   called with each transcribed utterance (may block; audio
                    captured meanwhile is discarded).
    stop_event      threading.Event set when the app shuts down.
    enabled_event   optional threading.Event; listening only while it is set.
    """
    from faster_whisper import WhisperModel

    logger.info("[STT] Loading model '%s' (first run downloads it)...", MODEL_SIZE)
    try:
        model = WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8")
    except Exception as exc:
        logger.error("[STT] Could not load model: %r", exc)
        return

    q = queue.Queue()

    def callback(indata, frames, time_info, status):
        q.put(indata[:, 0].copy())

    try:
        stream = sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32",
            blocksize=BLOCK, device=INPUT_DEVICE, callback=callback,
        )
        stream.start()
    except Exception as exc:
        logger.error("[STT] Could not open the microphone: %r "
                     "(run `python sst.py --devices`, then set STT_DEVICE)", exc)
        return

    try:
        threshold = FIXED_THRESHOLD or _calibrate(q)
        logger.info("[STT] Listening (threshold=%.4f). Speak when ready.", threshold)

        pre_roll = collections.deque(maxlen=PRE_ROLL_BLOCKS)
        collected = []
        in_speech = False
        silence = 0
        last_spoke = 0.0

        def reset():
            nonlocal in_speech, silence
            pre_roll.clear()
            collected.clear()
            in_speech = False
            silence = 0

        while not stop_event.is_set():
            try:
                block = q.get(timeout=0.2)
            except queue.Empty:
                continue

            # Deaf while the mic is toggled off or the robot is talking
            if speaking.is_set():
                last_spoke = time.time()
            if (enabled_event is not None and not enabled_event.is_set()) \
                    or speaking.is_set() \
                    or time.time() - last_spoke < COOLDOWN_AFTER_SPEAKING:
                reset()
                continue

            loud = _rms(block) > threshold

            if not in_speech:
                pre_roll.append(block)
                if loud:
                    in_speech = True
                    collected[:] = list(pre_roll)
                    silence = 0
                continue

            collected.append(block)
            silence = 0 if loud else silence + 1

            if silence >= SILENCE_END_BLOCKS or len(collected) >= MAX_UTTERANCE_BLOCKS:
                speech_blocks = len(collected) - silence
                audio = np.concatenate(collected)
                reset()
                if speech_blocks < MIN_SPEECH_BLOCKS:
                    continue

                text = _transcribe(model, audio)
                if text:
                    logger.info("[STT] Heard: %s", text)
                    try:
                        on_text(text)
                    except Exception as exc:
                        logger.error("[STT] Callback failed: %r", exc)
                    # Discard audio captured while the callback was busy
                    while not q.empty():
                        try:
                            q.get_nowait()
                        except queue.Empty:
                            break
                    reset()
    finally:
        stream.stop()
        stream.close()
        logger.info("[STT] Listener stopped.")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if "--devices" in sys.argv:
        list_devices()
        sys.exit(0)

    stop = threading.Event()
    t = threading.Thread(target=stt_listener,
                         args=(lambda s: print("You said:", s), stop), daemon=True)
    t.start()
    print("Speak into the mic. Ctrl-C to quit.")
    try:
        while t.is_alive():
            time.sleep(0.5)
    except KeyboardInterrupt:
        stop.set()
        t.join(timeout=3)
