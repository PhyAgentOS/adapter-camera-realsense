# Changelog

All notable changes to this project are documented in this file.

The project follows Semantic Versioning. Dates use the `YYYY-MM-DD` format.

## Unreleased

## 1.1.0 - 2026-08-22

### Added

- Added optional Forge PointCloud v1 Dora output with organized XYZ/XYZRGB semantics, explicit optical-frame metadata, invalid-point handling, reference configuration, hardware-validation routing, `PointCloudView` sink decoding, and PyInstaller packaging support.
- Added immutable SDK-buffer detachment and low-copy `PointCloudBatch` publishing so high-throughput producers avoid Python lists and redundant Arrow payload copies.

### Changed

- Updated the public dependency to `forge-msgs==1.1.0` and isolated optional point-cloud setup, conversion, and publishing failures from existing Color, Depth, and IR outputs.

### Removed

- Removed the optional security-policy and code-of-conduct files to align the public documentation set across adapters.

## 1.0.0 - 2026-08-15

### Added

- Initial public Intel RealSense camera adapter release with Color, Depth, dual-IR capture, Dora streaming, snapshots, environment checks, and PyInstaller packaging.
- Apache-2.0 licensing and public package/repository metadata.
- Contributor, security, conduct, release, privacy, and continuous-integration documentation.
- Python 3.11 and 3.12 CI, package builds, dependency auditing, and binary release gates.

### Changed

- Replaced internal Forge Git dependencies with exact public PyPI dependencies `forge-common==1.0.1` and `forge-msgs==1.0.1`.
- Bounded runtime dependencies and required `pyrealsense2>=2.58.2,<3` while retaining `dora-rs==0.4.1`.

### Removed

- Removed environment-specific hardware baseline and parameter validation reports from the public tree.
