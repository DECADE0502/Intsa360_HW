# Lifecycle V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the installation, OTA update, rollback, and uninstall chain with one manifest-driven transactional lifecycle system.

**Architecture:** The backend downloads and stages a complete runtime payload. A detached elevated PowerShell worker performs a same-volume directory swap with a durable journal and exact-instance health verification. Setup and uninstall are thin Inno owners; mutable state lives under LocalAppData and is never mixed with runtime files.

**Tech Stack:** Python standard library HTTP backend, PowerShell 5.1-compatible worker, C# .NET Framework launcher, Inno Setup 6, React/TypeScript frontend, pytest.

---

### Task 1: State and Release Contracts

**Files:**
- Create: `app/backend/app_paths.py`
- Create: `app/backend/release_manifest.py`
- Create: `tests/test_lifecycle_v2_contract.py`
- Modify: backend modules that currently address mutable state through the runtime root

- [ ] Add failing tests for installed and development state-root resolution.
- [ ] Add failing tests for strict release manifest parsing and SHA256 requirements.
- [ ] Implement the path and manifest value objects.
- [ ] Move data, local config, and user plugin consumers to the state-root contract.
- [ ] Run `python -m pytest tests/test_lifecycle_v2_contract.py -q`.

### Task 2: Transaction Worker

**Files:**
- Create: `scripts/lifecycle/Contract.ps1`
- Create: `scripts/lifecycle/Runtime.ps1`
- Create: `scripts/lifecycle/Worker.ps1`
- Create: `tests/test_lifecycle_v2_worker.py`

- [ ] Add tests for path refusal, journal writes, exact-instance matching, full candidate validation, directory switching, and fault injection.
- [ ] Implement atomic JSON state writes and named mutex ownership.
- [ ] Implement same-volume candidate construction and Inno file preservation.
- [ ] Implement journaled switch, verification, rollback, and restart.
- [ ] Run the worker tests and PowerShell parser checks.

### Task 3: Backend Update Orchestrator

**Files:**
- Create: `app/backend/lifecycle_update.py`
- Replace update responsibilities in: `app/backend/update_api.py`
- Modify: `app/backend/suite_app.py`
- Modify: `tests/test_update_api.py`

- [ ] Add tests for one-manifest checking, no source fallback, streamed download progress, cancellation, staging validation, worker launch, stale jobs, and recovered jobs.
- [ ] Implement the job state machine and byte-level progress.
- [ ] Keep diagnostics and Cadence repair APIs separate from OTA.
- [ ] Run update API and HTTP endpoint tests.

### Task 4: Installer and Uninstaller

**Files:**
- Replace: `HWAgent_Setup.iss`
- Replace: `install.ps1`
- Replace: `uninstall.ps1`
- Replace: `oneclick_install.ps1`, `oneclick_update.ps1`, `oneclick_uninstall.ps1`
- Modify: `tests/test_distribution_install.py`

- [ ] Add tests for idempotent install, legacy state migration, keep/purge uninstall, exact Cadence cleanup, and stable Inno finish behavior.
- [ ] Implement thin compatibility adapters to lifecycle V2.
- [ ] Remove the custom installer-as-uninstaller flow.
- [ ] Compile Setup and run install/uninstall sandbox tests.

### Task 5: Launcher and Cadence Integration

**Files:**
- Modify: `launcher/Insta360_HW.cs`
- Modify: `launch_tool_suite.ps1`
- Modify: `scripts/lib/Cadence.ps1`
- Modify: `cadence/iac_bom_tool.tcl`

- [ ] Add tests for installed state-root propagation, recovery-before-launch, exact health identity, and 16.6/17.4 loader rendering.
- [ ] Make the launcher run recovery before normal startup.
- [ ] Pass runtime and state roots explicitly.
- [ ] Render the Cadence loader with separate runtime and state roots.
- [ ] Build the launcher and run Cadence static/runtime checks.

### Task 6: Frontend Lifecycle UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Replace update interaction in: `frontend/src/components/UpdateStatus.tsx`
- Add: component tests for update state transitions

- [ ] Add tests for check/update separation, byte progress, pre-commit cancellation, reconnect, rollback failure, and completion dismissal.
- [ ] Render structured phases and errors without raw log parsing.
- [ ] Keep the progress modal above notices and visible through reconnect.
- [ ] Run frontend typecheck, tests, and production build.

### Task 7: Release Automation and End-to-End Verification

**Files:**
- Modify: `scripts/build_release.ps1`
- Replace: `scripts/publish_release.ps1`
- Create: `.github/workflows/release.yml`
- Modify: `scripts/pre_release_check.ps1`

- [ ] Produce a complete runtime ZIP and strict `update-manifest.json`.
- [ ] Publish runtime ZIP, manifest, and Setup from a Windows release workflow.
- [ ] Reject missing, unreachable, or mismatched assets before publishing.
- [ ] Run full pytest, frontend build, PowerShell parse, release build, Inno compilation, and a local install-update-rollback-uninstall scenario.

