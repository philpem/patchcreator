# PatchCreator

PatchCreator is a Python library, CLI and optional desktop editor for constructing
layered, editable, mission-patch-style SVG artwork from procedural components
and reusable SVG assets.

The normal workflow is:

1. describe a patch declaratively in YAML;
2. generate an embroidery-aware, Inkscape-friendly master SVG;
3. validate physical geometry and inspect any debug overlay;
4. refine the artwork in Inkscape if required;
5. create a conservative compatibility SVG for downstream import or continue
   into Ink/Stitch/PE-DESIGN.

The project deliberately targets patch-like composition rather than replacing a
general vector editor or stitch-plan generator.

## Current status

Version 0.1 is the first complete implementation of the initial roadmap. It
includes:

- the versioned YAML model/loader, layered scene graph and physical-mm geometry;
- Cartesian, polar, anchor-relative and path-following placement;
- reversible patch/safe/custom clipping with physical inset/outset;
- layered machine/design-intent embroidery profiles;
- semantic stars and deterministic decorative starfields;
- Natural-Earth-backed orthographic Earth rendering;
- editable trajectories, elliptical orbits and front/back occlusion;
- live curved/path text plus font-aware text-to-path compatibility export;
- reusable SVG assets with anchors and semantic colour roles;
- independent SVG normalisation and geometry validation;
- validation debug overlays, overlap diagnostics and physical knockout export;
- an optional PySide6 GUI using the same YAML/render pipeline, with live preview,
  scene tree, placement/drag controls, safe-margin/clip editing, validation
  overlays and starfield seed controls.

See:

- [`docs/specification.md`](docs/specification.md) — design requirements and behaviour;
- [`docs/architecture.md`](docs/architecture.md) — package and scene-graph architecture;
- [`docs/external-data.md`](docs/external-data.md) — third-party dataset acquisition/cache policy;
- [`docs/gui.md`](docs/gui.md) — optional GUI installation and editing workflow;
- [`examples/README.md`](examples/README.md) — runnable example catalogue;
- [`CHANGELOG.md`](CHANGELOG.md) — release notes and version history;
- [`docs/initial-issues.md`](docs/initial-issues.md) — historical bootstrap backlog.

## Development install

PatchCreator requires Python 3.11 or later.

```text
python -m pip install -e '.[dev]'
pytest
patchcreator --help
```

Install the optional GUI with:

```text
python -m pip install -e '.[dev,gui]'
patchcreator gui
```

## Quick start

Render the small self-contained example:

```text
patchcreator render examples/minimal-patch.yaml
```

The full 80 mm demonstrator uses Natural Earth land data. Dataset acquisition is
an explicit action and rendering never silently downloads it:

```text
patchcreator data fetch natural-earth-land-110m
patchcreator render examples/basic-round-patch.yaml
```

Open the same YAML document in the optional live editor:

```text
patchcreator gui examples/basic-round-patch.yaml
```

After rendering, run the independent embroidery-geometry validator and create a
separate visual diagnostic copy:

```text
patchcreator check examples/basic-round-patch.svg \
  --debug-svg examples/basic-round-patch.debug.svg
```

Create a conservative downstream SVG, optionally applying physical overlap
knockout and font-aware text outlining:

```text
patchcreator export examples/basic-round-patch.svg
patchcreator export examples/basic-round-patch.svg --knockout --text paths
```

## Command-line interface

Main commands include:

```text
patchcreator schema [-o design-schema.json]
patchcreator render design.yaml
patchcreator check artwork.svg
patchcreator normalize asset.svg
patchcreator export artwork.svg
patchcreator profiles list
patchcreator profiles show intent standard-patch
patchcreator profiles effective design.yaml
patchcreator data list
patchcreator data fetch natural-earth-land-110m
patchcreator gui [design.yaml]
```

`patchcreator schema` emits JSON Schema 2020-12 directly from the authoritative Pydantic design model for editor/tooling integration. Component-specific element fields remain open because built-in and third-party component renderers extend the common element envelope dynamically; the normal loader/render pipeline remains authoritative for those semantic fields.

Third-party datasets are never silently downloaded or committed into the
PatchCreator source tree. See [`docs/external-data.md`](docs/external-data.md)
for cache locations, source declarations and the explicit fetch workflow.

## Licence

PatchCreator is available under the [MIT Licence](LICENSE).

## Design priorities

- physical sizing in millimetres;
- embroidery-aware geometry with profile-driven, overridable thresholds;
- editable layered SVG and strong Inkscape integration;
- Cartesian, polar, anchor-relative and path-following placement;
- reversible clipping and explicit embroidery-overlap handling;
- procedural Earth, starfields, trajectories/orbits, borders and curved text;
- reusable hand-cleaned SVG artwork with semantic anchors and colour roles;
- validation usable independently on non-PatchCreator SVG;
- conservative compatibility export without making the editable master destructive;
- one YAML/source model shared by the library, CLI and GUI.
