"""Exercise the actual build-script URL guard against the observed ELF false positive."""
import re
import runpy
import subprocess
import tomllib
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/build_pyinstaller.sh"
PATTERN = re.search(r"LC_ALL=C grep -aR -E -l '([^']+)'", SCRIPT.read_text()).group(1)

def scan(data: bytes) -> bool:
    result = subprocess.run(["grep", "-aE", PATTERN], input=data, capture_output=True, env={"LC_ALL": "C"})
    assert result.returncode in (0, 1)
    return result.returncode == 0

def test_incomplete_upstream_elf_uri_is_not_a_private_url():
    assert not scan(b"\x7fELF\x00ssh://git@\xcf\x01\x00")
    assert not scan(b"ssh://git@\x00")

def test_valid_transport_urls_remain_blocked():
    for url in (b"git+ssh://ci@git.internal.example/repo", b"ssh://git@10.0.0.8/repo", b"ssh://git@[fd00::1]/repo", b"ssh://user:password@private.example/repo", b"ssh://git@[fe80::1%25eth0]/repo"):
        assert scan(b"\x00" + url + b"\x00")


def test_ci_and_build_script_use_the_same_url_guard():
    assert PATTERN in (SCRIPT.parents[1] / ".github/workflows/ci.yml").read_text()


def test_source_cli_version_matches_distribution_metadata():
    root = SCRIPT.parents[1]
    source_version = runpy.run_path(str(root / "src/forge_devices_realsense_camera/__init__.py"))["__version__"]
    project_version = tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    assert source_version == project_version
