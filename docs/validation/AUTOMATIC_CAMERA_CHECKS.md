# Automatic camera-to-LiDAR target finding

`camera_roi: null` is now the default. Full-camera temporal variation identifies complete candidate wheels, and independent multi-harmonic rotation verifies the region. Partial targets and comparable multiple wheels request target selection. The detected image centre then guides LiDAR with the matching device calibration. LiDAR depth/shape/rotation evidence verifies its own region; camera angles and RPM are not passed into its angle estimator.

Validation:

- Camera discovery found the target in **all 10 original Device 1 bags**, without fixed coordinates.
- A spatial integration check confirmed that calibrated LiDAR search used the same automatic camera crop. Peak RSS for the sequential discovery check was **379.6 MiB**.
- One complete actual-bag run finished with **1,443 camera frames**, **423 scans**, and **10,152,000 input points**. Detected crop: **[244, 160, 96, 96]**; camera/LiDAR RPM: **-14.999286 / -14.999948**. Its calculated single-bag candidate is **-16.0 ms**, displayed with multiple-RPM guidance.
- Unit cases cover an off-centre wheel, clipped reflection, brightness changes, static scene, multiple wheels, manual override, and a camera topic occupying only part of a longer bag. **61 tests passed**.
- Browser checks covered automatic/manual settings, the real detection artifacts, calibrated LiDAR linkage, and 390/320 px phone layouts. No browser errors.

Discovery retains at most 128 grayscale images with longest edge capped at 640 px; frame selection remains bounded when the camera occupies only part of the bag. All final camera frames use the original resolution within the measured crop. This validates localization/software behavior on these recordings; it does not establish an absolute-angle benchmark.

Earlier reference analyses remain separately stored. The new full run is retained in the development workspace; the repository includes its compact checks and images. No additional raw bags or large arrays were added for this update.

[Camera discovery](evidence/automatic-camera-verification/capture_checks.json) · [Spatial integration](evidence/automatic-camera-verification/integration_checks.json) · [Complete run](evidence/automatic-camera-verification/end_to_end_checks.json) · [Browser checks](evidence/automatic-camera-verification/browser_checks.json)
