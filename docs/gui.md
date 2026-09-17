# Optional GUI editor

PatchCreator's GUI is an optional front end over the same YAML loader, scene graph and SVG renderer used by the command-line tools. It does not maintain a separate GUI-only document model.

Install the optional Qt dependency:

```text
pip install -e '.[gui]'
```

Then start the editor with an existing design:

```text
patchcreator-gui examples/basic-round-patch.yaml
```

or start with a small blank 80 mm round-patch document:

```text
patchcreator-gui
```

The first GUI slice provides a YAML source editor, live SVG preview, render diagnostics, and Open/Save/Save As actions. Source edits are debounced before rendering. If an edit makes the document invalid, the diagnostics area shows the parser/render error while the preview keeps displaying the last valid render, so partially typed YAML does not make the visual reference disappear.

Opening a file sets its directory as the design source directory before rendering, so relative reusable-asset references behave the same way as `patchcreator render`.

Qt is deliberately not a core dependency. Importing `patchcreator.gui` and using `PreviewSession` does not require PySide6; only launching the Qt application does. This keeps library/CLI installations lightweight and lets normal CI test the source/preview state independently of a desktop environment.

Future GUI work under issue #22 will layer structured controls such as a scene/layer tree, property editors, Cartesian/polar placement controls, validation overlays and direct manipulation on top of the same YAML/session state.
