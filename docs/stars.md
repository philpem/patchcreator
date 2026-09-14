# Stars and starfields

PatchCreator distinguishes **semantic stars** (explicit objects placed by the artist) from **decorative starfields** (deterministically generated background detail).

## Semantic `star`

A star is centred on its local origin and uses the normal PatchCreator placement system:

```yaml
- id: payload-star
  type: star
  glyph: four-point
  size: 3.0
  fill: white
  position:
    mode: polar
    angle: 25deg
    radius: 0.55r
```

Initial glyphs are `dot`, `four-point`, `four-point-narrow`, `five-point` and `eight-point`. `size` is the overall physical diameter in millimetres. An optional `stroke` mapping accepts `colour` and `width`.

## Decorative `starfield`

A starfield is generated after scene placement so named avoidance targets can appear anywhere in paint order. A fixed seed produces identical SVG geometry on every render.

```yaml
- id: stars
  type: starfield
  seed: 123456789
  count: 14
  glyphs: [dot, four-point, five-point]
  size_range: [1.0, 2.0]
  minimum_separation: 0.5
  region:
    type: annular-sector
    inner_radius: 0.2r
    outer_radius: 0.88r
    angle_start: 285deg
    angle_end: 75deg
  avoidance:
    - target: earth
      clearance: 1.5
```

If `seed` is omitted or set to `auto`, PatchCreator generates a 64-bit seed, emits it as a render warning (and therefore on the CLI), and stores it as `patchcreator:seed` on the SVG group. Copy that value into the YAML to lock the layout.

By default generated stars must fit wholly inside the patch safe area. Set `respect_safe_area: false` only when clipping/overflow is intentionally being handled another way.

### Regions

`annular-sector` is centred on the patch. Angles use PatchCreator's normal convention: 0° up and increasing clockwise. Radius values may use millimetres or fractions such as `0.8r`.

`rectangle` uses `x` and `y` relative to patch centre, with width/height in millimetres:

```yaml
region: {type: rectangle, x: -20, y: -15, width: 40, height: 30}
```

`polygon` similarly uses patch-centred `[x, y]` points and may be concave:

```yaml
region:
  type: polygon
  points:
    - [-25, -12]
    - [20, -15]
    - [28, 10]
    - [-18, 18]
```

### Avoidance

Avoidance is evaluated against the resolved world-space bounds of named scene objects. Clearance is in millimetres and the decorative star's own radius is also included. This is intentionally conservative: a rectangular bounds approximation is preferred to accidentally placing embroidery underneath another object. Exact silhouette avoidance can be added later when the boolean-geometry subsystem exists.

Generated stars also avoid one another using `minimum_separation`. If the requested count cannot fit within `max_attempts`, the field is emitted with the stars that fit and a warning reports the shortfall rather than silently crowding geometry.

For embroidery, decorative starfields should normally use `overlap_policy: avoid` and explicit avoidance entries for foreground artwork. Visual SVG occlusion is not a substitute for avoiding hidden stitches.
