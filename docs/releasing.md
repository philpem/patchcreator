# Releasing PatchCreator

PatchCreator releases are published on GitHub Releases only. The release
workflow does not upload to PyPI.

## Normal release flow

1. Merge the final release PR containing the version and changelog update.
2. Tag that merge commit using the matching `v<version>` tag.
3. Create and publish the GitHub Release for that tag.

Publishing the release starts the **Release artifacts** workflow. It checks out
the tag, confirms that it matches the version in `pyproject.toml`, builds and
validates the source and wheel distributions, smoke-tests the installed wheel,
generates `SHA256SUMS`, and attaches all three files to the release.

The upload uses `--clobber`, so rerunning the workflow replaces incomplete or
stale assets rather than creating duplicates.

## Populate an existing release

For a release which was published before the workflow existed, or to rebuild
its assets:

1. open **Actions → Release artifacts → Run workflow**;
2. enter the existing release tag, such as `v0.1.0`;
3. run the workflow from the default branch.

The workflow stops without uploading if the tag does not match the package
version.
