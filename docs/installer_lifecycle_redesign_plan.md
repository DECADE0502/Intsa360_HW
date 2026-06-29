# Insta360_HW Installer Lifecycle Redesign Plan

Goal: turn the current script bundle into a standard installable runtime with fast install, observable self-check, reliable update, and clean uninstall.

## Phase 1 Runtime Package Boundary

- Release/install directories contain runtime files only.
- User machines never run `npm install`, `vite build`, or `pip install` during install/update/start.
- Build-time scripts may still run frontend build on the developer machine.
- Add `install_manifest.json` to the release root so install, update, repair, and uninstall can reason from facts.
- Add one lifecycle status/log format for long-running actions.

## Phase 2 Self Check

- Backend exposes `/api/lifecycle/check`.
- Checks installation root, manifest, frontend assets, Python runtime, config, data directories, Cadence loader candidates, and update capability.
- Frontend displays checks in System Status.

## Phase 3 Install And Uninstall

- Inno installer copies release files and runs only lightweight initialization.
- `install.ps1` initializes config, data dirs, manifest, and Cadence loader.
- `uninstall.ps1` supports detach, keep-data uninstall, and full uninstall using manifest.

## Phase 4 Update

- Update uses a release package, not source zip.
- It downloads to staging, verifies manifest, backs up user data, swaps runtime files, restores data, self-checks, and restarts.

## Phase 5 Manager UI

- Platform UI has separate check, repair, update, detach, uninstall, and diagnostics actions.
- All long-running actions stream from lifecycle status/log.
