# Releasing RealSense Camera

## Versioning

The project follows Semantic Versioning. Update the package version in `pyproject.toml`, regenerate `uv.lock`, update version-sensitive checks, and move relevant entries from `Unreleased` into a dated section in `CHANGELOG.md`.

The public repository is <https://github.com/Forgelab-Robotics/adapter-camera-realsense> and releases are cut from `master`.

## Release checks

Release from a clean, reviewed commit using a supported Python version:

```bash
uv lock --check
uv sync --frozen
uv run --frozen pytest tests -q
uv build
uv export --frozen --no-dev --no-emit-project --no-hashes \
  --format requirements-txt --output-file requirements-audit.txt
uvx pip-audit --requirement requirements-audit.txt
```

Confirm the wheel and sdist contain `LICENSE`, use only public dependency sources, and contain no generated captures, device identifiers, private paths, internal URLs, SDK files, or build artifacts.

Complete applicable hardware checks for device discovery, Color/Depth/left-IR/right-IR capture, alignment, snapshots, shutdown/reopen behavior, permissions, and failure modes affected by the release.

## Source release

Before creating a tag:

1. Confirm `pyproject.toml`, `uv.lock`, `README.md`, and `CHANGELOG.md` agree on the version and requirements.
2. Confirm the `master` working tree is clean and all CI jobs pass.
3. Confirm `dora-rs==0.4.1`, `forge-common==1.0.1`, and `forge-msgs==1.1.0` resolve from public PyPI.
4. Create an immutable annotated tag named `v<version>` at the validated commit.

Do not store PyPI or repository tokens in this repository. Published package versions and public release tags must never be replaced.

## Binary release contract

Build the Linux x86_64 single-file executable in a clean environment using locked dependencies:

```bash
bash scripts/build_pyinstaller.sh
dist/realsense_camera --version
dist/realsense_camera licenses > license-output.txt
dist/realsense_camera init-device
```

The first two commands must run without camera hardware or network access. `--version` must report the release version. `licenses` must include the project Apache-2.0 notice, X-ERA copyright, and notices for bundled dependencies including `dora-rs==0.4.1` and `pyrealsense2`. Exercise `init-device` on a release-like host and verify that its permission guidance is correct.

The public archive filename is exactly:

```text
realsense_camera-v<version>-linux-x86_64-glibc<minimum>.tar.gz
```

For version 1.0.0, the selected and tested release-host baseline is glibc 2.39. The archive is therefore named `realsense_camera-v1.0.0-linux-x86_64-glibc2.39.tar.gz`. The complete payload currently has a highest symbol requirement of `GLIBC_2.29`, but this project does not claim compatibility with hosts older than glibc 2.39.

The archive must contain exactly one non-directory entry, the executable named `realsense_camera`. Project and third-party license text must be embedded and available through `realsense_camera licenses`; do not add a separate license file, configuration, checksum, test utility, capture, or directory to the archive.

Create and verify the archive with an empty staging directory. These checks are release-blocking:

```bash
stage="$(mktemp -d)"
install -m 0755 dist/realsense_camera "$stage/realsense_camera"
archive="realsense_camera-v1.0.0-linux-x86_64-glibc2.39.tar.gz"
tar --sort=name \
  --owner=0 --group=0 --numeric-owner \
  --mtime='UTC 1970-01-01' \
  -C "$stage" -czf "$archive" realsense_camera
test "$(tar -tzf "$archive" | wc -l)" -eq 1
test "$(tar -tzf "$archive")" = "realsense_camera"
test "$(tar -tvzf "$archive" | awk '{print substr($1,1,1)}')" = "-"
test "$(tar --numeric-owner -tvzf "$archive" | awk '{print $2}')" = "0/0"
rm -rf "$stage"
```

For later releases, update both the version and the explicitly selected release-host glibc baseline. The normalized owner, group, and timestamp prevent release archives from leaking the build account or varying only because of local filesystem metadata. Inspect the resulting tar listing manually as well.

## Mandatory ELF ABI audit

A release is blocked until an ELF audit has been completed and retained with the release record. Audit the outer PyInstaller executable **and every bundled ELF object**, including the Python runtime, `pyrealsense2` extension, bundled librealsense libraries, NumPy/OpenCV/Arrow extensions, and any other shared objects. Auditing only the outer bootloader is insufficient.

Use version-matched PyInstaller inspection/extraction tooling in a disposable directory to inventory the one-file payload. For each ELF object:

1. Run `file` and `readelf -h` to confirm Linux x86_64 ELF format and architecture.
2. Run `readelf -l` and record the interpreter where applicable.
3. Run `readelf -d` and review `NEEDED`, `RPATH`, and `RUNPATH`; reject missing dependencies and unsafe search paths.
4. Run `readelf --version-info` and `objdump -T` to inventory required `GLIBC_*`, `GLIBCXX_*`, and `CXXABI_*` symbol versions.
5. Run `ldd` in a controlled release image and reject every `not found` result. Treat `ldd` output as a runtime check, not as a substitute for symbol-version inspection.
6. Determine and record the highest required `GLIBC_*` version across the complete extracted ELF set. For 1.0.0 this is `GLIBC_2.29`; it is audit evidence, not the advertised compatibility floor.
7. Smoke-test `--version`, `licenses`, `init-device`, device enumeration, and a real snapshot on the selected release-host baseline. For 1.0.0 that baseline is Linux x86_64 with glibc 2.39.

Record the build host, compiler/build tooling, Python and PyInstaller versions, full ELF inventory, per-object symbol requirements, selected release-host baseline, and hardware test result. If the bundled payload cannot be completely extracted and audited, do not release it.

## Final binary checks

Before upload:

- Confirm the archive has exactly the one executable described above.
- Confirm `realsense_camera --version` reports `<version>` and `realsense_camera licenses` works offline.
- Confirm the binary needs no system librealsense when the bundled `pyrealsense2` wheel includes it, while libusb/libudev and udev permissions remain documented runtime requirements.
- Scan both the executable and extracted payload for the current checkout path, credential-bearing SSH URLs, internal hosts, credentials, device serials, and other private build markers. Public upstream build paths embedded in third-party native libraries are provenance, not local checkout leakage.
- Record and publish the archive SHA-256 digest.
- Confirm all GitHub Actions jobs pass for the tagged commit.

Published binary archives and checksums are immutable. Any changed payload requires a new version and tag.
