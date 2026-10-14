"""
tts.py - Text-to-Speech watcher for the Autonomous Robot project.

Watches config/emotion.json; when the 'text' field changes, speaks it through
the laptop speaker.

Backends (set TTS_BACKEND in .env):
    auto     (default) Gemini TTS if GEMINI_API_KEY is set, else offline.
             If Gemini fails for any reason, falls back to offline.
    gemini   Gemini only
    offline  pyttsx3 only (system voices, no internet, no key)

Optional .env values:
    GEMINI_API_KEY=...
    GEMINI_TTS_MODEL=gemini-2.5-flash-preview-tts
    GEMINI_TTS_VOICE=Kore
"""

import base64
import io
import json
import logging
import os
import threading
import time
import wave

import pygame
import requests
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(BASE_DIR, ".env"))

logger = logging.getLogger(__name__)

EMOTION_JSON_PATH = os.path.join(BASE_DIR, "config", "emotion.json")
POLL_INTERVAL = 0.25

TTS_BACKEND = os.environ.get("TTS_BACKEND", "auto").lower()
GEMINI_TTS_MODEL = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")
GEMINI_TTS_VOICE = os.environ.get("GEMINI_TTS_VOICE", "Kore")
GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TTS_MODEL}:generateContent"
)

# Gemini TTS returns raw 16-bit mono PCM at 24 kHz
SAMPLE_RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH = 2


# ── Audio init ────────────────────────────────────────────────────────────────

def init_audio() -> None:
    """Initialise pygame's mixer (needed for the Gemini backend)."""
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init(frequency=SAMPLE_RATE, size=-16,
                              channels=CHANNELS, buffer=4096)
        except pygame.error as exc:
            logger.error("[TTS] Could not initialise the audio device: %s", exc)
            raise


# ── Backend 1: Gemini ─────────────────────────────────────────────────────────

def _speak_gemini(text: str) -> bool:
    """Returns True if audio was played, False on any failure."""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        logger.warning("[TTS] GEMINI_API_KEY not set.")
        return False
    if not pygame.mixer.get_init():
        logger.warning("[TTS] pygame mixer not initialised; cannot play Gemini audio.")
        return False

    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": GEMINI_TTS_VOICE}
                }
            },
        },
    }
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}

    try:
        logger.info("[TTS] Gemini (%s): %s", GEMINI_TTS_MODEL, text[:60])
        resp = requests.post(GEMINI_API_URL, json=payload, headers=headers, timeout=30)
        if resp.status_code != 200:
            # Show WHY it failed (bad model name, bad key, quota, ...)
            logger.error("[TTS] Gemini HTTP %s: %s", resp.status_code, resp.text[:400])
            return False

        data = resp.json()
        parts = data["candidates"][0]["content"]["parts"]
        inline = parts[0]["inlineData"]
        pcm = base64.b64decode(inline["data"])

        rate = SAMPLE_RATE
        mime = inline.get("mimeType", "")          # e.g. audio/L16;codec=pcm;rate=24000
        if "rate=" in mime:
            try:
                rate = int(mime.split("rate=")[1].split(";")[0])
            except ValueError:
                pass

        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(CHANNELS)
            w.setsampwidth(SAMPLE_WIDTH)
            w.setframerate(rate)
            w.writeframes(pcm)
        buf.seek(0)

        sound = pygame.mixer.Sound(buf)
        sound.play()
        while pygame.mixer.get_busy():
            time.sleep(0.05)
        return True

    except (requests.RequestException, KeyError, IndexError, ValueError) as exc:
        logger.error("[TTS] Gemini failed: %r", exc)
        return False


# ── Backend 2: offline (pyttsx3 -> Windows SAPI5 / system voices) ────────────

def _speak_offline(text: str) -> bool:
    try:
        import pyttsx3
    except ImportError:
        logger.error("[TTS] pyttsx3 not installed. Run: pip install pyttsx3 pywin32")
        return False

    # SAPI5 needs COM initialised in any non-main thread (Windows)
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except ImportError:
        pass

    try:
        logger.info("[TTS] Offline voice: %s", text[:60])
        engine = pyttsx3.init()          # fresh engine per call avoids thread hangs
        engine.setProperty("rate", 175)
        engine.setProperty("volume", 1.0)
        engine.say(text)
        engine.runAndWait()
        engine.stop()
        return True
    except Exception as exc:
        logger.error("[TTS] Offline TTS failed: %r", exc)
        return False


def _speak(text: str) -> None:
    if TTS_BACKEND == "offline":
        _speak_offline(text)
        return
    if TTS_BACKEND == "gemini":
        _speak_gemini(text)
        return
    # auto
    if os.environ.get("GEMINI_API_KEY", "").strip() and _speak_gemini(text):
        return
    logger.info("[TTS] Falling back to offline voice.")
    _speak_offline(text)


# ── Watcher thread ────────────────────────────────────────────────────────────

def tts_watcher(stop_event: threading.Event) -> None:
    """Polls emotion.json; speaks the 'text' field whenever it changes."""
    try:
        init_audio()
    except pygame.error:
        logger.warning("[TTS] No pygame mixer; only the offline backend can work.")

    # Baseline: whatever is in the file at startup is NOT spoken.
    last_mtime = None
    last_text = ""
    try:
        last_mtime = os.path.getmtime(EMOTION_JSON_PATH)
        with open(EMOTION_JSON_PATH, "r") as f:
            last_text = str(json.load(f).get("text", "")).strip()
    except (json.JSONDecodeError, OSError):
        pass

    logger.info("[TTS] Watcher started (backend=%s).", TTS_BACKEND)

    while not stop_event.is_set():
        try:
            mtime = os.path.getmtime(EMOTION_JSON_PATH)
        except OSError:
            time.sleep(POLL_INTERVAL)
            continue

        if mtime != last_mtime:
            try:
                with open(EMOTION_JSON_PATH, "r") as f:
                    data = json.load(f)
                last_mtime = mtime
                text = str(data.get("text", "")).strip()
                if text and text != last_text:
                    last_text = text
                    _speak(text)      # blocks until finished -> no overlap
            except (json.JSONDecodeError, OSError):
                logger.debug("[TTS] emotion.json busy; retrying.")

        time.sleep(POLL_INTERVAL)

    logger.info("[TTS] Watcher stopped.")


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=4096)
    pygame.mixer.init()

    # Quick direct test, bypassing the file watcher:
    _speak("Hello, this is a speaker test.")

    stop = threading.Event()
    t = threading.Thread(target=tts_watcher, args=(stop,), daemon=True)
    t.start()
    print("Watching emotion.json. Edit its 'text' to test. Ctrl-C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        t.join(timeout=3)
        pygame.mixer.quit()
