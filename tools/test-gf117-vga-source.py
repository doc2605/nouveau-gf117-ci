#!/usr/bin/env python3
"""Compile actual nvkm_lockvgac with counted register mocks; no GPU access."""
import argparse
from pathlib import Path
import subprocess
import tempfile
p=argparse.ArgumentParser();p.add_argument('source',type=Path);a=p.parse_args()
s=(a.source/'drivers/gpu/drm/nouveau/nvkm/engine/disp/vga.c').read_text()
start=s.index('\nnvkm_lockvgac(')+1;end=s.index('\n}',start)+2
function='bool\n'+s[start:end]+'\n'
prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define NV_50 0x50
struct nvkm_device { int chipset,card_type; };
static int reads,writes,read32s,last_head,last_index,last_value;
static u8 value=1;
static u8 nvkm_rdvgac(struct nvkm_device *d,int head,u8 index)
{ (void)d;assert(head==0 && index==0x1f);reads++;return value; }
static void nvkm_wrvgac(struct nvkm_device *d,int head,u8 index,u8 val)
{ (void)d;writes++;last_head=head;last_index=index;last_value=val; }
static u32 nvkm_rd32(struct nvkm_device *d,u32 reg)
{ (void)d;assert(reg==0x001084);read32s++;return 0; }
'''
tests=r'''
int main(void) {
 struct nvkm_device d={.chipset=0xd7,.card_type=0xc0};
 for(int lock=0;lock<2;lock++) {
  assert(!nvkm_lockvgac(&d,lock));
  assert(reads==0 && writes==0 && read32s==0);
 }
 for(int chip=0;chip<2;chip++) {
  d.chipset=chip?0xe4:0xd9;
  value=1;assert(!nvkm_lockvgac(&d,false));
  assert(last_index==0x3f && last_value==0x57);
  value=0;assert(nvkm_lockvgac(&d,true));
  assert(last_index==0x3f && last_value==0x99);
 }
 d.chipset=0x11;d.card_type=0x10;
 reads=writes=read32s=0;value=1;
 assert(!nvkm_lockvgac(&d,false));
 assert(reads==1 && writes==2 && read32s==1);
 assert(last_head==1 && last_index==0x1f && last_value==0x57);
 puts("ok: GF117 lock/unlock causes zero VGA accesses; GF119/Kepler/NV11 behavior preserved");
}
'''
with tempfile.TemporaryDirectory(prefix='gf117-vga-test-') as d:
 c=Path(d)/'test.c';exe=Path(d)/'test';c.write_text(prelude+function+tests)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                 '-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
