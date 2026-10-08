# Validation records

| Record | What it checks |
|---|---|
| [Publication](PUBLICATION_CHECKS.md) | How to run checks in a clean checkout |
| [App audit](APP_AUDIT.md) | App, CLI, worker recovery and actual-bag processing |
| [Example cleanup](EXAMPLE_CLEANUP.md) | Single example, concise tables and 77 passing tests |
| [Automatic camera](AUTOMATIC_CAMERA_CHECKS.md) | Camera wheel discovery and LiDAR guidance |
| [Automatic LiDAR](AUTOMATIC_CHECKS.md) | Target search, fallback and measured results |
| [Readability](READABILITY_CHECKS.md) | Text, figure sizing and mobile layouts |
| [Scan angles](SCAN_ANGLE_CHECKS.md) | Wrapped orientation and accumulated rotation |
| [Timing illustration](TIMING_ILLUSTRATION_CHECKS.md) | Calculated offset, signs and exported diagrams |
| [Timing wording](TIMING_COPY_CHECKS.md) | Labels and result explanations |

`evidence/` holds the screenshots, test logs and machine-readable checks linked by these records. `reference/` holds the publication manifest and capture metadata; `reproduce_automatic.py` uses its `published_automatic.json` to refit the included example.

[Historical workspace validation](WORKSPACE_VALIDATION.md) describes an earlier archived run. Older evidence and scripts record the app at that stage and may refer to archived result IDs; use the publication checks above for the current checkout.
