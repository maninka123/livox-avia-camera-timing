# Publication checks

The repository contains two raw Device 1 bags and **one saved ten-capture example**. Open the example to inspect each capture, scan data and the combined timing candidate. Earlier result variants and trial runs are archived locally.

| Check | Evidence |
|---|---|
| Layout, app and CLI | [Current review](WORKSPACE_REVIEW.md) · [Detailed audit](APP_AUDIT.md) |
| Camera localization | [Automatic camera checks](AUTOMATIC_CAMERA_CHECKS.md) |
| Timing model | `reproduce_automatic.py` refits the example’s saved phase observations |
| Data delivery | Raw bags and observation arrays use Git LFS |

```bash
source /opt/ros/noetic/setup.bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python reproduce_automatic.py
git lfs fsck
```

Dataset assertions expect a clean checkout: two Device 1 bags and empty Devices 2–5. GitHub Actions runs numerical checks without ROS or bag downloads. [Example/library cleanup checks](EXAMPLE_CLEANUP.md).
