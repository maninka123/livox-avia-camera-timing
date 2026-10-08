# Saved results

This folder includes **one Device 1 example**, with results from ten recordings. The two raw example bags are in [`bagfiles/device_1/`](../bagfiles/device_1/); `captures/` stores processed results, not additional bags.

Start with the [overall report](batch_device_1_20261007T064645Z_f2b206cc/REPORT.md), or open **Device 1 · example** in the app’s **Saved results**.

```text
results/
└── batch_device_1_…/         Whole-folder results
    ├── REPORT.md            Overall findings
    ├── capture_metrics.csv  One summary row per bag
    ├── figures/             Comparisons across recordings
    ├── timing/              Combined offset and uncertainty
    └── captures/
        ├── rig_…/           Results for one bag
        └── …                Ten individual captures
```

Each folder inside [`captures/`](batch_device_1_20261007T064645Z_f2b206cc/captures/) contains:

| Folder / file | What to inspect |
|---|---|
| `REPORT.md`, `report.html` | That bag’s findings |
| `flir/`, `livox/` | Independent angles, RPM and fitted models |
| `scans/` | Individual Livox scan measurements |
| `intermediates/`, `figures/` | Detection previews and plots |
| `localization/` | Target position and search evidence |
| `timing/` | That bag’s timing fit and paired detections |
| `request.json`, `metadata.json` | Processing settings and recorded topics |

The individual folders and combined files serve different purposes: per-bag detection results versus comparisons and overall timing. Top-level `all_*.csv` files combine measurements from those captures for convenient export.

New single-bag runs create their own `rig_…` folder; whole-folder runs create a `batch_…` folder. Names include the UTC start time and a unique ID, so reprocessing preserves earlier results. New runs remain local unless explicitly published. Fetch Git LFS data to inspect saved arrays.
