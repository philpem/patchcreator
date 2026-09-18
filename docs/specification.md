# PatchCreator Design Specification

Status: Version 0.1

PatchCreator is a Python library and command-line tool for constructing layered, editable, mission-patch-style SVG artwork from procedural elements and reusable SVG assets. The generated master artwork is intended to be refined in Inkscape and then exported for embroidery workflows such as Brother PE-DESIGN or Ink/Stitch/PES.

The project deliberately targets patch-like vector composition rather than general-purpose vector illustration.

## 1. Goals

PatchCreator shall:

- provide a Python library as the primary API;
- provide a CLI built on the same library;
- use a human-editable declarative design format, initially YAML;
- use real physical dimensions, with millimetres as the canonical internal unit;
- generate layered, editable SVG with Inkscape-friendly metadata;
- generate embroidery-safe master artwork by default, with safety checks and corrections configurable or disableable;
- optionally generate a simplified/compatibility SVG for downstream import;
- support procedural elements such as patch boundaries, borders, Earth, stars/starfields, trajectories/orbits and curved text;
- support reusable SVG assets with anchors and recolourable semantic colour roles;
- support Cartesian, polar, relative/anchor and path-following placement;
- support compositing, clipping and occlusion without requiring a general 3D scene engine;
- support validation and visual debug overlays for geometry likely to embroider poorly;
- be extensible with third-party procedural components without modifying the core package;
- provide an optional GUI editor with live preview on the same declarative model.

## 2. Non-goals

PatchCreator is not intended to:

- replace Inkscape as a vector editor;
- generate stitch plans or replace Ink/Stitch/PE-DESIGN;
- provide a general 3D renderer;
- provide a general GIS editor;
- automatically trace character artwork from raster images.

## 3. Typical physical sizes

The expected standard patch diameters are:

- 70 mm and 80 mm: normal designs;
- 50 mm: unusually simple designs;
- 100 mm: unusually complex designs.

All geometry and embroidery-safety decisions shall be evaluated in physical units, not display pixels.

## 4. Declarative design format

YAML is the initial authoring format. JSON may be used internally for schema tooling but shall not be the preferred human-authored representation.

A machine-readable JSON Schema shall be derived from the same Pydantic models used by the loader rather than maintained separately. It is available through `patchcreator schema` (or `patchcreator schema -o FILE`) for editor/tooling integration. Because component implementations and plugins extend the common element envelope dynamically, component-specific extra fields remain open in the structural JSON Schema and receive their semantic validation through the normal loader/component pipeline.

Example skeleton:

```yaml
version: 0.1
units: mm

canvas:
  shape: circle
  diameter: 80
  safe_margin:
    fixed: 3

profile:
  machine: brother-innovis-750e
  intent: standard-patch

palette:
  border: "#ffc928"
  space: "#000000"
  blue: "#08a7ed"
  blue_light:
    from: blue
    lighten: 0.30

layers:
  - id: background
    label: Background
    elements: []

  - id: artwork
    label: Artwork
    elements: []
```

## 5. Scene graph

The internal representation shall be a scene graph. Artist-defined hierarchy determines ordinary compositing order. PatchCreator may add generated groups/layers for:

- patch boundary and border;
- text;
- construction guides;
- debug/validation overlays;
- compatibility/export transformations.

Every scene node shall have a stable ID where possible. Generated SVG groups should use meaningful IDs and Inkscape labels.

## 6. Coordinate and placement systems

### 6.1 Cartesian placement

Cartesian positions are measured from the current reference origin, normally the patch centre.

```yaml
position:
  mode: cartesian
  x: 8
  y: -14
```

Positive X is right. Positive Y follows SVG convention internally, but the authoring API should document a consistent artist-facing convention and perform conversion where necessary.

### 6.2 Polar placement

Polar coordinates use:

- 0 degrees at the top;
- increasing angle clockwise;
- radius measured from the current reference centre;
- default reference radius equal to patch radius.

Radius may be specified in millimetres or as a fraction of the reference radius.

```yaml
position:
  mode: polar
  angle: 135deg
  radius: 0.72r
```

