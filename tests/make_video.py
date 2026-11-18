#!/usr/bin/env python3
"""Synthetic 'tablet camera' videos of a paper target with laser flashes, plus ground truth.

Output: tests/out/<scene>.mjpeg (Chromium fake-webcam format) and tests/out/<scene>.json.
The camera model is deliberately unkind: perspective + rotation, vignetting, slow auto-exposure wobble,
an exposure jump, rolling-shutter flicker bands, sensor noise, JPEG 4:2:0 compression (which smears the
red of a small dot), 1-3 frame laser pulses with partial exposure, a person in a red shirt walking
past, a camera nudge, and a neighbouring tablet's green flash.
"""
import io
import json
import math
import pathlib
import random
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)
W, H, FPS = 1280, 720, 30


def homography(src, dst):
    A = []
    for (x, y), (u, v) in zip(src, dst):
        A.append([x, y, 1, 0, 0, 0, -u * x, -u * y, -u])
        A.append([0, 0, 0, x, y, 1, -v * x, -v * y, -v])
    _, _, vt = np.linalg.svd(np.asarray(A, float))
    m = vt[-1].reshape(3, 3)
    return m / m[2, 2]


def apply_h(m, x, y):
    p = m @ np.array([x, y, 1.0])
    return p[0] / p[2], p[1] / p[2]


def warp_rgba(tex, h_tex_to_frame, size):
    inv = np.linalg.inv(h_tex_to_frame)
    inv = inv / inv[2, 2]
    coeffs = tuple(inv.flatten()[:8])
    return tex.transform(size, Image.Transform.PERSPECTIVE, coeffs, Image.Resampling.BICUBIC)


def black_disk_of_photo(tex):
    """Centre/radius of the black disk in the user's scanned target (photo 1).
    Scans 8 off-axis directions (the ring numbers sit on the axes) for the first light run,
    then re-centres on the edge points and repeats."""
    g = np.asarray(tex.convert("L"), float)
    h, w = g.shape
    cx, cy = w / 2, h / 2
    for _ in range(3):
        pts = []
        for k in range(8):
            ang = math.radians(22.5 + 45 * k)
            run = 0
            for r in range(5, int(min(w, h) / 2) - 2):
                x, y = int(round(cx + r * math.cos(ang))), int(round(cy + r * math.sin(ang)))
                run = run + 1 if g[y, x] > 110 else 0
                if run >= 5:
                    re_ = r - 5 + 0.5
                    pts.append((cx + re_ * math.cos(ang), cy + re_ * math.sin(ang)))
                    break
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
    R = sum(math.hypot(px - cx, py - cy) for px, py in pts) / len(pts)
    return cx, cy, R


SCENES = {
    # our printable target: A4 texture at 4 px/mm, black disk 59.5 mm, centre (105, 140) mm
    "scene_a4": dict(
        texture=ROOT / "target" / "target-a4-59.5mm.png", tex_center=(420.0, 560.0), tex_R=119.0,
        paper=[(452, 52), (848, 70), (884, 676), (418, 662)], seconds=24, light=1.0, noise=2.6, seed=7,
        clutter=True, events=True,
    ),
    # the 25 m target filmed head-on, small and off-centre in the frame (frontal circle fit + zoom fit)
    "front_photo": dict(
        texture=pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None, tex_center=None, tex_R=None,
        paper=[(445, 207), (675, 207), (675, 452), (445, 452)], seconds=14, light=0.9, noise=3.0, seed=17,
        clutter=True, events=False,
    ),
    # the school's existing 25 m target (photo 1), dimmer room, noisier sensor, seen from the right
    "scene_photo": dict(
        texture=pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else None, tex_center=None, tex_R=None,
        paper=[(470, 120), (800, 92), (812, 640), (482, 610)], seconds=16, light=0.72, noise=4.0, seed=11,
        clutter=False, events=False,
    ),
}


