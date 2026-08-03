#!/usr/bin/env python3
"""Trace a bitmap drawing into a single simplified SVG path.

Stdlib only. macOS `sips` decodes the input to BMP, so any format sips reads
(png, jpeg, heic, tiff, gif) works without third-party packages.

Pipeline: threshold to ink -> dilate to close gaps in the linework -> flood-fill
the background inward from the border -> everything unreached is the figure ->
walk its boundary (Moore neighbourhood) -> simplify (Douglas-Peucker). Enclosed
light regions inside the figure come out as extra rings, so the result is meant
to be filled with fill-rule="evenodd".
"""

import argparse
import os
import struct
import subprocess
import sys
import tempfile
from collections import deque

sys.setrecursionlimit(100000)


def to_bmp(src, size):
    """Decode any sips-readable image to a 24-bit BMP, longest side `size`."""
    if not os.path.isfile(src):
        sys.exit(f'no such image: {src}')
    fd, path = tempfile.mkstemp(suffix='.bmp')
    os.close(fd)
    cmd = ['sips', '-s', 'format', 'bmp']
    if size:
        cmd += ['-Z', str(size)]
    cmd += [src, '--out', path]
    r = subprocess.run(cmd, capture_output=True, text=True)
    # sips exits 0 even when it skips an unreadable file, so check the output.
    if r.returncode or not os.path.getsize(path):
        os.unlink(path)
        msg = (r.stderr or r.stdout).strip() or 'sips produced no output'
        sys.exit(f'could not decode {src}: {msg}')
    return path


