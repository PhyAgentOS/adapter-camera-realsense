#!/usr/bin/env bash
# 目标机 RealSense 系统环境配置：librealsense 运行时/udev 规则。
# 供 PyInstaller 打包后的 realsense 二进制等免源码部署场景使用。
#
# 本脚本不执行 uv、pip，也不安装 Python 项目依赖。
#
# 用法：
#   sudo bash scripts/setup.sh

set -euo pipefail

if [[ "$(id -u)" -ne 0 ]]; then
  echo "请以 sudo 运行本脚本：sudo bash $0" >&2
  exit 1
fi

if ! command -v apt-get >/dev/null 2>&1; then
  echo "[setup] 未检测到 apt-get；请按发行版安装 librealsense2 运行时与 udev 规则。" >&2
  exit 0
fi

. /etc/os-release
CODENAME="${VERSION_CODENAME:-}"
if [[ -z "${CODENAME}" ]] && command -v lsb_release >/dev/null 2>&1; then
  CODENAME="$(lsb_release -cs)"
fi
if [[ -z "${CODENAME}" ]]; then
  echo "[setup] 无法识别 Debian/Ubuntu codename。" >&2
  exit 1
fi

install -d -m 0755 /etc/apt/keyrings
if [[ ! -f /etc/apt/keyrings/librealsenseai.gpg ]]; then
  echo "[setup] install Intel RealSense apt key"
  curl -sSf https://librealsense.realsenseai.com/Debian/librealsenseai.asc | \
    gpg --dearmor > /etc/apt/keyrings/librealsenseai.gpg
  chmod 0644 /etc/apt/keyrings/librealsenseai.gpg
fi

cat > /etc/apt/sources.list.d/librealsense.list <<EOF
deb [signed-by=/etc/apt/keyrings/librealsenseai.gpg] https://librealsense.realsenseai.com/Debian/apt-repo ${CODENAME} main
EOF

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  librealsense2 \
  librealsense2-utils \
  librealsense2-udev-rules

udevadm control --reload-rules || true
udevadm trigger || true

echo "[setup] 完成。请重新插拔 RealSense 设备，并运行：realsense-viewer"
