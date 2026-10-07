# App guide

## Start and select data

Run `bash setup.sh` once, then `bash launch.sh`. ROS Noetic must be sourced and compatible with the Python interpreter. The local virtual environment retains ROS system packages. `STUDIO_BASE_PYTHON` selects the setup interpreter; `STUDIO_PYTHON` selects an already configured runtime interpreter.

Device 1 contains two example bags. Device 2–5 are empty destinations for additional recordings. Import into the selected device, or copy `.bag` files into its directory. Inspect message types/counts before processing; automatic selection prefers camera Image and Livox PointCloud2 topics. Manual selection remains available.

The shipped camera crop is `[235, 150, 110, 110]`. Use the full-frame preview and acquisition controls when the target occupies another location. Review the setup group before timing comparisons: captures within a group must share sensor pose and phase convention. The normal/red filename suggestions apply only to these recordings.

## Processing and results

Choose one bag or the entire device folder. The app displays stages, processed/remaining counts, elapsed time, live measured previews and angle traces. Each run saves a new directory. Folder runs isolate failures and continue with other bags. Cancellation preserves completed captures and partial artifacts. Restarting the server reconnects to matching live workers.

The result view has detection/quality/timing plots and a scan browser. Every cloud is available with input/retained point counts, relative angle, local RPM, depth spread and quality flags. Local RPM and optional LiDAR smoothing are offline quantities using future observations.

Saved reference results cover all ten original Device 1 captures. Eight source bags are absent from this distribution; their saved arrays, models, angles and scan tables remain available. The included batch is complete and its reports can be viewed immediately. Running the two examples creates a new two-capture batch, not the original ten-capture result.

## Timing interpretation

Individual approximately constant-speed captures have unresolved timing. Their conditional lag minima are diagnostic and are not sensor offsets. A cross-speed comparison requires at least four distinct captures with enough signed-speed variation in stable setup groups. The two shipped +10 RPM examples do not meet this requirement.

The saved ten-capture comparison is a model-based −25.97 ms candidate, with conditional interval [−28.13, −23.81] ms. Camera content leads on bag-record time. Matching LiDAR scenes have later recorded timestamps. Exposure/per-ray timing and absolute encoder angles are not calibrated.

The flywheel explanation lets you select a reference speed/time, expand the visual angle difference, try a clearly labeled hypothetical delay, reset to the saved value, and export SVG. Visual expansion affects drawing only; printed numbers keep their modeled values.

## Saved artifacts

```text
results/<run>/
  summary.json, metadata.json, request.json, status.json
  REPORT.md, report.html, metrics.csv
  flir/                 Camera CSVs, features, final/validation models
  livox/                LiDAR CSVs, features, final/validation models
  intermediates/        Camera crops and measured central-ray arrays
  timing/               Agreement, profiles, bootstrap, clocks
  figures/              Detection, quality, timing, scan plots
```

Folder outputs also contain `captures/`, combined CSVs and `timing/overall_offset.json`. Numerical `flir` field/directory names are retained for format compatibility; UI labels use camera. View an HTML report directly, download a file, or export a complete run ZIP. Download all LFS objects before browsing arrays or scans.

The original long-form development validation record is archived as `WORKSPACE_VALIDATION.md`. Its referenced development screenshots/scripts are workspace evidence; publication-specific checks are documented separately in `PUBLICATION_CHECKS.md`.

## Automatic target search

Keep the default Automatic setting. A device calibration file guides the search when valid; missing or unsupported calibration triggers independent LiDAR localization. Live previews and the saved result explain which method was used. The LiDAR result includes a full-scene localization figure and alignment review. Folder tables show the method for each capture. See [LOCALIZATION.md](../LOCALIZATION.md) for calibration and diagnostic CLI flags.
