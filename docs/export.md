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

The master continues to keep text live and editable. When a downstream importer
needs font-independent artwork, use:

```text
patchcreator export mission.svg --text paths
```

Text-to-path export uses the installed Inkscape executable as the shaping and
outlining backend. This is intentional: Inkscape's Pango/font stack handles
kerning, glyph substitution and PatchCreator's live `<textPath>` layouts in the
same way the artist sees them in Inkscape, instead of PatchCreator approximating
font metrics itself. The conversion happens on a temporary copy; the master SVG
is never changed.

`fontconfig`'s `fc-match` command is used before conversion to resolve each
requested family/style/weight. A missing requested family therefore produces an
actionable error rather than silently changing the patch. Install the requested
font, add an installed fallback family to the SVG, or use the Python API with
`ExportOptions(allow_font_substitution=True)` when a deliberate substitution is
acceptable. Allowed substitutions and possible synthesized weight/slant choices
are returned as export warnings.

Inkscape and `fc-match` must both be on `PATH`. `PATCHCREATOR_INKSCAPE` and
`PATCHCREATOR_FC_MATCH` may be set to alternative executable names or paths when
needed. If no live text is present, `--text paths` is a no-op and does not require
those external programs.

Text-on-path construction geometry is deliberately removed *after* outlining,
so a curved title is first shaped in its final position and only then has its
hidden baseline discarded. The resulting compatibility SVG contains ordinary
editable path geometry and no live `<text>` elements.

Font outlining is only reproducible when the same font files and compatible
Inkscape/Pango versions are available. For archival or CI-sensitive workflows,
record the font family/style and environment used for the export; do not commit
font files to this repository merely to make an example self-contained.

This division is intentional: the compatibility SVG should be simpler for tools
such as PE-DESIGN while still being deterministic and reviewable.
