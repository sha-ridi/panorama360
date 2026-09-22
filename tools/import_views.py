#!/usr/bin/env python3
"""
Импортёр рендеров видов из окна.

Берёт папку с рендерами UE (структура вида
    <SRC>/<корпус>-<этаж>-<кв>/<timestamp>/<Prefix>.ViewCameraComponent<unit>_<idx>.png
),
для каждого PNG определяет КОД КВАРТИРЫ и ИНДЕКС КАМЕРЫ, сжимает картинку и
кладёт в views/<код>_<idx>.jpg. Затем (по умолчанию) пересобирает
data/apartments.json.

Как определяется квартира:
  - индекс камеры  — суффикс _N в имени компонента (ViewCameraComponent205_0 -> 0);
  - номер юнита    — число перед _N в имени компонента (-> 205);
  - КОРПУС         — из имени папки рендера (2-02-05 -> корпус 2), потому что
                     имя компонента содержит только юнит, а юниты повторяются
                     между корпусами (501 есть и в 1-05-501, и в 2-05-501).
  - код квартиры   — по паре (корпус, юнит) из CSV data/apartment_view_cameras.csv,
                     это уникально. Если корпус из пути не вытащить, но юнит
                     встречается лишь в одном корпусе — берём его.

Примеры:
    python tools/import_views.py
    python tools/import_views.py "E:/UE_Projects/Marta/Vesper/Vesper/360"
    python tools/import_views.py --dry-run
    python tools/import_views.py --width 6144 --quality 90
    python tools/import_views.py --no-build

После импорта:
    git add -A && git commit -m "views <коды>" && git push
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
VIEWS_DIR = os.path.join(REPO, "views")

DEFAULT_SRC = r"E:/UE_Projects/Marta/Vesper/Vesper/360"
DEFAULT_WIDTH = 4096
DEFAULT_QUALITY = 85


def load_maps(csv_path):
    """(building, unit) -> code ; unit -> {codes}."""
    bu2code, unit2codes = {}, {}
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            code = row["ApartmentID"].strip()
            b = row["Building"].strip()
            u = row["Unit"].strip()
            bu2code[(b, u)] = code
            unit2codes.setdefault(u, set()).add(code)
    return bu2code, unit2codes


def component_from_filename(path):
    """'.../BP_B_F2.ViewCameraComponent205_0.png' -> 'ViewCameraComponent205_0'."""
    base = os.path.splitext(os.path.basename(path))[0]
    return base.split(".")[-1]


def parse_component(comp):
    """'ViewCameraComponent205_0' -> ('205', 0). Иначе (None, None)."""
    m = re.search(r"(\d+)_(\d+)$", comp)
    if not m:
        return None, None
    return m.group(1), int(m.group(2))


def building_from_path(path):
    """Ищем в пути сегмент вида '<корпус>-<этаж>-<кв>' и берём корпус."""
    for part in re.split(r"[\\/]+", path):
        m = re.match(r"^(\d+)-\d+-\d+", part)
        if m:
            return m.group(1)
    return None


def resolve_code(path, comp, bu2code, unit2codes):
    unit, idx = parse_component(comp)
    if unit is None:
        return None, None, "нет юнита/индекса в имени компонента"
    b = building_from_path(path)
    if b and (b, unit) in bu2code:
        return bu2code[(b, unit)], idx, None
    codes = unit2codes.get(unit)
    if codes and len(codes) == 1:
        return next(iter(codes)), idx, None
    if not b:
        return None, None, "не удалось определить корпус из пути (юнит %s неоднозначен)" % unit
    return None, None, "пара (корпус %s, юнит %s) не найдена в CSV" % (b, unit)


def find_pngs(src):
    out = []
    for root, _dirs, files in os.walk(src):
        for fn in files:
            if fn.lower().endswith(".png"):
                out.append(os.path.join(root, fn))
    return out


def main():
    ap = argparse.ArgumentParser(description="Импорт рендеров видов в views/")
    ap.add_argument("src", nargs="?", default=DEFAULT_SRC, help="папка с рендерами")
    ap.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    ap.add_argument("--quality", type=int, default=DEFAULT_QUALITY)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-build", action="store_true")
    args = ap.parse_args()

    if not os.path.isdir(args.src):
        print("Папка не найдена:", args.src); sys.exit(1)
    if not os.path.exists(CSV_PATH):
        print("Нет CSV:", CSV_PATH); sys.exit(1)

    bu2code, unit2codes = load_maps(CSV_PATH)
    pngs = find_pngs(args.src)
    print("Найдено PNG: %d в %s" % (len(pngs), args.src))

    # (code, idx) -> (path, mtime): при повторных рендерах берём самый свежий
    chosen, skipped = {}, []
    for p in pngs:
        comp = component_from_filename(p)
        code, idx, err = resolve_code(p, comp, bu2code, unit2codes)
        if err:
            skipped.append((os.path.basename(p), err))
            continue
        key = (code, idx)
        mt = os.path.getmtime(p)
        if key not in chosen or mt > chosen[key][1]:
            chosen[key] = (p, mt)

    if skipped:
        print("\nПропущены:")
        for fn, err in skipped:
            print("  %s  — %s" % (fn, err))

    if not chosen:
        print("\nНечего импортировать."); sys.exit(0)

    plan = []
    for (code, idx), (path, _mt) in chosen.items():
        dst = os.path.join(VIEWS_DIR, "%s_%d.jpg" % (code, idx))
        plan.append((code, idx, path, dst))
    plan.sort(key=lambda t: (t[0], t[1]))

    codes = sorted(set(c for c, _i, _s, _d in plan))
    print("\nК импорту: %d видов | квартиры: %s" % (len(plan), ", ".join(codes)))

    if args.dry_run:
        print("\n--dry-run: файлы не записаны. План:")
        for code, idx, src, _dst in plan:
            print("  %s_%d  <-  %s" % (code, idx, os.path.relpath(src, args.src)))
        return

    from PIL import Image
    os.makedirs(VIEWS_DIR, exist_ok=True)
    w, h = args.width, args.width // 2
    total_kb = 0
    for code, idx, src, dst in plan:
        im = Image.open(src).convert("RGB")
        if im.size != (w, h):
            im = im.resize((w, h), Image.LANCZOS)
        im.save(dst, "JPEG", quality=args.quality, optimize=True, progressive=True)
        kb = round(os.path.getsize(dst) / 1024)
        total_kb += kb
        print("  %-16s %5d KB" % (os.path.basename(dst), kb))
    print("Готово: %d файлов, ~%.1f МБ" % (len(plan), total_kb / 1024))

    if not args.no_build:
        print("\nПересобираю data/apartments.json …")
        env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
        subprocess.run([sys.executable, os.path.join(HERE, "build_data.py"),
                        "--use-views"], check=True, env=env)

    print("\nДальше:")
    print('  cd "%s"' % REPO)
    print('  git add -A && git commit -m "views %s" && git push' % " ".join(codes))


if __name__ == "__main__":
    main()
