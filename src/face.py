import math
import random

# Each emotion is a set of target parameters, expressed relative to
# "neutral". Tweak these numbers freely to change how expressive each
# emotion looks - that's most of the "art direction" of this project.
EMOTIONS = {
    "neutral": {
        "eyebrow_angle": 0.0,
        "eyebrow_height": 0.0,
        "eye_openness": 1.0,
        "mouth_curve": 0.0,
        "mouth_openness": 0.0,
    },
    "happy": {
        "eyebrow_angle": 0.0,
        "eyebrow_height": 0.08,
        "eye_openness": 0.75,
        "mouth_curve": 0.85,
        "mouth_openness": 0.15,
    },
    "sad": {
        "eyebrow_angle": -0.35,
        "eyebrow_height": -0.12,
        "eye_openness": 0.55,
        "mouth_curve": -0.7,
        "mouth_openness": 0.0,
    },
    "angry": {
        "eyebrow_angle": 0.55,
        "eyebrow_height": -0.22,
        "eye_openness": 0.7,
        "mouth_curve": -0.5,
        "mouth_openness": 0.1,
    },
    "surprised": {
        "eyebrow_angle": 0.0,
        "eyebrow_height": 0.35,
        "eye_openness": 1.35,
        "mouth_curve": 0.0,
        "mouth_openness": 0.6,
    },
    "scared": {
        "eyebrow_angle": -0.2,
        "eyebrow_height": 0.25,
        "eye_openness": 1.2,
        "mouth_curve": -0.2,
        "mouth_openness": 0.3,
    },
    "disgust": {
        "eyebrow_angle": 0.45,
        "eyebrow_height": -0.15,
        "eye_openness": 0.5,
        "mouth_curve": -0.4,
        "mouth_openness": 0.05,
    },
}

PARAM_KEYS = [
    "eyebrow_angle",
    "eyebrow_height",
    "eye_openness",
    "mouth_curve",
    "mouth_openness",
]


class FaceState:
    """Tracks current + target facial parameters and animates between them."""

    def __init__(self):
        self.current = dict(EMOTIONS["neutral"])
        self.target = dict(EMOTIONS["neutral"])
        self.emotion_name = "neutral"
        self.intensity = 1.0
        self.last_text = ""

        # --- blinking ---
        self.blink_timer = random.uniform(2.0, 5.0)
        self.blinking = False
        self.blink_progress = 0.0  # 0 -> 1 closing, 1 -> 2 opening
        self.blink_speed = 9.0

        # --- talking (fake mouth-flap until real audio sync exists) ---
        self.talking = False
        self.talk_timer = 0.0
        self.talk_duration = 0.0
        self.talk_phase = 0.0

    def set_emotion(self, name, intensity=1.0, text=None):
        """Called whenever a new JSON message arrives."""
        preset = EMOTIONS.get(name, EMOTIONS["neutral"])
        self.emotion_name = name if name in EMOTIONS else "neutral"
        self.intensity = max(0.0, min(1.0, intensity))

        neutral = EMOTIONS["neutral"]
        for k in PARAM_KEYS:
            base = neutral[k]
            full = preset[k]
            # Blend toward neutral based on intensity (0 = neutral, 1 = full emotion)
            self.target[k] = base + (full - base) * self.intensity

        if text:
            self.last_text = text
            self.start_talking(text)

    def start_talking(self, text, wpm=170):
        """Crude speaking-duration estimate from word count.

        Replace this later with real timing from your friend's TTS/audio
        module (e.g. actual playback duration, or live amplitude).
        """
        words = max(1, len(text.split()))
        self.talk_duration = max(0.6, words / (wpm / 60))
        self.talk_timer = 0.0
        self.talking = True

    def update(self, dt):
        # Smoothly ease current parameters toward target every frame.
        smoothing = 6.0
        for k in PARAM_KEYS:
            self.current[k] += (self.target[k] - self.current[k]) * min(1.0, smoothing * dt)

        # Blink cycle, independent of emotion.
        if not self.blinking:
            self.blink_timer -= dt
            if self.blink_timer <= 0:
                self.blinking = True
                self.blink_progress = 0.0
        else:
            self.blink_progress += self.blink_speed * dt
            if self.blink_progress >= 2.0:
                self.blinking = False
                self.blink_progress = 0.0
                self.blink_timer = random.uniform(2.5, 6.0)

        # Talk timer.
        if self.talking:
            self.talk_timer += dt
            self.talk_phase += dt * 9.0
            if self.talk_timer >= self.talk_duration:
                self.talking = False

    def blink_multiplier(self):
        """Returns 0..1 - how "open" the eye currently is due to blinking."""
        if not self.blinking:
            return 1.0
        p = self.blink_progress
        openness = (p - 1.0) if p >= 1.0 else (1.0 - p)
        return max(0.0, openness)

    def get_mouth_openness(self):
        base = self.current["mouth_openness"]
        if self.talking:
            flap = (math.sin(self.talk_phase) + 1) / 2 
            return min(1.0, base + flap * 0.35)
        return base
