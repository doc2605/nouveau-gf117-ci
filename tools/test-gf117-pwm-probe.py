#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(sys.argv[1])
debugfs = (root / "drivers/gpu/drm/nouveau/nouveau_debugfs.c").read_text()
base = (root / "drivers/gpu/drm/nouveau/nvkm/engine/device/base.c").read_text()
therm = (root / "drivers/gpu/drm/nouveau/nvkm/subdev/therm/gf119.c").read_text()
marker = "/* GF117 uses gf119_therm_new(). Expose the documented GF119 PWM"
assert marker in debugfs
probe = debugfs.split(marker, 1)[1].split("\n\t\t\t}", 1)[0]
for address in ("0x00d63c", "0x00e114", "0x00e118", "0x00e11c",
                "0x00e120", "0x0200d8", "0x0200dc"):
    assert address in probe, address
assert "nvif_rd32" in probe
for forbidden in ("nvif_wr32", "nvkm_wr32", "nvif_mask", "nvkm_mask"):
    assert forbidden not in probe, forbidden
assert probe.index("u32 gpio11 = nvif_rd32") < probe.index("switch (pwm_index)")
assert "u32 div = 0, duty = 0;" in probe
channel_reads = {
    0: ("0x00e114", "0x00e118"),
    1: ("0x00e11c", "0x00e120"),
    2: ("0x0200d8", "0x0200dc"),
}
switch = probe.split("switch (pwm_index)", 1)[1]
for index, addresses in channel_reads.items():
    case = switch.split(f"case {index}:", 1)[1].split("break;", 1)[0]
    assert all(address in case for address in addresses), (index, addresses)
    for other_index, other_addresses in channel_reads.items():
        if index != other_index:
            assert not any(address in case for address in other_addresses), (index, other_index)
assert "default:\n\t\t\t\t\tbreak;" in switch
assert "selected=%08x/%08x" in probe
for mapping in ("case 0x00: case 0x1e: pwm_index = 2;",
                "case 0x19: pwm_index = 1;",
                "case 0x1c: pwm_index = 0;"):
    assert mapping in probe, mapping
nvd7 = base.split("nvd7_chipset =", 1)[1].split("};", 1)[0]
assert '.therm    = { 0x00000001, gf119_therm_new }' in nvd7
assert 'gf117_pwm_diag' in probe

# Compile the real GF119 mux decoder too, so the debugfs probe is compared
# against the production PWM routing rather than a second copied table.
pwm_info = therm[therm.index("\npwm_info(") + 1:]
pwm_info = "static int\n" + pwm_info.split("\n}\n", 1)[0] + "\n}"

# Compile and execute the actual diagnostic block with mocked MMIO reads.
# This verifies mux-to-channel routing and that invalid muxes touch no candidate
# register; it does not emulate hardware behavior or voltage measurement.
block = probe[probe.index("\n\t\t\t{"):]
block += "\n\t\t\t}"
harness = r'''#include <stdarg.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
struct nvif_object { int unused; };
struct nouveau_drm {
	struct { struct { struct nvif_object object; } device; } client;
};
struct seq_file { char text[256]; };
struct nvkm_device { int unused; };
struct nvkm_subdev { struct nvkm_device *device; };
struct nvkm_therm { struct nvkm_subdev subdev; };
static u32 gpio_value;
static u32 addresses[4];
static unsigned read_count;
static unsigned nvkm_gpio_reads;
static u32 nvkm_rd32(struct nvkm_device *device, u32 address)
{
	(void)device;
	if (address != 0x00d63c) return 0xffffffff;
	nvkm_gpio_reads++;
	return gpio_value;
}
#define nvkm_error(...) do { } while (0)
static u32 nvif_rd32(struct nvif_object *object, u32 address)
{
	(void)object;
	if (read_count < sizeof(addresses) / sizeof(addresses[0]))
		addresses[read_count] = address;
	read_count++;
	if (address == 0x00d63c) return gpio_value;
	if (address == 0x00e114) return 0x11141114;
	if (address == 0x00e118) return 0x11181118;
	if (address == 0x00e11c) return 0x111c111c;
	if (address == 0x00e120) return 0x11201120;
	if (address == 0x0200d8) return 0x20d820d8;
	if (address == 0x0200dc) return 0x20dc20dc;
	return 0xffffffff;
}
static int seq_printf(struct seq_file *m, const char *format, ...)
{
	va_list args;
	va_start(args, format);
	int ret = vsnprintf(m->text, sizeof(m->text), format, args);
	va_end(args);
	return ret;
}
/* PWM_INFO_FUNCTION */
static void run_probe(struct nouveau_drm *ndrm, struct seq_file *m)
{
/* PROBE_BLOCK */
}
static int check(u32 gpio, int index, u32 first, u32 second,
		 u32 div, u32 duty)
{
	struct nouveau_drm drm = {0};
	struct seq_file output = {0};
	struct nvkm_device device = {0};
	struct nvkm_therm pwm_therm = { .subdev = { .device = &device } };
	gpio_value = gpio;
	nvkm_gpio_reads = 0;
	int actual_index = pwm_info(&pwm_therm, 11);
	if (index < 0) {
		if (actual_index != -ENODEV || nvkm_gpio_reads != 1) return 6;
	} else if (actual_index != index || nvkm_gpio_reads != 1) {
		return 7;
	}
	read_count = 0;
	memset(addresses, 0, sizeof(addresses));
	run_probe(&drm, &output);
	if (addresses[0] != 0x00d63c) return 1;
	if (index < 0) {
		if (read_count != 1) return 2;
		if (!strstr(output.text, "pwm_index=-1 selected=00000000/00000000"))
			return 3;
		return 0;
	}
	if (read_count != 3 || addresses[1] != first || addresses[2] != second)
		return 4;
	char expected[96];
	snprintf(expected, sizeof(expected),
		 "pwm_index=%d selected=%08x/%08x", index, div, duty);
	return strstr(output.text, expected) ? 0 : 5;
}
int main(void)
{
	if (check(0x1c, 0, 0x00e114, 0x00e118, 0x11141114, 0x11181118)) return 10;
	if (check(0x59, 1, 0x00e11c, 0x00e120, 0x111c111c, 0x11201120)) return 11;
	if (check(0x00, 2, 0x0200d8, 0x0200dc, 0x20d820d8, 0x20dc20dc)) return 12;
	if (check(0x1e, 2, 0x0200d8, 0x0200dc, 0x20d820d8, 0x20dc20dc)) return 13;
	if (check(0x9c, -1, 0, 0, 0, 0)) return 14;
	if (check(0x01, -1, 0, 0, 0, 0)) return 15;
	return 0;
}
'''.replace("/* PROBE_BLOCK */", block).replace(
    "/* PWM_INFO_FUNCTION */", pwm_info)
with tempfile.TemporaryDirectory(prefix="gf117-pwm-probe-") as directory:
    source = Path(directory) / "probe.c"
    binary = Path(directory) / "probe"
    source.write_text(harness)
    subprocess.run(["cc", "-std=c11", "-Wall", "-Wextra", "-Werror",
                    str(source), "-o", str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
print("GF117/GF119 PWM probe: routed-source tests passed (mock reads only)")
