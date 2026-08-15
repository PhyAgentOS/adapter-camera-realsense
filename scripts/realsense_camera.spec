# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: build the RealSense dora node as a single executable.
#
# Usage from repository root:
#   bash scripts/build_pyinstaller.sh

import glob
import importlib.util
import os


def _collect_pyrealsense2_binaries():
    """Collect only adjacent SDK libraries missed by normal package analysis."""
    spec_mod = importlib.util.find_spec("pyrealsense2")
    if spec_mod is None or not spec_mod.origin:
        raise SystemExit(
            "PyInstaller: pyrealsense2 not found. Run uv sync before building RealSense."
        )

    origin = os.path.abspath(spec_mod.origin)
    site_dir = os.path.dirname(origin)
    out = []
    seen = set()

    def add(src: str, dest_dir: str = ".") -> None:
        src = os.path.abspath(src)
        if src in seen or not os.path.isfile(src):
            return
        seen.add(src)
        out.append((src, dest_dir))

    extensions = sorted(glob.glob(os.path.join(site_dir, "pyrealsense2*.so*")))
    if not extensions:
        raise SystemExit(
            "PyInstaller: pyrealsense2 native extension not found in installed wheel."
        )

    # PyInstaller collects the package extension through the hidden import. Do not
    # add it again at archive root. Only supplement adjacent SDK shared libraries.
    for pattern in ("librealsense2*.so*", "librealsense*.so*"):
        for path in glob.glob(os.path.join(site_dir, pattern)):
            add(path, ".")

    return out


_spec_dir = os.path.dirname(os.path.abspath(SPEC))
_node_dir = os.path.dirname(_spec_dir)
_src_dir = os.path.join(_node_dir, "src")

_realsense_bins = _collect_pyrealsense2_binaries()
_rule = os.path.join(
    _src_dir,
    "forge_devices_realsense_camera",
    "resources",
    "70-realsense-libusb.rules",
)
if not os.path.isfile(_rule):
    raise SystemExit(f"PyInstaller: bundled udev rule not found: {_rule}")
_license_bundle = os.path.join(
    _node_dir, "build", "pyinstaller", "THIRD_PARTY_LICENSES.txt"
)
if not os.path.isfile(_license_bundle):
    raise SystemExit(
        f"PyInstaller: license bundle not found: {_license_bundle}; "
        "use build_pyinstaller.sh."
    )

a = Analysis(
    [os.path.join(_spec_dir, "pyinstaller_entry.py")],
    pathex=[_src_dir],
    binaries=_realsense_bins,
    datas=[
        (
            os.path.join(_node_dir, "config", "sensor.example.yaml"),
            "config",
        ),
        (_rule, "forge_devices_realsense_camera/resources"),
        (_license_bundle, "."),
    ],
    hiddenimports=[
        "pyrealsense2",
        "forge_devices_realsense_camera.backend",
        "forge_devices_realsense_camera.backend_realsense",
        "forge_devices_realsense_camera.config",
        "forge_devices_realsense_camera.list_devices",
        "forge_devices_realsense_camera.snapshot",
        "forge_devices_realsense_camera.system_setup",
        "cv2",
        "numpy",
        "pyarrow",
        "pyarrow.lib",
        "yaml",
        "_yaml",
        "forge_msgs",
        "forge_msgs.image",
        "forge_common",
        "dora",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
# Keep normal distribution-provided libusb/libudev/glibc libraries external.
# Native libraries shipped inside Python wheels remain bundled.
a.exclude_system_libraries()

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="realsense_camera",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
