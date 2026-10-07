# Livox Avia–Camera Timing Studio

Estimate rotating-target angles and relative observation-time offsets from **Livox Avia LiDAR + camera ROS1 bags**. A local browser app shows live detections, every scan, quality metrics, and downloadable reports.

![Studio showing Device 1 recordings and automatically selected sensor topics](app_preview.png)

## Start

**Environment:** Linux, Python 3.8, and a sourced ROS Noetic installation with `rosbag` and `sensor_msgs`. Install `python3-venv` and `git-lfs` through your package manager if needed.

```bash
git lfs install
git clone https://github.com/maninka123/livox-avia-camera-timing.git
cd livox-avia-camera-timing
git lfs pull
source /opt/ros/noetic/setup.bash
bash setup.sh
bash launch.sh
```

Open **http://127.0.0.1:8765** → choose **Device 1** → select one bag or the entire folder → inspect topics → **Start processing**. Change the crop/topics for your own recordings. Use `bash launch.sh --port 8766` for another port.

**Explore without processing:** open **Saved results** to view the included ten-capture Device 1 analysis and cross-speed comparison. Bags and numerical arrays use [Git LFS](https://docs.github.com/en/repositories/working-with-files/managing-large-files/about-git-large-file-storage); a normal ZIP download may contain pointers instead of data. The complete LFS download is about **1.7 GB**.

## What you can do

- Process one bag or a device folder, with automatic/manual camera and LiDAR topic selection.
- Watch progress, remaining counts, measured detections, and relative-angle traces.
- Inspect every point cloud: angle, local RPM, target returns, depth spread, and quality flags.
- Compare captures and explore exaggerated flywheel/timestamp diagrams explaining the offset.
- Save angles, models, intermediate arrays, plots, metrics, HTML/Markdown reports, and ZIP bundles under a fresh `results/<run>/`.

## Methods

![Independent camera and LiDAR estimation followed by timing analysis](method_overview.svg)

| Camera | Livox Avia |
|---|---|
| Moving-region ellipse calibration; subpixel polar sampling; normalized grayscale harmonics. | Measured-ray depth/radial/angular signatures: 336 features with regularized correlated-noise weighting. |
| Learn a periodic appearance model; refine each frame's phase. | Learn a periodic return model; refine each cloud's phase. |

Each sensor estimates signed RPM from **its own data**; commanded motor RPM is never supplied. Speed initializes a phase-search branch, so the estimator still assumes repeated, approximately constant-speed motion. Five-fold and chronological validation report repeatability/agreement. Optional offline LiDAR smoothing uses future scans and is labeled separately.

<p><img src="camera_detection.png" width="49%" alt="Measured camera crop, calibrated rotor, and polar appearance"><img src="livox_detection.png" width="49%" alt="Measured Livox returns and extracted rotation features"></p>

Timing profiles a free phase for each lag. Across different signed speeds in a shared setup, circular phase regression separates fixed phase from a common delay and checks alternate wrap branches. A single constant-speed bag cannot establish the physical offset.

## Included recordings

Two original bags are under [`bagfiles/device_1/`](bagfiles/device_1/); Device 2–5 folders are ready for new data. Other streams remain in the bags, but processing uses only `/camera/image_raw` and `/livox/lidar`.

| Bag | Measured camera RPM | Camera held-out STD | LiDAR held-out agreement STD |
|---|---:|---:|---:|
| `rig_20260828_192028_0.bag` | +9.99985 | 0.261° | 0.574° |
| `rig_20260828_191845_0.bag` | +9.99967 | 0.201° | 0.605° |

These rank first/second by the ranking score `sqrt(camera_STD² + LiDAR_agreement_STD²)` among ten captures. This is a selection heuristic, **not an absolute accuracy measurement**. See [all rankings](docs/bag_quality_ranking.csv) and [SHA256 manifest](bagfiles/manifest.json). Both examples have approximately +10 RPM; processing these two alone leaves overall timing unresolved. Positive/negative RPM indicates direction in the estimator's angle convention.

## Device 1 reference results

The saved analysis covers **10 bags · 14,281 camera frames · 4,205 clouds · 100,920,000 decoded LiDAR points**. Full detections, intermediate arrays, models, scan tables, and figures are included for all ten, although only two raw bags are distributed.

| Combined timing metric | Value |
|---|---:|
| Model-based offset candidate, τ | **−25.97 ms** |
| Standard error | **0.914 ms** |
| Conditional 95% interval | **[−28.13, −23.81] ms** |
| Phase-fit residual STD | **0.182°** |

![Cross-speed phase fit for the ten Device 1 captures](device_1_timing.png)

Convention: `θ_L(t) = phase + θ_C(t + τ)`. Here, camera content leads on bag-record time; the matching LiDAR scene is recorded about **25.97 ms later**. This is **not calibrated physical synchronization**: exposure midpoint, per-ray timing, and encoder ground truth are unavailable. The interval is conditional on the model and does not include unknown systematic bias.

[Device 1 report](results/batch_device_1_20261007T005914Z_2e5dcccf/REPORT.md) · [Per-capture metrics](results/batch_device_1_20261007T005914Z_2e5dcccf/capture_metrics.csv) · [Cross-speed report](results/comparison_20261007T054924Z_01265fa4/REPORT.md) · [Methods and limitations](docs/METHODS.md)

## Research background

- **Measurement:** Ranasinghe et al., [Correcting time offsets and enclosure-induced measurement distortions in LiDAR–camera systems](https://doi.org/10.1016/j.measurement.2026.122285), 285, 122285 (2026).
- **Preprint:** Ranasinghe et al., [A Rotating Aperture Target with a Common Geometric Estimator for Temporal Calibration of Heterogeneous Sensors](https://doi.org/10.2139/ssrn.7513129), SSRN (2026).

These papers provide the research background. This app implements independent periodic appearance/return models; its results are separate from the papers' reported offsets.

## CLI and checks

```bash
source /opt/ros/noetic/setup.bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python process_bag.py device_1/rig_20260828_192028_0.bag
OPENBLAS_NUM_THREADS=1 .venv/bin/python process_bag.py --folder device_1
OPENBLAS_NUM_THREADS=1 .venv/bin/python reproduce_reference.py
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest discover -s tests -v
```

[App guide](docs/APP_GUIDE.md) · [Publication verification](docs/PUBLICATION_CHECKS.md) · [Software citation](CITATION.cff)
