# Historical workspace validation

This record describes an earlier run, now archived locally. For current use, see the [app guide](../guides/APP_GUIDE.md) and [published example](../../results/README.md). The measurements below belong to that earlier run.

# Livox + FLIR Studio: folder processing and validation

The app supports **one ROS bag** or **every bag in a selected device folder**. Existing data are in `bagfiles/device_1/`; `device_2/` through `device_5/` are ready for additional data. Imports are saved in the selected device. Only the selected Livox PointCloud2 and FLIR Image topics are processed.

Open http://127.0.0.1:8765, select a device, choose **One bag file** or **Entire device folder**, and start. For the precomputed folder results, open Saved results and select **Device 1**. See `README.md` for topic/group overrides and command-line use.

## Complete actual Device 1 run

Batch: `results/batch_device_1_20261006T151840Z_0c7febaa/`.

- 10 of 10 bags completed, with 0 failures.
- Every one of the 4,205 Livox scans was decoded, containing 100,920,000 input points.
- Every one of the 14,281 selected FLIR frames was processed.
- Every capture has nine figures, full extraction/features/models, individual angle and scan CSVs, held-out/chronological validation, timing/clock diagnostics, and individual reports.
- The batch adds five comparison figures: fitted RPM/quality/return variability, point-count distributions, all scan/RPM traces, a within-capture variability matrix and the overall timing fit.
- The downloaded batch ZIP contains 723 files, including all ten captures' complete nested outputs.

## Per-capture measurements

These statistics describe held-out repeatability and sensor disagreement. Absolute angle accuracy requires separate reference validation.

| Bag | Livox scans | FLIR RPM | Livox RPM | Local Livox RPM STD | FLIR STD (deg) | Livox agreement STD (deg) | Offline agreement STD (deg) | Target returns mean ± STD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `rig_20260828_191635_0.bag` | 419 | -4.99977 | -5.00031 | 0.02394 | 0.1876 | 0.6103 | 0.3169 | 672.4 ± 68.1 |
| `rig_20260828_191845_0.bag` | 419 | +9.99967 | +10.00011 | 0.02864 | 0.2013 | 0.6045 | 0.2551 | 674.7 ± 70.0 |
| `rig_20260828_192028_0.bag` | 419 | +9.99985 | +10.00057 | 0.02377 | 0.2608 | 0.5738 | 0.2750 | 675.0 ± 69.9 |
| `rig_20260828_192202_0.bag` | 425 | -14.99923 | -14.99940 | 0.04521 | 0.2596 | 0.7887 | 0.4278 | 675.7 ± 69.1 |
| `rig_20260828_192433_0.bag` | 421 | +4.99977 | +5.00024 | 0.02378 | 0.2515 | 0.6272 | 0.3137 | 678.7 ± 69.4 |
| `rig_20260828_192618_0.bag` | 419 | -9.99947 | -9.99954 | 0.03791 | 0.2539 | 0.6116 | 0.3142 | 682.9 ± 66.8 |
| `rig_20260828_192752_0.bag` | 420 | +14.99944 | +14.99984 | 0.03451 | 0.2628 | 0.8222 | 0.2974 | 684.4 ± 66.6 |
| `rig_20260828_192952_0.bag` | 420 | -4.99983 | -5.00014 | 0.02242 | 0.2267 | 0.6711 | 0.4213 | 580.8 ± 84.7 |
| `rig_20260828_193136_0.bag` | 420 | +9.99988 | +10.00067 | 0.02777 | 0.2363 | 0.6321 | 0.2713 | 584.9 ± 84.4 |
| `rig_20260828_193309_0.bag` | 423 | -14.99928 | -15.00000 | 0.04062 | 0.2303 | 0.7065 | 0.3882 | 584.5 ± 84.0 |

The two sensors infer their own signed speed from their own observations; commanded motor RPM is not supplied. Local RPM is a centered two-second linear phase slope with up to one second of future data. Its scatter includes detection noise and periodic-model effects and is not an independent measurement of mechanical speed fluctuation. Spatial target-depth spread is distinct from angular error. Motion inference uses measured returns in the target region; full raw clouds remain in the source bags.

The app's **View scans** button opens any capture's **Individual scans** tab. Select a zero-based scan index or page through the table to inspect the measured cloud, original/target counts, relative angle, local RPM, depth mean/spread, held-out motion residual and quality flag. `all_scan_metrics.csv` contains every cloud. `capture_metrics.csv` and `verification/all_bag_metrics.csv` contain exact per-capture metrics and result IDs.

## Overall timestamp result

