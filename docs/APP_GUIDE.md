# App guide

## Process

1. Start with `bash setup.sh`, then `bash launch.sh`.
2. Open **http://127.0.0.1:8765** and select a device.
3. Choose one bag or the entire folder. Topics and the camera crop are selected automatically.
4. Start; watch counts, progress and measured detections.
5. Open results to inspect plots, every scan, reports or downloads.

Import bags into the selected device or copy them to `bagfiles/device_<n>/`. Add calibration to `calibrations/device_<n>.json`. Optional topics, crop and setup group are under **Acquisition settings**.

## Saved results

One **Device 1 · example** folder is included, containing ten captures and their combined timing result. Two raw bags are distributed; all ten saved captures remain inspectable inside the example.

New runs appear alongside the example. Each creates a fresh folder; app and CLI processing share one worker slot. Folder failures are isolated. Cancellation preserves partial output; server restarts reconnect to active workers.

## Read the numbers

| Value | Meaning |
|---|---|
| Camera STD | Held-out angle repeatability |
| Livox STD | Held-out agreement with the camera |
| Offline STD | Agreement after smoothing with future scans |
| Orientation | Angle from the first scan, wrapped to 0–360° |
| Accumulated rotation | All turns from the first scan; used for RPM |
| Time offset | Calculated fitting candidate; compare different RPMs for stronger timing evidence |

The flywheel illustration uses the calculated offset. Its displayed value is rounded to one decimal; calculations retain full precision. Visual expansion changes the drawing only.

## Files

`results/<run>/` contains sensor angles/models, extracted arrays, scan tables, timing metrics, figures and reports. Folder runs also contain individual outputs in `captures/`. Use **Open report**, **Download artifacts**, or an individual file link.

Plots retain their original resolution. The correlation matrix displays compactly; long figures scroll. [Calibration](../LOCALIZATION.md) · [Methods](METHODS.md) · [Checks](APP_AUDIT.md).
