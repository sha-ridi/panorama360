#!/usr/bin/env python3
"""
Готовит кадры облёта дома для «турнтейбла» (осмотр комплекса).

Берёт последовательность рендеров (напр. LS_Test_360.0000.png ... .0720.png),
пропускает пре-ролл (кадры с минусом), прореживает и сжимает в JPEG, кладёт в
complex/ как frame_000.jpg ... и пишет complex/manifest.json {count,width,height}.

Использование:
  python tools/make_orbit.py <dir_с_кадрами> [--step 4] [--width 1280] [--quality 82]
    --step 4  = брать каждый 4-й кадр (0.5°*4 = 2° между кадрами -> 180 кадров)
"""
import argparse, json, os, re, sys
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "complex")
BG = (15, 17, 19)   # тема сайта — фон под возможную прозрачность


def frame_num(name):
    m = re.search(r'\.(-?\d+)\.', name)          # LS_Test_360.0123.png -> 123
    return int(m.group(1)) if m else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--step", type=int, default=4)
    ap.add_argument("--width", type=int, default=1280)
    ap.add_argument("--quality", type=int, default=82)
    args = ap.parse_args()

    files = []
    for f in os.listdir(args.src):
        if not f.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        n = frame_num(f)
        if n is None or n < 0:                    # пропускаем пре-ролл (минусовые)
            continue
        files.append((n, f))
    files.sort()
    # 0000 и 0720 — один угол: берём 0..719
    files = [x for x in files if x[0] < 720] or files
    chosen = files[::args.step]
    print("всего кадров:", len(files), "| берём каждый %d-й ->" % args.step, len(chosen))

    if not chosen:
        print("нет кадров"); sys.exit(1)

    os.makedirs(OUT, exist_ok=True)
    # почистим старые
    for old in os.listdir(OUT):
        if old.startswith("frame_") or old == "manifest.json":
            os.remove(os.path.join(OUT, old))

    W = args.width; H = None; total = 0
    for i, (_n, f) in enumerate(chosen):
        im = Image.open(os.path.join(args.src, f))
        if im.mode == "RGBA":
            bg = Image.new("RGB", im.size, BG); bg.paste(im, mask=im.split()[3]); im = bg
        else:
            im = im.convert("RGB")
        if im.size[0] != W:
            H = round(im.size[1] * W / im.size[0]); im = im.resize((W, H), Image.LANCZOS)
        else:
            H = im.size[1]
        dst = os.path.join(OUT, "frame_%03d.jpg" % i)
        im.save(dst, "JPEG", quality=args.quality, optimize=True, progressive=True)
        total += os.path.getsize(dst)
    json.dump({"count": len(chosen), "width": W, "height": H, "pattern": "frame_%03d.jpg"},
              open(os.path.join(OUT, "manifest.json"), "w"))
    print("готово:", OUT, "| кадров:", len(chosen), "| ~%.1f МБ" % (total / 1e6), "| %dx%d" % (W, H))


if __name__ == "__main__":
    main()
