#!/usr/bin/env python3
"""Analyse a diagnosis recording from the tablet (설정 › 진단 › 진단 녹화).

usage: python3 tests/replay.py diag/laser-diag-....mp4 [log.txt]

1. Decodes every frame (ffmpeg from imageio-ffmpeg) with its timestamp: real camera frame rate, gaps in the video.
2. Finds every red blink in the video offline (slow and thorough, independent of the app): frame, place, strength,
   how many frames it lasts. This is what the camera really saw.
3. Lines that up with the app's own log (-log.txt, recorded at the same time): which blinks the app counted,
   which it never looked at (lost frames) and which it looked at but rejected, plus anything it counted that the
   video does not show.
4. Writes tests/out/<name>.mjpeg + .json so the whole app can replay it as a fake camera:
   node tests/e2e.mjs <name>   (Chromium plays MJPEG at 30 fps, so timings are stretched if the camera ran at 60)
"""
import json
import pathlib
import re
import subprocess
import sys

import numpy as np

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "out"


def ffmpeg():
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe(path):
    """frame size and per-frame timestamps (seconds), from ffmpeg's showinfo filter"""
    p = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(path), "-map", "0:v:0", "-vf", "showinfo", "-fps_mode", "passthrough", "-f", "null", "-"],
                       capture_output=True, text=True)
    pts = [float(m.group(1)) for m in re.finditer(r"pts_time:\s*([0-9.]+)", p.stderr)]
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", p.stderr)
    if not m:
        sys.exit("could not read the video:\n" + p.stderr[-2000:])
    return int(m.group(1)), int(m.group(2)), pts


def frames(path, w, h):
    cmd = [ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:v:0", "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    with subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL) as pr:
        n = w * h * 3
        while True:
            b = pr.stdout.read(n)
            if len(b) < n:
                break
            yield np.frombuffer(b, np.uint8).reshape(h, w, 3)


def box3(a):
    p = np.pad(a, 1, mode="edge")
    return sum(p[dy:dy + a.shape[0], dx:dx + a.shape[1]] for dy in range(3) for dx in range(3))


