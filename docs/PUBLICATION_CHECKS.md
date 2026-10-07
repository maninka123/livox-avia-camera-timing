# Publication verification — 7 October 2026

**Story:** clone this standalone repository, install its runtime, select a Device 1 bag in the browser, process camera/Livox observations, and inspect the saved results.

| Boundary | Verified evidence |
|---|---|
| Installation | `bash setup.sh` created a fresh local virtual environment with pinned dependencies and ROS system packages. All runtime imports passed. |
| Automated checks | All 47 Python tests passed: API validation, malformed inputs, cancellation/recovery, concurrent uploads/writes, timing identifiability, and scan statistics. |
| UI → API → bag | The browser listed two Device 1 bags and five devices; camera/Livox topics matched the real ROS message types automatically. |
| Actual processing | `rig_20260828_192028_0.bag` completed with 1,425 camera frames and 419 clouds in the fresh environment. Camera held-out STD 0.2607651412488571°; LiDAR held-out agreement STD 0.5738409309878187°. Both match the archived reference. |
| Progress → browser | Live camera preview and extraction/calibration/validation/export stages were observed. |
| Saved data → UI | Ten-capture reference totals, an arbitrary measured scan preview, and the timing explanation rendered successfully. |
| Exports | HTML report returned HTTP 200. A fresh-run ZIP contained 71 entries, including scan metrics and extracted measured returns. |
| Mobile | The comparison result at 390 px width had no horizontal page overflow. |
| Browser errors | Zero JavaScript errors and zero failed requests in the completed flow. |
| Source data | Both distributed bag sizes and streaming SHA256 hashes matched the original capture manifest. |
| Timing reproducibility | Refit from the ten saved phase observations reproduced the −25.970701588690304 ms candidate, 0.9141299471744596 ms standard error, and confidence limits to numerical precision. |

Machine-readable browser evidence: [publication_browser_results.json](publication_browser_results.json). Screenshots: [live processing](live_processing.png), [offset explanation](offset_explanation.png), and [mobile results](mobile_results.png).

The repository publishes one complete ten-capture reference batch and its consistent cross-speed comparison. A separate fresh verification run is retained only locally, so the example result library stays compact. Development worker identities, live preview caches, and logs are omitted; all numerical results, plots, models and extracted observation arrays are retained. Ten publication summary copies carry verified source SHA256 hashes while preserving their original numerical estimator hashes.

To repeat the checks after fetching LFS data:

```bash
source /opt/ros/noetic/setup.bash
OPENBLAS_NUM_THREADS=1 .venv/bin/python -m unittest discover -s tests -v
OPENBLAS_NUM_THREADS=1 .venv/bin/python reproduce_reference.py
git lfs fsck
```

Full API tests expect the two shipped examples and empty Device 2–5 folders; use a clean checkout for these dataset assertions. GitHub Actions runs the numerical timing/scan tests without ROS or large data downloads. This verification establishes software/data delivery and internal numerical consistency, not absolute angle accuracy or physical sensor clock calibration.
