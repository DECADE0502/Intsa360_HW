# Insta360_HW Lifecycle V2 Design

## Purpose

Replace the existing install, update, rollback, and uninstall implementation as one coherent lifecycle system. The old update library, source-ZIP fallback, port-wide process killing, and install-tree overlay behavior are not part of V2.

## User Contract

- `Insta360_HW_Setup.exe` is the only installer and Windows uninstaller owner.
- `Insta360_HW.exe` is the only visible application entry after installation.
- The platform exposes separate **Check for updates** and **Install update** actions.
- An update always shows download, verification, staging, switching, restart, and final status.
- Cancellation is allowed before the commit phase. Commit is short and cannot be cancelled.
- User data, local settings, history, outputs, and user plugins survive upgrade and normal uninstall.
- A full-data removal choice is offered by the Windows uninstaller.
- Cadence integration is idempotently installed, repairable, removable, and removed during uninstall without touching third-party scripts.
- Cadence 16.6 and 17.4 use the same generated GBK loader and discovery contract.

## Directory Model

Runtime files are immutable and live under the selected installation directory, normally:

```
C:\Program Files\Insta360\HWAgent
```

Mutable state lives outside Program Files:

```
%LOCALAPPDATA%\Insta360_HW
  data\
  config\local.json
  plugins\user\
  logs\
  lifecycle\
    jobs\
    transactions\
    cache\
```

Development checkouts keep the legacy in-tree state location unless `INSTA360_HW_STATE_ROOT` is set. Installed launchers always set it.

## Release Contract

Production updates consume a complete runtime ZIP and a schema-versioned manifest. They never consume a GitHub source archive.

The stable metadata URL is:

```
https://github.com/DECADE0502/Intsa360_HW/releases/latest/download/update-manifest.json
```

The manifest contains product, schema, version, revision, release notes, minimum launcher version, runtime asset URL, byte size, and SHA256. Missing or invalid integrity metadata makes the release non-installable.

## Update State Machine

1. `checking`: fetch and validate one remote manifest.
2. `downloading`: stream the runtime ZIP into the lifecycle cache and report bytes, speed, and percent.
3. `verifying`: verify size and SHA256.
4. `staging`: extract into a transaction directory and validate the payload manifest and required runtime files.
5. `awaiting_elevation`: launch the detached worker through UAC.
6. `committing`: acquire the global lifecycle mutex, stop only the registered HWAgent instance, prepare a same-volume candidate, preserve Inno uninstall files, and journal every transition.
7. `switching`: rename the old installation to a backup, then rename the complete candidate into place.
8. `integrating`: deploy the generated Cadence loader only when integration is enabled.
9. `verifying_runtime`: start the exact new runtime and require product, root, version, and instance token to match.
10. `completed`: remove backup and cache after verification.

Any failure after commit begins restores the previous directory, Cadence snapshot, and service. Recovery is journal-driven and idempotent after process termination or reboot.

## Install State Machine

Setup validates the complete release before modifying an existing installation. It stops the registered instance, migrates legacy mutable state once, replaces runtime-owned paths, writes the install identity, deploys Cadence integration, and launches the platform only after post-install verification succeeds.

Reinstall and upgrade use the same path. There is no separate custom pseudo-uninstaller inside Setup.

## Uninstall State Machine

The Windows/Inno uninstaller asks whether to preserve user data. Its cleanup action stops the exact registered runtime, removes only loader files carrying the Insta360 marker, restores any third-party script archives owned by the platform, removes protocol/shortcut integration, and writes progress to the uninstaller. Inno then removes the installation directory. The finish page remains visible until the user clicks Finish.

## Safety Rules

- Every destructive path must resolve to a verified product root and must not be a drive root, Program Files root, user profile root, or state root parent.
- Never stop a process based on port alone. Match PID, executable, root identity, and health token.
- Never overwrite a live runtime tree file by file.
- Never declare success before the new service reports the expected product, root, version, and instance token.
- Never delete or replace unknown Cadence scripts.
- Never use a source ZIP in production.
- One lifecycle operation may run at a time through a named global mutex.

## Compatibility Bridge

Top-level `install.ps1`, `update.ps1`, and `uninstall.ps1` remain as small command adapters because 0.2.x installers and installed runtimes call those names. They contain no lifecycle logic and delegate to V2. The bridge is removed only after the supported installed base has crossed to V2.

## Acceptance

- Clean install, reinstall, update, interrupted update recovery, rollback, keep-data uninstall, purge uninstall, and Cadence repair each have automated tests.
- A fault can be injected before and after each commit journal transition.
- Frontend update controls are driven only by structured job state.
- Full Python tests, frontend typecheck/build, PowerShell parsing, release build, and Inno compilation pass.

