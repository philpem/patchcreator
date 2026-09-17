# Initial GitHub Issue Backlog

> **Historical document.** This was the bootstrap implementation plan used to
> bring PatchCreator from an empty repository through the initial compositor,
> procedural components, validation/export pipeline and first GUI editor. All
> numbered items below have now been implemented and their corresponding GitHub
> issues closed. Keep this file as design history; use current GitHub issues for
> new roadmap work rather than treating this list as an active backlog.

Completed bootstrap milestones:

- **v0.1 Core scene/compositor**
- **v0.2 Procedural patch primitives**
- **v0.3 Embroidery-aware validation**
- **v0.4 Asset workflow and compatibility export**
- **Future: GUI editor**

Historical suggested labels: `architecture`, `cli`, `scene-graph`, `svg`, `inkscape`, `component`, `embroidery`, `validation`, `assets`, `documentation`, `future-gui`.

## 1. Create Python package and CLI skeleton

**Milestone:** v0.1

Create installable Python package and a CLI with initial subcommands:

```text
patchcreator render
patchcreator check
patchcreator normalize
patchcreator profiles
```

Acceptance criteria:

- package installs in editable mode;
- CLI has `--help`;
- unit-test framework configured;
- no compositor-specific logic is embedded in CLI handlers.

## 2. Define YAML design schema and loader

**Milestone:** v0.1

Implement human-editable YAML loading with schema/model validation and useful diagnostics including source locations where practical.

Acceptance criteria:

- versioned document root;
- units, canvas, profiles, palette and layer tree represented;
- invalid component/property errors are actionable;
- schema can later drive GUI property editing.

## 3. Implement scene graph core

**Milestone:** v0.1

Implement hierarchical nodes, stable IDs, groups/layers, transforms, bounds and anchors.

Acceptance criteria:

- arbitrary artist-defined hierarchy;
- traversal in visual paint order;
- nodes expose geometry/bounds/anchors after resolution.

## 4. Implement physical units and patch geometry

**Milestone:** v0.1

Use mm as canonical internal unit. Implement circular canvas/boundary and safe-area calculation.

Acceptance criteria:

- fixed safe margin;
- percentage safe margin;
- optional min/max clamps;
- correct geometry for 50/70/80/100 mm patches.

## 5. Implement placement system

**Milestone:** v0.1

Implement Cartesian, polar, relative/anchor and path-following placement.

Acceptance criteria:

- polar 0° is up and increases clockwise;
- local group origin/reference radius supported;
- self-anchor supported;
- path tangent orientation and normal offset supported.

## 6. Implement SVG writer with Inkscape metadata

**Milestone:** v0.1

Emit layered editable SVG with meaningful IDs and labels.

Acceptance criteria:

- Inkscape layers open correctly;
- Inkscape metadata can be disabled globally;
- simple generated SVG round-trips through Inkscape without visual change.

## 7. Implement clip policies and safe-area clipping

**Milestone:** v0.1

Per-node clip policy with design default.

Acceptance criteria:

- inherit/none/patch/safe-area/custom;
- local inset/outset;
- clip uses ordinary SVG clipPath;
- intended clip can remain recorded while disabled for overflow editing.

## 8. Implement profile system

**Milestone:** v0.1

Load built-in and custom machine/design-intent profiles and merge them deterministically.

Acceptance criteria:

- named built-in profile;
- user custom profile;
- machine + intent override layering;
- effective profile printable from CLI.

## 9. Implement star glyphs and deterministic starfield

**Milestone:** v0.2

Procedural decorative and semantic stars.

Acceptance criteria:

- several reusable glyph types;
- generated seed if absent, printed and embedded in metadata;
- annular-sector, rectangle and polygon regions;
- avoidance geometry and configurable clearance;
- deterministic output for a fixed seed.

## 10. Implement Earth globe/horizon component

**Milestone:** v0.2

Generate recognisable Earth geometry from accurate coastline data, projected and simplified for physical output size.

Acceptance criteria:

- configurable orthographic viewpoint;
- full globe and limb/horizon modes;
- sea/land paths;
- simplification varies with physical scale/profile;
- output remains editable SVG geometry.

## 11. Implement trajectories and procedural orbits

**Milestone:** v0.2

Support explicit Bézier paths plus procedural ellipse/orbit geometry.

Acceptance criteria:

- semantic stroke styling;
- under-stroke/halo;
- arrowheads/markers;
- path-following object placement;
- object-based 2D occlusion;
- procedural orbit can split front/back halves.

## 12. Implement curved text

**Milestone:** v0.2

Support live SVG text/textPath for top arc, bottom arc, arbitrary path and basic bands.

Acceptance criteria:

- automatic fitting/tracking;
- remains editable in Inkscape;
- explicit future hook for text-to-path/warp operations.

## 13. Implement reusable SVG asset loader and anchors

**Milestone:** v0.2

Load plain SVG assets, discover named PatchCreator anchors and expose semantic colour roles.

Acceptance criteria:

- hidden Inkscape anchor layer convention documented;
- anchor positions survive transform/scale;
- palette roles can override asset colours;
- derived colours supported.

## 14. Implement independent asset normaliser

**Milestone:** v0.4

`patchcreator normalize` should inspect and prepare hand-cleaned/traced SVG assets for reuse.

Acceptance criteria:

- report/fix viewBox;
- report bounds;
- optionally flatten safe transforms;
- list anchors and palette roles;
- preserve editable grouping where practical.

## 15. Geometry validator: minimum stroke width

**Milestone:** v0.3

Detect visible strokes below selected profile threshold and emit structured findings/debug overlay.

## 16. Geometry validator: small features and detached islands

**Milestone:** v0.3

Detect objects/components below minimum dimension/area thresholds.

## 17. Geometry validator: narrow gaps

**Milestone:** v0.3

Detect clearances likely to merge at embroidery scale.

## 18. Geometry validator: overlap diagnostics

**Milestone:** v0.3

Detect suspicious overlap between non-background elements and support overlap policies.

Acceptance criteria:

- report-only initially;
- procedural `avoid` is usable by starfields;
- future-compatible with compatibility-export knockout.

## 19. Visual validation/debug layer

**Milestone:** v0.3

Generate a top Inkscape layer that highlights validation findings in configurable colours.

Acceptance criteria:

- findings remain separate from artwork;
- layer can be hidden/deleted;
- CLI report links findings to object IDs.

## 20. Compatibility/export SVG pass

**Milestone:** v0.4

Generate a more conservative SVG variant intended for final Inkscape cleanup and downstream import.

Candidate operations:

- expand `<use>`;
- flatten selected transforms;
- optional overlap knockout;
- simplify clipping;
- strip Inkscape metadata;
- preserve or convert text according to export settings.

## 21. Example 80 mm mission patch

**Milestone:** v0.2

Create a regression/example design containing:

- circular border;
- safe margin;
- Earth;
- decorative starfield with exclusions;
- curved title;
- trajectory/orbit;
- path-following marker/object.

Use it as a golden-output test for SVG structure and layout.

## 22. Future GUI editor and live preview

**Milestone:** Future: GUI editor

Build a GUI on the same scene/config model, not a separate document representation.

Initial goals:

- live preview;
- layer tree;
- drag placement;
- Cartesian/polar editor;
- clip/safe-margin controls;
- validation overlay;
- seed lock/regenerate.
