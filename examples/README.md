# PatchCreator examples

These inputs are intended both as runnable demonstrations and as regression
fixtures. They are deliberately small enough to edit by hand.

## Quick start

Render the smallest example:

```text
patchcreator render examples/minimal-patch.yaml
```

Render the full 80 mm mission-patch demonstrator:

```text
patchcreator data fetch natural-earth-land-110m
patchcreator render examples/basic-round-patch.yaml
```

The Natural Earth data is downloaded into PatchCreator's external data cache; it
is not committed to this repository.

After rendering a master SVG, create the conservative downstream variant with:

```text
patchcreator export examples/basic-round-patch.svg
```

## Example catalogue

`minimal-patch.yaml` is the smallest useful authoring document: physical sizing,
safe margin, palette, border and live curved text.

`basic-round-patch.yaml` is the main 80 mm end-to-end example. It exercises the
border and safe area, Natural-Earth-backed globe, deterministic decorative
starfield with avoidance, curved text, an orbit that passes in front of/behind
the Earth and a marker positioned along that orbit.

`trajectory-and-placement.yaml` needs no external datasets. It demonstrates a
line/cubic trajectory, halo and dash styling, arrowheads, an elliptical orbit,
path-following objects and deterministic procedural stars.

`text-layouts.yaml` keeps all text live and editable. It demonstrates top and
bottom arcs, automatic fitting/tracking, text following a procedural trajectory
and a width-constrained band.

`reusable-asset-patch.yaml` imports `assets/demo-satellite.svg`. The asset shows
the hidden Inkscape anchor-layer convention and semantic fill/stroke colour
roles. The YAML remaps those roles through the patch palette and positions a
second object relative to the asset's `dish-tip` anchor.

`validation-risk-demo.svg` is intentionally problematic input for the independent
geometry validator. It contains a thin stroke, a tiny filled island, a narrow
gap, an ordinary overlap and an overlap marked for future knockout. Generate a
separate visual diagnostic copy with:

```text
patchcreator check examples/validation-risk-demo.svg \
  --debug-svg examples/validation-risk-demo.debug.svg
```

The debug SVG adds a removable top Inkscape layer and leaves the example source
unchanged.

The reusable asset can also be inspected directly:

```text
patchcreator normalize examples/assets/demo-satellite.svg
```

This reports its viewBox, physical size, geometry bounds, anchors, colour roles
and remaining transforms without changing the file.
