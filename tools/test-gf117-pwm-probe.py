#!/usr/bin/env python3
from pathlib import Path
import sys

root = Path(sys.argv[1])
debugfs = (root / "drivers/gpu/drm/nouveau/nouveau_debugfs.c").read_text()
base = (root / "drivers/gpu/drm/nouveau/nvkm/engine/device/base.c").read_text()
marker = "/* GF117 uses gf119_therm_new(). Expose the documented GF119 PWM"
assert marker in debugfs
probe = debugfs.split(marker, 1)[1].split("\n\t\t\t}", 1)[0]
for address in ("0x00d63c", "0x00e114", "0x00e118", "0x00e11c",
                "0x00e120", "0x0200d8", "0x0200dc"):
    assert address in probe, address
assert "nvif_rd32" in probe
for forbidden in ("nvif_wr32", "nvkm_wr32", "nvif_mask", "nvkm_mask"):
    assert forbidden not in probe, forbidden
nvd7 = base.split("nvd7_chipset =", 1)[1].split("};", 1)[0]
assert '.therm    = { 0x00000001, gf119_therm_new }' in nvd7
assert 'gf117_pwm_diag' in probe
print("GF117/GF119 PWM probe: read-only source checks passed")
