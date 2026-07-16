# Git-Only OTA Design

## Goal

Publish signed Insta360_HW updates with credentials that only permit Git
`send-pack`. Publishing must not call the GitHub Releases API, depend on GitHub
Actions, or build anything on GitHub.

## Channel Layout

Use a dedicated `ota` branch with one parentless snapshot commit. The branch
contains the new stable version and the immediately previous stable version:

```text
channel/stable/update-manifest-v3.json
channel/stable/update-manifest.json
versions/<version>/Insta360_HW_Runtime_<version>.zip
versions/<version>/Insta360_HW_runtime_v<version>.zip
versions/<version>/Insta360_HW_Setup.exe
versions/<version>/update-manifest-v3.json
versions/<version>/update-manifest.json
versions/<version>/SHA256SUMS.txt
```

The stable manifest URL is:

```text
https://raw.githubusercontent.com/DECADE0502/Intsa360_HW/ota/channel/stable/update-manifest-v3.json
```

Signed asset URLs point at the versioned directory on the same branch. The
Ed25519 signature authenticates the manifest and the manifest authenticates the
runtime ZIP by exact size and SHA256.

## Publishing

The local release builder accepts an explicit HTTPS asset base URL and signs
that URL into both V3 and compatibility manifests. The Git-only publisher then:

1. requires a clean source worktree and a verified local release bundle;
2. reads the current remote `ota` snapshot, if one exists;
3. preserves only its current stable version as the previous version;
4. creates a new parentless snapshot containing previous plus new assets;
5. pushes with `--force-with-lease` against the exact observed remote SHA;
6. clones the resulting branch and byte-verifies every newly published file;
7. verifies the public raw stable manifest before reporting success.

The source checkout is never switched to the `ota` branch. Interrupted staging
is confined to a temporary directory. A failed push leaves the prior channel
untouched.

## Client Migration

New runtime defaults read the raw `ota` channel. An environment override remains
available for tests and emergency recovery. Existing installations that only
know the old Release URL require one manual Setup upgrade; all later releases
can use Git-only OTA.

## Error Handling

- Reject dirty source trees, unsigned or mismatched bundles, non-HTTPS asset
  URLs, version regressions, and remote branch races.
- Never force-push without an exact lease.
- Never report publication success until the remote branch and public stable
  manifest match the local signed bytes.
- Retain the previous stable version so a controlled rollback package remains
  available without retaining unbounded binary history.

## Verification

- Unit-test asset URL generation and manifest signatures.
- Integration-test first publication, second publication retention, third
  publication pruning, and stale lease rejection against a local bare Git repo.
- Run backend tests, frontend tests, production build, signed release build, and
  a real `ota` push before considering the channel usable.
