import json
import logging
import os
import sys
import threading
import time

import pygame

from face import FaceState, EMOTIONS
from renderer import draw_face
from text_gen import generate_response
from tts import SAMPLE_RATE, init_audio, tts_watcher

WIDTH, HEIGHT = 1280, 720  # 16:9
JSON_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "emotion.json"
)
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
        return None, last_mtime


def text_gen_worker():
    """Background thread: console input -> LLM -> writes emotion.json."""
    print("Type to chat with the robot. Type 'quit' to exit.")
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
    test_mode = "--test" in sys.argv

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    pygame.mixer.pre_init(frequency=SAMPLE_RATE, size=-16, channels=1, buffer=4096)
    pygame.init()
    try:
        init_audio()
    except pygame.error:
        print("[warn] pygame mixer unavailable; Gemini audio disabled "
              "(offline voice will still be tried).")

    pygame.display.set_caption("Facial Expression Prototype")
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("arial", 18)

    face_state = FaceState()

    if not test_mode:
        threading.Thread(target=text_gen_worker, daemon=True).start()
        threading.Thread(target=tts_watcher, args=(stop_event,), daemon=True).start()

    last_mtime = None
    last_poll = 0.0
    frame_count = 0

    running = True
    while running and not stop_event.is_set():
        dt = clock.tick(60) / 1000.0

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in KEY_TO_EMOTION:
                    face_state.set_emotion(KEY_TO_EMOTION[event.key], intensity=1.0)
                elif event.key == pygame.K_t:
                    face_state.set_emotion(
                        face_state.emotion_name,
                        intensity=face_state.intensity,
                        text=SAMPLE_LINES.get(face_state.emotion_name, "Testing, testing."),
                    )

        now = time.time()
        if now - last_poll > POLL_INTERVAL:
            last_poll = now
            data, last_mtime = load_json_emotion(last_mtime)
            if data:
                emotion = data.get("emotion", "neutral")
                try:
                    intensity = float(data.get("intensity", 1.0))
                except (TypeError, ValueError):
                    intensity = 1.0
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
    