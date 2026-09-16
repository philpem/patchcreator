# Font resolution, shaping and future text outlining

PatchCreator keeps text live in the editable master SVG. Compatibility export can later outline that text, but correct outlining has two separate stages:

1. resolve the requested family/style/weight to one concrete local font face and shape the Unicode text;
2. convert the shaped glyphs to SVG paths and place those paths in the straight, curved or path-following layout.

The first stage lives in `patchcreator.text` and is deliberately independent of SVG export so the same logic can be reused by a future GUI preview.

## Reproducibility

Font family names are environment-dependent. For reproducible output, pass an explicit font file to `FontRequest(path=...)`. PatchCreator records the actual resolved family, style, weight, face index and units-per-em in the returned `ResolvedFont` object; it does not copy the font into the project or repository.

Without an explicit path, `resolve_font()` scans the platform's normal local font directories. It considers only the requested family and explicit fallbacks. Generic families (`sans-serif`, `serif`, `monospace`) have a short deterministic preference list. PatchCreator does not silently choose an unrelated installed font when a named family is missing.

A resolution can contain substitution notes, for example when a generic family resolves to DejaVu Sans or when the nearest available weight/style differs from the request. Missing or unreadable fonts produce an actionable `FontResolutionError`.

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

FontTools is exposed through `open_ttfont()` so the outlining stage can retrieve the exact glyph geometry selected by HarfBuzz.

## Compatibility export

This foundation does **not** yet change `patchcreator export --text paths`. That operation remains explicit/unavailable until the follow-up work converts shaped glyphs into ordinary SVG paths and correctly places them for straight text and `<textPath>` layouts. Keeping the stages separate avoids an implementation that merely converts Unicode code points to glyph outlines and loses real text shaping.
