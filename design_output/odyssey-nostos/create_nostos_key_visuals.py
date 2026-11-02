from pathlib import Path
import math
import random

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont


SOURCE = Path("/Users/ocean/Desktop/Photo/The Odyssey")
OUT = Path(__file__).resolve().parent
FONT_ROOT = Path("/Users/ocean/.codex/skills/canvas-design/canvas-fonts")

W, H = 1080, 1350
INK = (8, 13, 17)
BONE = (220, 218, 202)
SIGNAL = (178, 66, 43)
MIST = (142, 167, 164)


def font(name, size):
    return ImageFont.truetype(str(FONT_ROOT / name), size=size)


DISPLAY = font("Gloock-Regular.ttf", 116)
DISPLAY_SMALL = font("InstrumentSerif-Italic.ttf", 43)
MONO = font("GeistMono-Regular.ttf", 17)
MONO_BOLD = font("GeistMono-Bold.ttf", 18)
CN = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", size=34)


def fit_cover(im, size=(W, H), center=(0.5, 0.5)):
    tw, th = size
    scale = max(tw / im.width, th / im.height)
    nw, nh = round(im.width * scale), round(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = round(center[0] * nw - tw / 2)
    top = round(center[1] * nh - th / 2)
    left = max(0, min(nw - tw, left))
    top = max(0, min(nh - th, top))
    return im.crop((left, top, left + tw, top + th))


def luminous_exile_grade(im, strength=0.72, dim=0.91):
    arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    lum = arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722
    lum = np.clip((lum - 0.47) * 1.08 + 0.47, 0, 1)
    lum = np.power(lum, 1.08)

    shadow = np.array([0.025, 0.075, 0.095], dtype=np.float32)
    middle = np.array([0.10, 0.29, 0.32], dtype=np.float32)
    light = np.array([0.79, 0.80, 0.72], dtype=np.float32)
    t1 = np.clip(lum / 0.52, 0, 1)[..., None]
    t2 = np.clip((lum - 0.52) / 0.48, 0, 1)[..., None]
    mapped = shadow * (1 - t1) + middle * t1
    mapped = mapped * (1 - t2) + light * t2

    gray = lum[..., None]
    original = gray + (arr - gray) * 0.70
    graded = original * (1 - strength) + mapped * strength
    graded *= dim

    ih, iw = lum.shape
    yy, xx = np.mgrid[0:ih, 0:iw]
    dx = (xx - iw / 2) / (iw / 2)
    dy = (yy - ih / 2) / (ih / 2)
    radius = np.sqrt(dx * dx + dy * dy)
    vignette = 1.0 - np.clip((radius - 0.47) / 0.82, 0, 1) * 0.35
    graded *= vignette[..., None]

    rng = np.random.default_rng(1701)
    grain = rng.normal(0, 0.014, graded.shape[:2])[..., None]
    grain *= (0.55 + (1 - lum[..., None]) * 0.85)
    graded = np.clip(graded + grain, 0, 1)
    return Image.fromarray((graded * 255).astype(np.uint8), "RGB")


def soft_projector_bloom(im):
    light = im.convert("L").point(lambda p: max(0, (p - 168) * 3))
    glow = im.filter(ImageFilter.GaussianBlur(16))
    return Image.composite(Image.blend(im, glow, 0.28), im, light)


def tracking_text(draw, xy, text, face, fill, tracking=3):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=face, fill=fill)
        x += draw.textlength(ch, font=face) + tracking
    return x


def projector_gate(im, seed=7):
    base = im.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    # The curved gate recalls projected light without becoming a retro border.
    draw.ellipse((-260, -126, W + 260, 54), fill=(0, 0, 0, 205))
    draw.ellipse((-300, H - 30, W + 300, H + 142), fill=(0, 0, 0, 178))
    draw.rectangle((0, 0, 11, H), fill=(0, 0, 0, 120))
    draw.rectangle((W - 10, 0, W, H), fill=(0, 0, 0, 110))

    rng = random.Random(seed)
    for _ in range(78):
        x = rng.randint(20, W - 20)
        y = rng.randint(25, H - 25)
        r = rng.choice([1, 1, 1, 2])
        alpha = rng.randint(10, 36)
        color = (230, 227, 208, alpha) if rng.random() > 0.35 else (0, 0, 0, alpha)
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
    return Image.alpha_composite(base, overlay).convert("RGB")


