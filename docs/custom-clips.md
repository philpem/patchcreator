# Custom clip geometry and physical offsets

A component can use another scene element as its clipping silhouette:

```yaml
clip:
  target: custom:mask-shape
  inset: 0
```

With a zero inset PatchCreator keeps the clip maximally reversible: the SVG
`<clipPath>` contains a `<use>` reference to the source component. Editing the
source geometry in Inkscape therefore changes the clip as well.

A non-zero inset/outset requires a derived shape because ordinary SVG has no
general path-offset operation. PatchCreator converts the target's visible filled
silhouette into analysis geometry, applies a physical Shapely offset, then emits
the result as an editable SVG path inside the clip definition. The source
component itself is not changed.

The sign convention matches patch/safe-area clips:

- positive `inset` moves the boundary inward by that many millimetres;
- negative `inset` moves it outward.

Straight polygon corners use mitred joins (with a finite mitre limit) rather
than bbox scaling or arbitrary corner rounding. Concave and multipart geometry
is handled by the boolean geometry backend. Separate components may remain
separate or merge naturally if an outset grows them until they meet. An inset
that consumes the complete silhouette is an explicit error.

Derived clip paths carry PatchCreator metadata naming the source component and
the physical offset. They are therefore inspectable/editable in Inkscape even
though they no longer live-link to later edits of the source shape. Regenerate
the SVG after changing the source to refresh the offset path.

## Supported source geometry

The current offset pass accepts visible filled paths, rectangles, circles,
ellipses, polygons and polylines, including descendant group transforms. It
intentionally refuses visible text, images, `<use>` references, filters, masks
or nested clip paths when deriving an offset rather than silently dropping or
approximating them. Normalize/convert such a source to ordinary filled path
geometry first.

Zero-offset custom clips retain the existing `<use>` behaviour and are not
subject to these derived-geometry restrictions.
