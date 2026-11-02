from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont


SOURCE = Path("/Users/ocean/Desktop/Photo/The Odyssey")
OUT = Path(__file__).resolve().parent
FONT_ROOT = Path("/Users/ocean/.codex/skills/canvas-design/canvas-fonts")

CREAM = (237, 232, 215)
MIST = (205, 218, 215)
DEEP_INK = (17, 43, 52)


def font(name, size):
    return ImageFont.truetype(str(FONT_ROOT / name), size=size)


DISPLAY = font("Gloock-Regular.ttf", 118)
MONO = font("GeistMono-Regular.ttf", 17)
CN = ImageFont.truetype("/System/Library/Fonts/Supplemental/Songti.ttc", size=35)


def fit_cover(im, size, center=(0.5, 0.5)):
    tw, th = size
    scale = max(tw / im.width, th / im.height)
    nw, nh = round(im.width * scale), round(im.height * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = max(0, min(nw - tw, round(center[0] * nw - tw / 2)))
    top = max(0, min(nh - th, round(center[1] * nh - th / 2)))
    return im.crop((left, top, left + tw, top + th))


def tracking_text(draw, xy, text, face, fill, tracking=4):
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=face, fill=fill)
        x += draw.textlength(ch, font=face) + tracking


def aegean_grade(im, seed=1, saturation=0.89, contrast=1.01, warmth=0.022):
    arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    lum = arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722

    # Gentle highlight roll-off keeps the sunlit source intact without digital glare.
    arr = np.clip((arr - 0.5) * contrast + 0.5, 0, 1)
    arr = arr - np.maximum(arr - 0.78, 0) * 0.22
    gray = lum[..., None]
    arr = gray + (arr - gray) * saturation

    shadow_weight = np.clip((0.48 - lum) / 0.48, 0, 1)[..., None]
    highlight_weight = np.clip((lum - 0.52) / 0.48, 0, 1)[..., None]
    arr += shadow_weight * np.array([-0.006, 0.006, 0.018], dtype=np.float32)
    arr += highlight_weight * np.array([warmth, warmth * 0.62, -warmth * 0.25], dtype=np.float32)

    # Prevent the original cyan from dominating while retaining an Aegean blue identity.
    cyan = np.clip((arr[..., 1] + arr[..., 2] - arr[..., 0] * 1.35 - 0.20), 0, 1)[..., None]
    arr += cyan * np.array([0.026, -0.013, -0.030], dtype=np.float32)

    rng = np.random.default_rng(seed)
    grain = rng.normal(0, 0.0045, lum.shape)[..., None]
    grain *= 0.55 + (1 - lum[..., None]) * 0.45
    arr = np.clip(arr + grain, 0, 1)
    return Image.fromarray((arr * 255).astype(np.uint8), "RGB")


def local_tone(im, center, radii, exposure=0.0, contrast=0.0, ring=None):
    arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    h, w = arr.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    dx = (xx - center[0]) / radii[0]
    dy = (yy - center[1]) / radii[1]
    rr = np.sqrt(dx * dx + dy * dy)
    mask = np.clip(1 - rr, 0, 1) ** 1.8
    if ring is not None:
        mask = np.exp(-((rr - ring) ** 2) / 0.028)
    lum = arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722
    arr += mask[..., None] * exposure
    if contrast:
        arr += mask[..., None] * (lum[..., None] - 0.5) * contrast
    return Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB")


def finish_photo(im):
    crisp = im.filter(ImageFilter.UnsharpMask(radius=1.35, percent=58, threshold=4))
    return Image.blend(im, crisp, 0.72)


