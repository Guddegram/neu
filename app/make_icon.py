"""Draw the app icon (Romanian tricolour with a white shield) and save it as .icns.

Usage: python make_icon.py OUT.icns   (needs Pillow)
"""

import sys

from PIL import Image, ImageDraw

SIZE = 1024
BLUE, YELLOW, RED = (0, 43, 127), (252, 209, 22), (206, 17, 38)


def draw() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    # macOS icon grid: rounded square with some margin
    margin, radius = 100, 185
    flag = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(flag)
    third = (SIZE - 2 * margin) / 3
    for i, color in enumerate((BLUE, YELLOW, RED)):
        x0 = margin + i * third
        d.rectangle([x0, margin, x0 + third + 1, SIZE - margin], fill=color)
    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle([margin, margin, SIZE - margin, SIZE - margin],
                                           radius=radius, fill=255)
    img.paste(flag, (0, 0), mask)

    # white shield with a keyhole = "protected connection"
    d = ImageDraw.Draw(img)
    cx, top, w, h = SIZE / 2, 300, 300, 400
    shield = [(cx - w / 2, top), (cx + w / 2, top), (cx + w / 2, top + h * 0.55),
              (cx, top + h), (cx - w / 2, top + h * 0.55)]
    d.polygon(shield, fill=(255, 255, 255, 245))
    d.ellipse([cx - 45, top + 110, cx + 45, top + 200], fill=BLUE)
    d.polygon([(cx - 28, top + 180), (cx + 28, top + 180), (cx + 18, top + 290),
               (cx - 18, top + 290)], fill=BLUE)
    return img


if __name__ == "__main__":
    draw().save(sys.argv[1], sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256),
                                    (512, 512), (1024, 1024)])
