0.2.26 OTA payload packaging hotfix — 2026-07-02

This release supersedes 0.2.25, whose release zip packed the runtime at the archive root — a layout no deployed updater could consume, so every OTA attempt failed at 40% before touching the installed tree. 0.2.26 restores the HWAgent_release wrapper inside the zip, teaches the payload detector to accept both layouts, and carries all 0.2.25 reliability fixes.

## Highlights

- Release zips again wrap the runtime in a top-level HWAgent_release directory so the payload detector shipped on every installed version can locate it; 0.2.25's root-flat zip made OTA fail at 40% for all clients.
- Find-HwAgentUpdatePayloadRoot now also accepts a runtime unpacked at the extraction root, so a future packaging layout change cannot strand deployed updaters again.
- Rollback backup and restore now include app/frontend and every packaged runtime dir. Dev-only exclude names (frontend/tests/docs/launcher) are anchored as absolute paths so /XD no longer eats packaged directories at deeper levels.
- OTA no longer runs verify_all: verification used to fire after the rollback transaction committed, so a failure could only strand the tree as FAILED without restarting the service.
- Revision-only hotfixes now reach installed runtimes; check_update no longer requires local .git for the ancestor check, which meant hotfixes were silently invisible to every real user.
- Reconnect from the offline banner now works on Chrome 90+ / Firefox by using a top-level navigation instead of a hidden iframe.
- Update-in-progress modal explains the backend-restart window instead of stalling at the last known progress, and auto-reloads once the update finishes.
- Interrupted update transactions that fail to roll back are quarantined so a bad pending file no longer blocks every subsequent launch.
- pre_release_check.ps1 now HEAD-requests every UPDATE_NOTICE asset URL and diffs highlights against the previous release; publish_release.ps1 verifies the just-uploaded asset resolves anonymously before returning success.

## Integrity

| Asset | Size | SHA256 |
|---|---|---|
| `Insta360_HW_v0.2.26.zip` | 12,826,940 bytes | `b22311af80f3f6b0efd4ab99efbda24d3c4d5d2c19c0bb7ecb19668f2180efd3` |

No data migration is required. Existing history, user plugins and local config are preserved.
