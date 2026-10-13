"""
debug_tts.py - Diagnostic script to find exactly why TTS is not working.
Run from the project root:
    .venv\Scripts\python debug_tts.py
"""

import sys
import os

print("=" * 60)
print("TTS DIAGNOSTICS")
print("=" * 60)

# 1. Check .env file
print("\n[1] Checking .env file...")
env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(env_path):
    print(f"    .env found at: {env_path}")
    with open(env_path) as f:
        content = f.read()
    if "GEMINI_API_KEY" in content:
        # Don't print the actual key
        val = [line for line in content.splitlines() if "GEMINI_API_KEY" in line]
        key_val = val[0].split("=", 1)[-1].strip() if val else ""
        if key_val and key_val != "your_api_key_here":
            print(f"    GEMINI_API_KEY is SET (starts with: {key_val[:8]}...)")
        else:
            print("    ERROR: GEMINI_API_KEY is still the placeholder 'your_api_key_here'")
            print("    -> Replace it with your real key from https://aistudio.google.com/apikey")
    else:
        print("    ERROR: GEMINI_API_KEY not found in .env file")
else:
    print(f"    ERROR: .env file NOT found at {env_path}")
    print("    -> Create a .env file with: GEMINI_API_KEY=your_key_here")

# 2. Load dotenv and check env var
print("\n[2] Loading dotenv and checking GEMINI_API_KEY env var...")
try:
    from dotenv import load_dotenv
    load_dotenv(env_path)
    print("    python-dotenv loaded OK")
except ImportError:
    print("    ERROR: python-dotenv not installed!")
    print("    -> Run: .venv\\Scripts\\pip install python-dotenv")
    sys.exit(1)

api_key = os.environ.get("GEMINI_API_KEY", "")
if api_key and api_key != "your_api_key_here":
    print(f"    GEMINI_API_KEY is available in environment (starts with: {api_key[:8]}...)")
else:
    print("    ERROR: GEMINI_API_KEY not available after loading .env")
    sys.exit(1)

# 3. Check pygame mixer
print("\n[3] Checking pygame.mixer...")
try:
    import pygame
    pygame.mixer.init(frequency=24000, size=-16, channels=1, buffer=4096)
    print(f"    pygame version: {pygame.version.ver}")
    print(f"    mixer init: {pygame.mixer.get_init()}")
    pygame.mixer.quit()
except Exception as e:
    print(f"    ERROR: {e}")

# 4. Test Gemini TTS API call
print("\n[4] Testing Gemini TTS API...")
import requests
import base64
import io
import wave

GEMINI_TTS_MODEL = "gemini-2.5-flash-preview-tts"
url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_TTS_MODEL}:generateContent?key={api_key}"

payload = {
    "contents": [{"parts": [{"text": "Hello, I am your robot."}], "role": "user"}],
    "generationConfig": {
        "responseModalities": ["AUDIO"],
        "speechConfig": {
            "voiceConfig": {"prebuiltVoiceConfig": {"voiceName": "Kore"}}
        }
    }
}

try:
    resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=30)
    print(f"    HTTP status: {resp.status_code}")
    
    if resp.status_code != 200:
        print(f"    ERROR response body: {resp.text[:500]}")
        sys.exit(1)
    
    data = resp.json()
    candidates = data.get("candidates", [])
    print(f"    Candidates: {len(candidates)}")
    
    if not candidates:
        print(f"    ERROR: No candidates. Full response: {data}")
        sys.exit(1)
    
    parts = candidates[0].get("content", {}).get("parts", [])
    print(f"    Parts: {len(parts)}")
    
    if not parts:
        print(f"    ERROR: No parts. Candidate: {candidates[0]}")
        sys.exit(1)
    
    inline_data = parts[0].get("inlineData", {})
    mime_type = inline_data.get("mimeType", "MISSING")
    b64_audio = inline_data.get("data", "")
    print(f"    mimeType: {mime_type}")
    print(f"    Audio data length (b64): {len(b64_audio)}")
    
    if not b64_audio:
        print(f"    ERROR: No audio data. Part keys: {list(parts[0].keys())}")
        sys.exit(1)
    
    print("    API call SUCCESS - audio data received!")

    # 5. Try playing it
    print("\n[5] Testing audio playback...")
    pcm_bytes = base64.b64decode(b64_audio)
    print(f"    PCM bytes decoded: {len(pcm_bytes)}")
    
    # Detect sample rate from mime type (e.g. "audio/pcm;rate=24000")
    detected_rate = 24000
    if "rate=" in mime_type:
        try:
            detected_rate = int(mime_type.split("rate=")[1].split(";")[0])
        except Exception:
            pass
    print(f"    Detected sample rate: {detected_rate} Hz")
    
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(detected_rate)
        wf.writeframes(pcm_bytes)
    wav_bytes = buf.getvalue()
    
    pygame.mixer.init(frequency=detected_rate, size=-16, channels=1, buffer=4096)
    sound = pygame.mixer.Sound(io.BytesIO(wav_bytes))
    sound.play()
    print("    Playing... (wait 3 seconds)")
    import time
    time.sleep(3)
    pygame.mixer.quit()
    print("    Playback complete!")

except requests.exceptions.RequestException as e:
    print(f"    NETWORK ERROR: {e}")
    sys.exit(1)
except Exception as e:
    import traceback
    print(f"    ERROR: {e}")
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("ALL CHECKS PASSED - TTS is working correctly!")
print("=" * 60)