def find_blinks(path, w, h, pts, calib=None, z_thr=8.0):
    """What a red laser adds and nothing else does: red rises more than green and blue, against a slow per-pixel
    background whose brightness is matched row by row first (mains flicker bands, white balance, exposure), summed
    over 3x3 and compared with each pixel's own noise (edges flicker more than flat paper).
    Returns blinks grouped over consecutive frames, and places that light up again and again (edges, reflections)."""
    bg = var = None
    age = 0
    spots = []
    yy, xx = np.mgrid[0:h, 0:w]
    region = np.ones((h, w), bool)
    if calib:  # only the printed target and a margin around it
        co, si = np.cos(calib["theta"]), np.sin(calib["theta"])
        dx, dy = xx - calib["cx"], yy - calib["cy"]
        u, v = (dx * co + dy * si) / calib["a"], (-dx * si + dy * co) / calib["b"]
        region = u * u + v * v <= 3.2 ** 2
    for i, f in enumerate(frames(path, w, h)):
        x = f.astype(np.float32)
        if bg is None:
            bg, var = x.copy(), np.zeros((h, w), np.float32)
            continue
        # per-row, per-colour brightness match (robust: median of ratios), smoothed over 9 rows
        ratio = np.where(bg > 20, x / np.maximum(bg, 1), np.nan)
        g = np.nanmedian(ratio, axis=1)
        g = np.where(np.isnan(g), 1.0, g)
        k = np.ones(9) / 9
        g = np.stack([np.convolve(np.pad(g[:, c], 4, mode="edge"), k, mode="valid") for c in range(3)], 1).astype(np.float32)
        dif = x - bg * g[:, None, :]
        ex = dif[..., 0] - np.maximum(dif[..., 1], dif[..., 2])
        d = box3(ex)
        dr = box3(dif[..., 0])
        med = float(np.median(d))
        dd = d - med
        g2 = (np.median(np.abs(dd)) * 1.4826 + 1.0) ** 2
        sd = np.sqrt(np.maximum(var, g2) if age >= 15 else np.maximum(var, 4 * g2))
        z = dd / sd
        cand = (z > z_thr) & (dr > 0.6 * d) & region & (age >= 30)  # first half second: still learning the noise
        ys, xs = np.nonzero(cand)
        if len(xs) and len(xs) < 5000:
            order = np.argsort(-z[ys, xs])
            used = np.zeros(len(xs), bool)
            for kk in order:
                if used[kk]:
                    continue
                near = (np.abs(xs - xs[kk]) <= 14) & (np.abs(ys - ys[kk]) <= 14) & ~used  # a bright dot has a wide halo
                used |= near
                bw = xs[near].max() - xs[near].min() + 1
                bh = ys[near].max() - ys[near].min() + 1
                if max(bw, bh) > 3 * min(bw, bh) + 3:  # a line, not a dot
                    continue
                zz = z[ys[near], xs[near]]
                spots.append(dict(frame=i, t=pts[i] if i < len(pts) else None, x=float((xs[near] * zz).sum() / zz.sum()),
                                  y=float((ys[near] * zz).sum() / zz.sum()), z=float(z[ys[kk], xs[kk]]), area=int(near.sum()), rise=float(d[ys[kk], xs[kk]] / 9)))
        # learn: background and each pixel's noise follow slow changes, but not where something lit up
        calm = z < 4
        a = np.where(calm, 0.06, 0.0).astype(np.float32)[..., None]
        bg += (x - bg) * a
        if age < 15:
            var += (np.minimum(dd * dd, 16 * g2) - var) / (age + 1)
        else:
            var += np.where(calm, 0.04, 0.0).astype(np.float32) * (np.minimum(dd * dd, 16 * var + 100) - var)
        age += 1
    # group into blinks: same place in consecutive frames
    blinks = []
    for s in sorted(spots, key=lambda s: s["frame"]):
        for b in blinks:
            if s["frame"] - b["last"] <= 1 and abs(s["x"] - b["x"]) <= 16 and abs(s["y"] - b["y"]) <= 16:
                if s["frame"] != b["last"]:
                    b["last"] = s["frame"]; b["n"] += 1
                if s["z"] > b["z"]:
                    b.update(x=s["x"], y=s["y"], z=s["z"], rise=s["rise"])
                break
        else:
            blinks.append(dict(first=s["frame"], last=s["frame"], n=1, t=s["t"], x=s["x"], y=s["y"], z=s["z"], rise=s["rise"]))
    # a place that lights up over and over is an edge or a reflection, not a trigger pull
    rep = [b for b in blinks if sum(1 for o in blinks if abs(o["x"] - b["x"]) <= 6 and abs(o["y"] - b["y"]) <= 6) >= 4]
    return [b for b in blinks if b not in rep], rep