def add_registration(draw, index, role):
    tracking_text(draw, (54, 54), f"NOSTOS / {index}", MONO_BOLD, (*BONE, 215), 1.4)
    tracking_text(draw, (54, H - 61), role.upper(), MONO, (*MIST, 210), 1.2)
    draw.line((W - 154, H - 51, W - 56, H - 51), fill=(*MIST, 170), width=1)
    draw.ellipse((W - 54, H - 57, W - 42, H - 45), fill=(*SIGNAL, 225))


def spiral_echo_from_source(size=(870, 650)):
    src = Image.open(SOURCE / "IMG_1766.jpg").convert("RGB")
    # Crop the real current ring, so the cover's myth grows out of recorded water.
    patch = src.crop((350, 350, 1550, 1130)).resize(size, Image.Resampling.LANCZOS)
    patch = luminous_exile_grade(fit_cover(patch, size, center=(0.50, 0.55)), strength=0.84, dim=0.72)

    pw, ph = size
    yy, xx = np.mgrid[0:ph, 0:pw]
    cx, cy = pw * 0.49, ph * 0.57
    rx, ry = (xx - cx) / (pw * 0.48), (yy - cy) / (ph * 0.42)
    rr = np.sqrt(rx * rx + ry * ry)
    ring = np.exp(-((rr - 0.55) ** 2) / 0.035)
    fade = np.clip((1.05 - rr) / 0.58, 0, 1)
    alpha = np.clip(ring * fade * 118, 0, 92).astype(np.uint8)
    rgba = patch.convert("RGBA")
    rgba.putalpha(Image.fromarray(alpha, "L"))
    return rgba


def create_cover():
    src = Image.open(SOURCE / "IMG_1793.jpg").convert("RGB")
    frame = fit_cover(src, center=(0.66, 0.50))
    frame = luminous_exile_grade(frame, strength=0.76, dim=0.84)
    frame = soft_projector_bloom(frame).convert("RGBA")

    vortex = spiral_echo_from_source()
    vortex = vortex.filter(ImageFilter.GaussianBlur(0.6))
    frame.alpha_composite(vortex, (105, 330))

    veil = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    vd = ImageDraw.Draw(veil)
    vd.rectangle((0, 0, W, 430), fill=(4, 9, 13, 52))
    vd.rectangle((0, 1040, W, H), fill=(3, 7, 10, 36))
    frame = Image.alpha_composite(frame, veil)

    draw = ImageDraw.Draw(frame)
    tracking_text(draw, (52, 124), "NOSTOS", DISPLAY, (*BONE, 242), 8)
    draw.line((57, 278, 1018, 278), fill=(*BONE, 98), width=1)
    draw.text((58, 303), "没有人原样归来", font=CN, fill=(*BONE, 224))
    tracking_text(draw, (61, 360), "NO ONE RETURNS UNCHANGED", MONO, (*MIST, 220), 1.8)
    draw.text((720, 1165), "the sea keeps the rest", font=DISPLAY_SMALL, fill=(*BONE, 206))
    add_registration(draw, "00", "a study of return / 2026")

    out = projector_gate(frame.convert("RGB"), seed=17)
    out.save(OUT / "nostos-cover-1080x1350.png", optimize=True)


