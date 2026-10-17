# GF117 module CI

This workflow only builds and checks source with mock hardware. It does not
validate reclocking on a GPU. The bundled headers are the installed CachyOS
linux-cachyos-headers 7.2.9-2 build tree, including exact config and Module.symvers.
Large optional vmlinux/System.map/debug helpers are omitted; BTF can be skipped.
The official matching source tarball and the header bundle are SHA-256 checked.
Clang must report 23.1.1. Clang, LLVM, LLVM-libs and LLD are pinned to official
Arch Archive 23.1.1-1 packages using SHA-256 hashes and package signatures.
The artifact contains the compressed module, patch/source/config hashes, vermagic
and full build output. Workflow permission is contents:read.
The real-source harnesses cover core/voltage, RAM, VGA, CRTC, worker completion
and PLL calculation. Journal and helper parsing use fixtures without loading
the module or writing GPU registers.

The archive has only distro kernel build inputs. Proprietary driver files,
VBIOS dumps, notebook logs and local build outputs are not CI inputs.

Public CI: https://github.com/doc2605/nouveau-gf117-ci
Verified successful run with patches 0001-0013:
https://github.com/doc2605/nouveau-gf117-ci/actions/runs/38993610060
Compiled commit: d6cfd3bdb4df61581a2ce024ad638d50ee6b7602.
