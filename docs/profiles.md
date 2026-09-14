# Embroidery profiles

PatchCreator keeps machine characteristics separate from design intent. The effective geometry profile for a document is assembled in this order:

1. machine profile;
2. design-intent profile;
3. document-local overrides.

Only values explicitly supplied by a later layer replace earlier values.

## Design file

```yaml
profile:
  machine: brother-innovis-750e
  intent: standard-patch
  overrides:
    minimum_gap: 0.8
```

The initial constraint vocabulary is:

```yaml
constraints:
  validation_enabled: true
  minimum_stroke_width: 0.6       # mm
  minimum_gap: 0.6                # mm
  minimum_feature_dimension: 0.8  # mm
  minimum_island_area: 1.5        # mm^2
```

These values describe vector-geometry checks. They are not stitch-plan settings and do not replace Ink/Stitch or PE-DESIGN.

## Built-in profiles

PatchCreator currently supplies:

- `brother-innovis-750e` — machine identity/profile; no unverified machine-specific geometry limits are imposed yet;
- `standard-patch` — an **experimental** initial set of conservative embroidery geometry heuristics;
- `display-art` — disables embroidery validation for artwork intended only for display.

The thresholds in `standard-patch` are deliberately marked experimental. They should be tuned from real stitch-outs and should not be treated as universal embroidery limits.

## Custom profiles

Profiles are ordinary YAML files. For example:

```yaml
name: my-small-patch
kind: intent
description: Limits established from my own stitch tests.
constraints:
  validation_enabled: true
  minimum_stroke_width: 0.7
  minimum_gap: 0.75
  minimum_feature_dimension: 1.0
  minimum_island_area: 2.0
```

Profile sources are loaded in increasing precedence:

1. built-in profiles;
2. the user profile directory (`$XDG_CONFIG_HOME/patchcreator/profiles`, normally `~/.config/patchcreator/profiles`);
3. directories in `PATCHCREATOR_PROFILE_PATH`;
4. explicit `--profile-path DIR` directories passed on the CLI.

A later profile with the same `kind` and `name` replaces the earlier definition. This makes it possible to tune a built-in profile locally without editing the installed package.

## CLI

List all available profiles:

```text
patchcreator profiles list
```

Inspect one profile:

```text
patchcreator profiles show intent standard-patch
```

Show the effective merged profile for a design:

```text
patchcreator profiles effective examples/basic-round-patch.yaml
```

Additional profile directories can be supplied to these commands using `--profile-path DIR`.
