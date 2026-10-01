#!/usr/bin/env python3
"""律问 · 小程序头像生成（1024×1024，两版设计 + 圆形预览）"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent
FONT = "/System/Library/Fonts/Supplemental/Songti.ttc"

INK = (43, 90, 160)        # 墨蓝
PAPER = (246, 244, 239)    # 暖纸
GOLD = (217, 178, 95)      # 描金
RED = (176, 58, 46)        # 朱砂
WHITE = (255, 253, 248)

S = 1024
f_hei = lambda size: ImageFont.truetype(FONT, size, index=0)  # Songti SC Black


def ring(d, color=GOLD, r=470, width=12):
    d.ellipse([S/2 - r, S/2 - r, S/2 + r, S/2 + r], outline=color, width=width)


def center_text(d, xy, text, font, fill):
    x, y = xy
    l, t, r, b = d.textbbox((0, 0), text, font=font)
    d.text((x - (r - l) / 2 - l, y - (b - t) / 2 - t), text, font=font, fill=fill)


def draw_scale(d, cx, top, color=GOLD, w=10):
    """极简天平：立柱+横梁+两侧秤盘"""
    beam_y = top + 18
    d.line([cx - 120, beam_y, cx + 120, beam_y], fill=color, width=w)
    d.line([cx, top, cx, top + 62], fill=color, width=w)
    d.line([cx - 40, top + 64, cx + 40, top + 64], fill=color, width=w)
    for sx in (cx - 120, cx + 120):
        d.line([sx, beam_y, sx, beam_y + 26], fill=color, width=8)
        r = 34
        d.arc([sx - r, beam_y + 26, sx + r, beam_y + 26 + 2 * r], start=0, end=180, fill=color, width=8)


# ---- 方案 A：墨蓝底 · 描金环 · 白字律问 ----
img = Image.new("RGB", (S, S), INK)
d = ImageDraw.Draw(img)
ring(d)
draw_scale(d, S / 2, 180)
center_text(d, (S / 2, 520), "律问", f_hei(330), WHITE)
center_text(d, (S / 2, 790), "法律检索问答", f_hei(92), GOLD)
img.save(OUT / "头像-方案A-墨蓝.png")

# ---- 方案 B：暖纸底 · 朱砂印章 ----
img = Image.new("RGB", (S, S), PAPER)
d = ImageDraw.Draw(img)
ring(d, color=GOLD, r=480, width=10)
seal = Image.new("RGBA", (720, 720), (0, 0, 0, 0))
sd = ImageDraw.Draw(seal)
sd.rounded_rectangle([10, 10, 710, 710], radius=90, fill=RED + (255,))
sd.rounded_rectangle([42, 42, 678, 678], radius=70, outline=WHITE + (230,), width=8)
center_text(sd, (360, 250), "律", f_hei(240), WHITE)
center_text(sd, (360, 490), "问", f_hei(240), WHITE)
seal = seal.rotate(-4, expand=False, resample=Image.BICUBIC)
img.paste(seal, (S // 2 - 360, S // 2 - 360), seal)
img.save(OUT / "头像-方案B-朱印.png")

# ---- 圆形预览（微信头像以圆形展示）----
for src, name in [("头像-方案A-墨蓝.png", "预览-方案A-圆形.png"),
                  ("头像-方案B-朱印.png", "预览-方案B-圆形.png")]:
    avatar = Image.open(OUT / src)
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, S, S], fill=255)
    prev = Image.new("RGB", (600, 600), (236, 236, 236))
    prev.paste(avatar.resize((512, 512), Image.LANCZOS), (44, 44), mask.resize((512, 512)))
    prev.save(OUT / name)

print("生成完成：")
for p in sorted(OUT.glob("*.png")):
    print(" ", p.name, p.stat().st_size // 1024, "KB")
