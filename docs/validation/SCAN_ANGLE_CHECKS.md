# Scan angle display checks

The scan explorer now labels two different quantities explicitly:

| Scan 396, Device 1 −15 RPM capture | Value |
| --- | ---: |
| Time from first scan | 39.600 s |
| Relative orientation within one revolution | 35.683° |
| Accumulated rotation from first scan | −3564.317° |
| Signed turns from first scan | −9.900879 |
| Local phase-derived RPM | −15.11667 |

The accumulated value is consistent with roughly 9.9 revolutions at −15 RPM. The wrapped orientation agrees with the existing `relative_wrapped_angle_deg` export. This display correction does not establish absolute angle accuracy.

Chromium checks covered scan selection, both paginated table columns, positive/negative multiple turns, zero, rounding near 360°, missing values, and desktop/mobile layouts at 390 and 320 px. No browser errors occurred. Saved scan statistics and the analysis summary retained their SHA256 hashes. No inference was rerun.

[Check evidence](evidence/scan-angle-verification/checks.json) · [Desktop](evidence/scan-angle-verification/scan_396_desktop.png) · [Mobile](evidence/scan-angle-verification/scan_396_mobile.png)
