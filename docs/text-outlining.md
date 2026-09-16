# Font resolution, shaping and text outlining

PatchCreator keeps text live in the editable master SVG. Compatibility export can outline that text, but correct outlining has two separate stages:

1. resolve the requested family/style/weight to one concrete local font face and shape the Unicode text;
2. convert the shaped glyphs to SVG paths and place those paths in the straight, curved or path-following layout.

The first stage lives in `patchcreator.text` and is deliberately independent of SVG export so the same logic can be reused by a future GUI preview.

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

`patchcreator export --text paths` now supports the first deliberately narrow outlining slice: horizontal `<text>` elements with direct text content. This covers PatchCreator's straight, upper/lower-band and width-fitted band text.

The exporter shapes the run with HarfBuzz, obtains the selected glyph outlines from FontTools and replaces the live `<text>` node with a `<g>` containing ordinary SVG `<path>` glyphs. Baseline x/y placement, `text-anchor`, transforms, fill/stroke/opacity styling, numeric letter spacing and PatchCreator's `textLength` + `lengthAdjust="spacing"` fitting are retained.

The current pass deliberately rejects constructs it cannot place faithfully yet, including:

- `<textPath>` curved/path-following text;
- `<tspan>` children;
- vertical writing modes and per-character rotation/dx lists;
- non-unitless text geometry values in external SVGs;
- `lengthAdjust="spacingAndGlyphs"`;
- non-normal font stretch.

Those failures are intentional rather than approximations. The next #55 slice will place already-shaped glyph outlines along `<textPath>` baselines, including PatchCreator's top/bottom arc titles.
