from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

ROOT = Path("/Users/ocean/Desktop/Photo/7.22济州岛")
OUT = Path(__file__).resolve().parent
FONT_ROOT = Path("/Users/ocean/.codex/skills/canvas-design/canvas-fonts")

W, H = 1080, 1350
PAPER = (242, 241, 234)
INK = (15, 35, 43)
BLUE = (13, 112, 151)
PALE = (204, 220, 218)
ORANGE = (230, 126, 48)

def font(name, size):
    return ImageFont.truetype(str(FONT_ROOT / name), size=size)

SERIF = font("InstrumentSerif-Italic.ttf", 104)
MONO = font("GeistMono-Regular.ttf", 17)
MONO_BOLD = font("GeistMono-Bold.ttf", 16)
SMALL = font("GeistMono-Regular.ttf", 13)

def fit_cover(img, size, center=(0.5, 0.5)):
    tw, th = size
    scale = max(tw / img.width, th / img.height)
    nw, nh = round(img.width * scale), round(img.height * scale)
    resized = img.resize((nw, nh), Image.Resampling.LANCZOS)
    cx = max(0, min(nw - tw, round(center[0] * nw - tw / 2)))
    cy = max(0, min(nh - th, round(center[1] * nh - th / 2)))
    return resized.crop((cx, cy, cx + tw, cy + th))

def prepare(path):
    im = Image.open(path).convert("RGB")
    im = ImageEnhance.Contrast(im).enhance(0.98)
    im = ImageEnhance.Color(im).enhance(0.94)
    return im

def tracking_text(draw, xy, text, face, fill, tracking=2):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=face, fill=fill)
        x += draw.textlength(ch, font=face) + tracking

canvas = Image.new("RGB", (W, H), PAPER)
draw = ImageDraw.Draw(canvas)

# Header: the serif line behaves like wind crossing a technical field note.
tracking_text(draw, (58, 41), "JEJU SEA / FIELD NOTE 07.22", MONO_BOLD, BLUE, 1.5)
tracking_text(draw, (748, 41), "WIND / PADDLE / LIGHT", SMALL, BLUE, 1.2)
draw.line((58, 76, 1022, 76), fill=PALE, width=2)
draw.ellipse((1006, 43, 1022, 59), fill=ORANGE)
draw.text((56, 86), "Two kinds of motion", font=SERIF, fill=INK)

# Main observation window preserves the complete horizontal scale.
main = prepare(ROOT / "IMG_1818.jpg").resize((964, 642), Image.Resampling.LANCZOS)
main_x, main_y = 58, 218
canvas.paste(main, (main_x, main_y))

# Fine registration marks and a horizon observation line.
draw.line((main_x, main_y - 10, main_x + 964, main_y - 10), fill=INK, width=1)
for x in (main_x, main_x + 241, main_x + 482, main_x + 723, main_x + 964):
    draw.line((x, main_y - 16, x, main_y - 3), fill=INK, width=1)

# Distant wind marks turn the horizon into a restrained score.
horizon_y = main_y + 182
for i in range(13):
    x = main_x + 79 + i * 68
    length = 10 if i % 3 else 18
    draw.line((x, horizon_y - length, x, horizon_y + 3), fill=(236, 246, 243), width=2)
tracking_text(draw, (main_x + 18, main_y + 18), "OBS. 01 / DISTANT ROTATION", SMALL, (240, 248, 246), 1.0)
tracking_text(draw, (main_x + 640, main_y + 603), "03 TRANSIENT BODIES", SMALL, (240, 248, 246), 1.0)

# Sequential contact observations: one gesture moving through time.
strip_y = 896
strip_w, strip_h, gap = 306, 216, 23
specs = [
    ("IMG_1817.jpg", (0.51, 0.57), "01"),
    ("IMG_1818.jpg", (0.47, 0.64), "02"),
    ("IMG_1819.jpg", (0.47, 0.68), "03"),
]
for idx, (name, center, label) in enumerate(specs):
    x = 58 + idx * (strip_w + gap)
    crop = fit_cover(prepare(ROOT / name), (strip_w, strip_h), center=center)
    canvas.paste(crop, (x, strip_y))
    draw.rectangle((x, strip_y, x + 36, strip_y + 30), fill=PAPER)
    draw.text((x + 9, strip_y + 5), label, font=SMALL, fill=INK)
    draw.line((x, strip_y + strip_h + 11, x + strip_w, strip_y + strip_h + 11), fill=PALE, width=2)

# Footer: a restrained observational conclusion, not a caption.
footer_y = 1165
tracking_text(draw, (58, footer_y), "FIXED", MONO_BOLD, BLUE, 1.0)
draw.line((133, footer_y + 10, 332, footer_y + 10), fill=PALE, width=2)
tracking_text(draw, (351, footer_y), "DRIFTING", MONO_BOLD, ORANGE, 1.0)
draw.line((460, footer_y + 10, 658, footer_y + 10), fill=PALE, width=2)
tracking_text(draw, (677, footer_y), "REFLECTED", MONO_BOLD, BLUE, 1.0)

draw.text((57, 1218), "the horizon turns", font=font("InstrumentSerif-Italic.ttf", 42), fill=INK)
draw.text((746, 1218), "the body crosses", font=font("InstrumentSerif-Italic.ttf", 42), fill=INK)
tracking_text(draw, (59, 1297), "A STUDY IN DISTANCE, REPETITION, AND HUMAN SCALE", SMALL, BLUE, 1.0)
tracking_text(draw, (896, 1297), "NO. 0722", SMALL, INK, 1.0)

# Crisp export plus a mild display preview.
out = OUT / "jeju-tidal-notation-1080x1350.png"
canvas.save(out, quality=95, optimize=True)
preview = canvas.resize((540, 675), Image.Resampling.LANCZOS)
preview.save(OUT / "jeju-tidal-notation-preview.png", optimize=True)
print(out)
