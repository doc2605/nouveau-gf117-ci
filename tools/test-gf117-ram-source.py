#!/usr/bin/env python3
"""Compile the actual patched kernel functions against mock BIOS/hardware.

No GPU access: callbacks count side effects. Requires the patched source tree.
This checks source behavior, not an independently reimplemented RAM model.
"""
import argparse
from pathlib import Path
import subprocess
import tempfile

ap = argparse.ArgumentParser()
ap.add_argument('source', type=Path)
a = ap.parse_args()
base = a.source / 'drivers/gpu/drm/nouveau'

def function(path, name):
    text = (base / path).read_text()
    start = text.index('\n' + name + '(') + 1
    body = text.index('{', start)
    depth = 1
    end = body + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return 'int\n' + text[start:end] + '\n'

header = (base / 'include/nvkm/subdev/fb.h').read_text()
start = header.index('struct nvkm_ram_dryrun {')
result_struct = header[start:header.index('\n};', start) + 3]
prelude = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <limits.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef int64_t s64;
#define abs(x) ((x)<0?-(x):(x))
#define U32_MAX UINT32_MAX
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define nv_clk_src_sppll0 2
#define nv_clk_src_sppll1 3
#define nv_clk_src_gpc 1
#define nv_clk_src_mem 0
#define NVKM_CLK_CSTATE_HIGHEST 0
struct nvkm_ram_dryrun;
struct nvkm_ram;
struct nvkm_bios { u8 bytes[1024]; };
struct nvkm_pci { int unused; };
struct nvkm_device;
struct nvkm_subdev { struct nvkm_device *device; };
struct nvkm_fb { struct nvkm_subdev subdev; struct nvkm_ram *ram; };
struct nvkm_ram_func {
 int (*calc)(struct nvkm_ram *, u32);
 int (*prog)(struct nvkm_ram *);
 void (*tidy)(struct nvkm_ram *);
};
struct nvkm_ram { struct nvkm_fb *fb; const struct nvkm_ram_func *func; };
struct gf100_ram { struct nvkm_ram base; };
#define gf100_ram(p) ((struct gf100_ram *)(p))
struct nvkm_cstate { u32 domain[2]; };
struct nvkm_pstate { struct nvkm_cstate base; int pcie_speed, pcie_width; };
struct nvkm_clk {
 struct nvkm_subdev subdev;
 struct { struct nvkm_pstate *one; } states;
 int pstate,state_nr;
};
#define list_for_each_entry(p,h,m) for ((p)=(h)->one; (p); (p)=NULL)
struct nvkm_device {
 struct nvkm_bios *bios; struct nvkm_clk *clk;
 struct nvkm_fb *fb; struct nvkm_pci *pci; int chipset; const char *cfgopt;
};
struct nvbios_ramcfg { int unused; };
static u8 map_ver=0x11, map_size=0x13, cfg_size=10, cfg_count=16;
static u8 strap_index=1, timing_ver=0x20, timing_size=0x33;
static int timing_missing, ref=500000, reads, pcie_writes, core_writes;
static int ram_calc_calls, ram_prog_calls, tidy_calls, calc_error, core_error;
static int selected_timing=-1, core_only, core_dryrun_error;
static int memory_clock=324000, core_clock=1548529;
static bool nvkm_boolopt(const char *options,const char *name,bool fallback)
{ (void)options;(void)fallback;return !strcmp(name,"NvReclockFermiCoreOnly") && core_only; }
static int nvkm_clk_dryrun(struct nvkm_clk *c,int state,struct nvkm_cstate *p)
{ (void)c;(void)state;p->domain[nv_clk_src_gpc]=1548529;return core_dryrun_error; }
static u32 nvbios_rammapEm(struct nvkm_bios *b, u32 f, u8 *v, u8 *h,
                          u8 *c, u8 *l, struct nvbios_ramcfg *cfg)
{ (void)b;(void)f;(void)cfg;*v=map_ver;*h=map_size;*c=cfg_count;*l=cfg_size;return 0x100; }
static u8 nvbios_ramcfg_index(struct nvkm_subdev *s) { (void)s; return strap_index; }
static u8 nvbios_rd08(struct nvkm_bios *b, u32 offset) { assert(offset<1024); return b->bytes[offset]; }
static u32 nvbios_timingEe(struct nvkm_bios *b, u8 index, u8 *v, u8 *h, u8 *c, u8 *l)
{ (void)b;selected_timing=index;*v=timing_ver;*h=timing_size;*c=0;*l=12;return timing_missing?0:0x200; }
static u32 nvkm_rd32(struct nvkm_device *d, u32 r) { (void)d;(void)r;reads++;return 0; }
static int nvkm_clk_read(struct nvkm_clk *c, int source)
{ (void)c;reads++;return source==nv_clk_src_mem?memory_clock:source==nv_clk_src_gpc?core_clock:ref; }
#define nvkm_error(...) ((void)0)
#define nvkm_debug(...) ((void)0)
static void nvkm_pcie_set_link(struct nvkm_pci *p,int s,int w) { (void)p;(void)s;(void)w;pcie_writes++; }
static int nvkm_cstate_prog(struct nvkm_clk *c,struct nvkm_pstate *p,int s) { (void)c;(void)p;(void)s;core_writes++;return core_error; }
static int ram_calc(struct nvkm_ram *r,u32 f) { (void)r;(void)f;ram_calc_calls++;return calc_error; }
static int ram_prog(struct nvkm_ram *r) { (void)r;ram_prog_calls++;return 0; }
static void ram_tidy(struct nvkm_ram *r) { (void)r;tidy_calls++; }
'''
wrapper = r'''
static int nvkm_ram_dryrun(struct nvkm_ram *r, u32 f, struct nvkm_ram_dryrun *p)
{ return gf100_ram_dryrun(r,f,p); }
'''
tests = r'''
int main(void) {
 struct nvkm_bios bios={0};
 struct nvkm_device dev={.bios=&bios,.chipset=0xd7};
 struct nvkm_clk clk={.subdev={.device=&dev},.pstate=-1,.state_nr=1};
 struct nvkm_ram_func ops={.calc=ram_calc,.prog=ram_prog,.tidy=ram_tidy};
 struct nvkm_fb fb={.subdev={.device=&dev}};
 struct gf100_ram ram={.base={.fb=&fb,.func=&ops}};
 struct nvkm_pstate state={.base={.domain={1001000}}};
 struct nvkm_ram_dryrun plan;
 dev.clk=&clk;dev.fb=&fb;fb.ram=&ram.base;clk.states.one=&state;
 assert(nvkm_pstate_prog(&clk,-1)==-EINVAL);
 assert(nvkm_pstate_prog(&clk,1)==-EINVAL);
 assert(reads==0 && pcie_writes==0 && core_writes==0);
 /* GF117's config 1: ID at byte 0, flags at byte 1 must be ignored. */
 bios.bytes[0x100+0x13+10]=2;bios.bytes[0x100+0x13+10+1]=16;
 assert(gf100_ram_dryrun(&ram.base,1001000,&plan)==-EOPNOTSUPP);
 assert(plan.rammap_ver==0x11 && plan.timing_ver==0x20);
 assert(plan.timing_present && selected_timing==2 && plan.timing_index==2);
 assert(!strcmp(plan.failure_stage,"ram-sequence-unimplemented"));
 assert(reads==0);
 assert(nvkm_pstate_prog(&clk,0)==-EOPNOTSUPP);
 assert(clk.pstate==-1 && pcie_writes==0 && core_writes==0);
 assert(ram_calc_calls==0 && ram_prog_calls==0 && tidy_calls==0);
 strap_index=16;
 assert(gf100_ram_dryrun(&ram.base,1001000,&plan)==-EINVAL);
 assert(!strcmp(plan.failure_stage,"ramcfg"));strap_index=1;
 timing_size=0x32;
 assert(gf100_ram_dryrun(&ram.base,1001000,&plan)==-EINVAL);
 assert(!strcmp(plan.failure_stage,"timing"));timing_size=0x33;
 timing_missing=1;
 assert(gf100_ram_dryrun(&ram.base,1001000,&plan)==-EINVAL);timing_missing=0;
 /* Legacy v0x10 reads timing at +1 and retains divider arithmetic. */
 map_ver=0x10;map_size=14;cfg_size=14;timing_ver=0x10;timing_size=25;
 bios.bytes[0x100+14+14]=99;bios.bytes[0x100+14+14+1]=3;
 assert(gf100_ram_dryrun(&ram.base,1001000,&plan)==0);
 assert(selected_timing==3 && plan.rounded_khz==500000 && !plan.failure_stage);
 ref=INT_MAX;
 assert(gf100_ram_dryrun(&ram.base,1001000,&plan)==0);ref=500000;
 /* A later RAM error must also prevent core programming and state update. */
 calc_error=-EIO;
 assert(nvkm_pstate_prog(&clk,0)==-EIO);
 assert(clk.pstate==-1 && core_writes==0 && ram_prog_calls==0 && tidy_calls==1);
 calc_error=0;core_error=-EIO;
 assert(nvkm_pstate_prog(&clk,0)==-EIO && clk.pstate==-1);
 core_error=0;
 assert(nvkm_pstate_prog(&clk,0)==0 && clk.pstate==0);
 /* Core-only mode must leave all RAM/PCIe callbacks unused. */
 map_ver=0x11;map_size=19;cfg_size=10;timing_ver=0x20;timing_size=51;
 core_only=1;clk.pstate=-1;
 int old_ram=ram_calc_calls, old_prog=ram_prog_calls, old_pcie=pcie_writes;
 assert(nvkm_pstate_prog(&clk,0)==0 && clk.pstate==0);
 assert(ram_calc_calls==old_ram && ram_prog_calls==old_prog && pcie_writes==old_pcie);
 core_dryrun_error=-EINVAL;int old_core=core_writes;
 assert(nvkm_pstate_prog(&clk,0)==-EINVAL && core_writes==old_core);
 core_dryrun_error=0;memory_clock=0;
 assert(nvkm_pstate_prog(&clk,0)==-ENODEV && core_writes==old_core);
 memory_clock=324000;core_error=-ETIMEDOUT;
 assert(nvkm_pstate_prog(&clk,0)==-ETIMEDOUT && clk.pstate==-1);
 core_error=0;core_clock=500000;
 assert(nvkm_pstate_prog(&clk,0)==-EIO && clk.pstate==-1);
 core_clock=1548529;dev.chipset=0xe0;
 assert(!nvkm_clk_fermi_core_only(&clk));
 puts("ok: core-only path skips PCIe/RAM and checks dry-run, memory, core errors and readback");
 puts("ok: actual kernel dry-run parses 0x11/0x20, correct timing offset and sizes");
 puts("ok: unsupported GF117 transition causes zero PCIe/RAM/core programming calls");
 puts("ok: RAM/core failures preserve pstate; legacy divider and success path checked");
 return 0;
}
'''
source = prelude + result_struct + '\n'
source += function('nvkm/subdev/clk/base.c', 'nvkm_clk_fermi_core_only')
source += function('nvkm/subdev/fb/ramgf100.c', 'gf100_ram_dryrun')
source += wrapper + function('nvkm/subdev/clk/base.c', 'nvkm_pstate_prog') + tests
with tempfile.TemporaryDirectory(prefix='gf117-source-test-') as d:
    c = Path(d)/'test.c'; exe = Path(d)/'test'; c.write_text(source)
    subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                    '-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
    subprocess.run([str(exe)],check=True)
