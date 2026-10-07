# Automatic flywheel localization

The app uses **Automatic** by default. You do not need to select an algorithm.

1. Search the full forward LiDAR view for a compact region whose measured depths change repeatedly.
2. If device calibration is supplied and matches the recorded image size, use the detected camera wheel centre as a **rough spatial prior**. LiDAR shape and coherent rotation still verify the candidate.
3. If calibration is absent, invalid, or points to an unsupported region, retry using LiDAR evidence alone. The app and `localization/summary.json` show each attempt and its reason.
4. If both searches fail, only an exact SHA256-verified reference bag may use the original rig region after its return count and independent rotating signature pass checks. Ambiguous multiple targets never use this fallback. Unknown scenes remain unresolved.

## Device calibration

Store a JSON file at `calibrations/device_1.json` through `device_5.json`, matching the bag's device folder. The supplied Device 1 file contains **enclosure-off OpenCV fisheye** intrinsics for **484 × 366 pixels**, `D = [k1,k2,k3,k4]`, and metre-valued extrinsics:

`p_camera = R_lidar_to_camera @ p_lidar + t_lidar_to_camera`.

The reverse transform is retained and checked as the inverse. Other devices have no default calibration. Specify your own `camera_model` (`fisheye` or `pinhole`), `image_size_wh`, `K`, `D`, `T_lidar_to_camera` and `translation_units: "metres"`. Wrong image sizes never trigger guessed intrinsic scaling; Automatic uses LiDAR-only instead. A malformed transform, zero focal lengths or wrong distortion coefficient count is rejected.

Adding intrinsics and extrinsics helps identify the intended wheel among multiple moving regions. A pixel gives a direction, not a unique depth: the algorithm learns the foreground depth from LiDAR returns. Camera **angles and RPM are never given to the LiDAR angle estimator**.

The supplied calibration was obtained in a September calibration run. Its reported held-out projection error and bootstrap uncertainties are provenance from that run, not accuracy measured on these August bags. Here, the localized wheel centre projects roughly 31 pixels from the detected camera centre. The saved figure and report flag this alignment difference. Calibration therefore remains a broad guide; verify sensor pose, enclosure state and camera resolution for new data.

## What the LiDAR estimator uses

Discovery samples are spread across the recording (up to 96 full clouds and 120 image crops). Robust per-direction depth percentiles reduce dependence on changing scan density. Thin depth edges are removed before compact-envelope fitting. Several angular harmonics must support a coherent signed rotation; similarly plausible multiple candidates are rejected.

The chosen LiDAR centre and angular radius normalize the measured coordinates; foreground/background depths set the feature bands. H1 and several spatial orders initialize a periodic measured-return model, followed by per-cloud registration and purged validation. No points are invented and no motor speed is supplied. **Every recorded cloud** is decoded again for angle estimation and scan statistics. Original forward depth in metres is preserved.

This supports a visible asymmetric rotating aperture in a fixed scene with repeated, roughly constant-speed motion. It is not a universal object detector or a guarantee for abrupt reversals, strong occlusion, extreme foreshortening, arbitrary rotor shapes or missing sensor overlap.

## Keep timing references comparable

For the exact original rig recordings, identified by their source SHA256, Automatic preserves the established **sensor-coordinate H5/3 timing phase modulo 120°**, measured directly from their original rays. Their improved relative angles use the localized region; retaining this separate reference avoids silently changing cross-speed zero when the ROI moves.

Other recordings use **target-centred H1 modulo 360°**. Incompatible conventions are rejected by comparison; do not merge their phase observations as though they shared a zero. The `--localization lidar_only` diagnostic override can produce the same target-centred convention for a complete new analysis. The original ten-bag timing result remains separately saved.

Single constant-speed recordings still have unresolved physical timing. A combined phase-model candidate and its confidence interval are conditional on a stable sensor phase, target localization and setup grouping; camera exposure and per-ray timing require separate calibration.

## Saved evidence and commands

Each run keeps `localization/summary.json`, `discovery_samples.npz`, `spatial_evidence.npz`, and `target_localization.png`. The selected calibration values and file hash are saved in the summary. Reports include selection/fallback reasons and alignment review. Discovery geometry uses samples across the full recording, so angle validation is **conditional on this shared ROI**, rather than an independently held-out localization benchmark.

```bash
# Recommended: no method selection necessary.
python process_bag.py device_1/rig_20260828_192028_0.bag
python process_bag.py --folder device_1

# Optional diagnostic / old-reference reproduction overrides.
python process_bag.py device_1/rig_20260828_192028_0.bag --localization lidar_only
python process_bag.py device_1/rig_20260828_192028_0.bag --localization legacy
```

The app uses offline system fonts, restrained translucent navigation and immediate press feedback. Reduced-motion, reduced-transparency and increased-contrast preferences are supported. Previews contain real recorded data; schematic timing diagrams remain explicitly labelled.
