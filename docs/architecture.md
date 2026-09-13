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
    transforms.py
    clipping.py
    overlap.py
  geometry/
    units.py
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