def create_whirlpool():
    src = Image.open(SOURCE / "IMG_1766.jpg").convert("RGB")
    frame = fit_cover(src, center=(0.47, 0.53))
    frame = luminous_exile_grade(frame, strength=0.80, dim=0.83)

    # Three very restrained temporal echoes make the real current feel in motion.
    base = frame.convert("RGBA")
    yy, xx = np.mgrid[0:H, 0:W]
    cx, cy = 545, 768
    rr = np.sqrt(((xx - cx) / 475) ** 2 + ((yy - cy) / 345) ** 2)
    for angle, center_r, alpha in ((1.2, 0.72, 46), (-1.4, 0.92, 34), (2.0, 1.10, 22)):
        rotated = frame.rotate(angle, center=(cx, cy), resample=Image.Resampling.BICUBIC).convert("RGBA")
        band = np.exp(-((rr - center_r) ** 2) / 0.012)
        mask = Image.fromarray(np.clip(band * alpha, 0, alpha).astype(np.uint8), "L")
        rotated.putalpha(mask)
        base = Image.alpha_composite(base, rotated)

    shade = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    sd.ellipse((366, 632, 730, 884), fill=(3, 9, 12, 26))
    base = Image.alpha_composite(base, shade)

    draw = ImageDraw.Draw(base)
    # Broken arcs indicate measured recurrence while leaving the photographed wake dominant.
    draw.arc((177, 492, 914, 1030), start=210, end=302, fill=(*BONE, 108), width=2)
    draw.arc((177, 492, 914, 1030), start=334, end=52, fill=(*BONE, 82), width=2)
    draw.arc((222, 530, 866, 992), start=78, end=156, fill=(*MIST, 64), width=1)
    tracking_text(draw, (704, 1023), "CHARYBDIS", MONO_BOLD, (*BONE, 225), 1.7)
    draw.text((706, 1054), "the point of no return", font=DISPLAY_SMALL, fill=(*BONE, 205))
    add_registration(draw, "02", "current / repetition / pull")

    out = projector_gate(base.convert("RGB"), seed=23)
    out.save(OUT / "nostos-whirlpool-1080x1350.png", optimize=True)


def create_vessel():
    src = Image.open(SOURCE / "IMG_1797.jpg").convert("RGB")
    frame = fit_cover(src, center=(0.61, 0.54))
    frame = luminous_exile_grade(frame, strength=0.86, dim=0.72)
    frame = ImageEnhance.Contrast(frame).enhance(1.07).convert("RGBA")

    # A faint displaced exposure suggests the boat has arrived without its story.
    ghost = frame.copy().filter(ImageFilter.GaussianBlur(1.1))
    ghost.putalpha(22)
    shifted = ImageChops.offset(ghost, -13, 4)
    frame = Image.alpha_composite(frame, shifted)

    gradient = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gradient)
    for y in range(0, 370):
        a = round(82 * (1 - y / 370))
        gd.line((0, y, W, y), fill=(2, 7, 11, a), width=1)
    frame = Image.alpha_composite(frame, gradient)

    draw = ImageDraw.Draw(frame)
    tracking_text(draw, (57, 141), "VESSEL", DISPLAY, (*BONE, 235), 8)
    draw.text((62, 290), "英雄已经离开画面", font=CN, fill=(*BONE, 220))
    tracking_text(draw, (64, 345), "CREW / 0     COURSE / UNKNOWN", MONO, (*MIST, 215), 1.4)
    draw.line((65, 389, 430, 389), fill=(*BONE, 84), width=1)
    add_registration(draw, "03", "evidence of an unfinished return")

    out = projector_gate(frame.convert("RGB"), seed=31)
    out.save(OUT / "nostos-vessel-1080x1350.png", optimize=True)


def create_preview():
    items = [
        ("nostos-cover-1080x1350.png", "00", "COVER"),
        ("nostos-whirlpool-1080x1350.png", "02", "WHIRLPOOL"),
        ("nostos-vessel-1080x1350.png", "03", "VESSEL"),
    ]
    thumb_w, thumb_h = 432, 540
    sheet = Image.new("RGB", (thumb_w * 3 + 96, thumb_h + 112), INK)
    draw = ImageDraw.Draw(sheet)
    for i, (name, index, role) in enumerate(items):
        im = Image.open(OUT / name).convert("RGB").resize((thumb_w, thumb_h), Image.Resampling.LANCZOS)
        x = 24 + i * (thumb_w + 24)
        sheet.paste(im, (x, 24))
        tracking_text(draw, (x, 582), f"{index} / {role}", MONO, BONE, 1.1)
    sheet.save(OUT / "nostos-key-visuals-preview.png", optimize=True)


if __name__ == "__main__":
    create_cover()
    create_whirlpool()
    create_vessel()
    create_preview()
    for path in sorted(OUT.glob("nostos-*.png")):
        print(path)
