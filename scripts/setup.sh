#!/usr/bin/env bash
# Explicit administrator setup for source deployments.
# Installs the fixed udev rule and configures the actual invoking user for the
# video group. The system libusb runtime must already be installed.
#
# Usage:
#   sudo bash scripts/install_permissions.sh

set -Eeuo pipefail

PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 022
unset BASH_ENV ENV CDPATH GLOBIGNORE LD_PRELOAD LD_AUDIT PYTHONPATH PYTHONHOME || true

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RULES_SRC="$SCRIPT_DIR/../src/forge_devices_realsense_camera/resources/70-realsense-libusb.rules"
EXPECTED_RULES_SHA256="e71c7b74961824b34b49f8c36dd84f818a998e0d8262863b3c9d6d69b0cfe1ce"
RULES_DIR="/etc/udev/rules.d"
RULES_DEST="$RULES_DIR/70-realsense-libusb.rules"
TEMP_RULE=""
COMPLETED_STEPS=()

cleanup() {
    if [ -n "$TEMP_RULE" ] && [ -e "$TEMP_RULE" ]; then
        rm -f -- "$TEMP_RULE"
    fi
}

report_partial_failure() {
    status=$?
    if [ "${#COMPLETED_STEPS[@]}" -gt 0 ]; then
        echo "[setup] 部分修改已经完成：" >&2
        for step in "${COMPLETED_STEPS[@]}"; do
            echo "  - $step" >&2
        done
        echo "[setup] 请根据以上错误处理，再运行 realsense-camera init-device 或直接启动相机节点确认状态。" >&2
    fi
    exit "$status"
}

trap cleanup EXIT
trap report_partial_failure ERR

if [ "$(id -u)" -ne 0 ]; then
    echo "请以 sudo 运行本脚本：sudo bash scripts/install_permissions.sh" >&2
    exit 1
fi

CALLER_USER=""
CALLER_UID=""
if [[ "${SUDO_UID:-}" =~ ^[1-9][0-9]*$ ]]; then
    CALLER_UID="$SUDO_UID"
elif [[ "${PKEXEC_UID:-}" =~ ^[1-9][0-9]*$ ]]; then
    CALLER_UID="$PKEXEC_UID"
fi
if [ -n "$CALLER_UID" ]; then
    CALLER_USER="$(getent passwd "$CALLER_UID" | cut -d: -f1)"
fi
if [ -n "${SUDO_USER:-}" ] && [ "$SUDO_USER" != "root" ]; then
    if [ -z "$CALLER_USER" ] || [ "$SUDO_USER" != "$CALLER_USER" ]; then
        echo "[setup] 错误：SUDO_USER 与 SUDO_UID 不一致。" >&2
        exit 1
    fi
fi

if [ -z "$CALLER_USER" ] || ! id "$CALLER_USER" >/dev/null 2>&1; then
    echo "[setup] 错误：无法确认实际普通调用用户；请通过 sudo 从目标用户会话运行。" >&2
    exit 1
fi
if [ "$(id -u "$CALLER_USER")" -ne "$CALLER_UID" ] || [ "$CALLER_UID" -le 0 ]; then
    echo "[setup] 错误：实际调用用户必须是 UID 大于 0 的普通用户。" >&2
    exit 1
fi
if ! getent group video >/dev/null 2>&1; then
    echo "[setup] 错误：系统不存在 video 用户组，请先由管理员确认系统用户组策略。" >&2
    exit 1
fi
if [ ! -f "$RULES_SRC" ] || [ -L "$RULES_SRC" ]; then
    echo "[setup] 错误：固定规则必须是普通文件且不能是符号链接：$RULES_SRC" >&2
    exit 1
fi
if grep -Eiq '(^|,)[[:space:]]*(RUN|PROGRAM|IMPORT)[{+:=]' "$RULES_SRC"; then
    echo "[setup] 错误：udev 规则不得包含 RUN、PROGRAM 或 IMPORT 指令。" >&2
    exit 1
fi
rules_sha256="$(sha256sum -- "$RULES_SRC" | cut -d ' ' -f1)"
if [ "$rules_sha256" != "$EXPECTED_RULES_SHA256" ]; then
    echo "[setup] 错误：udev 规则校验失败；请使用已审核版本。" >&2
    exit 1
fi

validate_root_directory() {
    directory="$1"
    if [ ! -d "$directory" ] || [ -L "$directory" ]; then
        echo "[setup] 错误：安全目录不存在、不是目录或为符号链接：$directory" >&2
        exit 1
    fi
    owner="$(stat -c %u "$directory")"
    mode="$(stat -c %a "$directory")"
    if [ "$owner" -ne 0 ] || (( (8#$mode & 0022) != 0 )); then
        echo "[setup] 错误：安全目录必须属于 root 且不可被 group/world 写入：$directory" >&2
        exit 1
    fi
}

validate_root_directory "/"
validate_root_directory "/etc"
validate_root_directory "/etc/udev"
validate_root_directory "$RULES_DIR"

if [ -e "$RULES_DEST" ] || [ -L "$RULES_DEST" ]; then
    if [ -L "$RULES_DEST" ] || [ ! -f "$RULES_DEST" ]; then
        echo "[setup] 错误：目标规则必须是普通文件且不能是符号链接：$RULES_DEST" >&2
        exit 1
    fi
    target_owner="$(stat -c %u "$RULES_DEST")"
    target_mode="$(stat -c %a "$RULES_DEST")"
    if [ "$target_owner" -ne 0 ] || (( (8#$target_mode & 0022) != 0 )); then
        echo "[setup] 错误：目标规则必须属于 root 且不可被 group/world 写入：$RULES_DEST" >&2
        exit 1
    fi
fi

# Existing vendor-provided RealSense rules may coexist with this restricted rule.
# This script never edits or removes those files.

echo "[setup] 本脚本不会调用包管理器；请事先安装发行版提供的 libusb 运行时。"

TEMP_RULE="$(mktemp "$RULES_DIR/.70-realsense-libusb.rules.XXXXXX")"
install -o root -g root -m 0644 "$RULES_SRC" "$TEMP_RULE"
temp_sha256="$(sha256sum -- "$TEMP_RULE" | cut -d ' ' -f1)"
if [ "$temp_sha256" != "$EXPECTED_RULES_SHA256" ]; then
    echo "[setup] 错误：临时 udev 规则校验失败。" >&2
    exit 1
fi
mv -fT -- "$TEMP_RULE" "$RULES_DEST"
TEMP_RULE=""
COMPLETED_STEPS+=("已原子安装 $RULES_DEST")
sync -f "$RULES_DIR"

if id -nG "$CALLER_USER" | tr ' ' '\n' | grep -qx video; then
    echo "[setup] 用户 $CALLER_USER 已属于 video 组。"
else
    usermod -aG video "$CALLER_USER"
    COMPLETED_STEPS+=("已将用户 $CALLER_USER 加入 video 组")
fi

udevadm control --reload-rules
COMPLETED_STEPS+=("已重新加载 udev 规则")
udevadm trigger
COMPLETED_STEPS+=("已触发 udev 设备更新")

echo "[setup] 完成："
for step in "${COMPLETED_STEPS[@]}"; do
    echo "  - $step"
done
echo "[setup] 请重新插拔 RealSense，并注销后重新登录以刷新用户组。"
