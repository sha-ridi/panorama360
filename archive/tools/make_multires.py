#!/usr/bin/env python3
"""
Генератор multires-тайлов для Pannellum из равнопрямоугольной (equirectangular)
панорамы. Раскладывает панораму на 6 граней куба и строит пирамиду тайлов —
так браузер грузит только видимые куски нужного разрешения, без лимита текстуры.

Результат кладётся в:  views/multires/<code>_<idx>/
  <level>/<face><y>_<x>.jpg   тайлы (face = f/b/u/d/l/r)
  fallback/<face>.jpg         превью-грань (быстрый первый кадр)
  config.json                 {tileResolution, maxLevel, cubeResolution}

Использование:
  python tools/make_multires.py <equirect.png> <code> <idx> [--quality 90]
  напр.  python tools/make_multires.py "X:/.../..._1101_0_FinalColor.png" 1-11-1101 0
"""
import argparse
import json
import math
import os
import sys
import numpy as np
from PIL import Image

Image.MAX_IMAGE_PIXELS = None
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# грань: (forward, right, up). Соглашение: equirect-центр = +Z, верх = +Y.
FACES = {
    "f": ((0, 0, 1),  (1, 0, 0),  (0, 1, 0)),
    "b": ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    "l": ((-1, 0, 0), (0, 0, 1),  (0, 1, 0)),
    "r": ((1, 0, 0),  (0, 0, -1), (0, 1, 0)),
    "u": ((0, 1, 0),  (1, 0, 0),  (0, 0, -1)),
    "d": ((0, -1, 0), (1, 0, 0),  (0, 0, 1)),
}


def render_face(S, W, H, C, F, R, U, chunk=256):
    F = np.array(F, np.float32); R = np.array(R, np.float32); U = np.array(U, np.float32)
    out = np.empty((C, C, 3), np.uint8)
    a = (2 * (np.arange(C) + 0.5) / C - 1).astype(np.float32)      # столбцы
    for y0 in range(0, C, chunk):
        y1 = min(y0 + chunk, C)
        b = (2 * (np.arange(y0, y1) + 0.5) / C - 1).astype(np.float32)  # строки
        A, B = np.meshgrid(a, b)                                    # (rows, C)
        dx = F[0] + A * R[0] - B * U[0]
        dy = F[1] + A * R[1] - B * U[1]
        dz = F[2] + A * R[2] - B * U[2]
        r = np.sqrt(dx * dx + dy * dy + dz * dz)
        lon = np.arctan2(dx, dz)
        lat = np.arcsin(np.clip(dy / r, -1, 1))
        u = (lon / (2 * np.pi) + 0.5) * W
        v = (0.5 - lat / np.pi) * H
        x0 = np.floor(u).astype(np.int64); fx = (u - x0).astype(np.float32)[..., None]
        y0i = np.floor(v).astype(np.int64); fy = (v - y0i).astype(np.float32)[..., None]
        x0m = np.mod(x0, W); x1m = np.mod(x0 + 1, W)
        y0c = np.clip(y0i, 0, H - 1); y1c = np.clip(y0i + 1, 0, H - 1)
        p00 = S[y0c, x0m].astype(np.float32); p01 = S[y0c, x1m].astype(np.float32)
        p10 = S[y1c, x0m].astype(np.float32); p11 = S[y1c, x1m].astype(np.float32)
        top = p00 * (1 - fx) + p01 * fx
        bot = p10 * (1 - fx) + p11 * fx
        out[y0:y1] = np.clip(top * (1 - fy) + bot * fy + 0.5, 0, 255).astype(np.uint8)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("code"); ap.add_argument("idx", type=int)
    ap.add_argument("--tile", type=int, default=512)
    ap.add_argument("--quality", type=int, default=90)
    args = ap.parse_args()

    im = Image.open(args.src).convert("RGB")
    W, H = im.size
    S = np.asarray(im)
    C = 8 * int(W / math.pi / 8)                    # разрешение грани (как в Pannellum)
    T = args.tile
    L = int(math.ceil(math.log2(C / T))) + 1
    print("equirect %dx%d -> cube %d, tile %d, levels %d" % (W, H, C, T, L))

    outdir = os.path.join(REPO, "views", "multires", "%s_%d" % (args.code, args.idx))
    os.makedirs(os.path.join(outdir, "fallback"), exist_ok=True)

    nfiles = 0
    for face, (F, R, U) in FACES.items():
        full = render_face(S, W, H, C, F, R, U)
        img = Image.fromarray(full)
        img.resize((T, T), Image.LANCZOS).save(
            os.path.join(outdir, "fallback", face + ".jpg"), "JPEG", quality=85, optimize=True)
        nfiles += 1
        for l in range(L, 0, -1):
            size = int(round(C / (2 ** (L - l))))
            lim = img if size == C else img.resize((size, size), Image.LANCZOS)
            ld = os.path.join(outdir, str(l)); os.makedirs(ld, exist_ok=True)
            n = int(math.ceil(size / T))
            for ty in range(n):
                for tx in range(n):
                    box = (tx * T, ty * T, min((tx + 1) * T, size), min((ty + 1) * T, size))
                    lim.crop(box).save(
                        os.path.join(ld, "%s%d_%d.jpg" % (face, ty, tx)), "JPEG",
                        quality=args.quality, optimize=True)
                    nfiles += 1
        del full, img
        print("  face", face, "done")

    cfg = {"tileResolution": T, "maxLevel": L, "cubeResolution": C}
    json.dump(cfg, open(os.path.join(outdir, "config.json"), "w"))
    total = sum(os.path.getsize(os.path.join(dp, f))
                for dp, _dn, fn in os.walk(outdir) for f in fn)
    print("готово:", outdir, "| файлов:", nfiles, "| ~%.1f МБ" % (total / 1e6), "| cfg:", cfg)


if __name__ == "__main__":
    main()
