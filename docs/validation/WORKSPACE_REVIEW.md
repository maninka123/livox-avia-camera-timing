# Review after reorganisation

Current imports, launchers, documentation links and saved-result paths were reviewed together. The worker’s code snapshot now covers app/CLI and algorithm sources without traversing datasets, environment packages or verification evidence. Local calibration and method guides follow the new documentation layout. ROS setup no longer receives the app’s arguments, fixing launcher `--help` handling; explicit missing interpreter paths fail clearly.

- **84 tests passed** in both workspaces. New checks cover stale imports, broken guide links, code-snapshot scope, launcher arguments and missing Python environments.
- Both reproduction commands returned the same saved timing estimate and uncertainty.
- A real two-bag folder run completed **2,848 camera frames, 838 Livox scans and 20,112,000 input points**, with zero failures and at most one cloud worker active.
- Live detections, folder plots, capture reports and scan previews worked. Desktop and 390/320 px layouts passed without script errors.
- A concurrent CLI folder request was blocked. Worker processes exited, and the original example summary stayed byte-for-byte unchanged.

The two distributed bags have similar RPMs; the report correctly recommends additional speed variation for combined timing. The verification run is archived locally, leaving one published example.

[Tests](evidence/workspace-review/software_checks.log) · [Browser/folder checks](evidence/workspace-review/browser_checks.json) · [Reproduced timing](evidence/workspace-review/reproduced_timing.json) · [Folder results](evidence/workspace-review/folder_results.png).