Groups may define a local polar origin and reference radius, allowing constellations and similar grouped structures to use their own coordinate system.

### 6.3 Relative and anchor placement

Objects may be placed relative to:

- another object's origin;
- another object's named anchor;
- a group origin;
- a patch/global named guide.

The placed object also has a self-anchor, e.g. centre, nose, eye, tail-tip, baseline-centre.

```yaml
position:
  mode: relative
  target: dragon-blue.anchor:nose
  self_anchor: centre
  offset: [2, -1]
```

### 6.4 Path-following placement

Objects may be positioned by fraction or physical distance along a named path.

```yaml
position:
  mode: path
  path: orbit-main
  at: 0.35
  orient: tangent
  normal_offset: 1.5
```

The system should expose path tangent and normal so an object may follow an orbit or trajectory naturally.

## 7. Patch boundary and safe area

The patch boundary is a first-class object. Initial patch shapes should include at least circle and ellipse; later shapes may include shields, polygons and arbitrary SVG paths.

The design safe margin is also first-class and may be defined as:

```yaml
safe_margin:
  fixed: 3
```

or:

```yaml
safe_margin:
  percent: 5
  min: 2
  max: 5
```

`min` and `max` are optional clamps in millimetres.

## 8. Clip policy

Every element has a clip policy. A design-level default applies unless overridden.

Initial policies:

- `inherit`
- `none`
- `patch`
- `safe-area`
- `custom:<id>`

A clip may also have a local inset/outset.

PatchCreator shall prefer normal SVG `<clipPath>` constructs so that clips remain reversible/editable in Inkscape. The SVG should preserve enough metadata to identify the intended clip even when application is disabled for visible-overflow editing.

Example:

```yaml
clip:
  target: safe-area
  enabled: true
  inset: 0
```

The author may disable application while retaining the intended clip metadata:

```yaml
clip:
  target: safe-area
  enabled: false
```

## 9. Compositing and embroidery overlap

Visual SVG occlusion does not guarantee embroidery safety: an object hidden by a later object may still be stitched beneath it.

PatchCreator shall therefore distinguish visual paint order from embroidery-overlap policy.

Candidate policies:

- `allow`: ordinary SVG overlap is permitted;
- `warn`: overlap is allowed but reported;
- `avoid`: procedural placement must avoid occupied geometry;
- `knockout`: covered lower geometry is removed or excluded in compatibility output;
- `background`: element is treated as background for overlap diagnostics.

The initial validator shall at minimum detect suspicious overlap between non-background elements. Hidden decorative geometry beneath later artwork should be discouraged because it may produce excessive stitch density or lumps.

Procedural starfields should normally be generated after avoidance geometry is known rather than relying on later visual occlusion.

## 10. Occlusion for trajectories and orbits

A general 3D scene is not required.

### 10.1 Generic trajectory occlusion

A trajectory may name 2D occluders. The trajectory is rendered only outside their visible silhouette, using masks/clips or path splitting.

```yaml
occlusion:
  behind:
    - earth
  gap: 0.6
```

The optional gap creates visual/stitch clearance around the occluding object.

### 10.2 Procedural orbits

Procedural orbital components may internally use a limited pseudo-3D representation such as inclination, node and phase in order to determine front/back path segments around a spherical body. This is an implementation detail of the orbit component and does not create a general 3D scene model.

Orbits should support:

- full visible ellipse;
- front/back splitting around an occluder;
- configurable under-stroke/halo or clearance;
- markers or placed objects along the path.

## 11. Reusable SVG assets

Reusable artwork shall remain ordinary SVG wherever possible.

Assets may define semantic anchors using ordinary SVG objects in a hidden Inkscape layer, for example objects carrying:

```xml
<data-patchcreator-anchor="nose" />
```

The exact convention shall be documented so an artist can add, move or rename anchors using Inkscape.

Assets should support semantic colour roles such as:

- `outline`
- `primary`
- `secondary`
- `highlight`
- `shadow`
- `eye`

Derived palette colours shall be supported, for example "primary, 30% lighter".

