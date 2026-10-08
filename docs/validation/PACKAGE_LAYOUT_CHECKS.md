# Supporting-module layout checks

Fifteen internal modules moved from the root to `algorithms/support/`. App and CLI commands stay the same. Background workers launch with `python -m`; recovery checks the module, workspace, request path, PID and start tick. Existing numerical results were preserved.

- **79 tests passed** in both workspaces, including live package-worker recovery, request/workspace rejection and cancellation.
- Both reproduction entry points returned identical saved timing results.
- Browser Start processed all **1,423 camera frames and 419 Livox scans** from one shipped bag. Independent RPM values were unchanged.
- Live localization and completed scan previews rendered without browser errors; the 390 px layout had no page overflow.
- A second CLI run was blocked with exit 2. Folder processing launched its package child; cancellation stopped both processes without orphan workers.

Terminal progress can precede interpreter exit briefly; the final check waits for process exit. Verification runs are archived locally outside the published result library, leaving the single included example.

[Software checks](evidence/package-refactor/software_checks.log) · [Browser and worker checks](evidence/package-refactor/browser_checks.json) · [Live preview](evidence/package-refactor/live_worker.png) · [Scan preview](evidence/package-refactor/scan_preview.png).
