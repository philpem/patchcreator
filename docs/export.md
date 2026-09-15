# Compatibility SVG export

PatchCreator keeps the generated master SVG editable. It deliberately retains
Inkscape/PatchCreator metadata, live text, ordinary SVG clip paths and other
information that is useful while refining artwork.

`patchcreator export` creates a second, more conservative SVG for downstream
import without modifying the master:

```text
patchcreator export mission.svg
```

The default output is `mission.compat.svg`. An explicit destination can be
selected with `-o` / `--output`.

By default the compatibility pass:

- expands internal `<use>` references into ordinary copied geometry;
- rewrites copied IDs/references so repeated instances remain collision-safe;
- removes the PatchCreator validation overlay;
- removes geometry explicitly tagged as construction-only;
- flattens leaf-level translate/uniform-scale transforms where this can be done
  without changing primitive geometry semantics;
- removes unreferenced top-level definitions;
- strips Inkscape/Sodipodi authoring metadata;
- strips PatchCreator authoring metadata;
- preserves live SVG text;
- leaves ordinary SVG clipping in place.

The corresponding `--keep-*` options can retain each class of information when
a particular downstream editor benefits from it.

## Deliberately explicit destructive operations

Two candidate export operations are intentionally *not* guessed in this first
pass.

`--text paths` currently fails with an actionable error. Correct text outlining
requires font selection, shaping and glyph geometry; silently approximating it
would make the compatibility output less reliable than the editable master. Use
live text or explicitly convert text to paths in Inkscape until a shaping backend
is added.

`--knockout` also currently fails explicitly. PatchCreator already preserves
`overlap_policy: knockout` intent and reports pending knockout regions through
the validator, but physically removing covered lower geometry requires a
well-defined boolean/paint-order pass. The exporter does not silently destroy
master geometry or infer stitch semantics from visual SVG order.

This division is intentional: the compatibility SVG should be simpler for tools
such as PE-DESIGN while still being deterministic and reviewable.