The empirical cross-speed phase model gives a **candidate of -25.97 ms**, with Student-t 95% interval [-28.13, -23.81] ms, standard error 0.91 ms, and phase-fit residual STD 0.1821 degrees. It uses ten distinct captures, two setup/illumination intercepts, seven residual degrees of freedom and no quality exclusions.

Model: `theta_livox(t_bag) = phase + theta_flir(t_bag + tau); positive tau means Livox content leads FLIR on bag time.`. Thus the negative candidate means FLIR content leads Livox in the fitted empirical convention on bag-record time.

**This is not a calibrated physical sensor offset.** The interval is conditional on stable empirical harmonic phase and fixed sensor pose within each setup group; it does not include systematic geometry, native ray-time, scan-phase or exposure error. Each capture is a separate timing replicate. The app does not average per-bag lag minima or treat thousands of clouds as independent cross-capture timing replicates.

All ten individual constant-speed captures remain **NOT_IDENTIFIABLE_FROM_THIS_BAG**. Without enough nonconstant motion above the camera noise, fixed angular phase and time delay cannot be separated reliably within one recording. Insufficient captures or signed-speed variation also yield an unresolved overall result. Header clocks have different epochs and are not directly subtracted to claim physical synchronization.

The overall model, phase observations, residuals and covariance are in the batch's `timing/` directory. Each nested capture retains its lag profile, bootstrap interval and clock diagnostics. The earlier 66.7 ms result is neither assumed nor copied.

## Verification

- Twenty automated tests passed: timing identifiability/sign recovery, known cross-speed delay recovery, clock epochs, signed local RPM with irregular/missing observations, empty/invalid devices, protected paths, invalid settings, real ROS bag import into the selected device with a generic filename, and all-failed folder reporting.
- The actual ten-bag worker was started in the browser. Queue counts, total/capture progress and live measured detections were checked during processing. Completed stages are saved for every capture.
- Browser result checks passed: ten capture rows, exact counts, automatic per-bag setup groups, all comparison plots, overall timing confidence/qualification, nested capture drill-down, arbitrary scan selection, measured scan preview and pagination.
- The standalone folder report links all individual reports. The full ZIP was downloaded and checked for all ten scan CSVs, eleven reports, combined scan metrics and the overall model. Single-bag processing and downloads were also rechecked after the update.
- No JavaScript errors were found, and single/folder layouts passed the phone viewport overflow check.
- An intentionally unreadable first bag was reported as failed while the next real capture completed. Insufficient timing data stayed unresolved. The temporary Device 2 input fixtures were removed afterward; their diagnostic results are archived under `verification/trials/`.
- Real folder cancellation stopped the current child process and all remaining queued captures, preserved partial artifacts/manifest and left no orphan worker.
- The preservation audit checked 1,844 original files with **zero changes** and no unexpected files outside this project. All ten independently copied bags retain their verified source hashes and updated paths in `bagfiles/manifest.json`.

Evidence: `verification/tests.log`, `folder_browser_results.json`, `folder_failure_results.json`, `browser_results.json`, `audit_results.json`, and the screenshots. Development export failures and intentional cancellation trials are retained outside the working result library.

The interactive timing explanation was subsequently checked against the saved real single-bag, ten-bag folder and cross-speed comparison results. Positive, negative and zero offsets, reverse rotation, stopped motion, capture RPM selection, exaggerated versus actual angular scales, hypothetical edits, reset and time stepping passed. Single-bag ambiguity and missing-estimate examples remain explicitly labeled. The downloaded SVG parsed successfully and includes both diagrams, units and timing qualifications. The phone layout stacks the panels without page overflow. There were no browser errors, and all three saved analysis summaries retained their original SHA256 hashes. Evidence: `verification/timing_explanation_results.json`, `timing_explanation_example.svg`, and `timing_explanation_{folder,bag,mobile}.png`.

## App audit, 7 October 2026

The app was audited through its Python API, real ROS workers and browser. Forty-seven automated tests passed. Both normal processing and deliberate failure cases were exercised; the original captures and earlier analyses were preserved.

