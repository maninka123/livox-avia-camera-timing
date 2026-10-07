# Calibration and target finding

## Automatic search

1. Find a complete rotating wheel in full camera images; select its crop.
2. Use the detected image position and device calibration to guide LiDAR.
3. Verify the target from LiDAR depth, shape and rotation evidence. Fall back to LiDAR-only if calibration is missing or unsuitable.

Camera angles and RPM never enter LiDAR angle estimation. Discovery samples up to 128 images and 96 clouds; final estimation uses every selected observation. Comparable targets or more than 12 camera candidates request a manual crop.

`camera_roi: null` enables automatic cropping. A manual crop is available in Acquisition settings or with `--camera-roi X Y WIDTH HEIGHT`.

## Device file

Save calibration in `calibrations/device_<n>.json`, matching its bag folder.

| Field | Contents |
|---|---|
| `camera_model` | `fisheye` or `pinhole` |
| `image_size_wh` | Calibrated image width and height |
| `K`, `D` | Intrinsics and distortion coefficients |
| `T_lidar_to_camera` | 4×4 transform: LiDAR → camera |
| `translation_units` | `metres` |

`p_camera = R @ p_lidar + t`

[Device 1 calibration](calibrations/device_1.json) uses a 484×366 fisheye model. Image-size mismatches and invalid transforms trigger automatic LiDAR-only fallback. The recorded rig shows about 31 px of projection disagreement; calibration acts as a broad spatial guide.

## Evidence and overrides

Each run saves camera crop/motion evidence in `camera_localization/`, and LiDAR geometry, calibration snapshot, fallback reasons and figures in `localization/`. Only exact source-hash-verified reference captures qualify for the checked fixed-region backup.

Optional CLI diagnostics: `--localization camera_guided`, `lidar_only` or `legacy`. Keep `auto` for normal use. [Timing conventions and methods](docs/METHODS.md).
