#!/usr/bin/env python3
"""Printable laser-run targets (A4 portrait), drawn in millimetres as SVG.

Design notes for the camera:
- The scoring zone (7-10) is one solid black disk. Ring lines and numbers *inside* it are dark grey,
  not white, so the camera sees a single clean black ellipse and finds it instantly.
- Rings are evenly spaced (ring width = black radius / 4), the same model the app uses for scores.
- A 50 mm scale bar lets you check the printer did not shrink the page.
"""
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PAGE_W, PAGE_H = 210.0, 297.0


def target_svg(black_d: float, title: str, subtitle: str) -> str:
    R = black_d / 2.0
    cx, cy = PAGE_W / 2, 140.0
    max_r = 98.0  # keep inside a 196 mm circle
    rings = [n for n in range(1, 11) if R * (11 - n) / 4 <= max_r]
    out = []
    add = out.append
    add(f'<svg xmlns="http://www.w3.org/2000/svg" width="{PAGE_W}mm" height="{PAGE_H}mm" viewBox="0 0 {PAGE_W} {PAGE_H}">')
    add('<rect width="100%" height="100%" fill="#fff"/>')
    add('<g font-family="Barlow Condensed, IBM Plex Sans KR, Arial Narrow, Arial, sans-serif">')
    # header
    add(f'<text x="14" y="16" font-size="6.2" font-weight="700" fill="#111">{title}</text>')
    add(f'<text x="14" y="22.5" font-size="3.6" fill="#555">{subtitle}</text>')
    add(f'<text x="196" y="16" font-size="3.6" fill="#555" text-anchor="end">검정 원 = 명중 (7점 이상)</text>')
    add(f'<text x="196" y="22.5" font-size="3.6" fill="#555" text-anchor="end">검정 원 지름 {black_d:g} mm</text>')
    # outer rings: white bands with thin dark lines, outermost first
    for n in rings:
        r = R * (11 - n) / 4
        if n <= 6:
            add(f'<circle cx="{cx}" cy="{cy}" r="{r:.3f}" fill="#fff" stroke="#1b1b1b" stroke-width="0.3"/>')
    # black scoring disk (ring 7 edge)
    add(f'<circle cx="{cx}" cy="{cy}" r="{R:.3f}" fill="#000"/>')
    for n in (8, 9, 10):
        r = R * (11 - n) / 4
        add(f'<circle cx="{cx}" cy="{cy}" r="{r:.3f}" fill="none" stroke="#3c3c3c" stroke-width="0.35"/>')
    # ring numbers on the four axes (inside each band)
    band = R / 4
    fs = min(4.2, band * 0.62)
    for n in rings:
        if n > 8:
            continue
        r_mid = R * (10.5 - n) / 4
        col = "#2a2a2a" if n <= 6 else "#4d4d4d"
        for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
            x, y = cx + dx * r_mid, cy + dy * r_mid + fs * 0.35
            add(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{fs:.2f}" font-weight="600" fill="{col}" text-anchor="middle">{n}</text>')
    # footer: scale bar + print notes
    y0 = 262.0
    add(f'<line x1="14" y1="{y0}" x2="64" y2="{y0}" stroke="#111" stroke-width="0.5"/>')
    for x in (14, 39, 64):
        add(f'<line x1="{x}" y1="{y0 - 2}" x2="{x}" y2="{y0 + 2}" stroke="#111" stroke-width="0.5"/>')
    add(f'<text x="14" y="{y0 + 7}" font-size="3.4" fill="#333">50 mm · 인쇄 후 자로 재서 같은지 확인</text>')
    add(f'<text x="196" y="{y0 + 1}" font-size="3.4" fill="#333" text-anchor="end">인쇄: 실제 크기(100%) · 무광 용지</text>')
    add(f'<text x="196" y="{y0 + 7}" font-size="3.4" fill="#333" text-anchor="end">종이가 휘지 않게 판에 붙여 주세요</text>')
    add(f'<text x="14" y="282" font-size="3" fill="#888">레이저런 표적 · 카메라 인식용 · 검정 원 안의 선은 일부러 회색으로 인쇄합니다</text>')
    add('</g></svg>')
    return "\n".join(out)


VARIANTS = [
    ("target-a4-59.5mm", 59.5, "LASER RUN 10m 표적", "10m 공기권총 표적의 검정 부분과 같은 크기"),
    ("target-a4-100mm", 100.0, "LASER RUN 연습용 큰 표적", "처음 배우는 학생·짧은 거리용"),
]

if __name__ == "__main__":
    for name, d, title, sub in VARIANTS:
        (HERE / f"{name}.svg").write_text(target_svg(d, title, sub), encoding="utf-8")
        print("wrote", name + ".svg")