| Area | Repairs and checks |
|---|---|
| Selection and navigation | Bag, device, result, file-list and scan requests preserve the newest selection. Returning to the workbench supersedes pending result navigation. Dataset refresh after import preserves a device chosen in the meantime. |
| Acquisition controls | Empty or invalid crop/search controls fail before processing. Manual topic values must be text. Automatic and manual folder queues validate each bag independently, including an unsuitable first bag. |
| Worker lifecycle | Worker identities persist PID, start tick and exact worker/request arguments. Server restarts reconnect to live jobs; missing workers become terminal instead of polling forever. Recent queued jobs have a launch grace period. |
| Cancellation | Single and folder cancellation preserve partial files. A recovered folder job stops its current child and remaining queue. Repeated cancellation does not send repeated termination signals. |
| Concurrent requests | Unique temporary JSON files prevent same-process publication races. Atomic upload destination creation preserves both simultaneous imports. File reservations prevent two server processes from launching overlapping jobs. ZIP generation uses a separate lock. |
| Long filenames | Upload names and generated single/folder run IDs fit filesystem byte limits, including Unicode. Original source names remain unchanged when starting a run. Long headings and file paths wrap on small screens. |
| Saved results | Corrupt, missing or incomplete summaries cannot break the result library. Failed and damaged runs expose individual preserved files. Inspecting an older failed run does not replace the active job tracker. Files and ZIPs exclude links outside the run directory. |
| Scan browsing | Negative, fractional, empty and excessive indices are rejected. The final scan remains selectable. Delayed requests cannot overwrite a newer scan; pagination cannot skip or mix pages. Nonfinite CSV values become JSON nulls. |
| Image and cloud inputs | Image dimensions, row strides and buffer lengths are checked. Cloud coordinates must be scalar, field names unique and data layout valid; padded and big-endian cloud decoding passed. Repeated timestamps, insufficient fold duration and too few training observations give explicit errors. |
| Timing inference | SHA256 source identity prevents renamed bag copies from becoming extra timing replicates. Alternate circular phase branches are refined and checked; plausible aliases or a minimum outside the supported search leave timing unresolved. |
| Offset illustration | Real scale preserves the actual model angle above 135 degrees; the exaggeration cap applies to expanded displays. Invalid illustrative values retain the last valid view with a message. Bag/folder status labels, signs, time stepping, phone layout and SVG exports passed. |

The full ten-bag browser run is `batch_device_1_20261007T005914Z_2e5dcccf`: **14,281 FLIR frames, 4,205 Livox clouds and 100,920,000 decoded input points, with zero failed captures**. Scan drill-down, all comparison plots, reports and the complete nested ZIP passed. The later single-bag browser run `rig_20260828_192433_0_20261007T010940Z_0c569491` completed with 1,426 frames and 421 clouds, including source-hash provenance and report/download checks.

The updated cross-speed fit checked four circular branches on ten distinct source hashes and retained **−25.9707015887 ms** as the folder-data candidate, with the same conditional interval as before. Its saved comparison is `comparison_20261007T010945Z_ddd0ad77`. The numerical detection outputs and timing conclusion for the supplied captures did not change through these guards.

Real server-restart checks reconnected to the same single-bag worker PID/start tick, blocked a duplicate launch, and completed all detections. A folder worker and its child also survived restart, then cancelled without an orphan process. A separate mixed-folder trial contained a readable bag without Livox, an unreadable bag and two byte-identical real capture copies under different names. Both unsuitable bags failed individually; both valid copies completed; timing used one distinct capture and remained unresolved. Deliberate failure/cancellation fixtures are archived under `verification/trials/`.

Browser stress checks passed fourteen scenarios, including deliberately delayed responses and invalid uploads/previews. There were no JavaScript errors. Two HTTP 400 console messages were expected from the intentionally failed preview and invalid upload; they were recorded rather than hidden. The full phone layout passed the page-overflow check.

Evidence:

- `verification/corner_tests.log`: 47 automated tests, zero failures.
- `verification/corner_browser_results.json`: browser stress checks and intentional network failures.
- `verification/restart_worker_results.json`: worker continuity, duplicate-launch guard and recovered cancellation.
- `verification/folder_browser_results.json`, `browser_results.json`: actual processing and artifacts.
- `verification/folder_failure_results.json`: mixed-folder failure isolation, duplicate-source exclusion and cancellation.
- `verification/current_comparison_results.json`: source hashes, refined branch count and unchanged timing candidate.
- `verification/timing_explanation_results.json`: diagram signs, controls, uncertainty labels, SVG and unchanged saved summaries.
- `verification/audit_results.json`: original-file preservation and independently hashed source/copy verification.

This audit validates software behavior and reproducibility on the supplied ROS1 captures. Absolute angular accuracy and physical exposure-to-ray synchronization remain unverified without external reference measurements; the fixed-rig periodic-motion assumptions still apply.

## Reproduce

From the workspace root:

```bash
bash "Livox_FLIR_Studio/launch.sh"
```

For CLI folder processing, from this project folder:

```bash
source /opt/ros/noetic/setup.bash
OPENBLAS_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 ../.venv/bin/python process_bag.py --folder device_1
```

Every run creates fresh results. `--all` processes every nonempty device separately. Filename-only single-bag commands remain compatible when the filename is unique across device folders.
