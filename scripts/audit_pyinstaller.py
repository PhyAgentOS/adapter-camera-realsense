#!/usr/bin/env python3
"""Extract and audit the outer executable and every ELF in a PyInstaller binary."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from PyInstaller.archive.readers import CArchiveReader

_SYMBOL_PATTERNS = {
    "glibc": re.compile(r"\bGLIBC_(\d+(?:\.\d+)+)\b"),
    "glibcxx": re.compile(r"\bGLIBCXX_(\d+(?:\.\d+)+)\b"),
    "cxxabi": re.compile(r"\bCXXABI_(\d+(?:\.\d+)+)\b"),
}
_RPATH_PATTERN = re.compile(r"\((?:RPATH|RUNPATH)\).*?\[(.*?)\]")
_NEEDED_PATTERN = re.compile(r"\(NEEDED\).*?\[(.*?)\]")
_INTERPRETER_PATTERN = re.compile(r"Requesting program interpreter:\s*([^\]]+)")


def _version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def _run(*args: str, env: dict[str, str] | None = None) -> str:
    result = subprocess.run(
        args,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"command failed ({result.returncode}): {' '.join(args)}\n{result.stdout}"
        )
    return result.stdout


def _safe_destination(root: Path, member: str) -> Path:
    relative = Path(member)
    if relative.is_absolute() or ".." in relative.parts:
        raise RuntimeError(f"unsafe archive member path: {member!r}")
    destination = (root / relative).resolve()
    if destination != root and root not in destination.parents:
        raise RuntimeError(f"archive member escapes extraction root: {member!r}")
    return destination


def _prepare_extract_dir(extract_dir: Path) -> Path:
    extract_dir = extract_dir.resolve()
    if extract_dir.exists():
        if not extract_dir.is_dir() or any(extract_dir.iterdir()):
            raise RuntimeError(
                f"extract directory must not exist or must be empty: {extract_dir}"
            )
        extract_dir.rmdir()
    extract_dir.mkdir(parents=True)
    return extract_dir


def _extract(binary: Path, root: Path) -> tuple[list[Path], list[dict[str, str]]]:
    archive = CArchiveReader(str(binary))
    files: list[Path] = []
    pending_symlinks: list[tuple[Path, str, str]] = []
    symlinks: list[dict[str, str]] = []

    for member, toc_entry in archive.toc.items():
        data = archive.extract(member)
        if not isinstance(data, bytes):
            continue
        destination = _safe_destination(root, member)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if toc_entry[-1] == "n":
            target_bytes = data.rstrip(b"\0")
            if b"\0" in target_bytes:
                raise RuntimeError(f"invalid symlink target for {member!r}")
            try:
                target = target_bytes.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise RuntimeError(f"invalid symlink target for {member!r}") from exc
            _safe_destination(root, target)
            pending_symlinks.append((destination, member, target))
            continue
        destination.write_bytes(data)
        files.append(destination)

    for destination, member, target in pending_symlinks:
        target_path = _safe_destination(root, target)
        if not target_path.exists():
            raise RuntimeError(
                f"archive symlink target is missing: {member!r} -> {target!r}"
            )
        destination.symlink_to(target)
        symlinks.append({"path": member, "target": target})

    return files, symlinks


def _highest_symbol(version_info: str, pattern: re.Pattern[str]) -> str | None:
    versions = set(pattern.findall(version_info))
    return max(versions, key=_version_key) if versions else None


def _safe_origin_path(component: str, *, origin: Path, allowed_root: Path) -> bool:
    prefixes = ("$ORIGIN", "${ORIGIN}")
    for prefix in prefixes:
        if component == prefix:
            resolved = origin.resolve()
            break
        if component.startswith(prefix + "/"):
            resolved = (origin / component[len(prefix) + 1 :]).resolve()
            break
    else:
        return False
    allowed_root = allowed_root.resolve()
    return resolved == allowed_root or allowed_root in resolved.parents


def _header_summary(header: str) -> dict[str, str]:
    wanted = {"Class", "Data", "Machine", "Type"}
    summary: dict[str, str] = {}
    for line in header.splitlines():
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key in wanted:
            summary[key.lower()] = value
    return summary


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit(binary: Path, extract_dir: Path) -> dict[str, object]:
    binary = binary.resolve(strict=True)
    extract_dir = _prepare_extract_dir(extract_dir)
    extracted, symlinks = _extract(binary, extract_dir)

    candidates: list[tuple[str, Path, Path]] = [
        ("<outer-executable>", binary, binary.parent)
    ]
    for path in extracted:
        if path.read_bytes()[:4] == b"\x7fELF":
            candidates.append((str(path.relative_to(extract_dir)), path, extract_dir))

    loader_env = os.environ.copy()
    loader_env["LD_LIBRARY_PATH"] = str(extract_dir)

    maxima: dict[str, tuple[str, str] | None] = {
        name: None for name in _SYMBOL_PATTERNS
    }
    entries: list[dict[str, object]] = []
    missing_dependencies: list[dict[str, object]] = []
    unsafe_search_paths: list[dict[str, str]] = []
    incompatible_elf: list[dict[str, str]] = []
    hashes: dict[str, list[str]] = {}

    for relative, path, allowed_root in candidates:
        file_output = _run("file", str(path)).strip()
        if "ELF 64-bit LSB" not in file_output or "x86-64" not in file_output:
            incompatible_elf.append({"file": relative, "description": file_output})

        header = _run("readelf", "-h", str(path))
        program_headers = _run("readelf", "-l", str(path))
        version_info = _run("readelf", "--version-info", str(path))
        symbol_table = _run("objdump", "-T", str(path))
        dynamic = _run("readelf", "-d", str(path))
        symbols: dict[str, str | None] = {}
        combined_symbols = version_info + "\n" + symbol_table
        for name, pattern in _SYMBOL_PATTERNS.items():
            highest = _highest_symbol(combined_symbols, pattern)
            symbols[name] = highest
            current = maxima[name]
            if highest is not None and (
                current is None or _version_key(highest) > _version_key(current[0])
            ):
                maxima[name] = (highest, relative)

        search_paths = _RPATH_PATTERN.findall(dynamic)
        for search_path in search_paths:
            for component in search_path.split(":"):
                if component and not _safe_origin_path(
                    component, origin=path.parent, allowed_root=allowed_root
                ):
                    unsafe_search_paths.append({"file": relative, "path": component})

        needed = _NEEDED_PATTERN.findall(dynamic)
        if needed:
            ldd = subprocess.run(
                ("ldd", str(path)),
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=loader_env,
            )
            if ldd.returncode != 0 or "not found" in ldd.stdout:
                missing_dependencies.append(
                    {
                        "file": relative,
                        "returncode": ldd.returncode,
                        "ldd": ldd.stdout,
                    }
                )

        digest = _sha256(path)
        hashes.setdefault(digest, []).append(relative)
        interpreter_match = _INTERPRETER_PATTERN.search(program_headers)
        entries.append(
            {
                "path": relative,
                "file": file_output,
                "header": _header_summary(header),
                "interpreter": (
                    interpreter_match.group(1).strip() if interpreter_match else None
                ),
                "needed": needed,
                "symbols": symbols,
                "search_paths": search_paths,
                "sha256": digest,
            }
        )

    duplicate_payloads = [
        paths for paths in hashes.values() if len(paths) > 1
    ]
    pyrealsense_extensions = [
        entry["path"]
        for entry in entries
        if re.search(r"(^|/)pyrealsense2[^/]*\.so(?:\.|$)", str(entry["path"]))
    ]

    return {
        "binary": str(binary),
        "archive_members": len(extracted) + len(symlinks),
        "symlinks": symlinks,
        "elf_count": len(candidates),
        "maxima": {
            name: None if value is None else {"version": value[0], "file": value[1]}
            for name, value in maxima.items()
        },
        "missing_dependencies": missing_dependencies,
        "unsafe_search_paths": unsafe_search_paths,
        "incompatible_elf": incompatible_elf,
        "duplicate_elf_payloads": duplicate_payloads,
        "pyrealsense2_extensions": pyrealsense_extensions,
        "host_runtime_check": (
            "ldd resolution used the current host plus the PyInstaller extraction root; "
            "repeat in the declared minimum target image"
        ),
        "elf_files": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--extract-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = audit(args.binary, args.extract_dir)
    except (OSError, RuntimeError) as exc:
        print(f"audit failed: {exc}", file=sys.stderr)
        return 1

    output = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
    print(output, end="")

    pyrealsense_extensions = report.get("pyrealsense2_extensions")
    pyrealsense_count = (
        len(pyrealsense_extensions)
        if isinstance(pyrealsense_extensions, list)
        else 0
    )
    failures = (
        (not report["elf_count"], "no ELF objects found"),
        (bool(report["missing_dependencies"]), "unresolved ELF dependencies"),
        (bool(report["unsafe_search_paths"]), "unsafe RPATH/RUNPATH entries"),
        (bool(report["incompatible_elf"]), "non-x86_64 or incompatible ELF objects"),
        (
            pyrealsense_count != 1,
            "expected exactly one bundled pyrealsense2 extension",
        ),
    )
    for failed, message in failures:
        if failed:
            print(f"audit failed: {message}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
