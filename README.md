# PatchCreator

PatchCreator is a Python library and CLI for constructing layered, editable, mission-patch-style SVG artwork from procedural components and reusable SVG assets.

The primary workflow is:

1. describe a patch declaratively in YAML;
2. generate an embroidery-aware, Inkscape-friendly master SVG;
3. refine the artwork in Inkscape;
4. export an optimised SVG for Brother PE-DESIGN or produce embroidery output with Ink/Stitch.

The project deliberately targets patch-like composition rather than replacing a general vector editor.

## Current status

Early implementation. The repository now contains the YAML model/loader, the first scene-graph structures, physical patch/safe-area geometry and an editable SVG writer capable of producing a circular or elliptical canvas and border. Most procedural components and embroidery validation are still tracked as roadmap issues.

See:

- [`docs/specification.md`](docs/specification.md) — design requirements and behaviour;
- [`docs/architecture.md`](docs/architecture.md) — proposed Python/scene-graph architecture;
- [`docs/initial-issues.md`](docs/initial-issues.md) — implementation backlog;
- [`examples/minimal-patch.yaml`](examples/minimal-patch.yaml) — currently renderable example;
- [`examples/basic-round-patch.yaml`](examples/basic-round-patch.yaml) — target end-to-end procedural example.

## Development install

PatchCreator requires Python 3.11 or later.

```text
python -m pip install -e '.[dev]'
pytest
patchcreator --help
```

Render the minimal example with:

```text
patchcreator render examples/minimal-patch.yaml
```

The richer `basic-round-patch.yaml` deliberately references components which are not all implemented yet. During development it can be rendered with unsupported elements skipped:

```text
patchcreator render --allow-unsupported examples/basic-round-patch.yaml
```

## Command-line interface

```text
patchcreator render design.yaml
patchcreator check artwork.svg
patchcreator normalize asset.svg
patchcreator profiles list
```

`render` is implemented first; the other commands are present as stable CLI entry points while their underlying subsystems are built.

## Design priorities

- physical sizing in millimetres;
- embroidery-safe geometry by default, with tunable/disableable filtering;
- editable layered SVG and strong Inkscape integration;
- Cartesian, polar, anchor-relative and path-following placement;
- reversible SVG clipping and explicit embroidery-overlap handling;
- procedural Earth, starfields, trajectories/orbits, borders and curved text;
- reusable hand-cleaned SVG artwork with semantic anchors and colour roles;
- a validation subsystem usable independently of the compositor;
- an eventual GUI editor with live preview, built on the same document model.
