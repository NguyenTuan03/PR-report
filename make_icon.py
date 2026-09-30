"""
Vẽ icon app (icon.png 1024px -> icon.icns). Chạy lại khi muốn đổi icon:
    .venv/bin/python make_icon.py
"""

import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

S = 4  # vẽ to gấp 4 rồi thu nhỏ cho mịn
N = 1024 * S
HERE = Path(__file__).parent


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def draw() -> Image.Image:
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))

    # Khung bo góc kiểu macOS: 824px trong canvas 1024, bo 185px.
    inset, radius = 100 * S, 185 * S
    box = (inset, inset, N - inset, N - inset)

    # Bóng đổ nhẹ phía dưới.
    shadow = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (box[0], box[1] + 12 * S, box[2], box[3] + 12 * S), radius, fill=(0, 0, 0, 90))
    img.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(18 * S)))

    # Nền gradient chéo: tím than -> tím -> hồng.
    grad = Image.new("RGBA", (N, N))
    top, mid, bot = (67, 56, 202), (124, 58, 237), (219, 39, 119)
    px = grad.load()
    step = 8
    for y in range(0, N, step):
        for x in range(0, N, step):
            t = (x + y) / (2 * N)
            c = lerp(top, mid, t / 0.6) if t < 0.6 else lerp(mid, bot, (t - 0.6) / 0.4)
            for dy in range(step):
                for dx in range(step):
                    px[x + dx, y + dy] = (*c, 255)
    mask = Image.new("L", (N, N), 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius, fill=255)
    img.paste(grad, (0, 0), mask)

    # Ánh sáng dịu từ trên xuống + viền sáng mảnh.
    light = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    lp = light.load()
    for y in range(box[1], box[3], 4):
        a = max(0, round(46 * (1 - (y - box[1]) / (0.55 * (box[3] - box[1])))))
        for x in range(0, N, 4):
            for dy in range(4):
                for dx in range(4):
                    lp[x + dx, y + dy] = (255, 255, 255, a)
    lit = Image.alpha_composite(img, light)
    img.paste(lit, (0, 0), mask)
    ImageDraw.Draw(img).rounded_rectangle(box, radius, outline=(255, 255, 255, 40), width=4 * S)

    # Biểu tượng pull request (trắng), nét bo tròn.
    d = ImageDraw.Draw(img)
    white = (255, 255, 255, 255)
    w = 40 * S          # độ dày nét
    r = 64 * S          # bán kính vòng tròn commit
    lx, rx = 340 * S, 684 * S
    ty, by = 330 * S, 694 * S
    R = 100 * S         # bán kính chỗ rẽ

    def ring(cx, cy):
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=white, width=w)

    # Nhánh trái: 2 commit nối bằng đường thẳng.
    ring(lx, ty)
    ring(lx, by)
    d.line((lx, ty + r, lx, by - r), fill=white, width=w)

    # Nhánh phải: commit dưới -> đi lên -> rẽ trái -> mũi tên.
    ring(rx, by)
    d.line((rx, by - r, rx, ty + R), fill=white, width=w)
    d.arc((rx - 2 * R - w // 2, ty - w // 2, rx + w // 2, ty + 2 * R + w // 2),
          270, 360, fill=white, width=w)
    tip, base = 468 * S, 556 * S
    d.line((base - 10 * S, ty, rx - R, ty), fill=white, width=w)
    ah = 74 * S
    d.polygon([(tip, ty), (base, ty - ah), (base, ty + ah)], fill=white)

    return img.resize((1024, 1024), Image.LANCZOS)


def main() -> None:
    png = HERE / "icon.png"
    draw().save(png)

    iconset = HERE / "icon.iconset"
    shutil.rmtree(iconset, ignore_errors=True)
    iconset.mkdir()
    base = Image.open(png)
    for size in (16, 32, 128, 256, 512):
        base.resize((size, size), Image.LANCZOS).save(iconset / f"icon_{size}x{size}.png")
        base.resize((size * 2, size * 2), Image.LANCZOS).save(iconset / f"icon_{size}x{size}@2x.png")
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
    shutil.rmtree(iconset)
    print("OK -> icon.png, icon.icns")


if __name__ == "__main__":
    main()
