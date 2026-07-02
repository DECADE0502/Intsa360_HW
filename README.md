# release-assets (orphan branch)

Staging area for GitHub Release publication in a send-pack-only environment.
No PAT/API access is available on the dev machine, so releases are published by
`.github/workflows/publish-release.yml` running GitHub-side.

To publish a release:

1. Build the zip locally and confirm its sha256 matches `UPDATE_NOTICE.json` on
   the release commit (`scripts/pre_release_check.ps1` gates this).
2. Push the release tag first: `git push origin vX.Y.Z`.
3. On this branch, replace the zip, update `release-manifest.json` and
   `release-notes.md`, commit, and `git push origin release-assets`.
4. The workflow verifies sha256 + size, creates the Release on the existing
   tag, uploads the asset, and polls the anonymous download URL until 200.

This branch shares no history with `main`; installed clients never read it
(update_api.py pins every fetch to ref=main).
