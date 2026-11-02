from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter
import numpy as np

SRC = Path("/Users/ocean/Desktop/Photo/7.22济州岛")
OUT = Path(__file__).resolve().parent
FONTS = Path("/Users/ocean/.codex/skills/canvas-design/canvas-fonts")
W, H = 1080, 1350

def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size=size)

def cover(im, center_x=.5):
    s = max(W / im.width, H / im.height)
    nw, nh = round(im.width*s), round(im.height*s)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, min(nw-W, round(center_x*nw-W/2)))
    return im.crop((left, 0, left+W, H))

def grade(im):
    im = ImageEnhance.Contrast(im).enhance(1.035)
    im = ImageEnhance.Color(im).enhance(.91)
    # A pale cyan veil makes all four source frames live in one atmosphere.
    veil = Image.new("RGB", im.size, (180, 225, 229))
    return Image.blend(im, veil, .045)

def wave_mask(level, amplitude=25, period=360, phase=0, feather=42):
    """Reveal everything below a slow tidal curve, then soften the meeting line."""
    yy, xx = np.mgrid[0:H, 0:W]
    edge = level + amplitude*np.sin((xx+phase)*2*np.pi/period) + 7*np.sin((xx-phase)*2*np.pi/127)
    # Smooth logistic transition; broad enough to dissolve water into water.
    mask = 255/(1 + np.exp(-(yy-edge)/max(1, feather/6)))
    return Image.fromarray(mask.astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(feather/5))

def shifted_cover(path, shift_y=0, center_x=.5):
    im = grade(cover(Image.open(path).convert("RGB"), center_x))
    if shift_y == 0:
        return im
    stage = Image.new("RGB", (W, H), im.getpixel((W//2, H-1)))
    stage.paste(im, (0, shift_y))
    return stage

base = grade(cover(Image.open(SRC/"IMG_1816.jpg").convert("RGB"), .5))

# Four photographs become geological layers of time. Their borders behave like tides,
# so the eye reads one impossible seascape rather than four rectangular panels.
layer_18 = shifted_cover(SRC/"IMG_1818.jpg", 105, .5)
base.paste(layer_18, (0, 0), wave_mask(900, amplitude=20, period=470, phase=70, feather=48))

layer_19 = shifted_cover(SRC/"IMG_1819.jpg", 185, .5)
base.paste(layer_19, (0, 0), wave_mask(1035, amplitude=25, period=395, phase=210, feather=46))

# The close frame contains only water and kayaks; move it downward to become foreground time.
layer_17 = shifted_cover(SRC/"IMG_1817.jpg", 520, .52)
base.paste(layer_17, (0, 0), wave_mask(1175, amplitude=28, period=520, phase=10, feather=44))
base = base.convert("RGBA")

# Give the lower sea a barely visible soft bloom, unifying pasted reflections.
bloom = Image.new("RGBA", (W, H), (0,0,0,0))
bd = ImageDraw.Draw(bloom)
bd.ellipse((150, 810, 1070, 1375), fill=(173, 233, 235, 15))
base = Image.alpha_composite(base, bloom.filter(ImageFilter.GaussianBlur(70)))

# Film-like grain binds the four image sources.
rgb = np.asarray(base.convert("RGB")).astype(np.int16)
rng = np.random.default_rng(722)
noise = rng.normal(0, 1.55, (H, W, 1))
rgb = np.clip(rgb + noise, 0, 255).astype(np.uint8)
result = Image.fromarray(rgb, "RGB")
d = ImageDraw.Draw(result)

# Typography behaves like a faint memory in the sky, not a poster heading.
serif = font("InstrumentSerif-Italic.ttf", 78)
mono = font("GeistMono-Regular.ttf", 15)
white = (244, 247, 238)
blue_white = (220, 240, 237)
d.text((53, 70), "the sea, four times", font=serif, fill=(240, 246, 238))
d.text((57, 157), "JEJU ISLAND — 07.22", font=mono, fill=blue_white)
d.text((57, H-48), "ONE HORIZON / FOUR MOMENTS", font=mono, fill=white)

out = OUT/"jeju-temporal-tide-cover-1080x1350.png"
result.save(out, optimize=True)
print(out)
