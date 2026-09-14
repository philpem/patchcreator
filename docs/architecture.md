# PatchCreator Proposed Architecture

Status: Draft 0.1

## Package layout

```text
patchcreator/
  __init__.py
  cli.py
  config/
    loader.py
    schema.py
  scene/
    graph.py
    node.py
    placement.py
    clipping.py
    overlap.py
  geometry/
    units.py
    primitives.py
    transform.py
    paths.py
    boolean.py
    simplify.py
  components/
    registry.py
    boundary.py
    border.py
    stars.py
    earth.py
    trajectory.py
    text.py
    assets.py
  profiles/
    loader.py
    defaults/
  validation/
    engine.py
    feature_size.py
    gaps.py
    islands.py
    strokes.py
    overlaps.py
    overlay.py
  svg/
    writer.py
    inkscape.py
    metadata.py
    export.py
  assets/
    normalize.py
```

This is a logical architecture, not a requirement to create every module immediately.

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
- standard bounds-derived anchors such as `centre`, `top`, `left`, and corners.

Groups and layers which do not have geometry of their own receive aggregate bounds from their descendants. Component-provided anchors override bounds-derived anchors of the same name.

The affine matrix representation follows SVG's six-value matrix convention. This keeps the scene model and editable SVG output compatible without making the SVG DOM itself the internal scene graph.

The scene graph deliberately does **not** make placement decisions during this generic resolution pass. The placement subsystem resolves Cartesian/polar/anchor/path-following rules into local transforms first; scene resolution then combines those transforms and geometry deterministically.

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