def ell_rho(c, x, y):
    import math
    dx, dy = x - c["cx"], y - c["cy"]
    co, si = math.cos(c["theta"]), math.sin(c["theta"])
    u = (dx * co + dy * si) / c["a"]
    v = (-dx * si + dy * co) / c["b"]
    return math.hypot(u, v)


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    vid = pathlib.Path(sys.argv[1])
    logp = pathlib.Path(sys.argv[2]) if len(sys.argv) > 2 else vid.with_name(vid.stem + "-log.txt")
    log = json.loads(logp.read_text(encoding="utf-8")) if logp.exists() else None
    w, h, pts = probe(vid)
    dts = np.diff(pts) * 1000 if len(pts) > 1 else np.array([0.0])
    med = float(np.median(dts)) if len(dts) else 0
    gaps = int(np.sum(np.round(dts / med) - 1)) if med > 0 else 0
    print(f"video {vid.name}: {w}x{h}, {len(pts)} frames over {pts[-1] - pts[0]:.2f} s · frame interval median {med:.1f} ms "
          f"(≈{1000 / med:.0f} fps) · gaps in the video itself: {gaps} frames")
    if log:
        fs = log.get("end", log).get("frameStats", {})
        print(f"app: v{log.get('app')} · reader {log.get('reader')} · camera {fs.get('cam', 0):.0f}/s · processed {fs.get('proc', 0):.0f}/s · "
              f"lost {fs.get('lostPct', 0):.0f}% · processing {log.get('perf')} · proc size {log.get('proc')}")
        print(f"     settings: sens {log['settings'].get('sensitivity')} mode {log['settings'].get('laserMode')} · calib {log.get('calib')}")
        caps = (log.get("camera") or {}).get("caps") or {}
        print(f"     camera caps: {', '.join(sorted(caps.keys()))}")
    calib = log.get("calib") if log else None
    blinks, repeats = find_blinks(vid, w, h, pts, calib)
    if repeats:
        print(f"(left out {len(repeats)} flashes at places that light up again and again: edges or reflections)")
    print(f"\nred blinks in the video: {len(blinks)}")
    app_ev = log.get("events", []) if log else []
    app_fr = log.get("frames", []) if log else []
    # line the video clock up with the log clock: try offsets, keep the one that matches most app events
    off = 0.0
    if app_ev and blinks and blinks[0]["t"] is not None:
        best = (-1, 0.0)
        for o in np.arange(-1500, 1500, 5):
            n = sum(1 for e in app_ev for b in blinks if abs((b["t"] - pts[0]) * 1000 + o - e["t"]) < 60 and abs(b["x"] - e["x"]) < 15 and abs(b["y"] - e["y"]) < 15)
            if n > best[0]:
                best = (n, float(o))
        off = best[1]
        print(f"(video time + {off:.0f} ms = log time; {best[0]} events lined up)")
    print("  t(ms)  frames  x      y      strength(z)  rise  rho    | app")
    matched = set()
    for b in blinks:
        tl = (b["t"] - pts[0]) * 1000 + off if b["t"] is not None else None
        rho = ell_rho(calib, b["x"], b["y"]) if calib else None
        hit = None
        for k, e in enumerate(app_ev):
            if k not in matched and tl is not None and abs(e["t"] - tl) < 120 and abs(e["x"] - b["x"]) < 20 and abs(e["y"] - b["y"]) < 20:
                hit = (k, e)
                matched.add(k)
                break
        if hit:
            e = hit[1]
            what = f"{e['kind']} {('HIT ' + str(e['score'])) if e.get('hit') else ('miss ' + str(e.get('score')))} tier {e['tier']} frames {e['frames']} lost {e['lostB']}/{e['lostIn']}/{e['lostA']}"
        elif tl is not None and app_fr:
            near = [f for f in app_fr if abs(f["t"] - tl) < 50]
            if not near:
                what = "NOT SEEN: the app processed no frame at that moment"
            else:
                what = "NOT COUNTED: app frames there " + " ".join(f"[{f['t']:.0f} pk{f['pk']} pz{f['pz']}{' q' if f.get('q') else ''}{' ' + f['b'] if f.get('b') else ''}{' lost' + str(f['lost']) if f.get('lost') else ''}]" for f in near)
        else:
            what = "-"
        print(f"{tl if tl is not None else 0:7.0f}  {b['n']:4d}   {b['x']:6.1f} {b['y']:6.1f} {b['z']:8.1f}   {b['rise']:5.1f}  {('%.2f' % rho) if rho is not None else '  - '}  | {what}")
    for k, e in enumerate(app_ev):
        if k not in matched:
            print(f"app counted something the video does not show: t {e['t']} ms at ({e['x']}, {e['y']}) {e['kind']} tier {e['tier']} z {e['z']} frames {e['frames']}")
    # fake-camera copy for the whole app
    name = "replay_" + re.sub(r"[^A-Za-z0-9_]+", "_", vid.stem)[-40:]
    OUT.mkdir(exist_ok=True)
    subprocess.run([ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(vid), "-map", "0:v:0", "-fps_mode", "passthrough", "-q:v", "2", "-f", "mjpeg",
                    str(OUT / f"{name}.mjpeg")], check=True, stderr=subprocess.DEVNULL)
    shots = []
    for b in blinks:
        rho = ell_rho(calib, b["x"], b["y"]) if calib else 9.0
        shots.append(dict(frame=b["first"], x=round(b["x"], 2), y=round(b["y"], 2), rho=round(rho, 4), hit=rho <= 1.0,
                          score=0 if rho > 2.5 else max(1, min(10, int(11 - 4 * rho))), dur=b["n"], strength=[1.0] * b["n"], amp=1.0))
    cx = calib["cx"] if calib else w / 2
    cy = calib["cy"] if calib else h / 2
    (OUT / f"{name}.json").write_text(json.dumps(dict(scene=name, fps=30, frames=len(pts), width=w, height=h, shots=shots, truth=dict(center=[cx, cy]), source=str(vid)), indent=1), encoding="utf-8")
    print(f"\nwrote tests/out/{name}.mjpeg (+ .json with the blinks above as ground truth) → node tests/e2e.mjs {name}")


if __name__ == "__main__":
    main()
