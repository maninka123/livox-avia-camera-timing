# Methods and interpretation

## Camera angle estimation

1. Identify the moving rotor in a grayscale crop using temporal appearance variation; fit an ellipse to calibrate its projected geometry.
2. Sample 12 radial bands and 360 angular positions with subpixel interpolation. Normalize per-frame intensity gain/offset and retain spatial harmonics 1–12.
3. Estimate signed rotation rate from coherent spatial harmonics, searching approximately −20 to +20 RPM and excluding near-zero rotation.
4. Learn a regularized periodic appearance model with a reduced feature basis. Register each observation on that model with a coarse phase search and local refinement.

The motion trajectory initializes the local phase branch; frame registration does not add a penalty pulling its answer onto a straight trajectory. This is still a repeated-motion model, not unrestricted instantaneous orientation estimation. Camera angle zero is only approximately geometry anchored.

## Livox Avia angle estimation

1. Sample the full forward view to find a compact depth-changing envelope; verify coherent rotation with several angular harmonics. A calibrated camera centre is an optional spatial prior, with a LiDAR-only retry.
2. Decode every selected PointCloud2 message. Normalize angular rays around the learned target centre/radius; retain original forward depth in metres and learn foreground/background feature bands.
3. Construct 336 depth/radial/angular channels. Estimate signed speed from several measured spatial orders, learn a periodic return model, and regularize training-only noise covariance.
4. Register each cloud against the weighted model. Export raw phases, quality flags, modeled trajectories, and a separately labelled 21-cloud offline smoother.

Automatic searches that fail do not use arbitrary fixed geometry. Only exact source-SHA-verified original rig recordings qualify for a fixed-region backup after independent signal checks; ambiguous multiple targets remain unresolved. [Selection rules and calibration format](../LOCALIZATION.md).

The `--localization legacy` diagnostic reproduces the original central-region, empirical H5/3 method. Automatic original-recording timing retains that signature directly from the original rays, separately from improved target-centred relative angles. New-scene H1 timing is modulo 360°; mixed conventions are rejected. Absolute angle zero remains uncalibrated. Discovery geometry uses the full sequence, so angle validation is conditional on this shared ROI.

## Validation and bag selection

Five-fold held-out templates and a chronological holdout evaluate stability. Camera held-out residual STD measures repeatability relative to its fitted motion. Livox held-out agreement STD measures disagreement with the camera after fixed phase adjustment. Neither metric is encoder-verified angular accuracy.

The two distributed bags minimize `sqrt(camera_heldout_STD² + livox_heldout_agreement_STD²)` among ten eligible captures, using raw-cloud agreement rather than offline smoothing. This ranking score balances two residual metrics; it is not a derived independent-noise error bound. Both selected bags have approximately +10 RPM, so they are good detection examples but do not provide the signed-speed diversity needed for timing identifiability.

## Timing model

`theta_livox(t_bag) = phase_group + theta_camera(t_bag + tau)`

For approximately constant motion, the phase difference is `phase_group + omega * tau`, with signed angular rate `omega = 6 * RPM` in degrees/second. A single speed cannot distinguish fixed phase from delay. The single-bag analysis therefore fits free phase at every lag, bootstraps one-second blocks, and reports unresolved timing when motion variation is insufficient.

Cross-speed regression estimates a shared delay and one phase intercept per genuinely stable rig/illumination group. For the exact reference recordings, Livox timing phase is anchored to the empirical H5/3 convention modulo 120°; new scenes use target-centred H1 modulo 360°. All candidate circular branches inside ±1000 ms are checked; competing plausible branches or a best minimum outside the range leave the result unresolved. Distinct source SHA256 hashes prevent renamed recordings from becoming independent replicates.

The ten-bag result uses two groups, normal/red, and seven residual degrees of freedom. Its standard error and Student-t interval are conditional regression uncertainty. The phase residual STD describes scatter about that fitted model. None includes unmeasured systematic timing/phase bias.

Positive tau means Livox content leads camera at the same recorded time. Negative tau means camera content leads. Matching physical scenes satisfy `t_L = t_C - tau`. Sensor header epochs differ; subtracting native headers does not establish physical exposure or LiDAR acquisition delay.

## Scope and reproducibility

- Inputs: ROS1 bags with compatible `sensor_msgs/Image` and `sensor_msgs/PointCloud2`, at least 150 observations per sensor, strictly increasing record timestamps, and adequate duration for validation folds.
- Assumptions: fixed rig, repeated rotating target, approximately steady rotation and stable group phase. Abrupt reversals and general scenes are not validated.
- Sensor pipelines do not receive another sensor's angles or commanded motor RPM. Camera observations enter the later agreement/timing evaluation.
- These captures were also used to develop the observation estimators. Independent recordings are needed to assess transfer and systematic accuracy.
- Two raw bags are published, while derived arrays/models/results for all ten are preserved. New processing of the two examples cannot reproduce the ten-bag timing fit. The included phase observations can reproduce the saved fit without the eight omitted raw bags.
- Original algorithm hashes remain in the reference summaries. Source-bag hashes, independently verified in the workspace audit, were added to publication copies so saved comparisons remain verifiable when eight raw bags are absent. Publication changes to launch/setup and displayed names do not change numerical estimators.

The associated Measurement paper and SSRN preprint are linked in the root README. Their reported offsets and geometric estimator evaluations belong to their own experiments; this app's candidate should not be substituted for them.

## Reading the timing figure

The top shows the lead magnitude, conditional interval and signed model parameter. A matching-scene timestamp example uses `t_C = 1 s` and `t_L = 1 s - tau`. These are illustrative timestamps, not two selected exposure measurements. The lower plot converts angular speed to RPM (`omega / 6`) and subtracts each fitted setup intercept from its measured unwrapped phase. All original phase observations remain unchanged; the line is `6 * RPM * tau_seconds`. Original plots are retained as `*_raw.png` beside the simplified versions.
