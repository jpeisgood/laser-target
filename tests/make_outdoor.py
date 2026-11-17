#!/usr/bin/env python3
"""Outdoor synthetic camera videos (same output format as make_video.py).

Physics, roughly: light adds in *linear* space, the camera stores gamma-encoded values. In direct sun a
matte black disk reads ~55 (not 0) and the paper sits at or near 255, while a 1-5 mW red dot adds only
10-150 % to the red light already reflected there. So the laser is modelled as a contrast c (added linear
red / local linear red): c=0.5 on the black disk is only about +10 levels in the 8-bit red channel.

out_sun   : direct sun, weak dots (c 0.35-1.6), clouds, wind sway, moving leaf shadows (no shots then)
out_shade : target under a hood (shade) with bright surroundings, c 1.5-6
"""
import io
import json
import math
import pathlib
import random
import sys

import numpy as np
from PIL import Image

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_video as mv  # noqa: E402

ROOT = HERE.parent
OUT = HERE / "out"
W, H, FPS = mv.W, mv.H, mv.FPS
GAMMA = 2.2

SCENES = {
    "out_sun": dict(seconds=24, seed=31, paper_white=1.0, black=0.055, c=(0.35, 1.6), sigma=(1.6, 2.6),
                    noise=2.0, clouds=0.12, wind=0.7, leaves=True),
    # no shots at all: 40 s of strong clouds, wind and leaf shade sweeping over the black disk
    "out_soak": dict(seconds=40, seed=41, paper_white=1.0, black=0.055, c=(0.5, 1.5), sigma=(1.6, 2.6),
                     noise=2.2, clouds=0.2, wind=1.1, leaves=True, no_shots=True),
    "out_shade": dict(seconds=20, seed=37, paper_white=0.62, black=0.04, c=(1.5, 6.0), sigma=(1.6, 2.6),
                      noise=2.6, clouds=0.06, wind=0.4, leaves=False),
}


def to_lin(v):
    return np.power(np.clip(v, 0, 255) / 255.0, GAMMA)


def to_srgb(v):
    return np.power(np.clip(v, 0, 1), 1 / GAMMA) * 255.0


