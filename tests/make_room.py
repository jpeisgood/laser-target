#!/usr/bin/env python3
"""Classroom test video modelled on the real setup (photo of 2026-11-18): printed A4 target pinned at the
top to a cork board, iPad on a stand close to it and facing it head-on, ceiling lights, a homemade gun
whose blink is usually shorter than one camera frame.

What makes it hard (and what the first real test showed):
- mains flicker: faint coloured bands that drift (rolling shutter), slow white-balance drift
- the paper sways a fraction of a pixel now and then; the camera refocuses (image breathes ~0.2 %)
- blinks: mostly ONE frame, often only partly exposed; hits on black and on the white rings
- 6 s at the end with no shots at all (false alarms are counted there too)
Output format matches make_video.py (tests/out/<name>.mjpeg + .json).
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
from make_outdoor import to_lin, to_srgb  # noqa: E402

ROOT = HERE.parent
OUT = HERE / "out"
W, H, FPS = mv.W, mv.H, mv.FPS


def warp_frame(img, dx, dy, scale, cx, cy):
    """Sub-pixel shift + tiny zoom about (cx, cy), bilinear."""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    sx = (xx - cx - dx) / scale + cx
    sy = (yy - cy - dy) / scale + cy
    x0 = np.clip(np.floor(sx).astype(np.int32), 0, W - 2)
    y0 = np.clip(np.floor(sy).astype(np.int32), 0, H - 2)
    fx = np.clip(sx - x0, 0, 1)[..., None]
    fy = np.clip(sy - y0, 0, 1)[..., None]
    a = img[y0, x0]; b = img[y0, x0 + 1]; c = img[y0 + 1, x0]; d = img[y0 + 1, x0 + 1]
    return a * (1 - fx) * (1 - fy) + b * fx * (1 - fy) + c * (1 - fx) * fy + d * fx * fy


def make(name="front_room", seconds=26, seed=53):
    rnd = random.Random(seed)
    nrng = np.random.default_rng(seed)
    tex = Image.open(ROOT / "target" / "target-a4-59.5mm.png").convert("RGBA")
    tw, th = tex.size
    tcx, tcy, tR = 420.0, 560.0, 119.0
    # head-on, fairly close: the A4 sheet is ~520 px tall, a little left of centre
    paper_q = [(372, 96), (740, 96), (740, 616), (372, 616)]
    hm = mv.homography([(0, 0), (tw, 0), (tw, th), (0, th)], paper_q)

    lin = np.zeros((H, W, 3), np.float32)
    lin[:] = np.array([0.06, 0.16, 0.10])          # green cork board
    lin[:, :150] = np.array([0.55, 0.55, 0.52])    # wall
    lin[60:70, 150:] = np.array([0.08, 0.05, 0.04])  # board frame
    paper = mv.warp_rgba(tex, hm, (W, H))
    p = np.asarray(paper, np.float32)
    alpha = p[..., 3:4] / 255.0
    ink = to_lin(p[..., :3])
    surf = 0.03 + 0.97 * ink                       # toner black still reflects ~3 %
    lin = lin * (1 - alpha) + (surf * 0.75) * alpha  # white paper ~224 in 8-bit
    tc = mv.apply_h(hm, tcx, tcy)

    n_frames = seconds * FPS
    plan, f = [], int(2.5 * FPS)
    while f < (seconds - 6) * FPS:
        plan.append(f)
        f += rnd.randint(int(0.7 * FPS), int(1.3 * FPS))
    shots = []
    for f0 in plan:
        on_black = rnd.random() < 0.6
        rho = 0.93 * math.sqrt(rnd.random()) if on_black else 1.12 + rnd.random() * 1.25
        ang = rnd.random() * 2 * math.pi
        dur = 1 if rnd.random() < 0.75 else 2
        strength = [rnd.uniform(0.25, 1.0) for _ in range(dur)]   # partly exposed blink
        amp = rnd.uniform(0.6, 2.5)                                 # linear red added at the centre (1 = clip)
        shots.append(dict(frame=f0, rho=rho, angle=ang, dur=dur, strength=strength, amp=amp, sigma=rnd.uniform(1.6, 2.4),
                          tex=(tcx + rho * tR * math.cos(ang), tcy + rho * tR * math.sin(ang))))
    gusts = [(int(a * FPS), int((a + 1.6) * FPS)) for a in (4.0, 9.5, 14.0, 21.0, 23.5)]

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    out_path = OUT / f"{name}.mjpeg"
    gt = []
    phase = 0.0
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
                    a = s["amp"] * s["strength"][j] * g
                    frame[y0:y1, x0:x1, 0] += a
                    frame[y0:y1, x0:x1, 1] += a * 0.10
                    frame[y0:y1, x0:x1, 2] += a * 0.08
                    if j == 0:
                        gt.append(dict(frame=fi, x=round(x, 2), y=round(y, 2), rho=round(s["rho"], 4), hit=s["rho"] <= 1.0,
                                       score=0 if s["rho"] > 2.5 else max(1, min(10, math.floor(11 - 4 * s["rho"] + 1e-9))),
                                       dur=s["dur"], strength=[round(v, 2) for v in s["strength"]], amp=round(s["amp"], 2)))
            # mains flicker bands (coloured, drifting) and white-balance drift
            phase += 0.031
            band = 2 * np.pi * (yy[:, :1] / 150.0 + phase)
            flick = np.stack([1 + 0.035 * np.sin(band), 1 + 0.025 * np.sin(band + 0.5), 1 + 0.045 * np.sin(band + 1.1)], -1)
            awb = np.array([1 + 0.03 * math.sin(2 * math.pi * t / 7.0), 1.0, 1 - 0.025 * math.sin(2 * math.pi * t / 7.0 + 0.7)], np.float32)
            frame = frame * flick * awb
            # paper sway in gusts + focus breathing
            dx = dy = 0.0
            for a, b in gusts:
                if a <= fi <= b:
                    e = math.sin(math.pi * (fi - a) / (b - a))
                    dx = 0.45 * e * math.sin(2 * math.pi * t / 0.9)
                    dy = 0.25 * e * math.sin(2 * math.pi * t / 1.3)
            scale = 1 + 0.002 * math.sin(2 * math.pi * t / 3.1)
            frame = warp_frame(frame, dx, dy, scale, tc[0], tc[1])
            img = to_srgb(frame) + nrng.normal(0, 2.4, frame.shape)
            im = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8), "RGB")
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=88)
            fh.write(buf.getvalue())
            if fi == 0:
                im.save(OUT / f"{name}_first.png")
    meta = dict(scene=name, fps=FPS, frames=n_frames, width=W, height=H, shots=gt, truth=dict(center=tc), gusts=gusts,
                quiet_from=(seconds - 6) * FPS)
    (OUT / f"{name}.json").write_text(json.dumps(meta, indent=1), encoding="utf-8")
    print(name, "frames", n_frames, "shots", len(gt), "on black", sum(s["hit"] for s in gt),
          "single-frame", sum(1 for s in gt if s["dur"] == 1))


if __name__ == "__main__":
    make()
