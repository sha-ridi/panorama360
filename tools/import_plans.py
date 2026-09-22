#!/usr/bin/env python3
"""
Импортёр планов квартир.

Берёт папку с планами (файлы названы кодом квартиры, короткий или полный:
2-02-05.png / 2-02-205.png), приводит имя к ПОЛНОМУ коду, сжимает и кладёт
в plans/<код>.jpg. Затем пересобирает data/apartments.json.

Короткий код <корпус>-<этаж>-<кв> -> полный <корпус>-<этаж>-<этаж*100+кв>.
В отличие от видов, корпус уже есть в имени файла, так что неоднозначности нет.

Примеры:
    python tools/import_plans.py
    python tools/import_plans.py "C:/Users/shari/Desktop/360/plans"
    python tools/import_plans.py --dry-run
    python tools/import_plans.py --width 2160 --quality 90 --no-build
"""
import argparse
import csv
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
CSV_PATH = os.path.join(REPO, "data", "apartment_view_cameras.csv")
PLANS_DIR = os.path.join(REPO, "plans")

DEFAULT_SRC = r"C:/Users/shari/Desktop/360/plans"
DEFAULT_WIDTH = 1600
DEFAULT_QUALITY = 88


def full_code(name):
    m = re.match(r"^(\d+)-(\d+)-(\d+)$", name)
    if not m:
        return None
    b, ff, nn = m.groups()
    return f"{b}-{ff}-{nn}" if len(nn) >= 3 else f"{b}-{ff}-{int(ff)*100+int(nn)}"


def csv_codes():
    codes = set()
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            codes.add(row["ApartmentID"].strip())
    return codes


def main():
    ap = argparse.ArgumentParser(description="Импорт планов в plans/")
    ap.add_argument("src", nargs="?", default=DEFAULT_SRC)
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        print("Папка не найдена:", args.src); sys.exit(1)

    codes = csv_codes()
    plan = []       # (code, src_path)
    skipped = []
    for fn in os.listdir(args.src):
        if not fn.lower().endswith((".png", ".jpg", ".jpeg")):
            continue
        name = os.path.splitext(fn)[0]
        code = full_code(name)
        if code is None:
            skipped.append((fn, "имя не в формате корпус-этаж-кв")); continue
        if code not in codes:
            skipped.append((fn, "код %s не найден в CSV" % code)); continue
        plan.append((code, os.path.join(args.src, fn)))
    plan.sort(key=lambda t: t[0])

    if skipped:
        print("Пропущены:")
        for fn, why in skipped:
            print("  %s — %s" % (fn, why))
    if not plan:
        print("Нечего импортировать."); sys.exit(0)

    print("К импорту планов: %d | %s" % (len(plan), ", ".join(c for c, _ in plan)))
    if args.dry_run:
        for code, src in plan:
            print("  plans/%s.jpg  <-  %s" % (code, os.path.basename(src)))
        return

    from PIL import Image
    os.makedirs(PLANS_DIR, exist_ok=True)
    w = args.width
    total = 0
    for code, src in plan:
        im = Image.open(src).convert("RGB")
        if im.size[0] != w:
            h = round(im.size[1] * w / im.size[0])
            im = im.resize((w, h), Image.LANCZOS)
        dst = os.path.join(PLANS_DIR, "%s.jpg" % code)
        im.save(dst, "JPEG", quality=args.quality, optimize=True, progressive=True)
        kb = round(os.path.getsize(dst) / 1024); total += kb
        print("  %-16s %5d KB" % (code + ".jpg", kb))
    print("Готово: %d планов, ~%.1f МБ" % (len(plan), total / 1024))

    if not args.no_build:
        print("\nПересобираю data/apartments.json …")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        subprocess.run([sys.executable, os.path.join(HERE, "build_data.py"),
                        "--use-views"], check=True, env=env)

    print("\nДальше:")
    print('  cd "%s"' % REPO)
    print('  git add -A && git commit -m "plans %s" && git push' % " ".join(c for c, _ in plan))


if __name__ == "__main__":
    main()
