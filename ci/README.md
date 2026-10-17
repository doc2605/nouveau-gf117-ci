# GF117 module CI

This workflow only builds and checks source with mock hardware. It does not
validate reclocking on a GPU. The bundled headers are the installed CachyOS
linux-cachyos-headers 7.2.9-2 build tree, including exact config and Module.symvers.
Large optional vmlinux/System.map/debug helpers are omitted; BTF can be skipped.
The official matching source tarball and the header bundle are SHA-256 checked.
Clang must report 23.1.1. Package updates that change this version fail explicitly.
The artifact contains the compressed module, patch/source/config hashes, vermagic
and full build output. Workflow permission is contents:read.

The archive has only distro kernel build inputs. Proprietary driver files,
VBIOS dumps, notebook logs and local build outputs are not CI inputs.
