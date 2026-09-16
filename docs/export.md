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

## Physical overlap knockout

`--knockout` makes an explicitly requested embroidery-oriented change to the
compatibility copy only:

```text
patchcreator export mission.svg --knockout
```

For overlaps where one object declares `overlap_policy: knockout` and the other
side is `allow` or `knockout`, PatchCreator follows SVG paint order and physically
subtracts later filled geometry from the earlier filled geometry. This removes
the hidden lower fill rather than merely relying on visual occlusion, reducing
the chance that a downstream digitiser stitches both layers.

The boolean operation is performed in physical millimetres using Shapely, then
the changed geometry is transformed back into the original object's local SVG
coordinate system and written as an ordinary editable even-odd `<path>`. Nested
transforms, compound paths, disconnected polygon components and multiple later
occluders are supported. A completely covered lower fragment is removed from the
compatibility copy.

Policy precedence remains explicit. `background` overlap is ignored as before;
`warn` and `avoid` continue to mean that the overlap should remain diagnostically
visible rather than being silently made acceptable because the other object says
`knockout`. Thus the destructive pass resolves `knockout`/`allow` and
`knockout`/`knockout` pairs, while suspicious `warn` or forbidden `avoid`
overlaps remain for validation and author review.

The first knockout pass handles visible filled `path`, `rect`, `circle`,
`ellipse`, `polygon` and `polyline` geometry. If a lower fragment that must be
changed also has a visible SVG stroke, export fails rather than changing stroke
semantics. Unsupported painted content such as live text or images is left
unchanged and reported through the export warnings; convert or restructure that
content before relying on knockout around it. The editable master is never
modified.

## Text outlining

`--text paths` still fails with an actionable error. Correct text outlining
requires font selection, shaping and glyph geometry; silently approximating it
would make the compatibility output less reliable than the editable master. Use
live text or explicitly convert text to paths in Inkscape until the font-aware
export backend is added.

This division is intentional: the compatibility SVG should be simpler for tools
such as PE-DESIGN while still being deterministic and reviewable.
