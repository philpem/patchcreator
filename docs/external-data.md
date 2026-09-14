# External data sources

PatchCreator may use third-party datasets for procedural components, but those dataset payloads are **not vendored into this repository**.

This is especially important for geographic data such as Natural Earth: the PatchCreator source tree should contain the code and a small source manifest, not copies of shapefiles, GeoJSON exports or downloaded archives.

## Policy

Third-party data used by procedural components should follow these rules:

1. The tracked repository contains only a small source declaration: name, URL, upstream version/identity, licence/terms link, attribution text, expected files and optionally a SHA-256 digest.
2. Payloads are fetched only by an explicit user action. Rendering must never trigger an implicit network download.
3. The default cache is outside the source checkout:
   - `$PATCHCREATOR_DATA_DIR` when set;
   - otherwise `$XDG_CACHE_HOME/patchcreator/data` when `XDG_CACHE_HOME` is set;
   - otherwise `~/.cache/patchcreator/data`.
4. A developer may point the cache into a checkout if desired; `.patchcreator-data/` is ignored for that use case.
5. A configured SHA-256 is checked before an archive is installed. Sources without a pinned digest still record the observed SHA-256 in their installation marker.
6. Downloads are staged and moved into place only after archive and required-file validation.
7. Unit tests use local synthetic fixtures and must not require Internet access.
8. Large upstream repositories should only be Git submodules when PatchCreator genuinely needs the repository structure/history. A small selected dataset is better represented as an explicit URL in the source manifest.

## CLI

List known datasets and whether they are installed:

```text
patchcreator data list
```

Fetch one explicitly:

```text
patchcreator data fetch natural-earth-land-110m
```

Find the installed path:

```text
patchcreator data path natural-earth-land-110m
```

Use `--data-dir DIR` on these commands for a one-off cache location. `--force` on `data fetch` replaces an existing/incomplete cached copy.

A procedural component that needs unavailable data should fail with an actionable message naming the corresponding `patchcreator data fetch ...` command. It must not call the downloader itself.

## Source manifest

Built-in sources are declared in `src/patchcreator/data/sources.yaml`. This file is package metadata, not data payload.

A source entry may declare:

```yaml
sources:
  example:
    description: Human readable description
    version: "1.2.3"
    url: https://example.invalid/data.zip
    homepage: https://example.invalid/
    licence: Public domain
    licence_url: https://example.invalid/terms
    attribution: Optional attribution text
    sha256: 012345... # optional but preferred when a stable archive is available
    archive: zip
    required_members:
      - data.shp
      - data.shx
      - data.dbf
```

The source manager stores a `.patchcreator-source.json` marker beside installed data containing the dataset identity, URL, version and observed archive SHA-256.

## Natural Earth

The initial Earth renderer is expected to use **Natural Earth 1:110m land polygons**, currently the `natural-earth-land-110m` source.

Source archive:

```text
https://naturalearth.s3.amazonaws.com/110m_physical/ne_110m_land.zip
```

Natural Earth describes this theme as land polygons including major islands. At the time the source entry was created, the 1:110m land theme was listed as version 4.0.0.

Natural Earth's terms state that its raster and vector map data are in the public domain and that attribution is not required. PatchCreator nevertheless records their suggested attribution text in the source manifest:

> Made with Natural Earth. Free vector and raster map data @ naturalearthdata.com.

Relevant upstream pages:

```text
https://www.naturalearthdata.com/downloads/110m-physical-vectors/110m-land/
https://www.naturalearthdata.com/about/terms-of-use/
```

The Earth renderer should consume the installed cache through `require_dataset("natural-earth-land-110m")`; it should never contain or generate a hidden fallback copy of the Natural Earth payload.
