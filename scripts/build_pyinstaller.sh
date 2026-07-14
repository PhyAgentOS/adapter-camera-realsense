#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PACKAGE_DIR}/dist"
WORK_DIR="${PACKAGE_DIR}/build/pyinstaller"
VENV_DIR="${PACKAGE_DIR}/.venv_build"

cd "${PACKAGE_DIR}"
mkdir -p "${DIST_DIR}" "${WORK_DIR}"
rm -f "${DIST_DIR}/realsense_camera" "${DIST_DIR}/realsense_camera.exe"
rm -rf "${VENV_DIR}"
trap 'rm -rf "${VENV_DIR}"' EXIT

echo "==> [realsense] 正在初始化隔离的局部构建虚拟环境..."
uv venv --no-workspace "${VENV_DIR}" --python 3.12

echo "==> [realsense] 正在安装本地依赖和 PyInstaller..."
UV_PROJECT_ENVIRONMENT="${VENV_DIR}" uv sync \
  --project "${PACKAGE_DIR}" \
  --frozen \
  --no-default-groups \
  --group build \
  --python 3.12

echo "==> [realsense] 验证 pyrealsense2 可导入..."
"${VENV_DIR}/bin/python" - <<'PY'
import forge_devices_realsense_camera.backend_realsense  # noqa: F401
print("==> [realsense] pyrealsense2 import ok")
PY

echo "==> [realsense] 开始使用 PyInstaller 进行打包..."
"${VENV_DIR}/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --distpath "${DIST_DIR}" \
  --workpath "${WORK_DIR}" \
  "${SCRIPT_DIR}/realsense_camera.spec"

if [[ -f "${DIST_DIR}/realsense_camera" ]]; then
  echo "Built: ${DIST_DIR}/realsense_camera"
elif [[ -f "${DIST_DIR}/realsense_camera.exe" ]]; then
  echo "Built: ${DIST_DIR}/realsense_camera.exe"
else
  echo "WARNING: ${DIST_DIR}/realsense_camera 未找到，请检查 PyInstaller 输出。" >&2
  exit 1
fi
