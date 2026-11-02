---
name: trace-to-svg
description: Trace a bitmap drawing (png, jpeg, heic, screenshot) into a single simplified SVG path that can be tinted with currentColor. Use when the user wants artwork turned into an icon, glyph, game tile, logo, or silhouette; when they ask to "trace", "vectorize", or "convert to SVG"; or when hand-authoring SVG path data for an illustration is going badly and a reference image exists.
version: 1.0.0
allowed-tools: Bash(python3:*), Bash(sips:*), Read, Write, Edit
---

# Trace a drawing into an SVG path

Turns a bitmap drawing into one `<path>` you can drop into a component and tint
with `currentColor`. Stdlib Python plus macOS `sips` — nothing to install, no
`potrace`, no PIL.

**Use this instead of hand-authoring path data.** Writing bezier coordinates
from imagination, rendering, and squinting at the result has a low ceiling for
anything representational: the output reads as generic no matter how many
rounds you spend. If a reference image exists, trace it.

## How it works

1. Threshold the image to its ink.
2. Dilate to close gaps in the linework, so the outline is watertight.
3. Flood-fill the background inward from the border; everything unreached is
   the figure. (This is why a *line drawing* with a white interior still yields
   a filled silhouette.)
4. Walk the figure's boundary, then simplify with Douglas–Peucker.
5. Enclosed light regions — eyes, mouths, gaps between shapes — come out as
   extra rings, so fill with **`fill-rule="evenodd"`**.

## Usage

```sh
python3 "${CLAUDE_SKILL_DIR}/trace.py" IMAGE [options]
```

Prints the path data to stdout; diagnostics go to stderr.

| Option | Default | What it does |
| --- | --- | --- |
| `--size` | 720 | Trace resolution, longest side. **The highest-leverage knob.** |
| `--threshold` | 215 | Ink cutoff 0–255; raise it to catch lighter strokes |
| `--close` | 2 | Dilate radius that closes gaps in the outline |
| `--simplify` | 2.4 | Douglas–Peucker tolerance, in source pixels |
| `--min-hole` | 520 | Drop enclosed regions smaller than this many pixels |
| `--crop` | `0,0,1,1` | `x0,y0,x1,y1` as fractions, to isolate the subject |
| `--box` | 32 | viewBox size the result is fitted into |
| `--out` | — | Write a standalone `.svg` instead of printing |
| `--preview` | — | Write an HTML preview at 240/64/33/23px |

## Workflow

Always run with `--preview`, then screenshot it in headless Chrome and **look**:

```sh
python3 "${CLAUDE_SKILL_DIR}/trace.py" art.png --preview /tmp/p.html > /tmp/path.txt
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless --disable-gpu \
  --screenshot=/tmp/p.png --window-size=420,300 --force-device-scale-factor=3 \
  --hide-scrollbars file:///tmp/p.html
```

The preview deliberately shows tiny sizes. A trace that looks great at 240px
routinely turns to grain at 23px, and that is usually the size that matters.

Expect two or three tuning passes. Judge each by the preview, not by the
numbers.

## Tuning, in the order that pays

1. **Resolution beats file format.** Going 360px → 720px separated fused shapes
   and sharpened fine detail dramatically. Format matters much less than people
   expect, because downscaling averages compression noise away.
2. **But trace the original, not a re-export.** A lossy re-export blurs exactly
   the low-contrast boundaries the threshold depends on — and exports are often
   downsampled too, which compounds it. Ask for the source file.
3. **There is a ceiling.** Past a point, more resolution just adds speckle that
   turns to noise at icon size. Test one step up; if it comes back busier rather
   than better, stay put.
4. **`--min-hole` kills speckle.** Too low and dozens of pinholes survive as
   grain. Raise it until only meaningful openings remain.
5. **`--crop` before anything else** if the image has a background, a second
   subject, or a part you don't want. Watch for cropping *through* the subject —
   it leaves a hard straight edge that reads as a mistake.
6. **`--threshold` is the judgement call on shaded art.** Pencil and airbrush
   work are continuous-tone, so there's no correct cutoff — try 200 / 215 / 230.

## Using the result

```tsx
const ART = 'M25.6 1.8 L...';   // paste the traced path

<svg viewBox="0 0 32 32" aria-hidden="true">
  <path d={ART} fill="currentColor" fillRule="evenodd" />
</svg>
```

Because it's one path tinted by `currentColor`, one trace serves every colour
variant. `transform="translate(32 0) scale(-1 1)"` mirrors it — useful when two
variants must stay distinguishable without relying on colour.

Budget roughly 7–13 KB of path data at `--simplify 2.4`. Raise `--simplify` to
shrink it; that costs fine detail first.

## Limits

- macOS only (`sips`).
- Wants a drawing on a light background with a mostly closed outline. Photos,
  busy backgrounds, and subjects touching the image border all fail — crop
  first, or expect the flood fill to leak inward and swallow the figure.
- Output is a filled silhouette with holes. It is not stroke-preserving line
  art; thin strokes below roughly 1.5px at the target size vanish.
