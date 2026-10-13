"""
tts.py — Text-to-Speech watcher for the Autonomous Robot project.

Monitors config/emotion.json for changes to the 'text' field and speaks
the text using the Gemini TTS API (gemini-2.5-flash-preview-tts).
Audio is streamed as PCM, then played back via pygame.mixer.

Usage:
    Runs automatically as a daemon thread launched from main.py.
    Can also be tested standalone:
        python tts.py
"""

import io
import json
import logging
import os
import time
import threading
import wave

import pygame
import requests
from dotenv import load_dotenv

# Auto-load .env from the project root (one level above src/)
_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(_ENV_PATH)

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMOTION_JSON_PATH = os.path.join(BASE_DIR, "config", "emotion.json")

POLL_INTERVAL = 0.25          # seconds between file-change checks
GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
GEMINI_API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_TTS_MODEL}:generateContent"
)

# Gemini TTS returns LINEAR16 PCM at 24 000 Hz, mono
SAMPLE_RATE = 24_000
CHANNELS = 1
SAMPLE_WIDTH = 2  # 16-bit -> 2 bytes

# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_api_key() -> str:
    """Read the Gemini API key from the .env file or environment."""
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        raise EnvironmentError(
            "GEMINI_API_KEY is not set.\n"
            "Add it to your .env file in the project root:\n"
            "  GEMINI_API_KEY=your_key_here\n"
            "Get a free key at: https://aistudio.google.com/apikey"
        )
    return key


def _pcm_to_wav_bytes(pcm_bytes: bytes) -> bytes:
    """Wrap raw LINEAR16 PCM bytes in a proper WAV container."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm_bytes)
    return buf.getvalue()


def _speak(text: str) -> None:
    """
    Call the Gemini TTS API for *text* and play the result through pygame.

    The response contains base64-encoded PCM audio inline in the JSON body.
    We decode it, wrap it in a WAV header, and play via pygame.mixer.Sound.
    """
    import base64

    api_key = _get_api_key()

    payload = {
        "contents": [
            {
                "parts": [{"text": text}],
                "role": "user"
            }
        ],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": "Kore"   # clear, robotic-ish voice
                    }
                }
            }
        }
    }

    headers = {"Content-Type": "application/json"}
    url = f"{GEMINI_API_URL}?key={api_key}"

    try:
        logger.info(f"[TTS] Requesting speech for: {text[:60]}...")
        resp = requests.post(url, json=payload, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        # Navigate to the inline audio data
        # Path: candidates[0].content.parts[0].inlineData.data  (base64 PCM)
        candidates = data.get("candidates", [])
        if not candidates:
            logger.error("[TTS] No candidates in Gemini TTS response.")
            return

        parts = candidates[0].get("content", {}).get("parts", [])
        if not parts:
            logger.error("[TTS] No parts in Gemini TTS response candidate.")
            return

        inline_data = parts[0].get("inlineData", {})
        b64_audio = inline_data.get("data", "")
        if not b64_audio:
            logger.error("[TTS] No audio data in Gemini TTS response.")
            return

        pcm_bytes = base64.b64decode(b64_audio)
        wav_bytes = _pcm_to_wav_bytes(pcm_bytes)

        # Play via pygame (mixer must already be initialised in main.py)
        sound = pygame.mixer.Sound(io.BytesIO(wav_bytes))
        sound.play()
        logger.info("[TTS] Playing audio...")

        # Wait for playback to finish so we don't clobber rapid successive calls
        while pygame.mixer.get_busy():
            time.sleep(0.05)

    except requests.exceptions.RequestException as exc:
        logger.error(f"[TTS] Network error calling Gemini TTS: {exc}")
    except Exception as exc:
        logger.error(f"[TTS] Unexpected error: {exc}")


# ── Watcher thread ────────────────────────────────────────────────────────────

def tts_watcher(stop_event: threading.Event) -> None:
    """
    Background thread: polls emotion.json every POLL_INTERVAL seconds.
    When the 'text' field changes, speaks the new text via Gemini TTS.

    Args:
        stop_event: threading.Event set by main() when the app is shutting down.
    """
    # Ensure pygame.mixer is ready (it may already be initialised by main.py)
    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=CHANNELS, buffer=4096)

    last_mtime = None
    last_text: str = ""

    logger.info("[TTS] Watcher started -- monitoring emotion.json for text changes.")

    while not stop_event.is_set():
        try:
            mtime = os.path.getmtime(EMOTION_JSON_PATH)
        except OSError:
            time.sleep(POLL_INTERVAL)
            continue

        if mtime != last_mtime:
            last_mtime = mtime
            try:
                with open(EMOTION_JSON_PATH, "r") as f:
                    data = json.load(f)
                text = data.get("text", "").strip()
                if text and text != last_text:
                    last_text = text
                    # Speak in this same thread (blocks until done).
                    # Single-threaded audio prevents overlapping playback.
                    _speak(text)
            except (json.JSONDecodeError, OSError):
                pass  # file mid-write, skip and retry

        time.sleep(POLL_INTERVAL)

    logger.info("[TTS] Watcher stopped.")


# ── Standalone test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    pygame.mixer.init(frequency=SAMPLE_RATE, size=-16, channels=CHANNELS, buffer=4096)

    stop = threading.Event()
    t = threading.Thread(target=tts_watcher, args=(stop,), daemon=True)
    t.start()

    print("TTS watcher running. Edit config/emotion.json to test. Ctrl-C to quit.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop.set()
        t.join(timeout=3)
        pygame.mixer.quit()
        print("TTS watcher stopped.")
