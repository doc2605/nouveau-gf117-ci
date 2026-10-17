# Experimental GF117 Nouveau build CI

Build-only workspace for Nouveau patches targeting GF117 (Fermi), using
CachyOS kernel 7.2.9-2. This does not claim working reclocking, Vulkan support,
or game stability. No hardware is accessed in CI.

The workflow applies patches 0001–0010 to the exact official kernel source,
checks source functions against mocked hardware, and builds the module with
matching kernel headers, config and Module.symvers. The artifact includes the
compressed module, hashes, vermagic and complete log.

Kernel source: https://github.com/CachyOS/linux/releases/tag/cachyos-7.2.9-2
Source SHA-256: 2da9e6ffe31436657f46909db059059946dac22c2ac6cde05e49a66d61acfcba
Headers: distro linux-cachyos-headers 7.2.9-2. Optional vmlinux/System.map omitted.
Kernel files retain their upstream licenses. The matching full source release
contains their corresponding sources and license notices.

Only build scripts, patches, mock tests and distro headers are published here.
VBIOS dumps, proprietary NVIDIA files, notebook logs and private project
history are not included.
