#!/usr/bin/env python3
"""이미지/PDF를 픽셀 단위로 분석해 self-contained HTML로 변환.

- 이미지(jpg/png/webp/bmp/gif): Pillow 사용
- PDF: PyMuPDF(fitz)가 있으면 첫 페이지를 렌더해 처리, 없으면 안내

출력: 색상 모자이크 + 대표 팔레트 + 원본 정보가 담긴 단일 .html

사용법:
    python convert.py <입력> [-o out.html] [--cols 96] [--palette 6]
"""
import os
import sys
import html
import argparse
from collections import Counter

try:
    from PIL import Image, ImageOps
except ImportError:
    print("Pillow가 필요합니다.  pip install pillow", file=sys.stderr)
    raise SystemExit(3)

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


def load_image(path):
    """입력 경로에서 RGB Pillow 이미지를 만든다 (PDF는 첫 페이지)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        try:
            import fitz  # PyMuPDF
        except ImportError:
            print("PDF 입력에는 PyMuPDF가 필요합니다.  pip install pymupdf",
                  file=sys.stderr)
            raise SystemExit(3)
        doc = fitz.open(path)
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x 해상도
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
        return img
    img = Image.open(path)
    img = ImageOps.exif_transpose(img)  # 휴대폰 사진 회전 보정
    return img.convert("RGB")


def downsample(img, cols):
    w, h = img.size
    cols = max(8, min(cols, 400))
    rows = max(1, round(cols * h / w))
    return img.resize((cols, rows), Image.BILINEAR)


def extract_palette(img, n):
    """양자화로 빈도순 대표 색 n개를 추출."""
    small = img.resize((min(img.width, 200), min(img.height, 200)))
    q = small.quantize(colors=max(2, n * 2), method=Image.FASTOCTREE)
    pal = q.getpalette()
    counts = Counter(q.getdata())
    out = []
    for idx, _cnt in counts.most_common(n):
        r, g, b = pal[idx * 3:idx * 3 + 3]
        out.append((r, g, b))
    return out


def avg_color(img):
    px = list(img.getdata())
    n = len(px)
    r = sum(p[0] for p in px) // n
    g = sum(p[1] for p in px) // n
    b = sum(p[2] for p in px) // n
    return (r, g, b)


def hexc(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def build_html(src_name, orig_size, grid, palette, avg):
    cols = grid.width
    rows = grid.height
    px = list(grid.getdata())
    cells = []
    for p in px:
        cells.append(f'<i style="background:{hexc(p)}"></i>')
    mosaic = "".join(cells)
    swatches = "".join(
        f'<div class="sw"><span style="background:{hexc(c)}"></span>'
        f'<code>{hexc(c)}</code></div>' for c in palette
    )
    title = html.escape(src_name)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} · pixel → html</title>
<style>
  :root {{ --bg:#0f0f12; --ink:#e9e6df; --muted:#8a8580; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--ink);
    font-family:ui-sans-serif,system-ui,"Pretendard",sans-serif; padding:32px; }}
  h1 {{ font-size:18px; font-weight:700; margin:0 0 4px; }}
  .meta {{ color:var(--muted); font-size:13px; margin-bottom:22px;
    font-family:ui-monospace,monospace; }}
  .mosaic {{ display:grid; grid-template-columns:repeat({cols},1fr);
    width:min(720px,100%); aspect-ratio:{cols}/{rows};
    border-radius:10px; overflow:hidden; box-shadow:0 20px 60px -20px #000; }}
  .mosaic i {{ display:block; width:100%; height:100%; }}
  .palette {{ display:flex; gap:10px; flex-wrap:wrap; margin:24px 0 0; }}
  .sw {{ display:flex; align-items:center; gap:7px; font-size:12px;
    font-family:ui-monospace,monospace; color:var(--muted); }}
  .sw span {{ width:26px; height:26px; border-radius:7px;
    box-shadow:inset 0 0 0 1px #fff2; }}
</style></head><body>
  <h1>{title}</h1>
  <div class="meta">원본 {orig_size[0]}×{orig_size[1]}px · 격자 {cols}×{rows}
    · 평균색 {hexc(avg)}</div>
  <div class="mosaic">{mosaic}</div>
  <div class="palette">{swatches}</div>
</body></html>
"""


def main(argv=None):
    ap = argparse.ArgumentParser(description="이미지/PDF 픽셀 분석 → HTML")
    ap.add_argument("input", help="이미지 또는 PDF 경로")
    ap.add_argument("-o", "--output", help="출력 HTML 경로")
    ap.add_argument("--cols", type=int, default=96, help="가로 격자 칸 수")
    ap.add_argument("--palette", type=int, default=6, help="대표 색 개수")
    args = ap.parse_args(argv)

    if not os.path.isfile(args.input):
        print(f"파일을 찾을 수 없습니다: {args.input}", file=sys.stderr)
        return 2
    ext = os.path.splitext(args.input)[1].lower()
    if ext not in IMAGE_EXTS and ext != ".pdf":
        print(f"지원하지 않는 형식: {ext}", file=sys.stderr)
        return 2

    img = load_image(args.input)
    orig = img.size
    grid = downsample(img, args.cols)
    palette = extract_palette(img, args.palette)
    avg = avg_color(grid)

    out_path = args.output or (os.path.splitext(args.input)[0] + ".html")
    doc = build_html(os.path.basename(args.input), orig, grid, palette, avg)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"저장: {out_path}  (격자 {grid.width}×{grid.height}, "
          f"팔레트 {len(palette)}색, 평균 {hexc(avg)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
