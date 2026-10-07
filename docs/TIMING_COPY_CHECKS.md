# Result wording checks

The capture overview presents independently estimated RPM and the repeatability/agreement statistics. The camera detection caption describes measured image-processing stages.

Nearly constant-speed captures show their calculated value, e.g. **−16.0 ms**, under **Estimated time offset**. An amber recommendation suggests different RPMs for a stronger timing estimate. The timing evidence explains that a fixed angular difference and a time delay can produce the same separation. The illustration labels the calculated fitting minimum as a single-bag candidate and uses **Estimated time offset** for its read-only value. The numerical status, profile, uncertainty bounds and scientific qualification remain unchanged.

Browser checks covered the overview, camera caption, timing evidence, full-precision illustration calculations, and desktop/mobile layouts at 390 and 320 px. All 56 software tests passed. No inference was rerun. Explanatory report/metadata text was updated while all JSON numerical and boolean values, CSVs, arrays and raw recordings were retained. [Wording audit](timing-copy-verification/wording_audit.json).

[Check evidence](timing-copy-verification/checks.json) · [Speed summary](timing-copy-verification/speed_summary.png) · [Timing explanation](timing-copy-verification/timing_explanation.png)
