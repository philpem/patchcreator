# Render pipeline

PatchCreator uses a two-phase component/scene pipeline so generated SVG stays editable while placement remains geometry-aware.

1. Components render local SVG geometry and return a `ComponentResult` containing local bounds, named anchors and optional path samplers.
2. Scene nodes receive that local geometry metadata.
3. The placement resolver converts Cartesian, polar, relative-anchor and path-following placement into local affine transforms.
4. The generic scene pass resolves world transforms/bounds/anchors.
5. The SVG writer writes each node's **local** transform onto the corresponding nested `<g>`, preserving the artist hierarchy.
6. Clip paths are applied after placement. Patch/safe-area clips are compensated into node-local coordinates so they remain fixed in patch coordinates when an object moves.

Path samplers returned by a component are bound to that component's scene node. A path-following child therefore samples the path after the owner's placement transform has been applied.

Unsupported components rendered with `--allow-unsupported` remain in the SVG as labelled groups and are skipped by placement if their missing geometry would otherwise make the partial render fail.

This architecture deliberately keeps component registration extensible: adding a new procedural component does not require a core type switch.
