# Timing illustration checks

The illustration uses the saved timing candidate automatically. Offset and measured RPM are read-only and displayed to one decimal; diagrams and matching timestamps retain full precision. Folder/comparison results still allow selection of a capture for its measured rotation speed. Visual magnification and scene stepping remain available.

Checked in Chromium using saved single-bag, ten-capture folder and cross-speed results, without rerunning inference:

- Single bag: **−16.0 ms**, **−15.0 RPM**. The fitting minimum is labeled as a single-bag candidate, with a prompt to compare different speeds.
- Folder: displays **−25.9 ms**, while calculations retain **−25.946689773256537 ms**.
- Visual controls preserve the saved offset and numerical angular gap; SVG export contains both scenes and timing qualifications.
- Phone layout stacks controls and diagrams without page overflow.
- Missing offset or RPM does not substitute example data. Tiny/zero offsets and a stopped wheel remain valid.
- No browser errors; all three saved summary files retained their SHA256 hashes.

[Check evidence](timing-illustration-verification/checks.json) · [Exported SVG](timing-illustration-verification/example.svg)
