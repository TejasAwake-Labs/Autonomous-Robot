import math
import pygame

BG_COLOR = (10, 10, 14)
FACE_COLOR = (0, 220, 255)  # cyan, classic "robot face" look


def _rotated_line(surface, cx, cy, length, angle_rad, width, color):
    dx = math.cos(angle_rad) * length / 2
    dy = math.sin(angle_rad) * length / 2
    pygame.draw.line(surface, color, (cx - dx, cy - dy), (cx + dx, cy + dy), width)


def draw_eye(surface, cx, cy, base_w, base_h, openness, color):
    h = max(4, int(base_h * openness))
    rect = pygame.Rect(0, 0, base_w, h)
    rect.center = (cx, cy)
    pygame.draw.ellipse(surface, color, rect)


def draw_eyebrow(surface, cx, cy, width, angle, height_offset, base_y_offset, color):
    y = cy + base_y_offset - height_offset * 60
    _rotated_line(surface, cx, y, width, angle, 8, color)


def draw_mouth(surface, cx, cy, width, curve, openness, color):
    """Draws the mouth as a filled shape using a quadratic-bezier baseline.

    curve: -1 (frown) .. 0 (flat) .. +1 (smile)
    openness: 0 (closed line) .. 1 (wide open)
    """
    half_w = width / 2
    curve_amount = curve * 35
    open_amount = 6 + openness * 55  # min thickness so mouth never fully vanishes

    steps = 24
    top_points = []
    bottom_points = []
    for i in range(steps + 1):
        t = i / steps
        x = cx - half_w + t * width
        baseline = curve_amount * (1 - (2 * t - 1) ** 2)
        # taper the opening toward the corners so it looks like a mouth, not an oval
        taper = (1 - (2 * t - 1) ** 2)
        half_thickness = (open_amount / 2) * (0.25 + 0.75 * taper)
        top_points.append((x, cy + baseline - half_thickness))
        bottom_points.append((x, cy + baseline + half_thickness))

    polygon = top_points + list(reversed(bottom_points))
    pygame.draw.polygon(surface, color, polygon)


def draw_face(surface, face_state, width, height, font=None):
    surface.fill(BG_COLOR)

    cx, cy = width // 2, height // 2
    eye_gap = width * 0.16
    eye_w = width * 0.10
    eye_h = height * 0.16
    eye_y = cy - height * 0.06

    left_eye_x = cx - eye_gap
    right_eye_x = cx + eye_gap

    blink = face_state.blink_multiplier()
    eye_openness = max(0.0, face_state.current["eye_openness"]) * blink

    draw_eye(surface, left_eye_x, eye_y, eye_w, eye_h, eye_openness, FACE_COLOR)
    draw_eye(surface, right_eye_x, eye_y, eye_w, eye_h, eye_openness, FACE_COLOR)

    brow_w = eye_w * 1.3
    brow_y_offset = -eye_h * 0.75
    angle = face_state.current["eyebrow_angle"]
    height_offset = face_state.current["eyebrow_height"]

    draw_eyebrow(surface, left_eye_x, eye_y, brow_w, -angle, height_offset, brow_y_offset, FACE_COLOR)
    draw_eyebrow(surface, right_eye_x, eye_y, brow_w, angle, height_offset, brow_y_offset, FACE_COLOR)

    mouth_y = cy + height * 0.22
    mouth_w = width * 0.22
    draw_mouth(
        surface,
        cx,
        mouth_y,
        mouth_w,
        face_state.current["mouth_curve"],
        face_state.get_mouth_openness(),
        FACE_COLOR,
    )

    if font is not None:
        label = f"emotion: {face_state.emotion_name}  (intensity {face_state.intensity:.1f})"
        text_surf = font.render(label, True, (120, 120, 130))
        surface.blit(text_surf, (16, height - 34))

        if face_state.last_text:
            caption = font.render(face_state.last_text, True, (200, 200, 210))
            caption_rect = caption.get_rect(center=(cx, height - 60))
            surface.blit(caption, caption_rect)
