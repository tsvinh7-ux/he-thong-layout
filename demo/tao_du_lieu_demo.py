"""Tạo dữ liệu demo: ảnh gốc độ phân giải cao, ảnh nhúng độ phân giải thấp, và bản thảo .docx.

Ảnh đều là ảnh TỔNG HỢP (vẽ bằng máy) để minh họa, không phải ảnh y khoa thật.

    python demo/tao_du_lieu_demo.py           # tạo ảnh (+ .docx nếu máy có pandoc)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

NGUON = HERE / "nguon"
ANH_NHUNG = NGUON / "anh-nhung"  # ảnh nhúng trong Word (bản xem, độ phân giải thấp)
ANH_GOC = HERE / "anh-goc"       # ảnh gốc NXB cung cấp (độ phân giải cao)
BAN_THAO = HERE / "ban-thao"


def _font(size: int, bold: bool = False):
    try:
        from htl.preview import find_fonts

        d, files = find_fonts()
        return ImageFont.truetype(str(d / files[1 if bold else 0]), size)
    except Exception:
        return ImageFont.load_default()


def hinh_1_1(w=2400, h=1350) -> Image.Image:
    """Biểu đồ huyết áp 24 giờ (RGB)."""
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    L, R, T, B = 230, w - 80, 90, h - 170
    f, fb = _font(44), _font(52, bold=True)
    for v in range(60, 181, 20):  # lưới mmHg
        y = B - (v - 50) / 140 * (B - T)
        d.line([(L, y), (R, y)], fill=(220, 220, 220), width=3)
        d.text((L - 30, y), str(v), fill=(60, 60, 60), font=f, anchor="rm")
    for hh in range(0, 25, 3):
        x = L + hh / 24 * (R - L)
        d.line([(x, T), (x, B)], fill=(235, 235, 235), width=3)
        d.text((x, B + 40), f"{(hh + 6) % 24:02d}:00", fill=(60, 60, 60), font=f, anchor="mm")
    d.rectangle([L, T, R, B], outline=(80, 80, 80), width=4)
    t = np.linspace(0, 24, 400)
    night = 1 / (1 + np.exp(-(t - 16) * 2)) - 1 / (1 + np.exp(-(t - 23.5) * 2))
    rng = np.random.default_rng(3)
    sys_ = 138 - 22 * night + 4 * np.sin(t * 1.7) + rng.normal(0, 1.2, t.size)
    dia_ = 86 - 14 * night + 3 * np.sin(t * 1.3) + rng.normal(0, 1.0, t.size)
    d.rectangle([L + (16 / 24) * (R - L), T + 4, L + (23.5 / 24) * (R - L), B - 4], fill=(232, 240, 250))
    for series, col in ((sys_, (200, 30, 45)), (dia_, (20, 90, 180))):
        pts = [(L + ti / 24 * (R - L), B - (v - 50) / 140 * (B - T)) for ti, v in zip(t, series)]
        d.line(pts, fill=col, width=9, joint="curve")
    d.text((L, 30), "mmHg", fill=(60, 60, 60), font=fb, anchor="lm")
    d.text((L + (19.75 / 24) * (R - L), T + 50), "Ban đêm", fill=(20, 60, 120), font=fb, anchor="mm")
    d.text((L + 30, B - (sys_[0] - 50) / 140 * (B - T) - 60), "Tâm thu", fill=(200, 30, 45), font=fb, anchor="lm")
    d.text((L + 30, B - (dia_[0] - 50) / 140 * (B - T) + 70), "Tâm trương", fill=(20, 90, 180), font=fb, anchor="lm")
    return im


def hinh_1_2(n=2000) -> Image.Image:
    """Ảnh tổng hợp dạng phim X-quang ngực (grayscale) — chỉ để minh họa."""
    y, x = np.mgrid[0:n, 0:n] / n
    body = np.exp(-(((x - 0.5) / 0.44) ** 8 + ((y - 0.58) / 0.55) ** 8))
    img = 0.08 + 0.62 * body
    for cx in (0.31, 0.69):  # trường phổi (tối)
        r = ((x - cx) / 0.16) ** 2 + ((y - 0.47) / 0.3) ** 2
        img -= 0.5 * np.exp(-r ** 2)
    ribs = np.zeros_like(img)
    for k in range(10):  # xương sườn: cung mờ
        yy = 0.2 + k * 0.062 + 0.22 * (x - 0.5) ** 2
        ribs += np.exp(-((y - yy) / 0.007) ** 2)
    img += 0.07 * ribs * body
    heart = np.exp(-((((x - 0.56) / 0.21) ** 2 + ((y - 0.64) / 0.16) ** 2) ** 1.6))  # bóng tim to
    img = np.maximum(img, 0.25 + 0.5 * heart * body)
    img += 0.22 * np.exp(-((x - 0.5) / 0.03) ** 2) * body  # cột sống
    dia = (y > 0.78 + 0.25 * (x - 0.5) ** 2) * body  # vòm hoành
    img = np.maximum(img, 0.62 * dia)
    rng = np.random.default_rng(7)
    img += rng.normal(0, 0.01, img.shape)
    img = np.clip(img, 0, 1) ** 0.9
    return Image.fromarray((img * 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(3))


def hinh_2_1(w=2400, h=1300) -> Image.Image:
    """Sơ đồ lựa chọn thuốc (RGB)."""
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    f, fb = _font(46), _font(50, bold=True)

    def box(xy, text, fill, outline):
        d.rounded_rectangle(xy, radius=36, fill=fill, outline=outline, width=6)
        cx, cy = (xy[0] + xy[2]) / 2, (xy[1] + xy[3]) / 2
        d.multiline_text((cx, cy), text, fill=(20, 30, 50), font=fb, anchor="mm", align="center", spacing=14)

    box((800, 60, 1600, 260), "ĐTĐ type 2\n+ Metformin", (235, 242, 250), (11, 79, 138))
    items = [("Bệnh tim mạch\ndo xơ vữa", "GLP-1 RA\nhoặc SGLT2i"), ("Suy tim", "SGLT2i"), ("Bệnh thận mạn", "SGLT2i\n(± GLP-1 RA)")]
    for k, (a, b) in enumerate(items):
        x0 = 120 + k * 760
        box((x0, 450, x0 + 640, 690), a, (255, 244, 230), (210, 120, 20))
        box((x0, 900, x0 + 640, 1140), b, (230, 246, 236), (30, 140, 70))
        d.line([(1200, 260), (x0 + 320, 450)], fill=(90, 90, 90), width=7)
        d.line([(x0 + 320, 690), (x0 + 320, 900)], fill=(90, 90, 90), width=7)
        d.polygon([(x0 + 300, 870), (x0 + 340, 870), (x0 + 320, 900)], fill=(90, 90, 90))
    d.text((w / 2, h - 60), "Ưu tiên độc lập với mức HbA1c", fill=(90, 90, 90), font=f, anchor="mm")
    return im


def hinh_2_2(w=480, h=320) -> Image.Image:
    """Ảnh nhỏ, độ phân giải thấp — mô phỏng trường hợp NXB chưa gửi ảnh gốc."""
    y, x = np.mgrid[0:h, 0:w]
    base = np.stack([200 + 30 * np.sin(x / 60), 210 + 20 * np.cos(y / 40), 225 + 0 * x], -1)
    im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(im)
    d.rounded_rectangle([60, 130, 420, 190], radius=28, fill=(240, 240, 245), outline=(90, 90, 110), width=4)
    d.rectangle([330, 135, 410, 185], fill=(30, 120, 200))
    d.line([(20, 160), (60, 160)], fill=(120, 120, 120), width=3)
    return im


def tao_anh(force: bool = False) -> None:
    ANH_GOC.mkdir(parents=True, exist_ok=True)
    ANH_NHUNG.mkdir(parents=True, exist_ok=True)
    specs = {"hinh-1-1": hinh_1_1, "hinh-1-2": hinh_1_2, "hinh-2-1": hinh_2_1, "hinh-2-2": hinh_2_2}
    for name, fn in specs.items():
        goc = ANH_GOC / f"{name}-goc.tif"
        nhung = ANH_NHUNG / f"{name}.jpg"
        if goc.exists() and nhung.exists() and not force:
            continue
        im = fn()
        if name != "hinh-2-2":  # hình 2.2: cố ý KHÔNG có ảnh gốc
            im.save(goc, compression="tiff_lzw", dpi=(300, 300))
        small = im.copy()
        small.thumbnail((600, 600))
        small.convert("RGB").save(nhung, quality=70)
    print(f"Ảnh gốc: {ANH_GOC}")


def tao_docx() -> None:
    if not shutil.which("pandoc"):
        print("Không có pandoc — dùng bản thảo .docx có sẵn trong demo/ban-thao/.")
        return
    BAN_THAO.mkdir(exist_ok=True)
    for md in sorted(NGUON.glob("chuong-*.md")):
        out = BAN_THAO / (md.stem + ".docx")
        subprocess.run(["pandoc", md.name, "-f", "markdown", "-o", str(out)], cwd=NGUON, check=True)
        print(f"Bản thảo: {out}")


if __name__ == "__main__":
    tao_anh(force="--force" in sys.argv)
    tao_docx()
