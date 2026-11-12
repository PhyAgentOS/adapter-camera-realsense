"""PyInstaller entrypoint preserving package-relative imports."""

from forge_devices_realsense_camera.main import main

if __name__ == "__main__":
    raise SystemExit(main())
