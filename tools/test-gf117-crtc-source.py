#!/usr/bin/env python3
"""Exercise the real CRTC port and VBIOS-MMIO filters with counted mocks."""
import argparse
from pathlib import Path
import subprocess
import tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
root=a.source/'drivers/gpu/drm/nouveau/nvkm'
def fn(path,name,kind):
 s=(root/path).read_text();start=s.index('\n'+name+'(')+1;end=s.index('\n}',start)+2
 return kind+'\n'+s[start:end]+'\n'
prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;typedef uint16_t u16;typedef uint32_t u32;
#define NV_50 0x50
#define pr_warn_once(...) do { } while (0)
#define nvkm_warn(...) do { } while (0)
#define NV_40 0x40
struct nvkm_device;
struct nvkm_subdev { struct nvkm_device *device; };
struct nvkm_devinit { struct nvkm_subdev subdev; };
struct nvkm_device { int chipset,card_type;struct nvkm_devinit *devinit; };
struct nvbios_init { struct nvkm_subdev *subdev; };
static int reads8,writes8,reads32,writes32;static u32 last_addr;
static u8 nvkm_rd08(struct nvkm_device *d,u32 addr) { (void)d;reads8++;last_addr=addr;return 0x22; }
static void nvkm_wr08(struct nvkm_device *d,u32 addr,u8 data) { (void)d;(void)data;writes8++;last_addr=addr; }
static u32 nvkm_rd32(struct nvkm_device *d,u32 addr) { (void)d;reads32++;last_addr=addr;return 0x12345678; }
static void nvkm_wr32(struct nvkm_device *d,u32 addr,u32 data) { (void)d;(void)data;writes32++;last_addr=addr; }
static bool init_exec(struct nvbios_init *i) { (void)i;return true; }
'''
wrapper=r'''
static u32 init_nvreg(struct nvbios_init *i,u32 addr)
{ return gf100_devinit_mmio(i->subdev->device->devinit,addr & ~3U); }
'''
body=prelude+fn('engine/disp/vga.c','nvkm_rdport','u8')+fn('engine/disp/vga.c','nvkm_wrport','void')
body+=fn('engine/disp/vga.c','nvkm_rdvgac','u8')+fn('engine/disp/vga.c','nvkm_wrvgac','void')
body+=fn('subdev/devinit/gf100.c','gf100_devinit_mmio','u32')+wrapper
for name,kind in [('init_rd32','u32'),('init_wr32','void'),('init_mask','u32')]:body+=fn('subdev/bios/init.c',name,kind)
body+=r'''
struct nvif_object { int unused; };
struct drm_device { int unused; };
struct nouveau_drm { struct { struct { struct nvif_object object; struct { int chipset; } info; } device; } client; };
static struct nouveau_drm fake_drm;
static struct nouveau_drm *nouveau_drm(struct drm_device *d) { (void)d;return &fake_drm; }
#define NV_PRMCIO_CRX__COLOR 0x6013d4
#define NV_PRMCIO_CR__COLOR 0x6013d5
#define NV_PRMCIO_SIZE 0x2000
#define NV_CIO_SR_LOCK_INDEX 0x1f
#define NV_CIO_SR_LOCK_VALUE 0x99
#define NV_CIO_SR_UNLOCK_RW_VALUE 0x57
static int nvif_reads,nvif_writes;
static u8 nvif_rd08(struct nvif_object *o,u32 addr) { (void)o;nvif_reads++;last_addr=addr;return 0x22; }
static void nvif_wr08(struct nvif_object *o,u32 addr,u8 val) { (void)o;(void)val;nvif_writes++;last_addr=addr; }
static bool nv_heads_tied(struct drm_device *d) { (void)d;return false; }
'''
header=(a.source/'drivers/gpu/drm/nouveau/dispnv04/hw.h').read_text()
for name in ['NVWriteVgaCrtc','NVReadVgaCrtc','NVLockVgaCrtcs']:
 start=header.rfind('static inline',0,header.index(name+'('))
 end=header.index('\n}',header.index(name+'('))+2
 body+=header[start:end]+'\n'
body+=r'''
int main(void) {
 struct nvkm_device d={.chipset=0xd7,.card_type=0xc0};
 struct nvkm_devinit di={.subdev={.device=&d}};d.devinit=&di;
 struct nvbios_init i={.subdev=&di.subdev};
 for(int head=0;head<2;head++) {
  assert(nvkm_rdvgac(&d,head,0x1f)==0);
  nvkm_wrvgac(&d,head,0x1f,0x57);
  nvkm_wrport(&d,head,0x03d4,0x1f);
  assert(nvkm_rdport(&d,head,0x03d5)==0);
 }
 assert(reads8==0 && writes8==0);
 for(u32 addr=0x6013d4;addr<0x6013d8;addr++) {
  assert(gf100_devinit_mmio(&di,addr)==UINT32_MAX);
  assert(init_rd32(&i,addr)==0);
  init_wr32(&i,addr,0x8000001f);
  assert(init_mask(&i,addr,1,1)==0);
 }
 assert(reads32==0 && writes32==0);
 assert(gf100_devinit_mmio(&di,0x137000)==0x137000);
 init_wr32(&i,0x137000,1);assert(writes32==1 && last_addr==0x137000);
 assert(nvkm_rdport(&d,0,0x03c4)==0x22 && reads8==1);
 for(int chip=0;chip<2;chip++) {
  d.chipset=chip?0xe4:0xd9;
  assert(gf100_devinit_mmio(&di,0x6013d4)==0x6013d4);
  int old_w=writes32;init_wr32(&i,0x6013d4,0x1f);
  assert(writes32==old_w+1 && last_addr==0x6013d4);
  assert(nvkm_rdvgac(&d,0,0x1f)==0x22 && last_addr==0x6013d5);
 }
 struct drm_device drm={0};fake_drm.client.device.info.chipset=0xd7;
 for(int head=0;head<2;head++) {
  assert(NVReadVgaCrtc(&drm,head,0x1f)==0);
  NVWriteVgaCrtc(&drm,head,0x1f,0x57);
 }
 assert(!NVLockVgaCrtcs(&drm,false));assert(!NVLockVgaCrtcs(&drm,true));
 assert(nvif_reads==0 && nvif_writes==0);
 fake_drm.client.device.info.chipset=0xd9;
 assert(NVReadVgaCrtc(&drm,0,0x1f)==0x22);
 NVWriteVgaCrtc(&drm,0,0x1f,0x57);
 assert(nvif_reads==1 && nvif_writes==3);
 fake_drm.client.device.info.chipset=0x11;
 NVLockVgaCrtcs(&drm,false);
 assert(nvif_reads==2 && nvif_writes==8);
 puts("ok: DRM NVIF CRTC read/write/lock cause zero GF117 accesses; GF119 and NV11 preserved");
 puts("ok: GF117 CRTC port/indexed/MMIO paths perform zero accesses; ~0 skip sentinel verified");
 puts("ok: unrelated registers, GF119 and Kepler retain hardware access");
}
'''
with tempfile.TemporaryDirectory(prefix='gf117-crtc-test-') as d:
 c=Path(d)/'test.c';exe=Path(d)/'test';c.write_text(body)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-sign-compare','-fsanitize=undefined',
                 '-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