The normalisation workflow should be a separate reusable tool rather than hidden inside composition.

## 12. Earth generation

Earth shall be recognisable and geographically accurate enough that visible continents are not symbolic inventions.

Source geometry should come from real coastline/land data, then be simplified according to physical output scale and profile constraints.

### 12.1 External geographic data

Third-party geographic datasets shall not be vendored into the PatchCreator repository. The repository may contain only a small source manifest with URLs, upstream identity/version, expected files, licence/attribution information and optional checksums.

Dataset acquisition is explicit. Rendering must never silently download a missing dataset. Components requiring external data shall use the shared data-cache API and produce an actionable diagnostic such as:

```text
patchcreator data fetch natural-earth-land-110m
```

The default cache shall be outside the checkout, following `PATCHCREATOR_DATA_DIR`, then `XDG_CACHE_HOME`, then `~/.cache/patchcreator/data`. Unit tests shall use local synthetic fixtures and shall not require network access.

For the initial Earth component, Natural Earth 1:110m land polygons are the preferred source because this scale is appropriate to small world maps. Higher-detail Natural Earth scales may be added later if testing demonstrates useful retained detail on larger patches. See `docs/external-data.md` for the complete acquisition and attribution policy.

Initial render modes should include:

- full orthographic globe;
- Earth limb/horizon;
- flat land/sea colour;
- outline continents;
- latitude/longitude grid;
- day/night terminator;
- cloud bands;
- atmosphere rim.

Simplification should preserve recognisable geography while eliminating detail that cannot survive at patch scale.

## 13. Stars and starfields

Decorative stars and semantic stars are distinct concepts.

### 13.1 Decorative starfields

Random starfields shall be deterministic for a fixed seed.

If no seed is supplied:

- generate one;
- print/report it to the user;
- embed it in generated SVG metadata;
- allow the user to copy it back into YAML to reproduce the layout.

Starfield regions should support at least:

- annular/circular sectors using inner/outer radius and start/end angle;
- rectangles;
- arbitrary polygons;
- custom path/region references later.

Starfields shall support avoidance regions with configurable clearance.

### 13.2 Semantic stars

Explicit stars may be deliberately positioned and counted for mission symbolism. They should use reusable star glyphs rather than random-starfield placement.

Initial glyph library should include several mission-patch-appropriate dots and four/five/eight-point forms.

## 14. Trajectories and path styling

Trajectory components shall support both:

- procedural paths such as ellipses/orbits;
- explicitly authored/editable Bézier paths.

Semantic styling should include, where sensible:

- stroke colour/width;
- solid/dashed/dotted treatment;
- arrowheads;
- markers/waypoints;
- under-stroke or contrasting halo/border;
- foreground/background path splitting;
- path-following placement.

## 15. Text and typography

Text should remain live SVG text where practical, including `<textPath>` for curved text.

Initial layouts should include:

- top arc;
- bottom arc;
- arbitrary path;
- upper/lower bands;
- straight motto/banner layouts.

Automatic fitting/tracking should provide a usable starting point while remaining editable in Inkscape.

Warped/deformed text may be converted to paths when necessary. Final text-to-path conversion is expected to occur during Inkscape cleanup/export unless a dedicated export mode performs it later.

## 16. Embroidery profiles

Embroidery constraints shall be profile-driven.

A profile may be assembled from:

1. a machine/profile baseline, e.g. `brother-innovis-750e`;
2. a design-intent override, e.g. `standard-patch`, `small-patch`, `display-art`;
3. document-local overrides.

Candidate parameters include:

```yaml
minimum_stroke_width: 0.6
minimum_gap: 0.6
minimum_feature_dimension: 0.8
minimum_island_area: 1.5
```

Exact defaults require testing rather than being hard-coded as universal embroidery truths.

Profiles shall be loadable from built-in global defaults and from user-defined/custom profile files.

## 17. Geometry validation and correction

Initial validation priorities are:

1. strokes/lines too thin;
2. shapes/features too small;
3. gaps too narrow;
4. detached islands too small;
5. suspicious overlap between non-background objects.

