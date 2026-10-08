# Algorithms

```text
algorithms/
├── flir/       Camera photometry and periodic phase fitting
├── livox/      Cloud decoding, return features and phase fitting
└── support/    Shared processing and app support
```

`support/` contains bag I/O, calibration, target localization, sensor orchestration, timing, scan metrics, plots, reporting and worker management.

Each run records hashes of the app/CLI and algorithm sources. Documentation, test files, datasets and environment packages are excluded from that code snapshot; settings and bag provenance are saved separately.

The root keeps the user entry points: `app.py` and `process_bag.py`. The published repository also provides `reproduce_automatic.py` and `reproduce_reference.py` for the saved example. Launch commands stay the same. Internal workers run as `python -m algorithms.support.pipeline` or `python -m algorithms.support.batch_worker`, with a request JSON path; the app and CLI launch them automatically.
