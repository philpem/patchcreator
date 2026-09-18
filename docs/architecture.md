# PatchCreator Architecture

Status: Version 0.1

## Package layout

The implementation has grown beyond the original bootstrap sketch. The current
high-level package split is:

```text
patchcreator/
  assets/       reusable-SVG inspection and normalisation
  components/   built-in procedural/renderable components and registry
  config/       YAML loader and Pydantic document schema
  data/         explicit external-dataset catalogue/cache
  geography/    geographic data adapters and projections
  geometry/     affine transforms, bounds, paths and physical geometry
  gui/          optional GUI-independent editor state plus PySide6 shell
  profiles/     machine/design-intent profile loading and defaults
  scene/        scene graph, placement and coordinate-frame resolution
  svg/          editable writer and compatibility/export transforms
  text/         font resolution, shaping, outlines and SVG path sampling
  validation/   independent SVG geometry analysis and debug overlays
  cli.py        normal command handlers
  dispatch.py   lazy top-level CLI/optional-GUI dispatch
  palette.py    semantic/derived colour handling
```

Submodule names are allowed to evolve; the architectural boundaries are more
important than preserving an exact file tree in this document.

## Core objects

### `Design`

Owns document-wide settings, profiles, palette, asset registry and root scene node.

### `SceneNode`

Common properties:

- stable ID;
- label;
- children;
- transform/placement;
- self anchor;
- clip policy;
- overlap policy;
- visibility;
- semantic role;
- generated geometry/bounds/anchors.

### `Component`

A procedural component registered by type name. It receives validated config and a rendering context and returns scene geometry plus anchors/metadata.

### `Placement`

Variants:

- Cartesian;
- polar;
- relative/anchor;
- path-following.

### `Profile`

Layered configuration containing machine defaults and design-intent overrides.

### `Validator`

Operates on scene geometry or an imported SVG geometry model and emits structured findings plus optional overlay geometry.

## Scene geometry and resolution

Scene nodes distinguish between **local** geometry and **resolved** document-space geometry.

A component owns geometry in its own local coordinate system and supplies:

- an optional axis-aligned local `Bounds`;
- optional named local anchor points;
- later, richer path/shape geometry for validation and occlusion.

Placement supplies the node's local `AffineTransform`. A resolution pass walks the hierarchy and composes parent and child transforms. After resolution each node exposes:

- a world transform;
- document-space axis-aligned bounds;
- named document-space anchors;
- standard bounds-derived anchors such as `centre`, `top`, `left`, and corners;
- an `origin` anchor even for geometry-less groups.

Groups and layers which do not have geometry of their own receive aggregate bounds from their descendants. Component-provided anchors override bounds-derived anchors of the same name.

The affine matrix representation follows SVG's six-value matrix convention. This keeps the scene model and editable SVG output compatible without making the SVG DOM itself the internal scene graph.

## Placement and coordinate frames

Placement is a separate pass from generic scene resolution. Components first expose local bounds/anchors; placement resolves artist-facing rules to local affine transforms; the scene resolver then aggregates final world bounds and anchors.

The default placement frame is:

- origin at patch centre;
- reference radius equal to the patch reference radius;
- axes aligned with SVG/Inkscape coordinates (positive X right, positive Y down).

Polar coordinates retain the artist-facing convention of 0 degrees up and increasing clockwise.

A container can establish a frame for its children:

```yaml
- id: constellation
  type: group
  position:
    mode: cartesian
    x: 12
    y: -5
    self_anchor: origin
  frame:
    origin: self
    reference_radius: 10
  elements:
    - id: star-a
      type: star
      position:
        mode: polar
        angle: 60deg
        radius: 0.7r
```

Frame rules are deliberately explicit:

- no `frame` property: inherit the parent frame unchanged;
- `origin: inherit`: retain the parent frame origin/axes, optionally changing only `reference_radius`;
- `origin: self`: place the child frame at this node's local origin and make its axes follow this node's transform;
- `origin: [x, y]`: as above, but use an explicit point in this node's local coordinate system.

This lets ordinary nested groups continue to use patch coordinates while a constellation, instrument reticle or similar subsystem can opt into its own movable/rotatable polar frame.

All placement modes may select a `self_anchor`. Visual objects normally use `centre`; geometry-less positioning groups normally use `origin`.

Relative placement names the target and target anchor separately:

```yaml
position:
  mode: relative
  target: dragon-blue
  target_anchor: nose
  self_anchor: centre
  offset: [2, -1]
```

The initial resolver uses anchors belonging to the target's own local geometry. Aggregate group bounds are produced by the subsequent scene-resolution pass and therefore are not dependency inputs for relative placement.

Path-following placement consumes a small `PathSampler` protocol rather than SVG path syntax. Path components can therefore provide analytic or Bézier implementations later without changing placement. Samplers return document-space point and tangent information. Fractional positions accept either `0.35` or `35%`; positive normal offset is to the visual right of the path in SVG's y-down coordinate system.

Dependency resolution allows an object to reference a later sibling and detects relative-placement cycles explicitly.

## Key architectural rule

The compositor and validator share geometry primitives but remain separately callable. `patchcreator check` should be useful on an SVG that did not originate from PatchCreator.

## SVG strategy

The master writer favours editability:

- ordinary groups;
- SVG clip paths;
- live text/textPath;
- simple strokes/fills;
- Inkscape labels;
- no filters by default;
- no gratuitous nested transforms.

The compatibility writer may perform destructive transformations such as expanding references or knocking out hidden lower geometry.

## Third-party component loading

Prefer Python entry points so packages can register additional component types, e.g. an entry-point group such as:

```text
patchcreator.components
```

A component plugin should not require changes to core dispatch code.
