#!/usr/bin/env python3
"""
Собирает вариант сайта /v2/ — тот же сайт, но с другой картинкой плана.

  v2/index.html       копия index.html с <base href="../"> (ассеты, панорамы, шрифты
                      берутся из корня) и данными из v2/apartments.json
  v2/apartments.json  копия data/apartments.json: у 1-10-1002 другой план и точки
                      камер/плашка этажа/стартовый вид, пересчитанные на новый план
  plans/1-10-1002_v2.jpg  план v2 (4320, q90) — в plans/, иначе сайт покажет плашку «демо-план»

Точки переносятся гомографией «текущий план -> новый план» (tools/v2_map.json,
считается по совпадению картинок). Мини-карта не меняется.

Запускать после любых правок index.html или пересборки data/apartments.json:
  python tools/make_v2.py [--plan путь/к/плану.png]
"""
import json
import math
import os
import sys

from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
OUT = os.path.join(REPO, "v2")
CODE = "1-10-1002"
MAP = os.path.join(HERE, "v2_map.json")
PLAN = os.path.join(REPO, "plans", CODE + "_v2.jpg")


def warp(H, x, y):
    X = H[0][0] * x + H[0][1] * y + H[0][2]
    Y = H[1][0] * x + H[1][1] * y + H[1][2]
    W = H[2][0] * x + H[2][1] * y + H[2][2]
    return X / W, Y / W


def warp_dir(H, x, y, deg):
    """Направление конуса (0 = вверх, по часовой) после переноса на новый план."""
    r = math.radians(deg)
    p = warp(H, x, y)
    q = warp(H, x + 100 * math.sin(r), y - 100 * math.cos(r))
    return (math.degrees(math.atan2(q[0] - p[0], -(q[1] - p[1]))) + 360) % 360


def main():
    os.makedirs(OUT, exist_ok=True)
    H = json.load(open(MAP, encoding="utf-8"))["H"]

    if "--plan" in sys.argv:
        src = sys.argv[sys.argv.index("--plan") + 1]
        im = Image.open(src).convert("RGB")
        if im.size != (4320, 4320):
            im = im.resize((4320, 4320), Image.LANCZOS)
        im.save(PLAN, "JPEG", quality=90, optimize=True)
    plan_size = os.path.getsize(PLAN)

    data = json.load(open(os.path.join(REPO, "data", "apartments.json"), encoding="utf-8"))
    for apt in data["apartments"]:
        if apt["code"] != CODE:
            continue
        apt["plan"] = "plans/%s_v2.jpg?v=%d" % (CODE, plan_size)
        for cam in apt["cameras"]:
            p = cam.get("plan")
            if not p:
                continue
            nx, ny = warp(H, p["x"], p["y"])
            cam["plan"] = {"x": round(nx, 1), "y": round(ny, 1),
                           "dir": round(warp_dir(H, p["x"], p["y"], p["dir"]), 2)}
        if apt.get("floorLabel"):
            fx, fy = warp(H, apt["floorLabel"]["x"], apt["floorLabel"]["y"])
            apt["floorLabel"] = dict(apt["floorLabel"], x=round(fx), y=round(fy))
        if apt.get("planView"):
            vx, vy = warp(H, apt["planView"]["cx"], apt["planView"]["cy"])
            apt["planView"] = dict(apt["planView"], cx=round(vx), cy=round(vy))
    json.dump(data, open(os.path.join(OUT, "apartments.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    html = open(os.path.join(REPO, "index.html"), encoding="utf-8").read()
    html = html.replace("<head>\n", '<head>\n  <base href="../">   <!-- v2: всё, кроме данных, берётся из корня сайта -->\n', 1)
    old = 'fetch("data/apartments.json?ts="'
    assert old in html, "не нашёл загрузку data/apartments.json в index.html"
    html = html.replace(old, 'fetch("v2/apartments.json?ts="', 1)
    open(os.path.join(OUT, "index.html"), "w", encoding="utf-8", newline="\n").write(html)
    print("v2 готов: plan %.1f МБ" % (plan_size / 1e6))


if __name__ == "__main__":
    main()
