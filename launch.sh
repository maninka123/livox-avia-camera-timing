#!/usr/bin/env bash
set -euo pipefail
STUDIO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if [ -f /opt/ros/noetic/setup.bash ]; then
  studio_source_ros() {
    # ROS setup must not receive app options such as --help or --port.
    set +u
    source /opt/ros/noetic/setup.bash
    set -u
  }
  studio_source_ros
  unset -f studio_source_ros
fi
STUDIO_PYTHON="${STUDIO_PYTHON:-$STUDIO_ROOT/.venv/bin/python}"
if [ ! -x "$STUDIO_PYTHON" ]; then
  printf '%s\n' 'Python environment missing. Run bash setup.sh, or set STUDIO_PYTHON.' >&2
  exit 1
fi
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1
cd "$STUDIO_ROOT"
exec "$STUDIO_PYTHON" app.py "$@"
