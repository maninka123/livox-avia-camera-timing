# Methods

## Independent angle tracking

| Stage | Camera | Livox Avia |
|---|---|---|
| Find target | Full-frame motion and coherent rotation | Depth-changing envelope, optionally camera-guided |
| Describe target | Subpixel polar grayscale harmonics | 336 measured-return features |
| Track angle | Periodic appearance model and frame-phase refinement | Periodic return model and cloud-phase refinement |

Each sensor infers signed RPM from its own observations. Camera geometry guides position only. All selected frames/clouds are processed; held-out and chronological checks measure repeatability and agreement. Optional Livox smoothing is offline and uses future scans.

The workflow targets a visible asymmetric rotating aperture in a fixed scene with repeated motion. It requires at least 150 observations per sensor, increasing bag timestamps and enough duration for validation. Rate initialization searches approximately ±20 RPM; abrupt reversals are outside the validated workflow.

## Timing

`theta_livox(t) = phase + theta_camera(t + tau)`

Positive τ means Livox content leads on bag-record time; negative τ means camera content leads. For a matching scene, `t_livox = t_camera - tau`.

- **One speed:** fit a separate phase at every lag and report the calculated minimum with profile/bootstrap uncertainty. Fixed phase and delay can give the same separation.
- **Different speeds:** fit a shared delay and setup-specific phase intercepts. Circular branches are checked over ±1000 ms; ambiguous branches are rejected.
- **Reference phase:** exact original captures retain H5/3 modulo 120°; new scenes use target-centred H1 modulo 360°. Incompatible conventions cannot be mixed.

Identical source hashes are excluded as timing replicates. Confidence intervals are conditional on stable sensor pose and phase convention. Header epochs are checked separately; the candidate does not calibrate physical exposure or per-ray acquisition times.

[Calibration and target finding](LOCALIZATION.md) · [Example report](../../results/batch_device_1_20261007T064645Z_f2b206cc/REPORT.md) · [Verification](../validation/APP_AUDIT.md).
