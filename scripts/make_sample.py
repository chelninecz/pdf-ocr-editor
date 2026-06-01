"""Generate a synthetic 'scanned' part drawing PDF for testing.

Creates a raster drawing with mixed CN+EN labels (most on white, one on a
coloured band) and embeds it in a PDF together with a deliberately WRONG text
layer, so force-OCR behaviour can be verified.
"""

import io
import os
import sys

import fitz
from PIL import Image, ImageDraw, ImageFont

OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(__file__), "sample_drawing.pdf"
)

CJK = r"C:\Windows\Fonts\msyh.ttc"
W, H = 1240, 877  # ~A4 landscape at 150 dpi


def font(sz):
    return ImageFont.truetype(CJK, sz)


img = Image.new("RGB", (W, H), "white")
d = ImageDraw.Draw(img)

# Outer border + a simple "part" (circle + centre lines)
d.rectangle([20, 20, W - 20, H - 20], outline="black", width=3)
d.ellipse([180, 180, 520, 520], outline="black", width=4)
d.line([350, 120, 350, 580], fill="black", width=1)
d.line([120, 350, 580, 350], fill="black", width=1)
d.text((360, 330), "Ø30", font=font(34), fill="black")
d.text((250, 540), "R5  半径", font=font(30), fill="black")

# Title block (white background, CN + EN)
tb_x, tb_y = 760, 600
d.rectangle([tb_x, tb_y, W - 40, H - 40], outline="black", width=2)
d.text((tb_x + 20, tb_y + 20), "Part Name 零件名称: Bracket 支架", font=font(28), fill="black")
d.text((tb_x + 20, tb_y + 70), "Material 材料: Q235 钢", font=font(28), fill="black")
d.text((tb_x + 20, tb_y + 120), "Scale 比例 1:2", font=font(28), fill="black")
d.text((tb_x + 20, tb_y + 170), "Drawing No 图号: BRK-001", font=font(28), fill="black")

# Coloured band — should be detected as NON-erasable
d.rectangle([60, 640, 700, 700], fill=(70, 130, 200))
d.text((80, 652), "NOTE 注意: Deburr all edges 去毛刺", font=font(26), fill="white")

# Embed raster into a PDF, then add a WRONG text layer to test force-OCR
buf = io.BytesIO()
img.save(buf, format="PNG")
pdf = fitz.open()
page = pdf.new_page(width=W * 72 / 150, height=H * 72 / 150)  # 150 dpi -> points
page.insert_image(page.rect, stream=buf.getvalue())
page.insert_text((60, 60), "GARBAGE-TEXT-LAYER-zzz", fontsize=8, color=(1, 1, 1))
pdf.save(OUT)
pdf.close()
print("wrote", OUT)