def make_scene(name):
    cfg = SCENES[name]
    rnd = random.Random(cfg["seed"])
    nrng = np.random.default_rng(cfg["seed"])
    tex = Image.open(cfg["texture"]).convert("RGBA")
    tw, th = tex.size
    if cfg["tex_center"] is None:
        cx, cy, R = black_disk_of_photo(tex)
        cfg["tex_center"], cfg["tex_R"] = (cx, cy), R
    tcx, tcy = cfg["tex_center"]
    tR = cfg["tex_R"]
    hm = homography([(0, 0), (tw, 0), (tw, th), (0, th)], cfg["paper"])

    # ---- static background ----
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    wall = np.stack([108 + 30 * (1 - yy / H), 112 + 28 * (1 - yy / H), 106 + 26 * (1 - yy / H)], -1)
    bg = Image.fromarray(np.clip(wall, 0, 255).astype(np.uint8), "RGB")
    d = ImageDraw.Draw(bg)
    px = [p[0] for p in cfg["paper"]]
    py = [p[1] for p in cfg["paper"]]
    d.rectangle([min(px) - 40, min(py) - 30, max(px) + 40, max(py) + 40], fill=(126, 96, 62))  # wooden board
    if cfg["clutter"]:
        d.ellipse([1080, 90, 1160, 170], fill=(22, 22, 24))      # a black round speaker on the wall
        d.rectangle([40, 420, 300, 720], fill=(40, 44, 52))      # a dark cabinet at the edge
        d.rectangle([60, 120, 210, 260], fill=(200, 205, 210))   # a notice on the wall
    paper = warp_rgba(tex, hm, (W, H))
    # real auto-exposure puts white paper around 210-225, not at 255
    pr, pg, pb, pa = paper.split()
    paper = Image.merge("RGBA", [c.point(lambda v: int(v * 0.86)) for c in (pr, pg, pb)] + [pa])
    bg.paste(paper, (0, 0), paper)
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).polygon([(x + 7, y + 9) for x, y in cfg["paper"]], fill=90)
    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    base = np.asarray(bg, np.float32)
    sh = np.asarray(shadow, np.float32)[..., None] / 255.0
    mask = (np.asarray(paper, np.float32)[..., 3:4] / 255.0)
    base = base * (1 - 0.35 * sh * (1 - mask))
    vign = 1 - 0.22 * (((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2)
    base = base * vign[..., None] * cfg["light"]

    # ---- shot plan (unit coordinates: black edge = 1) ----
    n_frames = cfg["seconds"] * FPS
    shots = []
    f = int(2.6 * FPS)
    plan = []
    while f < n_frames - FPS:
        plan.append(f)
        f += rnd.randint(int(0.75 * FPS), int(1.5 * FPS))
    special = {2: 0.96, 5: 1.05, 8: 0.25}  # near-edge and centre shots
    for k, f0 in enumerate(plan):
        if k in special:
            rho = special[k]
        elif rnd.random() < 0.6:
            rho = 0.9 * math.sqrt(rnd.random())
        else:
            rho = 1.15 + rnd.random() * 1.25
        ang = rnd.random() * 2 * math.pi
        dur = rnd.choice([1, 2, 2, 3])
        strength = [1.0] * dur
        strength[0] = rnd.uniform(0.35, 1.0)  # partial exposure at pulse start
        if dur > 1:
            strength[-1] = rnd.uniform(0.3, 1.0)
        if k == 10:
            dur, strength = 1, [0.3]  # a weak, single-frame flash
        tx, ty = tcx + rho * tR * math.cos(ang), tcy + rho * tR * math.sin(ang)
        shots.append(dict(frame=f0, rho=rho, angle=ang, tex=(tx, ty), dur=dur, strength=strength))

    # disturbances (scene A only)
    ev = cfg["events"]
    exposure_jump = int(10.0 * FPS) if ev else None
    walk = (int(12.0 * FPS), int(13.2 * FPS)) if ev else None
    nudge = int(15.5 * FPS) if ev else None
    green = (int(18.2 * FPS), int(18.2 * FPS) + 2) if ev else None
    walk_frames = set(range(walk[0] - 10, walk[1] + 10)) if walk else set()
    shots = [s for s in shots if s["frame"] not in walk_frames]
    green_frames = set(range(green[0] - 6, green[1] + 6)) if green else set()
    shots = [s for s in shots if s["frame"] not in green_frames]
    if nudge:
        shots = [s for s in shots if not (nudge - 8 <= s["frame"] <= nudge + 8)]

    # ---- render ----
    out_path = OUT / f"{name}.mjpeg"
    gt = []
    with open(out_path, "wb") as fh:
        for fi in range(n_frames):
            t = fi / FPS
            frame = base.copy()
            shift = (4, -3) if nudge and fi >= nudge else (0, 0)
            # lasers
            for s in shots:
                j = fi - s["frame"]
                if 0 <= j < s["dur"]:
                    x, y = apply_h(hm, *s["tex"])  # drawn unshifted; the whole frame is rolled below
                    I = s["strength"][j]
                    x0, x1, y0, y1 = int(x) - 14, int(x) + 15, int(y) - 14, int(y) + 15
                    sx, sy = xx[y0:y1, x0:x1] - x, yy[y0:y1, x0:x1] - y
                    r2 = sx * sx + sy * sy
                    frame[y0:y1, x0:x1, 0] += I * 560 * np.exp(-r2 / (2 * 2.2 ** 2))
                    frame[y0:y1, x0:x1, 1] += I * 170 * np.exp(-r2 / (2 * 1.3 ** 2))
                    frame[y0:y1, x0:x1, 2] += I * 150 * np.exp(-r2 / (2 * 1.3 ** 2))
                    if j == 0:
                        ux, uy = s["rho"] * math.cos(s["angle"]), s["rho"] * math.sin(s["angle"])
                        gt.append(dict(frame=fi, x=round(x + shift[0], 2), y=round(y + shift[1], 2), rho=round(s["rho"], 4), hit=s["rho"] <= 1.0,
                                       score=0 if s["rho"] > 2.5 else max(1, min(10, math.floor(11 - 4 * s["rho"] + 1e-9))),
                                       dur=s["dur"], strength=[round(v, 2) for v in s["strength"]], unit=(round(ux, 4), round(uy, 4))))
            if walk and walk[0] <= fi < walk[1]:
                p = (fi - walk[0]) / (walk[1] - walk[0])
                cx = -150 + p * 760
                body = ((xx - cx) / 120) ** 2 + ((yy - 470) / 330) ** 2 < 1
                frame[body] = np.array([210, 38, 44], np.float32) * cfg["light"]
            if green and green[0] <= fi <= green[1]:
                gx, gy = apply_h(hm, tcx + 60, tcy - 40)
                glow = 70 * np.exp(-(((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * 160.0 ** 2)))
                frame[..., 1] += glow
                frame[..., 0] += glow * 0.25
            gain = 1 + 0.015 * math.sin(2 * math.pi * t / 2.7)
            if exposure_jump and fi >= exposure_jump:
                gain *= 1.15
            band = 1 + 0.025 * np.sin(2 * np.pi * (yy[:, :1] / 90.0 + 0.37 * fi))
            frame = frame * gain * band[..., None]
            frame += nrng.normal(0, cfg["noise"], frame.shape).astype(np.float32)
            if shift != (0, 0):
                frame = np.roll(frame, shift=(shift[1], shift[0]), axis=(0, 1))
            img = Image.fromarray(np.clip(frame, 0, 255).astype(np.uint8), "RGB")
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=88)
            fh.write(buf.getvalue())
            if fi == 0:
                img.save(OUT / f"{name}_first.png")
    true_e = dict(center=apply_h(hm, tcx, tcy))
    meta = dict(scene=name, fps=FPS, frames=n_frames, width=W, height=H, shots=gt, truth=true_e,
                disturbances=dict(exposure_jump=exposure_jump, walk=walk, nudge=nudge, green=green))
    (OUT / f"{name}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(name, "frames", n_frames, "shots", len(gt), "hits", sum(s["hit"] for s in gt), "->", out_path,
          f"{out_path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    make_scene(sys.argv[1])
