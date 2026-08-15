#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PACKAGE_DIR}/dist"
WORK_DIR="${PACKAGE_DIR}/build/pyinstaller"
VENV_DIR="${PACKAGE_DIR}/.venv_build"

# Keep host Python and loader paths from contaminating the frozen payload.
unset PYTHONHOME PYTHONPATH LD_LIBRARY_PATH LD_LIBRARY_PATH_ORIG

cd "${PACKAGE_DIR}"
mkdir -p "${DIST_DIR}" "${WORK_DIR}"
rm -f "${DIST_DIR}/realsense_camera" "${DIST_DIR}/realsense_camera.exe"
rm -rf "${VENV_DIR}"
trap 'rm -rf "${VENV_DIR}"' EXIT

echo "==> [realsense_camera] 正在安装锁定依赖和 PyInstaller..."
UV_PROJECT_ENVIRONMENT="${VENV_DIR}" uv sync \
  --project "${PACKAGE_DIR}" \
  --frozen \
  --no-default-groups \
  --group build \
  --no-install-project \
  --managed-python \
  --python 3.12

LICENSE_BUNDLE="${WORK_DIR}/THIRD_PARTY_LICENSES.txt"
LICENSE_JSON="${WORK_DIR}/third-party-licenses.json"
echo "==> [realsense_camera] 正在生成内嵌许可证清单..."
"${VENV_DIR}/bin/pip-licenses" \
  --format=json \
  --with-license-file \
  --no-license-path \
  --ignore-packages dora-rs forge-devices-realsense-camera pyrealsense2 \
  > "${LICENSE_JSON}"
"${VENV_DIR}/bin/python" - "${LICENSE_JSON}" <<'PY'
import json
import sys
from importlib.metadata import version

entries = json.load(open(sys.argv[1], encoding="utf-8"))
invalid = [
    entry.get("Name", "<unknown>")
    for entry in entries
    if not str(entry.get("LicenseText") or "").strip()
    or str(entry.get("LicenseText")).strip().upper() == "UNKNOWN"
]
if invalid:
    raise SystemExit(f"missing dependency license text: {', '.join(invalid)}")
expected = {
    "dora-rs": "0.4.1",
    "pyrealsense2": "2.58.2.10647",
}
for distribution_name, expected_version in expected.items():
    actual = version(distribution_name)
    if actual != expected_version:
        raise SystemExit(
            f"manual notice version mismatch for {distribution_name}: "
            f"expected {expected_version}, installed {actual}"
        )
PY
{
  printf '%s\n\n' 'forge-devices-realsense-camera — Apache License 2.0'
  cat "${PACKAGE_DIR}/LICENSE"
  printf '\n\n%s\n\n' 'Third-party Python distributions and license texts'
  "${VENV_DIR}/bin/pip-licenses" \
    --format=plain-vertical \
    --with-license-file \
    --no-license-path \
    --ignore-packages dora-rs forge-devices-realsense-camera pyrealsense2
  printf '\n\n%s\n\n' 'Dependencies with separately maintained notices'
  cat "${SCRIPT_DIR}/licenses/dora-rs-0.4.1.txt"
  printf '\n\n'
  cat "${SCRIPT_DIR}/licenses/pyrealsense2-2.58.2.txt"
} > "${LICENSE_BUNDLE}"
if grep -Eq '/home/|file:///|git\+ssh://' "${LICENSE_BUNDLE}"; then
  echo "ERROR: 许可证清单包含私有 URL 或构建路径。" >&2
  exit 1
fi
chmod 0644 "${LICENSE_BUNDLE}"

echo "==> [realsense_camera] 验证 pyrealsense2 可导入..."
PYTHONPATH="${PACKAGE_DIR}/src" "${VENV_DIR}/bin/python" - <<'PY'
import forge_devices_realsense_camera.backend_realsense  # noqa: F401
print("==> [realsense_camera] pyrealsense2 import ok")
PY

echo "==> [realsense_camera] 开始使用 PyInstaller 进行打包..."
"${VENV_DIR}/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --distpath "${DIST_DIR}" \
  --workpath "${WORK_DIR}" \
  "${SCRIPT_DIR}/realsense_camera.spec"

BINARY="${DIST_DIR}/realsense_camera"
if [[ ! -f "${BINARY}" ]]; then
  echo "ERROR: ${BINARY} 未找到，请检查 PyInstaller 输出。" >&2
  exit 1
fi

AUDIT_DIR="${WORK_DIR}/audit-extracted"
AUDIT_REPORT="${WORK_DIR}/elf-audit.json"
rm -rf "${AUDIT_DIR}"
echo "==> [realsense_camera] 正在审计外层程序和全部内嵌 ELF..."
"${VENV_DIR}/bin/python" "${SCRIPT_DIR}/audit_pyinstaller.py" \
  "${BINARY}" \
  --extract-dir "${AUDIT_DIR}" \
  --output "${AUDIT_REPORT}" \
  >/dev/null
"${VENV_DIR}/bin/python" - "${AUDIT_REPORT}" <<'PY'
import json
import sys

report = json.load(open(sys.argv[1], encoding="utf-8"))
print(f"==> [realsense_camera] audited ELF objects: {report['elf_count']}")
for family, maximum in report["maxima"].items():
    if maximum:
        print(f"    {family.upper()}: {maximum['version']} ({maximum['file']})")
PY

VERSION_OUTPUT="${WORK_DIR}/version-output.txt"
LICENSE_OUTPUT="${WORK_DIR}/license-output.txt"
"${BINARY}" --version > "${VERSION_OUTPUT}"
grep -q '1.0.0' "${VERSION_OUTPUT}"
"${BINARY}" licenses > "${LICENSE_OUTPUT}"
grep -q 'Apache License' "${LICENSE_OUTPUT}"
grep -q 'dora-rs 0.4.1' "${LICENSE_OUTPUT}"
grep -q 'pyrealsense2' "${LICENSE_OUTPUT}"
"${BINARY}" init-device --help >/dev/null
if grep -aR -F -l "${PACKAGE_DIR}" "${BINARY}" "${AUDIT_DIR}"; then
  echo "ERROR: 构建产物包含当前 checkout 的绝对路径。" >&2
  exit 1
fi
if grep -aR -E -l 'git\+ssh://[^/[:space:]]+@|ssh://[^/[:space:]]+@' "${BINARY}" "${AUDIT_DIR}"; then
  echo "ERROR: 构建产物包含私有传输 URL。" >&2
  exit 1
fi

echo "Built and audited: ${BINARY}"
echo "ELF audit report: ${AUDIT_REPORT}"
