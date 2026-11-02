from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import numpy as np

ROOT = Path("/Users/ocean/Desktop/Photo/7.22济州岛")
OUT = Path(__file__).resolve().parent / "starburst-series"
OUT.mkdir(parents=True, exist_ok=True)
FONT_ROOT = Path("/Users/ocean/.codex/skills/canvas-design/canvas-fonts")
W, H = 1080, 1350
INK, MUTED = (240, 244, 235), (198, 220, 215)

def f(name, size):
    return ImageFont.truetype(str(FONT_ROOT / name), size=size)
MONO, MONO_BOLD, SERIF = f("GeistMono-Regular.ttf", 16), f("GeistMono-Bold.ttf", 15), f("InstrumentSerif-Italic.ttf", 50)

def cover_crop(im, center=(0.5, 0.56)):
    scale = max(W / im.width, H / im.height)
    nw, nh = round(im.width * scale), round(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    cx = max(0, min(nw - W, round(center[0] * nw - W / 2)))
    cy = max(0, min(nh - H, round(center[1] * nh - H / 2)))
    return im.crop((cx, cy, cx + W, cy + H))

def starburst(canvas, x, y, radius=92, alpha=165, tint=(255, 246, 213), rotation=0.0):
    """A restrained 8-ray diffraction flare with soft glow and spectral edges."""
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0)); gd = ImageDraw.Draw(glow)
    for r, a in [(radius * 0.80, 10), (radius * 0.46, 18), (radius * 0.20, 36)]:
        gd.ellipse((x-r, y-r, x+r, y+r), fill=(*tint, a))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(radius * 0.28)))
    rays = Image.new("RGBA", (W, H), (0, 0, 0, 0)); rd = ImageDraw.Draw(rays)
    import math
    angles = [rotation, rotation + math.pi/2, rotation + math.pi/4, rotation - math.pi/4, rotation + 3*math.pi/4, rotation - 3*math.pi/4]
    lengths, widths = [radius * 1.30, radius * 1.08, radius * 0.68, radius * 0.68, radius * 0.44, radius * 0.44], [2, 2, 1, 1, 1, 1]
    for i, ang in enumerate(angles):
        L, dx, dy = lengths[i], math.cos(ang), math.sin(ang)
        fringe = (120, 225, 235, int(alpha * 0.22)) if i % 2 == 0 else (255, 170, 115, int(alpha * 0.18))
        rd.line((x-dx*L, y-dy*L, x+dx*L, y+dy*L), fill=fringe, width=widths[i] + 5)
        rd.line((x-dx*L, y-dy*L, x+dx*L, y+dy*L), fill=(*tint, alpha), width=widths[i])
    canvas.alpha_composite(rays.filter(ImageFilter.GaussianBlur(0.45)))
    core = Image.new("RGBA", (W, H), (0, 0, 0, 0)); cd = ImageDraw.Draw(core)
    cd.ellipse((x-5, y-5, x+5, y+5), fill=(255, 252, 235, min(245, alpha + 60)))
    canvas.alpha_composite(core.filter(ImageFilter.GaussianBlur(1.3)))

def add_grain(im, amount=2.2, seed=10):
    rng = np.random.default_rng(seed); arr = np.asarray(im).astype(np.int16)
    arr = np.clip(arr + rng.normal(0, amount, arr.shape[:2] + (1,)), 0, 255).astype(np.uint8)
    return Image.fromarray(arr, "RGB")

def tracking(draw, xy, text, font, fill, spacing=1.0):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill); x += draw.textlength(ch, font=font) + spacing

frames = [
    ("IMG_1816.jpg", (0.50, 0.54), [(0.80, 0.69, 108, 168, 0.10), (0.26, 0.84, 50, 105, 0.0)], "THE HORIZON TURNS"),
    ("IMG_1817.jpg", (0.53, 0.52), [(0.75, 0.18, 84, 160, 0.18), (0.48, 0.33, 42, 100, -0.20), (0.20, 0.55, 35, 88, 0.1)], "THREE BODIES / ONE CURRENT"),
    ("IMG_1818.jpg", (0.50, 0.56), [(0.78, 0.37, 92, 165, -0.12), (0.44, 0.61, 46, 105, 0.14), (0.82, 0.72, 65, 122, 0.04)], "DISTANCE HOLDS"),
    ("IMG_1819.jpg", (0.50, 0.58), [(0.84, 0.42, 86, 155, 0.13), (0.66, 0.69, 48, 110, -0.10), (0.28, 0.80, 34, 82, 0.2)], "AFTER THE PASSING"),
]

for idx, (name, center, points, note) in enumerate(frames, start=1):
    base = cover_crop(Image.open(ROOT / name).convert("RGB"), center)
    base = ImageEnhance.Color(ImageEnhance.Contrast(base).enhance(1.06)).enhance(0.92)
    layer = base.convert("RGBA")
    for nx, ny, radius, alpha, rot in points:
        starburst(layer, int(nx * W), int(ny * H), radius=radius, alpha=alpha, rotation=rot)
    result = add_grain(layer.convert("RGB"), amount=1.45, seed=idx * 47); d = ImageDraw.Draw(result)
    tracking(d, (42, 39), f"JEJU / 07.22 / {idx:02d}", MONO_BOLD, INK, 1.2)
    tracking(d, (42, H - 69), note, MONO, MUTED, 0.9); d.text((W - 81, H - 75), f"{idx:02d}", font=SERIF, fill=INK)
    out = OUT / f"jeju-diffraction-{idx:02d}.png"; result.save(out, optimize=True); print(out)

src = Image.open(ROOT / "IMG_1818.jpg").convert("RGB")
cover = cover_crop(src, (0.50, 0.56)).convert("RGBA")
starburst(cover, 614, 823, radius=120, alpha=185, rotation=-0.12)
cover = add_grain(cover.convert("RGB"), amount=1.2, seed=777); cd = ImageDraw.Draw(cover)
cd.text((42, 39), "JEJU / A STUDY IN LIGHT", font=MONO_BOLD, fill=INK)
cd.text((42, H - 78), "the sea keeps its own time", font=SERIF, fill=INK)
cover.save(OUT / "jeju-diffraction-cover.png", optimize=True); print(OUT / "jeju-diffraction-cover.png")
