# Reusable SVG assets

PatchCreator deliberately uses ordinary SVG files for reusable artwork such as
characters, spacecraft, badges and logos. Assets stay editable in Inkscape and
are imported as vector children of the generated document rather than being
converted into an opaque proprietary format.

## Asset component

A reusable asset is referenced from YAML with an `asset` element:

```yaml
- id: dragon
  type: asset
  source: assets/blue-dragon.svg
  width: 34
  roles:
    primary: dragon-blue
    outline: near-black
    highlight: dragon-highlight
  position:
    mode: polar
    angle: 315deg
    radius: 20
    self_anchor: chest
```

Relative `source` paths are resolved relative to the YAML design file. A design
constructed only with the in-memory `loads_design()` API has no source directory,
so relative paths in that case are resolved against the process working
directory.

At least one physical `width` or `height` should be supplied unless the source
SVG itself has physical `mm`, `cm`, `in` or `px` dimensions. Supplying one
preserves aspect ratio. Supplying both defines a containing size; aspect ratio is
preserved by default using the smaller scale. Set `preserve_aspect: false` only
when intentional non-uniform scaling is wanted.

Source SVGs must have a `viewBox`. This keeps conversion between SVG user units
and physical patch millimetres explicit and deterministic.

## Anchor convention

The recommended Inkscape convention is a hidden layer named
`PatchCreator Anchors`. Anchor marker objects carry a normal custom SVG
attribute:

```xml
<g
  inkscape:groupmode="layer"
  inkscape:label="PatchCreator Anchors"
  style="display:none">
  <circle
    cx="82"
    cy="37"
    r="1"
    data-patchcreator-anchor="nose" />
  <g
    transform="translate(45 70)"
    data-patchcreator-anchor="chest" />
</g>
```

The layer name is for the artist; discovery is driven by the
`data-patchcreator-anchor` attribute. This means an artist can unhide the layer,
move an anchor in Inkscape, and hide it again without using a PatchCreator-only
editor.

Marker geometry is interpreted as follows:

- circles/ellipses use `cx,cy`;
- rectangles use their centre;
- lines use their midpoint;
- text/image/use markers use `x,y`;
- groups and other elements use their local origin.

Nested SVG `matrix`, `translate`, `scale` and `rotate` transforms are included in
the anchor position. The asset's final physical scaling is then applied before
the anchor enters the PatchCreator scene graph, so anchor-relative placement
continues to work when the asset is resized.

Anchor marker objects are forced hidden in generated output even if the source
layer was accidentally left visible.

## Semantic colour roles

Artwork can expose semantic paint roles without encoding a particular palette:

```xml
<path
  d="..."
  fill="#4d84c4"
  data-patchcreator-fill-role="primary" />

<path
  d="..."
  fill="none"
  stroke="#222222"
  data-patchcreator-stroke-role="outline" />
```

`data-patchcreator-colour-role` is a shorthand which changes existing fill and
stroke paints together; when neither is present it supplies a fill.

The design maps those roles to palette entries:

```yaml
palette:
  dragon-blue: "#477fc4"
  dragon-highlight:
    from: dragon-blue
    lighten: 0.30
  near-black: "#1a1a1a"

# ...
roles:
  primary: dragon-blue
  highlight: dragon-highlight
  outline: near-black
```

Derived `lighten`/`darken` colours are resolved in perceptual OKLCH lightness,
rather than by independently scaling RGB channels. The resulting concrete CSS
colour is available to all built-in renderers, not just assets.

## IDs and internal references

Every imported SVG ID is prefixed with the PatchCreator element ID. References
such as `href="#shape"` and `url(#clip)` are rewritten to the prefixed IDs. This
allows the same source asset to be instantiated more than once without ID,
clip-path or gradient collisions.

Reusable assets must be self-contained. External image/use references and
scripts are rejected. Embed or normalise such resources before importing them.
The future `patchcreator normalize` command tracked separately will automate more
of that cleanup.