def read_bmp(path):
    data = open(path, 'rb').read()
    off = struct.unpack_from('<I', data, 10)[0]
    w, h = struct.unpack_from('<ii', data, 18)
    bpp = struct.unpack_from('<H', data, 28)[0]
    if bpp not in (24, 32):
        sys.exit(f'unsupported bit depth {bpp}')
    flip = h > 0
    h = abs(h)
    stride = ((w * bpp // 8) + 3) // 4 * 4
    px = bpp // 8
    grey = []
    for row in range(h):
        base = off + (h - 1 - row if flip else row) * stride
        grey.append([
            (data[base + c * px + 2] * 299 + data[base + c * px + 1] * 587
             + data[base + c * px] * 114) // 1000
            for c in range(w)
        ])
    return w, h, grey


def dilate(w, h, m, r):
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        row = m[y]
        for x in range(w):
            if not row[x]:
                continue
            for dy in range(max(0, y - r), min(h, y + r + 1)):
                orow = out[dy]
                for dx in range(max(0, x - r), min(w, x + r + 1)):
                    orow[dx] = 1
    return out


def erode(w, h, m, r):
    out = [[0] * w for _ in range(h)]
    for y in range(h):
        for x in range(w):
            if y - r < 0 or y + r >= h or x - r < 0 or x + r >= w:
                continue
            ok = 1
            for dy in range(y - r, y + r + 1):
                row = m[dy]
                if not all(row[dx] for dx in range(x - r, x + r + 1)):
                    ok = 0
                    break
            out[y][x] = ok
    return out


def flood_background(w, h, ink):
    bg = [[0] * w for _ in range(h)]
    q = deque()

    def seed(x, y):
        if not ink[y][x] and not bg[y][x]:
            bg[y][x] = 1
            q.append((x, y))

    for x in range(w):
        seed(x, 0)
        seed(x, h - 1)
    for y in range(h):
        seed(0, y)
        seed(w - 1, y)
    while q:
        x, y = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if 0 <= nx < w and 0 <= ny < h and not bg[ny][nx] and not ink[ny][nx]:
                bg[ny][nx] = 1
                q.append((nx, ny))
    return bg


def blobs(w, h, m, minpx):
    seen = [[0] * w for _ in range(h)]
    found = []
    for sy in range(h):
        for sx in range(w):
            if not m[sy][sx] or seen[sy][sx]:
                continue
            q = deque([(sx, sy)])
            seen[sy][sx] = 1
            cells = []
            while q:
                x, y = q.popleft()
                cells.append((x, y))
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < w and 0 <= ny < h and m[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = 1
                        q.append((nx, ny))
            if len(cells) >= minpx:
                found.append(cells)
    found.sort(key=len, reverse=True)
    return found


def mask_of(w, h, cells):
    m = [[0] * w for _ in range(h)]
    for x, y in cells:
        m[y][x] = 1
    return m


def boundary(w, h, m):
    start = next(((x, y) for y in range(h) for x in range(w) if m[y][x]), None)
    if not start:
        return []
    nbr = [(1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1), (0, -1), (1, -1)]
    ring, cur, d = [start], start, 0
    while len(ring) < w * h * 4:
        for k in range(8):
            i = (d + 6 + k) % 8
            nx, ny = cur[0] + nbr[i][0], cur[1] + nbr[i][1]
            if 0 <= nx < w and 0 <= ny < h and m[ny][nx]:
                cur, d = (nx, ny), i
                ring.append(cur)
                break
        else:
            break
        if cur == start and len(ring) > 3:
            break
    return ring


def simplify(pts, eps):
    """Iterative Douglas-Peucker (recursion blows the stack on long rings)."""
    if len(pts) < 3:
        return pts
    keep = [False] * len(pts)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        a, b = stack.pop()
        if b <= a + 1:
            continue
        x0, y0 = pts[a]
        x1, y1 = pts[b]
        dx, dy = x1 - x0, y1 - y0
        n = (dx * dx + dy * dy) ** 0.5
        worst, wi = -1.0, a
        for i in range(a + 1, b):
            px, py = pts[i]
            d = (abs(dy * px - dx * py + x1 * y0 - y1 * x0) / n if n
                 else ((px - x0) ** 2 + (py - y0) ** 2) ** 0.5)
            if d > worst:
                worst, wi = d, i
        if worst > eps:
            keep[wi] = True
            stack += [(a, wi), (wi, b)]
    return [p for p, k in zip(pts, keep) if k]


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('image', help='source drawing (png, jpeg, heic, ...)')
    ap.add_argument('--size', type=int, default=720,
                    help='trace resolution, longest side (default 720)')
    ap.add_argument('--threshold', type=int, default=215,
                    help='ink cutoff, 0-255; higher catches lighter strokes (default 215)')
    ap.add_argument('--close', type=int, default=2,
                    help='dilate radius to close gaps in the outline (default 2)')
    ap.add_argument('--simplify', type=float, default=2.4,
                    help='Douglas-Peucker tolerance in source px (default 2.4)')
    ap.add_argument('--min-hole', type=int, default=520,
                    help='drop enclosed regions smaller than this many px (default 520)')
    ap.add_argument('--crop', default='0,0,1,1',
                    help='x0,y0,x1,y1 as fractions of the image (default whole image)')
    ap.add_argument('--box', type=float, default=32.0,
                    help='viewBox size to fit the result into (default 32)')
    ap.add_argument('--out', help='write an SVG here (default: print the path data)')
    ap.add_argument('--preview',
                    help='write an HTML preview here, showing the result at several sizes')
    args = ap.parse_args()

    bmp = to_bmp(args.image, args.size)
    try:
        w, h, grey = read_bmp(bmp)
    finally:
        os.unlink(bmp)

    cx0, cy0, cx1, cy1 = (float(v) for v in args.crop.split(','))
    x0, y0, x1, y1 = int(cx0 * w), int(cy0 * h), int(cx1 * w), int(cy1 * h)
    grey = [r[x0:x1] for r in grey[y0:y1]]
    w, h = x1 - x0, y1 - y0

    ink = [[1 if grey[y][x] < args.threshold else 0 for x in range(w)] for y in range(h)]
    solid = dilate(w, h, ink, args.close) if args.close else ink
    bg = flood_background(w, h, solid)
    fig = [[0 if bg[y][x] else 1 for x in range(w)] for y in range(h)]
    if args.close:
        fig = erode(w, h, fig, args.close)

    big = blobs(w, h, fig, 1)
    if not big:
        sys.exit('nothing traced: try a higher --threshold')
    fig = mask_of(w, h, big[0])
    sys.stderr.write(f'figure: {len(big[0])} px of {w * h}\n')

    rings = [boundary(w, h, fig)]
    if args.min_hole:
        inner = [[1 if fig[y][x] and not ink[y][x] else 0 for x in range(w)]
                 for y in range(h)]
        holes = blobs(w, h, inner, args.min_hole)
        rings += [boundary(w, h, mask_of(w, h, c)) for c in holes]
        sys.stderr.write(f'holes: {len(holes)}\n')

    rings = [simplify(r, args.simplify) for r in rings if len(r) > 3]
    sys.stderr.write(f'points: {sum(len(r) for r in rings)} in {len(rings)} rings\n')

    xs = [p[0] for p in rings[0]]
    ys = [p[1] for p in rings[0]]
    cw, ch = max(xs) - min(xs), max(ys) - min(ys)
    s = args.box / max(cw, ch)
    ox = (args.box - cw * s) / 2 - min(xs) * s
    oy = (args.box - ch * s) / 2 - min(ys) * s
    d = ' '.join(
        'M' + ' L'.join(f'{p[0] * s + ox:.2f} {p[1] * s + oy:.2f}' for p in r) + ' Z'
        for r in rings
    )

    box = args.box
    if args.out:
        open(args.out, 'w').write(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {box:g} {box:g}">'
            f'<path fill-rule="evenodd" d="{d}"/></svg>\n')
        sys.stderr.write(f'wrote {args.out}\n')
    else:
        print(d)

    if args.preview:
        def cell(px):
            return (f'<div><svg viewBox="0 0 {box:g} {box:g}" width="{px}" height="{px}" '
                    f'style="background:#fff"><path fill-rule="evenodd" d="{d}" '
                    f'fill="currentColor"/></svg><br>{px}px</div>')
        open(args.preview, 'w').write(
            '<!doctype html><meta charset="utf-8">'
            '<body style="margin:0;padding:12px;font:11px sans-serif;background:#888;color:#111">'
            '<div style="display:flex;gap:12px;align-items:flex-start">'
            + ''.join(cell(p) for p in (240, 64, 33, 23)) + '</div></body>')
        sys.stderr.write(f'wrote {args.preview}\n')


main()
