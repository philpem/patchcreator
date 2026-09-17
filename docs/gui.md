# Optional GUI editor

PatchCreator's GUI is an optional front end over the same YAML loader, scene graph, SVG renderer and embroidery validator used by the command-line tools. It does not maintain a separate GUI-only document model.

Install the optional Qt dependency:

```text
pip install -e '.[gui]'
```

Then start the editor with an existing design:

```text
patchcreator gui examples/basic-round-patch.yaml
```

or start with a small blank 80 mm round-patch document:

```text
patchcreator gui
```

`patchcreator-gui` remains available as a direct GUI launcher and accepts the same optional design path.

The GUI provides a YAML source editor, live SVG preview, render diagnostics, a read-only layer/element hierarchy, and Open/Save/Save As actions. Source edits are debounced before rendering. If an edit makes the document invalid, the diagnostics area shows the parser/render error while both the preview and hierarchy keep displaying the last valid document, so partially typed YAML does not make the visual reference disappear.

The hierarchy is derived afresh from the successfully parsed `DesignSpec`. It shows labels, component types, IDs, visibility and nested groups. Selecting an entry reports its identity/type/visibility in the status bar. It is intentionally read-only in this slice: later structured editing will modify the same YAML/session state rather than introducing a second GUI document model.

## Live embroidery validation

Use **View → Show validation overlay** (or `Ctrl+Shift+V`) to run the normal embroidery validator against the most recent successful render. The GUI resolves the design's normal machine/intent profile and document overrides, then passes those thresholds to the same in-memory validation engine used by the CLI validation code. No GUI-only embroidery limits are introduced.

When enabled, the preview is an ephemeral copy of the current SVG with the ordinary removable **PatchCreator Validation** overlay added. The underlying master render remains unchanged and the overlay is never written back into the YAML source. The diagnostics panel shows the profile, error/warning/info counts and individual structured findings.

This is the interactive equivalent of the existing file workflow:

```text
patchcreator check artwork.svg --debug-svg artwork-debug.svg
```

If a design does not select a profile containing validation thresholds, the GUI leaves the normal preview visible and reports that validation is unavailable. Likewise, a validation-specific failure does not discard an otherwise valid render. Invalid YAML preserves the previous valid validation view rather than attempting to validate a broken source edit.

Opening a file sets its directory as the design source directory before rendering, so relative reusable-asset references behave the same way as `patchcreator render`.

Qt is deliberately not a core dependency. Importing `patchcreator.gui` and using `PreviewSession` does not require PySide6; only launching the Qt application does. The top-level command dispatcher also imports the GUI launcher only when the `gui` command is selected, so ordinary CLI use does not load Qt. This keeps library/CLI installations lightweight and lets normal CI test the source/preview state independently of a desktop environment.

Future GUI work under issue #22 can add property editors, Cartesian/polar placement controls, click-through validation navigation and direct manipulation on top of the same YAML/session state.
