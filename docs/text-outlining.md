# Font resolution, shaping and text outlining

PatchCreator keeps text live in the editable master SVG. Compatibility export can outline that text, but correct outlining has two separate stages:

1. resolve the requested family/style/weight to one concrete local font face and shape the Unicode text;
2. convert the shaped glyphs to SVG paths and place those paths in the straight, curved or path-following layout.

The first stage lives in `patchcreator.text` and is shared by live-text fitting,
compatibility export and the GUI preview.

## Live text and viewer compatibility

Automatic fitting measures the installed font. Long runs shrink to fit the
available width; shorter runs use explicit letter spacing. The SVG includes
both ordinary and legacy XLink path references for Inkscape compatibility.
Procedural path labels use baselines resolved after scene placement, so their
position agrees with the visible trajectory and outlined output.

If the requested font is not installed, live rendering keeps the editable text
and warns that fitting depends on the viewer's `textLength` support. Install the
font for measured fitting and outlined output.

Qt and Xviewer's librsvg renderer do not support live `textPath` drawing. The
GUI therefore outlines curved text in an ephemeral preview copy; the master
and YAML remain editable. For Xviewer and similar consumers, render outlined
text directly to a separate file:

```text
patchcreator render examples/text-layouts.yaml --text paths -o text-layouts.view.svg
```

This retains the render's layers and construction guides. For a clean downstream
SVG with guides removed, use `patchcreator export artwork.svg --text paths`.
Default render/export output keeps live text and the baselines it depends on.
See [librsvg's text support](https://gnome.pages.gitlab.gnome.org/librsvg/devel-docs/text_layout.html)
for its viewer limitation.

## Reproducibility

Font family names are environment-dependent. For reproducible output, pass an explicit font file to `FontRequest(path=...)`. PatchCreator records the actual resolved family, style, weight, face index and units-per-em in the returned `ResolvedFont` object; it does not copy the font into the project or repository.

Compatibility export exposes the same explicit-font route through the Python API:

```python
from patchcreator.svg import ExportOptions, export_svg_file

export_svg_file(
    "mission.svg",
    "mission.compat.svg",
    options=ExportOptions(text_mode="paths", font_path="/path/to/font.ttf"),
)
```

Without an explicit path, `resolve_font()` scans the platform's normal local font directories. It considers only the requested family and explicit fallbacks. Generic families (`sans-serif`, `serif`, `monospace`) have a short deterministic preference list. PatchCreator does not silently choose an unrelated installed font when a named family is missing.

A resolution can contain substitution notes, for example when a generic family resolves to DejaVu Sans or when the nearest available weight/style differs from the request. Compatibility export reports those notes as warnings. Missing or unreadable fonts produce an actionable error.

No font files are committed to PatchCreator and tests use fonts already installed by the CI operating system.

## Shaping

`shape_text()` uses HarfBuzz against the resolved font and returns immutable `ShapedRun` / `ShapedGlyph` records containing:

- glyph ID and FontTools glyph name;
- HarfBuzz cluster index;
- x/y advance;
- x/y offset;
- direction, script and language selected by HarfBuzz;
- units-per-em for physical scaling later.

The output remains in font units. This preserves kerning, ligatures, script shaping and positioning without prematurely mixing those decisions with SVG layout.

FontTools is exposed through `open_ttfont()` so the outlining stage retrieves the exact glyph geometry selected by HarfBuzz.

## Compatibility export

`patchcreator export --text paths` supports horizontal direct-content `<text>` plus single-subpath SVG `<textPath>` layouts.

For straight and band text, the exporter shapes the run with HarfBuzz, obtains the selected glyph outlines from FontTools and replaces the live `<text>` node with a `<g>` containing ordinary SVG `<path>` glyphs. Baseline x/y placement, `text-anchor`, transforms, fill/stroke/opacity styling, numeric letter spacing and PatchCreator's `textLength` + `lengthAdjust="spacing"` fitting are retained.

For path-following text, the referenced SVG `<path>` is parsed through FontTools and adapted to PatchCreator's measurable path sampler. Lines, cubic and quadratic curves, relative commands, elliptical arcs and closed single-subpaths are supported. Each shaped glyph is placed by physical arc length and rotated to the sampled tangent. `startOffset`, `text-anchor`, parent `dy` baseline shift, letter spacing and `textLength` spacing adjustment are applied before glyph paths are written. PatchCreator's top/bottom circular titles use the same path-placement machinery.

Open paths fail explicitly when the requested text run would extend before the path start or beyond its end. Closed paths can wrap the start position around the loop, but one text run may not exceed one full circuit. Construction baselines are consumed before the normal compatibility pass removes authoring-only geometry.

The current pass deliberately rejects constructs it cannot place faithfully yet, including:

- disconnected/multiple-subpath text baselines;
- transformed textPath baselines that have not been flattened into their geometry;
- `<tspan>` children or style overrides directly on `<textPath>`;
- vertical writing modes and per-character rotation/dx lists;
- non-unitless text geometry values in external SVGs;
- `lengthAdjust="spacingAndGlyphs"`;
- non-normal font stretch.

Those failures are intentional rather than approximations. The editable master remains live-text SVG and is never modified by compatibility export.
