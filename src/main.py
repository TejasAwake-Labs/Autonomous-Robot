import json
import os
import sys
import time

import pygame
import threading

from face import FaceState, EMOTIONS
from renderer import draw_face
from text_gen import generate_response

from auth.activation_state import is_authorized
from comms.listener import start_listener

WIDTH, HEIGHT = 1280, 720  # 16:9
JSON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "emotion.json")
POLL_INTERVAL = 0.2  # seconds between checking the JSON file for changes

KEY_TO_EMOTION = {
    pygame.K_1: "neutral",
    pygame.K_2: "happy",
    pygame.K_3: "sad",
    pygame.K_4: "angry",
    pygame.K_5: "surprised",
    pygame.K_6: "scared",
    pygame.K_7: "disgust",
}

SAMPLE_LINES = {
    "neutral": "Just checking things out.",
    "happy": "This is going really well!",
    "sad": "I was really hoping that would work.",
    "angry": "That is NOT what I asked for.",
    "surprised": "Whoa, I did not expect that!",
    "scared": "Uh... what was that noise?",
    "disgust": "Ugh, that is disgusting.",
}

stop_event = threading.Event()

def load_json_emotion(last_mtime):
    """Reads emotion.json if it changed since last_mtime. Returns (data, new_mtime)."""
    try:
        mtime = os.path.getmtime(JSON_PATH)
    except OSError:
        return None, last_mtime

    if mtime == last_mtime:
        return None, last_mtime

    try:
        with open(JSON_PATH, "r") as f:
            data = json.load(f)
        return data, mtime
    except (json.JSONDecodeError, OSError):
        # File mid-write or malformed - just skip this poll, try again next time
        return None, last_mtime

def text_gen_worker():
    """
    Runs in a background thread: takes console input, calls the LLM,
    and writes emotion.json. main.py's poll loop picks up the change
    and animates the face.
    """
    print("Type to chat with the robot. Type 'quit' to exit this input loop.")
    while not stop_event.is_set():
        try:
            user_in = input("You: ")
        except (EOFError, KeyboardInterrupt):
            break

        if user_in.lower() in ("quit", "exit"):
            stop_event.set()
            break

        if not user_in.strip():
            continue

        reply = generate_response(user_in)
        print("Robot:", reply)

def main():
    test_mode = "--test" in sys.argv  # runs a few frames headlessly then exits, for CI/sanity checks

    pygame.init()
    pygame.display.set_caption("Facial Expression Prototype")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 18)

    face_state = FaceState()

    authorized = is_authorized()
    if not authorized:
        print("[Auth] Device is LOCKED. Starting token listener on port 5000...")
        start_listener(port=5000)
        face_state.set_emotion("angry", intensity=1.0, text="LOCKED. Awaiting valid token.")

    if not test_mode and authorized:
        worker = threading.Thread(target=text_gen_worker, daemon=True)
        worker.start()

    last_mtime = None
    last_poll = 0.0
    last_auth_check = time.time()
    frame_count = 0

    running = True
    while running:
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif authorized and event.key in KEY_TO_EMOTION:
                    name = KEY_TO_EMOTION[event.key]
                    face_state.set_emotion(name, intensity=1.0)
                elif authorized and event.key == pygame.K_t:
                    face_state.set_emotion(
                        face_state.emotion_name,
                        intensity=face_state.intensity,
                        text=SAMPLE_LINES.get(face_state.emotion_name, "Testing, testing."),
                    )

        # Poll emotion.json a few times a second (cheap, avoids hammering the filesystem every frame)
        now = time.time()
        
        # Periodic authorization re-check (e.g. every 5 seconds for easier testing)
        if now - last_auth_check > 5.0:
            last_auth_check = now
            if authorized and not is_authorized():
                print("[Auth] Token expired or revoked mid-session. Locking...")
                authorized = False
                face_state.set_emotion("angry", intensity=1.0, text="LOCKED. Token expired or revoked.")
                stop_event.set()
                start_listener(port=5000)
            elif not authorized and is_authorized():
                print("[Auth] Valid token received! Unlocking...")
                authorized = True
                face_state.set_emotion("neutral", intensity=1.0, text="Unlocked. Ready.")
                stop_event.clear()
                if not test_mode:
                    worker = threading.Thread(target=text_gen_worker, daemon=True)
                    worker.start()

        if authorized and now - last_poll > POLL_INTERVAL:
            last_poll = now
            data, last_mtime = load_json_emotion(last_mtime)
            if data:
                emotion = data.get("emotion", "neutral")
                intensity = float(data.get("intensity", 1.0))
                text = data.get("text")
                if emotion not in EMOTIONS:
                    print(f"[warn] unknown emotion '{emotion}' in emotion.json, ignoring")
                else:
                    face_state.set_emotion(emotion, intensity=intensity, text=text)

        face_state.update(dt)
        draw_face(screen, face_state, WIDTH, HEIGHT, font=font)
        pygame.display.flip()

        frame_count += 1
        if test_mode and frame_count > 30:
            running = False

    stop_event.set()

    pygame.quit()

if __name__ == "__main__":
    main()
