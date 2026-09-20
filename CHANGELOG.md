# Changelog

Notable changes to PatchCreator are documented in this file.

## Unreleased

- Restore physical stroke widths for borders, trajectories and Earth artwork;
  correct validation of viewport-sized non-scaling strokes (#115).
- Size decorative starfields against embroidery profiles and report adjustments
  to explicitly undersized glyphs (#116).
- Preserve live-text baselines during compatibility export (#121).
- Preserve inherited source SVG styling during reusable-asset import (#122).
- Correct Earth land/sea fill topology near equatorial and polar viewpoints (#123).
- Handle empty border lengths during live YAML editing without an uncaught
  GUI traceback (#124).

## [0.1.0] - 2026-09-18

PatchCreator 0.1.0 is the first release of the procedural,
embroidery-aware mission-patch compositor.

### Added

- Authoritative, versioned YAML documents shared by the library, CLI and
  optional PySide6 editor.
- Physical-millimetre geometry, patch/safe/custom clipping, layered scene
  graphs, and Cartesian, polar, anchor-relative and path-following placement.
- Procedural stars and starfields, orthographic Earth rendering, editable
  trajectories and orbits, curved/path text, and reusable SVG assets with
  semantic colour roles and anchors.
- Construction guides for curved-text baselines, occluded trajectory source
  paths and reusable-asset anchors.
- Embroidery profiles, independent geometry validation, visual diagnostic
  overlays, overlap diagnostics and physical knockout export.
- Editable, Inkscape-friendly master SVG output and conservative compatibility
  export with optional font-aware text outlining.
- Explicit Natural Earth dataset discovery and download; third-party dataset
  payloads are neither committed nor downloaded implicitly.
- Source and wheel artifact validation, packaged-data smoke tests, and CI on
  Python 3.11, 3.12 and 3.13.

### Release notes

- Install from the source archive or wheel attached to the GitHub release.
- Install the optional GUI dependencies with the `gui` extra.
- Fetch Natural Earth land data explicitly before rendering examples that use
  the Earth component.
- PatchCreator is licensed under the MIT Licence.

[0.1.0]: https://github.com/philpem/patchcreator/releases/tag/v0.1.0
