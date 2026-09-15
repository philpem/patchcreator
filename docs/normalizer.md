# SVG asset normalizer

`patchcreator normalize` is an independent inspection/cleanup tool for SVGs that
will later be used by the `asset` component. It does not require a patch design.

Inspection is non-destructive:

```text
patchcreator normalize artwork.svg
```

The report includes the declared `viewBox`, physical size where available,
conservative visible-geometry bounds, PatchCreator anchor names, semantic colour
roles, transform count, and any visible geometry types whose bounds are not yet
understood by the normalizer.

Changes always require an explicit destination:

```text
patchcreator normalize artwork.svg --fix-viewbox -o artwork-normalized.svg
patchcreator normalize artwork.svg --fix-viewbox --padding 1 --in-place
```

`--fix-viewbox` calculates a conservative viewBox around visible supported
geometry. Hidden anchor layers and geometry inside `<defs>`, masks, clip paths,
markers and similar non-painted containers do not enlarge the result. If visible
unsupported geometry is present, PatchCreator refuses to rewrite the viewBox
rather than risk clipping it.

`--flatten-safe-transforms` is intentionally conservative. It currently bakes
leaf-level positive uniform scale/translate transforms into rectangles, circles,
ellipses, lines, polylines and polygons. Groups are preserved and complex,
rotating, skewing, non-uniform or path transforms are left intact. The command
reports how many transforms were actually flattened.

The normalizer's path bounds are conservative: line/end/control points bound
Bezier curves, while arc commands deliberately receive a loose radius allowance.
This is appropriate for viewBox repair, where extra whitespace is preferable to
clipped artwork. It is not intended to replace a full SVG rendering engine.
