# Security Policy

## Supported versions

Security fixes are provided for the latest published `1.x` release. Older releases may be assessed, but users should first reproduce the issue on the latest release when it is safe to do so.

## Reporting a vulnerability

Do not report security vulnerabilities through public issues.

Until a dedicated security address is published, use the private contact channel listed on the public repository profile or contact the maintainers directly. Include:

- A description of the issue and affected version.
- Reproduction steps or proof-of-concept code, if safe to share.
- Potential impact and required hardware or permissions.
- Suggested mitigations, if known.

Do not attach private camera images, depth or IR captures, device serial numbers, hardware credentials, API tokens, internal URLs, or unsanitized logs. Maintainers should acknowledge reports promptly and coordinate disclosure timing with the reporter.

## Scope

Security-sensitive areas include:

- Parsing and validating native SDK frame dimensions and buffers.
- Image allocation, pixel conversion, encoding, and snapshot paths.
- Device discovery, serial-number handling, USB access, and hardware reset behavior.
- Dora output, metadata, Arrow messages, and network boundaries.
- Administrator scripts, binary `init-device`, udev rules, and group membership changes.
- PyInstaller native libraries, embedded licenses, ELF compatibility, and the release supply chain.

The `pyrealsense2` wheel and release binary may bundle librealsense, but this does not remove the need to keep USB/udev runtimes and rules patched and correctly configured. Joining a hardware-access group or broadening udev permissions can grant access to cameras and other devices; only trusted users should receive that permission.
