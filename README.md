# Livox Avia–Camera Timing Studio

A local app for flywheel angles and relative timing from **Livox Avia + camera ROS1 bags**.

[![Full Studio workspace](docs/assets/app_preview.png)](docs/assets/app_preview.png)

Choose a recording, inspect its topics and camera view, then watch detection previews. Click any figure for full size.

## Run

Requires Linux, Python 3.8, ROS Noetic, `python3-venv` and Git LFS.

```bash
git lfs install
git clone https://github.com/maninka123/livox-avia-camera-timing.git
cd livox-avia-camera-timing
git lfs pull
source /opt/ros/noetic/setup.bash
bash setup.sh
bash launch.sh
```

Open **http://127.0.0.1:8765**. Select a device, choose one bag or the whole folder, then start. Watch detections and progress; inspect scans, plots and reports after completion.

Run the launcher from any directory. It uses the app’s `.venv`; `STUDIO_PYTHON` can select another Python executable.

## How it works

| Camera | Livox Avia | Timing |
|---|---|---|
| Find the wheel; fit its shape; track image phase. | Find rotating returns; track each cloud’s phase. | Compare sensor phases across different RPMs. |

Each sensor estimates its own angles and RPM. Camera position plus device calibration guides the LiDAR search; missing calibration falls back to LiDAR-only. Camera cropping is automatic; a manual crop is optional.

Add your device’s **K, D and LiDAR→camera transform** to `calibrations/device_<n>.json`. [Device 1 example](calibrations/device_1.json) · [Calibration details](docs/guides/LOCALIZATION.md).

![Automatic camera crop](docs/assets/automatic_camera.png)

[![Livox detection at four wheel orientations](docs/assets/livox_detection.png)](docs/assets/livox_detection.png)

Four orientations from a recorded capture: depth-coloured clouds (top), selected wheel returns in orange (middle), and their angular histograms (bottom).

## Included example

**Saved results** contains one labelled **Device 1 example**: 10 captures, 14,281 camera frames and 4,205 Livox scans. Open it to inspect individual captures and the combined timing estimate.

| Timing metric | Value |
|---|---:|
| Estimated τ | **−25.95 ms** |
| Standard error | 0.912 ms |
| Conditional 95% interval | [−28.10, −23.79] ms |

The modeled matching scene appears on Livox about **25.95 ms later**. This is a model-based timing candidate. Different RPMs help separate fixed angle differences from delay; exposure and per-ray timing require separate calibration.

![Example timing](docs/assets/automatic_device_1_timing.png)

[Results folder guide](results/README.md) · [Example report](results/batch_device_1_20261007T064645Z_f2b206cc/REPORT.md) · [Capture metrics](results/batch_device_1_20261007T064645Z_f2b206cc/capture_metrics.csv).

Two raw bags are included in `bagfiles/device_1/`; Devices 2–5 are ready for your recordings. Both raw examples are near +10 RPM, so additional speeds are needed for combined timing. The saved ten-capture example uses the earlier camera crop; the current app also discovers that crop automatically.

Every new run gets its own results folder. Bags and arrays use **Git LFS**; fetch them before opening scan previews.

## Sensor pipeline values

Measured on four camera–LiDAR pairs (29 captures, ±5/10/15 RPM, 28 Oct 2026); every validation check passed. Set the device's value as `lidar_timestamp_shift/capture_offset` in [Sensor_Computer](https://github.com/maninka123/Sensor_Computer) `src/node_pc/config/pipeline.yaml` (live sensors, `auto_timestamp_offset: true`).

| Device | Camera S/N | Livox S/N | τ (ms) | 95% interval (ms) | `capture_offset` (s) |
|---|---|---|---:|---:|---:|
| Pair 1 | 25120439 | 3JEDN920015M711 | −26.7 | [−28.6, −24.8] | **0.0705** |
| Pair 2 | 24510717 | 3JEDLB30015Y251 | −22.2 | [−27.6, −16.9] | **0.0757** |
| Pair 3 | 25500033 | 3JEDK3V0013U651 | −24.5 | [−26.4, −22.5] | **0.0731** |
| Pair 4 | 25120437 | 3JEDNB30018L201 | −24.8 | [−25.7, −23.8] | **0.0729** |

`capture_offset = 0.100 s + τ − camera header→arrival (≈ 2 ms)`. Replaying the pipeline's LiDAR stamping on all captures with these values leaves −0.1 to +2.7 ms. Valid for the same computer, drivers and camera settings (35 fps, 4×4 binning, 10 Hz LiDAR).

## CLI

```bash
.venv/bin/python process_bag.py device_1/rig_20260828_192028_0.bag
.venv/bin/python process_bag.py --folder device_1
.venv/bin/python reproduce_automatic.py
```

[Documentation](docs/README.md) · [App guide](docs/guides/APP_GUIDE.md) · [Validation](docs/validation/README.md) · [Code layout](algorithms/README.md).

## Papers

- **Measurement:** [Correcting time offsets and enclosure-induced measurement distortions in LiDAR–camera systems](https://doi.org/10.1016/j.measurement.2026.122285).
- **Preprint:** [A Rotating Aperture Target with a Common Geometric Estimator for Temporal Calibration of Heterogeneous Sensors](https://doi.org/10.2139/ssrn.7513129).

The papers provide the research background; this app’s independent estimators and results are described above.
