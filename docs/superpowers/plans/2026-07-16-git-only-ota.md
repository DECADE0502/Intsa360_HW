# Git-Only OTA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace GitHub Release API publication with a signed OTA channel that is published solely through Git `send-pack`.

**Architecture:** Extend the deterministic bundle builder with an explicit asset base URL, add a focused Python Git publisher that owns snapshot staging and leased pushes, and point the runtime at the raw `ota` stable manifest. The publisher keeps only current and previous versions and verifies remote bytes before success.

**Tech Stack:** Python 3, PowerShell 5.1, Git CLI, Ed25519 signed JSON manifests, pytest.

---

### Task 1: Parameterize signed asset URLs

**Files:**
- Modify: `scripts/release/release_bundle.py`
- Modify: `scripts/build_release_bundle.ps1`
- Test: `tests/test_local_release_pipeline.py`

- [ ] Write a failing test that builds a bundle with a raw Git asset base and asserts every manifest URL uses it.
- [ ] Run `python -m pytest tests/test_local_release_pipeline.py -q` and confirm the new assertion fails.
- [ ] Add `asset_base_url` to `build_bundle` and the CLI, validate it as HTTPS without query/fragment, and pass the raw `ota/versions/<version>` URL from PowerShell.
- [ ] Re-run the focused test and confirm it passes.

### Task 2: Implement leased Git-only publication

**Files:**
- Create: `scripts/release/git_ota.py`
- Create: `scripts/publish_ota.ps1`
- Test: `tests/test_git_ota_publisher.py`

- [ ] Write local-bare-repository integration tests for first publish, current-plus-previous retention, third-version pruning, and stale lease refusal.
- [ ] Run `python -m pytest tests/test_git_ota_publisher.py -q` and confirm failure because the publisher is absent.
- [ ] Implement bundle validation, previous-version extraction, parentless snapshot creation, exact `--force-with-lease`, post-push clone verification, and optional public manifest verification.
- [ ] Add a PowerShell wrapper that supplies repository defaults and never reads an API token.
- [ ] Re-run publisher tests and confirm all cases pass.

### Task 3: Move clients to the Git channel

**Files:**
- Modify: `app/backend/lifecycle_v3.py`
- Modify: `config/default.json`
- Modify: `docs/UPDATE.md`
- Modify: `docs/RELEASE.md`
- Test: `tests/test_lifecycle_v3_service.py`
- Test: `tests/test_distribution_install.py`

- [ ] Write failing assertions for the raw stable manifest URL and the documented Setup migration boundary.
- [ ] Run the focused tests and confirm the old Release URL fails them.
- [ ] Replace both V3 and compatibility defaults with the `ota/channel/stable` raw URLs and document build/publish/recovery commands.
- [ ] Re-run focused tests and confirm they pass.

### Task 4: Release and end-to-end verification

**Files:**
- Modify: `VERSION`, `REVISION`, `UPDATE_NOTICE.json`, `HWAgent_Setup.iss` only if the release identity changes.

- [ ] Run focused publisher, lifecycle, distribution, and release-pipeline tests.
- [ ] Run `scripts/verify_all.ps1` and confirm backend, frontend unit, and production build checks pass.
- [ ] Commit and push `main`, then rebuild the signed bundle so its revision matches remote `main`.
- [ ] Run `scripts/publish_ota.ps1` and verify the remote `ota` SHA plus public signed manifest.
- [ ] Confirm the source worktree remains clean and no local installation was changed.
