"""Generate deterministic Home Assistant icon.png and logo.png for O-Leaf."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parents[1] / "oleaf"
SYMBOL = "❧"
GREEN = "#65c77d"
DARK = "#101512"
WHITE = "#eef4ef"


def first_font(candidates: list[Path], size: int) -> ImageFont.FreeTypeFont:
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    raise FileNotFoundError("No suitable font found for O-Leaf branding")


symbol_candidates = [
    Path("C:/Windows/Fonts/seguisym.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
]
text_candidates = [
    Path("C:/Windows/Fonts/segoeuib.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def centered_text(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], text: str, font: ImageFont.FreeTypeFont, fill: str) -> None:
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    x = left + (right - left - width) / 2 - bounds[0]
    y = top + (bottom - top - height) / 2 - bounds[1]
    draw.text((x, y), text, font=font, fill=fill)


icon = Image.new("RGBA", (128, 128), (0, 0, 0, 0))
icon_draw = ImageDraw.Draw(icon)
icon_draw.rounded_rectangle((5, 5, 123, 123), radius=27, fill=DARK, outline=GREEN, width=4)
centered_text(icon_draw, (10, 5, 118, 119), SYMBOL, first_font(symbol_candidates, 83), GREEN)
icon.save(ROOT / "icon.png", optimize=True)

logo = Image.new("RGBA", (250, 100), (0, 0, 0, 0))
logo_draw = ImageDraw.Draw(logo)
logo_draw.rounded_rectangle((3, 3, 247, 97), radius=22, fill=DARK, outline="#344039", width=2)
centered_text(logo_draw, (13, 7, 88, 91), SYMBOL, first_font(symbol_candidates, 65), GREEN)
text_font = first_font(text_candidates, 37)
logo_draw.text((91, 28), "O-Leaf", font=text_font, fill=WHITE)
logo.save(ROOT / "logo.png", optimize=True)

print(ROOT / "icon.png")
print(ROOT / "logo.png")

