"""Exercise the actual build-script URL guard against the observed ELF false positive."""
import re
import subprocess
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
    for url in (b"git+ssh://ci@git.internal.example/repo", b"ssh://git@10.0.0.8/repo", b"ssh://git@[fd00::1]/repo"):
        assert scan(b"\x00" + url + b"\x00")