def subpixel_shift(img, dx, dy):
    ix, iy = math.floor(dx), math.floor(dy)
    fx, fy = dx - ix, dy - iy
    a = np.roll(img, (iy, ix), axis=(0, 1))
    b = np.roll(a, 1, axis=1)
    c = np.roll(a, 1, axis=0)
    d = np.roll(b, 1, axis=0)
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def make(name):
    cfg = SCENES[name]
    rnd = random.Random(cfg["seed"])
    nrng = np.random.default_rng(cfg["seed"])
    tex = Image.open(ROOT / "target" / "target-a4-59.5mm.png").convert("RGBA")
    tw, th = tex.size
    tcx, tcy, tR = 420.0, 560.0, 119.0
    paper_q = [(500, 70), (860, 96), (884, 668), (470, 650)]
    hm = mv.homography([(0, 0), (tw, 0), (tw, th), (0, th)], paper_q)

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    # outdoor backdrop in linear light: sky, far trees, sports field
    lin = np.zeros((H, W, 3), np.float32)
    sky = yy < 0.32 * H
    lin[sky] = np.array([0.62, 0.74, 0.92]) * (0.9 + 0.1 * (yy[sky] / (0.32 * H)))[:, None]
    trees = (yy >= 0.32 * H) & (yy < 0.45 * H)
    lin[trees] = np.array([0.05, 0.09, 0.04])
    field = yy >= 0.45 * H
    lin[field] = np.array([0.16, 0.26, 0.09])
    lin[field] *= (0.85 + 0.3 * nrng.random((int(field.sum()), 1))).astype(np.float32)
    # wooden board + stand
    lin[40:700, 440:920] = np.array([0.32, 0.2, 0.1])
    lin[700:, 660:700] = np.array([0.2, 0.13, 0.07])
    paper = mv.warp_rgba(tex, hm, (W, H))
    p = np.asarray(paper, np.float32)
    alpha = p[..., 3:4] / 255.0
    ink = to_lin(p[..., :3])  # 1 = white paper, 0 = black ink
    surf = cfg["black"] + (1 - cfg["black"]) * ink  # black ink still reflects a few percent
    lin = lin * (1 - alpha) + (surf * cfg["paper_white"]) * alpha
    red_lin_base = lin[..., 0].copy()

    # shot plan: hits concentrated on the black disk (that is what must work), some misses
    n_frames = cfg["seconds"] * FPS
    plan, f = [], int(2.8 * FPS)
    while f < n_frames - FPS:
        plan.append(f)
        f += rnd.randint(int(0.8 * FPS), int(1.4 * FPS))
    leaf_windows = [(int(7.0 * FPS), int(9.0 * FPS)), (int(15.0 * FPS), int(17.0 * FPS))] if cfg["leaves"] else []
    if cfg.get("no_shots"):
        leaf_windows = [(int(a * FPS), int((a + 3) * FPS)) for a in (3, 9, 15, 21, 27, 33)]
        plan = []
    plan = [f for f in plan if not any(a - 12 <= f <= b + 12 for a, b in leaf_windows)]
    shots = []
    for k, f0 in enumerate(plan):
        rho = 0.92 * math.sqrt(rnd.random()) if rnd.random() < 0.8 else 1.15 + rnd.random() * 1.0
        ang = rnd.random() * 2 * math.pi
        dur = rnd.choice([1, 2, 2, 3, 3])
        c = rnd.uniform(*cfg["c"])
        sig = rnd.uniform(*cfg["sigma"])
        shots.append(dict(frame=f0, rho=rho, angle=ang, dur=dur, c=c, sigma=sig,
                          tex=(tcx + rho * tR * math.cos(ang), tcy + rho * tR * math.sin(ang))))

    out_path = OUT / f"{name}.mjpeg"
    gt = []
    with open(out_path, "wb") as fh:
        for fi in range(n_frames):
            t = fi / FPS
            frame = lin.copy()
            for s in shots:
                j = fi - s["frame"]
                if 0 <= j < s["dur"]:
                    x, y = mv.apply_h(hm, *s["tex"])
                    x0, x1, y0, y1 = int(x) - 12, int(x) + 13, int(y) - 12, int(y) + 13
                    g = np.exp(-((xx[y0:y1, x0:x1] - x) ** 2 + (yy[y0:y1, x0:x1] - y) ** 2) / (2 * s["sigma"] ** 2))
                    add = s["c"] * red_lin_base[y0:y1, x0:x1] * g
                    frame[y0:y1, x0:x1, 0] += add
                    frame[y0:y1, x0:x1, 1] += add * 0.06
                    frame[y0:y1, x0:x1, 2] += add * 0.04
                    if j == 0:
                        gt.append(dict(frame=fi, x=round(x, 2), y=round(y, 2), rho=round(s["rho"], 4), hit=s["rho"] <= 1.0,
                                       score=0 if s["rho"] > 2.5 else max(1, min(10, math.floor(11 - 4 * s["rho"] + 1e-9))),
                                       dur=s["dur"], strength=[round(s["c"], 2)] * s["dur"], c=round(s["c"], 3),
                                       sigma=round(s["sigma"], 2)))
            for a, b in leaf_windows:  # soft moving shade from leaves (no shots in these windows)
                if a <= fi <= b:
                    ph = (fi - a) / (b - a)
                    spots = ((560, 250, 70), (700, 420, 55), (620, 560, 60)) + (((680, 335, 45),) if cfg.get("no_shots") else ())
                    for k, (ox, oy, rr) in enumerate(spots):
                        cx = ox - 160 + ph * 320 + 25 * math.sin(fi * 0.21 + k)
                        cy = oy + 18 * math.cos(fi * 0.17 + 2 * k)
                        d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / rr ** 2
                        frame *= (1 - 0.55 * np.exp(-d2 * d2))[..., None]
            cloud = 1 + cfg["clouds"] * math.sin(2 * math.pi * t / 6.3) + 0.5 * cfg["clouds"] * math.sin(2 * math.pi * t / 1.9)
            frame = frame * cloud
            dx = cfg["wind"] * math.sin(2 * math.pi * 0.7 * t)
            dy = 0.4 * cfg["wind"] * math.sin(2 * math.pi * 0.43 * t + 1)
            frame = subpixel_shift(frame, dx, dy)
            img = to_srgb(frame) + nrng.normal(0, cfg["noise"], frame.shape)
            im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
            fh.write(buf.getvalue())
            if fi == 0:
                im.save(OUT / f"{name}_first.png")
    meta = dict(scene=name, fps=FPS, frames=n_frames, width=W, height=H, shots=gt,
                truth=dict(center=mv.apply_h(hm, tcx, tcy)), leaves=leaf_windows)
    (OUT / f"{name}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    # how strong is a full-strength dot in 8-bit red on the black disk?
    blk = to_srgb(np.array([cfg["black"] * cfg["paper_white"]]))[0]
    print(name, "frames", n_frames, "shots", len(gt), "hits", sum(s["hit"] for s in gt),
          f"| black reads ~{blk:.0f}; dot adds +{to_srgb(np.array([cfg['black'] * cfg['paper_white'] * (1 + cfg['c'][0])]))[0] - blk:.0f}"
          f"..+{to_srgb(np.array([cfg['black'] * cfg['paper_white'] * (1 + cfg['c'][1])]))[0] - blk:.0f} red levels at its centre")


if __name__ == "__main__":
    make(sys.argv[1])