The validator shall support:

- report-only mode;
- automatic correction where a safe deterministic correction exists;
- configurable disable/override;
- a generated top debug layer highlighting findings in contrasting or user-selected colours.

Later work may add stitchability heuristics such as sharp spikes, excessive satin widths and stitch-density estimation.

The validation subsystem should be callable independently on imported SVG, e.g. conceptually:

```text
patchcreator check artwork.svg
```

## 18. Inkscape integration

Inkscape is the primary manual editing environment.

Generated master SVG should therefore support as much useful Inkscape structure as practical:

- labelled layers/groups;
- meaningful object IDs;
- guides and construction geometry;
- hidden/debug layers;
- ordinary reversible clip paths;
- editable live text;
- metadata describing generated objects and seeds.

Inkscape-specific metadata shall have a global off-switch for users who require cleaner generic SVG.

## 19. Construction guides

When `settings.construction_guides` is enabled, PatchCreator emits a dedicated
top Inkscape layer labelled **PatchCreator Construction**. The generic guide
layer currently includes:

- patch centre marker;
- horizontal/vertical axes;
- safe-area boundary;
- patch boundary/radius.

Construction geometry is ordinary editable SVG tagged with
`patchcreator:construction-role`. It is authoring-only: it does not enter the
scene graph or artwork bounds, the validator ignores it, and the default
compatibility export removes it.

Component-specific construction guides currently include:

- curved-text baselines;
- retained pre-occlusion trajectory/orbit source paths;
- reusable-asset semantic anchors.

Object/reference-origin markers and additional component-specific guides may be
added later where they improve authoring without affecting the rendered artwork.

## 20. SVG outputs

### 20.1 Master SVG

The default master SVG shall be:

- layered and editable;
- already embroidery-safe according to the selected profile unless safety filtering is disabled;
- Inkscape-friendly;
- structurally clear rather than aggressively optimised.

### 20.2 Compatibility/export SVG

An optional second SVG may apply more destructive operations for compatibility, such as:

- expand `<use>` references;
- flatten selected transforms;
- apply overlap knockouts;
- simplify clipping;
- remove construction/debug metadata;
- optionally convert text when appropriate.

Inkscape remains the preferred final optimisation/export step.

## 21. Extensibility

Third-party procedural components must be loadable without editing core dispatcher code.

A Python entry-point-based plugin mechanism is preferred, with a stable component registration API.

## 22. CLI direction

Initial commands are expected to resemble:

```text
patchcreator render design.yaml
patchcreator check artwork.svg
patchcreator normalize asset.svg
patchcreator profiles list
patchcreator data list
patchcreator data fetch natural-earth-land-110m
```

The CLI must be a thin layer over the Python library. External-data commands are explicit user actions; render/check operations shall not trigger downloads implicitly.

## 23. GUI editor

The optional GUI uses the same declarative YAML model, scene graph, renderer and
validator rather than introducing a second internal representation.

The initial GUI implementation includes:

- live SVG preview with last-valid-preview behaviour during invalid edits;
- layer/object hierarchy;
- drag placement for default/Cartesian/polar objects in the default patch frame;
- structured Cartesian and polar coordinate controls;
- safe-margin and clipping controls;
- starfield regenerate/seed-lock controls;
- live validation overlay and issue list;
- Open/Save/Save As over the human-authored YAML source.

Structured GUI edits round-trip the YAML and then re-enter the normal
parse/render pipeline. The GUI does not maintain a hidden authoritative scene
copy.

Future enhancements may include anchor/path-placement property editors,
click-through navigation between validation findings and objects, richer palette
and semantic-role editing, and direct manipulation for non-default coordinate
frames.

## 24. Initial end-to-end demonstrator

The first useful integration target should render an 80 mm round patch from YAML containing:

- circular boundary and border;
- safe area;
- simplified accurate Earth;
- deterministic decorative starfield with exclusions;
- curved live text;
- a trajectory/orbit;
- a marker/object positioned on the path;
- Inkscape-labelled layers and optional construction guides.

This should become a regression example/golden-output test for the system.
