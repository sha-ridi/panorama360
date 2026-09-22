#!/usr/bin/env python3
"""
Собирает data/apartments.json из двух источников:

  - data/apartment_view_cameras.csv  — камеры видов из окна (все квартиры дома)
  - data/feed_snapshot.xml           — фид продающихся квартир (снимок)

Логика:
  - Список квартир = все уникальные ApartmentID из CSV.
  - Квартира "в продаже", если её <number> есть в фиде.
  - Для продающихся берём из фида: комнаты, этаж, площадь.
  - Камеры группируются по квартире, сортируются по индексу (суффикс _N в Component).

Изображения видов пока не готовы: у каждой камеры image = плейсхолдер (panorama.jpg).
Когда появятся реальные рендеры, положите их в views/ по конвенции
    views/<code>_<idx>.jpg      напр. views/1-02-201_0.jpg
и запустите скрипт с флагом --use-views, чтобы прописать реальные пути
(с фолбэком на плейсхолдер для отсутствующих файлов).

Запуск:  python tools/build_data.py
"""
import csv
import json
import os
import re
import sys
import datetime
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DATA = os.path.join(REPO, "data")
CSV_PATH = os.path.join(DATA, "apartment_view_cameras.csv")
XML_PATH = os.path.join(DATA, "feed_snapshot.xml")
OUT_PATH = os.path.join(DATA, "apartments.json")
VIEWS_DIR = os.path.join(REPO, "views")
PLACEHOLDER = "panorama.jpg"

USE_VIEWS = "--use-views" in sys.argv


def parse_feed(path):
    """Вернуть dict: code -> {rooms, floor, area, building, status} для продающихся."""
    raw = open(path, encoding="utf-8").read()
    raw = re.sub(r'xmlns="[^"]+"', "", raw, count=1)  # убрать дефолтный namespace
    root = ET.fromstring(raw)
    feed = {}
    feed_date = root.findtext("generation-date")
    for o in root.findall("offer"):
        code = (o.findtext("number") or "").strip()
        if not code:
            continue
        area_el = o.find("area")
        area = area_el.findtext("value") if area_el is not None else None
        house = o.find("house")
        house_name = house.findtext("name") if house is not None else ""
        feed[code] = {
            "rooms": _to_int(o.findtext("rooms")),
            "floor": _to_int(o.findtext("floor")),
            "area": _to_float(area),
            "status": o.findtext("status"),
            "houseName": house_name,
        }
    return feed, feed_date


def _to_int(v):
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return None


def _to_float(v):
    try:
        return float(str(v).strip())
    except (TypeError, ValueError):
        return None


def parse_cameras(path):
    """Вернуть dict: code -> {building, floor, unit, cameras:[...]}"""
    apts = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            code = row["ApartmentID"].strip()
            comp = row["Component"].strip()
            m = re.search(r"_(\d+)$", comp)
            idx = int(m.group(1)) if m else 0
            cam = {
                "idx": idx,
                "component": comp,
                "yaw": _to_float(row.get("RotYaw")),
                "pitch": _to_float(row.get("RotPitch")),
                "perp": _to_float(row.get("PerpendicularAngleDeg")),
                "yawMin": _to_float(row.get("RotXMin")),
                "yawMax": _to_float(row.get("RotXMax")),
                "pitchMin": _to_float(row.get("RotYMin")),
                "pitchMax": _to_float(row.get("RotYMax")),
            }
            a = apts.setdefault(code, {
                "building": row["Building"].strip(),
                "floor": _to_int(row["Floor"]),
                "unit": row["Unit"].strip(),
                "cameras": [],
            })
            a["cameras"].append(cam)
    for a in apts.values():
        a["cameras"].sort(key=lambda c: c["idx"])
    return apts


def natural_key(code):
    return [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", code)]


def image_for(code, idx):
    if USE_VIEWS:
        fname = f"{code}_{idx}.jpg"
        if os.path.exists(os.path.join(VIEWS_DIR, fname)):
            return f"views/{fname}"
    return PLACEHOLDER


def main():
    feed, feed_date = parse_feed(XML_PATH)
    cams = parse_cameras(CSV_PATH)

    apartments = []
    for code in sorted(cams.keys(), key=natural_key):
        c = cams[code]
        sale = feed.get(code)
        for cam in c["cameras"]:
            cam["image"] = image_for(code, cam["idx"])
        apt = {
            "code": code,
            "building": c["building"],
            "floor": c["floor"],
            "unit": c["unit"],
            "forSale": sale is not None,
            "rooms": sale["rooms"] if sale else None,
            "area": sale["area"] if sale else None,
            "cameras": c["cameras"],
        }
        apartments.append(apt)

    out = {
        "generatedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "feedDate": feed_date,
        "placeholderImages": not USE_VIEWS,
        "counts": {
            "total": len(apartments),
            "forSale": sum(1 for a in apartments if a["forSale"]),
            "cameras": sum(len(a["cameras"]) for a in apartments),
        },
        "apartments": apartments,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("wrote", OUT_PATH)
    print("counts:", out["counts"], "| placeholders:", out["placeholderImages"])


if __name__ == "__main__":
    main()
