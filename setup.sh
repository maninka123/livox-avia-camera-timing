#!/usr/bin/env bash
set -euo pipefail
STUDIO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f /opt/ros/noetic/setup.bash ]; then
  set +u
  source /opt/ros/noetic/setup.bash
  set -u
fi
STUDIO_BASE_PYTHON="${STUDIO_BASE_PYTHON:-python3}"
"$STUDIO_BASE_PYTHON" -c 'import rosbag; import sensor_msgs.msg' || {
  printf '%s\n' 'Install/source ROS1 rosbag and sensor_msgs before setup; see README.md.' >&2
  exit 1
}
"$STUDIO_BASE_PYTHON" -m venv --system-site-packages "$STUDIO_ROOT/.venv"
"$STUDIO_ROOT/.venv/bin/python" -m pip install -r "$STUDIO_ROOT/requirements.txt"
"$STUDIO_ROOT/.venv/bin/python" -c 'import flask, numpy, scipy, cv2, matplotlib, rosbag, sensor_msgs.msg; print("Runtime dependencies OK. Start with bash launch.sh")'