def create_cover():
    src = Image.open(SOURCE / "IMG_1793.jpg").convert("RGB")
    frame = fit_cover(src, (1080, 1350), center=(0.66, 0.50))
    frame = aegean_grade(frame, seed=11, saturation=0.82, contrast=1.005, warmth=0.030)
    frame = finish_photo(frame).convert("RGBA")

    # A quiet density behind the title only; no projector effect is baked into the file.
    shade = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    sd = ImageDraw.Draw(shade)
    for y in range(0, 390):
        alpha = round(18 * (1 - y / 390) ** 1.7)
        sd.line((0, y, 1080, y), fill=(9, 22, 27, alpha), width=1)
    frame = Image.alpha_composite(frame, shade)

    draw = ImageDraw.Draw(frame)
    tracking_text(draw, (58, 88), "NOSTOS", DISPLAY, (*DEEP_INK, 242), 8)
    draw.line((62, 237, 1009, 237), fill=(*DEEP_INK, 105), width=1)
    draw.text((62, 267), "没有人原样归来", font=CN, fill=(*DEEP_INK, 232))
    frame.convert("RGB").save(OUT / "aegean-cover-1080x1350.png", optimize=True)


def create_whirlpool():
    src = Image.open(SOURCE / "IMG_1766.jpg").convert("RGB")
    frame = aegean_grade(src, seed=17, saturation=0.83, contrast=1.012, warmth=0.026)
    # Preserve the real wake: deepen its center and lift only the outer moving water.
    frame = local_tone(frame, center=(1000, 890), radii=(470, 300), exposure=-0.025, contrast=0.025)
    frame = local_tone(frame, center=(1000, 890), radii=(540, 350), exposure=0.035, contrast=0.035, ring=0.79)
    frame = finish_photo(frame)
    frame.save(OUT / "aegean-whirlpool-clean-2048x1365.png", optimize=True)


def create_vessel():
    src = Image.open(SOURCE / "IMG_1797.jpg").convert("RGB")
    frame = aegean_grade(src, seed=23, saturation=0.82, contrast=1.012, warmth=0.026)
    # Give the empty craft presence without making the surrounding sea unnaturally dark.
    frame = local_tone(frame, center=(1210, 875), radii=(820, 430), exposure=0.022, contrast=0.045)
    frame = finish_photo(frame)
    frame.save(OUT / "aegean-vessel-clean-2048x1365.png", optimize=True)


def projected_preview(photo, size=(760, 535)):
    canvas = Image.new("RGB", size, (3, 5, 7))
    target_w, target_h = 660, 440
    inner = photo.resize((target_w, target_h), Image.Resampling.LANCZOS)
    glow = Image.new("RGBA", size, (0, 0, 0, 0))
    glow_patch = Image.new("RGBA", (target_w + 30, target_h + 30), (92, 184, 211, 42)).filter(ImageFilter.GaussianBlur(15))
    glow.alpha_composite(glow_patch, ((size[0] - target_w) // 2 - 15, (size[1] - target_h) // 2 - 15))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), glow).convert("RGB")
    canvas.paste(inner, ((size[0] - target_w) // 2, (size[1] - target_h) // 2))
    return canvas


def create_preview():
    cover = Image.open(OUT / "aegean-cover-1080x1350.png").convert("RGB").resize((400, 500), Image.Resampling.LANCZOS)
    whirl = Image.open(OUT / "aegean-whirlpool-clean-2048x1365.png").convert("RGB")
    vessel = Image.open(OUT / "aegean-vessel-clean-2048x1365.png").convert("RGB")
    canvas = Image.new("RGB", (1600, 1040), (8, 12, 15))
    canvas.paste(cover, (48, 48))
    canvas.paste(projected_preview(whirl), (790, 28))
    canvas.paste(projected_preview(vessel), (790, 570))
    draw = ImageDraw.Draw(canvas)
    tracking_text(draw, (48, 587), "COVER / CLEAN TITLE ONLY", MONO, CREAM, 1.2)
    tracking_text(draw, (790, 535), "PROJECTOR SIMULATION / WHIRLPOOL", MONO, CREAM, 1.2)
    tracking_text(draw, (790, 1010), "PROJECTOR SIMULATION / VESSEL", MONO, CREAM, 1.2)
    draw.text((48, 668), "底片保留光，氛围交给放映。", font=CN, fill=CREAM)
    canvas.save(OUT / "aegean-afterlight-preview.png", optimize=True)


if __name__ == "__main__":
    create_cover()
    create_whirlpool()
    create_vessel()
    create_preview()
    for path in sorted(OUT.glob("*.png")):
        print(path)
