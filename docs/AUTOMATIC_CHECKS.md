# Automatic localization and app checks

- All ten original bags processed: 14,281 images, 4,205 clouds, 100,920,000 decoded points; no capture failures.
- 54 tests pass, including off-axis synthetic target discovery, rejection of static sampling-density changes, multiple-target ambiguity, fisheye/pinhole projection, transform validation, and incompatible timing conventions.
- Real-bag controlled failures verify missing calibration, incorrect camera prior, and wrong image size each fall back to LiDAR-only.
- A forced failed search permits the independently checked fixed region only for an exact reference SHA256. An unknown scene is rejected instead. These are controlled fallback checks, not independent accuracy benchmarks.
- The `--localization legacy` run reproduces the old 192028 bag's held-out disagreement STD exactly: 0.5738409309878187°.
- All ten saved original-ray H5 timing signatures match the previous arrays exactly (maximum absolute difference zero). New tracking estimates are independent of camera angles/RPM.
- Chromium verifies recorded preview/crop, frame modal, empty-device handling, chosen method/history, saved figures, scan 200, ten-bag results, exact timing diagram value, ZIP contents, 320/390-pixel layouts and reduced motion. No browser script errors.
- A fresh browser Start run with the pinned publication dependencies processed all 419 clouds and 1,425 frames, showed live localization/progress, and reproduced 0.4886775935072314° held-out agreement exactly. [End-to-end evidence](automatic-verification/published_end_to_end.json).
- Earlier result variants are archived locally; one ten-capture example is published. New automatic results are agreement statistics, not absolute angle/timing truth; 9/10 bags improved, median per-bag STD reduction 16.4%.

[Machine-readable browser checks](automatic-verification/automatic_browser_results.json) · [Test log](automatic-verification/automatic_tests.log) · [Fallback checks](automatic-verification/fallback_verification.json) · [Numerical comparison](../results/batch_device_1_20261007T064645Z_f2b206cc/automatic_validation.json)

The Apple design skill was installed permanently in the developer's Codex skill directory. Runtime uses local system fonts and assets and does not require that skill or a network connection.
