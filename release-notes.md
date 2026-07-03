0.2.27 phantom hotfix suppression — 2026-07-03

Installs updated by any earlier updater permanently reported a phantom revision hotfix: the updater stamped REVISION with the git head while check_update compares against the release-authored REVISION file. 0.2.27 keeps the payload's authored REVISION during updates, and check_update now consults install_manifest.json to recognize an already-current install and self-heal its REVISION stamp. Also carries the 0.2.26 packaging fix and all 0.2.25 reliability fixes.

## Highlights

- check_update no longer reports a phantom revision hotfix after a successful update: install_manifest.json (never rewritten by older updaters) confirms the installed release and the REVISION stamp self-heals.
- The updater keeps the release-authored REVISION delivered inside the payload instead of overwriting it with the resolved git head; the head is stamped only when the payload carries no REVISION.
- Release zips again wrap the runtime in a top-level HWAgent_release directory so the payload detector shipped on every installed version can locate it; 0.2.25's root-flat zip made OTA fail at 40% for all clients.
- Find-HwAgentUpdatePayloadRoot now also accepts a runtime unpacked at the extraction root, so a future packaging layout change cannot strand deployed updaters again.
- Plus all 0.2.25 reliability fixes (rollback completeness, no post-commit verify_all, revision hotfix delivery, reconnect on modern browsers, restart-window UX, interrupted-update quarantine, release-asset pre-flight checks).

## Integrity

| Asset | Size | SHA256 |
|---|---|---|
| `Insta360_HW_v0.2.27.zip` | 12,827,658 bytes | `da4525407b980316423384d904796680cb3bea986046a5d0c0618eec606a03f5` |

No data migration is required. Existing history, user plugins and local config are preserved.
