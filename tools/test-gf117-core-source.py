#!/usr/bin/env python3
"""Exercise actual core/voltage and PLL stage functions with mock hardware."""
import argparse
from pathlib import Path
import subprocess
import tempfile

ap=argparse.ArgumentParser()
ap.add_argument('source',type=Path)
a=ap.parse_args()
root=a.source/'drivers/gpu/drm/nouveau/nvkm/subdev/clk'

def function(file,name,kind='int'):
    s=(root/file).read_text(); start=s.index('\n'+name+'(')+1
    b=s.index('{',start); end=b+1; depth=1
    while depth:
        depth+=(s[end]=='{')-(s[end]=='}');end+=1
    return kind+'\n'+s[start:end]+'\n'

common=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;typedef uint32_t u32;
#define min(a,b) ((a)<(b)?(a):(b))
#define ARRAY_SIZE(a) (int)(sizeof(a)/sizeof((a)[0]))
#include <limits.h>
struct nvkm_volt { int uv,target,set_error; bool unreadable,stuck; u32 max_uv; u8 max0_id,max1_id,max2_id,vid_nr;struct {u32 uv;} vid[4]; };
struct nvkm_therm { int unused; };
struct nvkm_clk;
struct nvkm_cstate { int voltage; };
struct nvkm_pstate { struct nvkm_cstate base; int list,fanspeed; };
struct nvkm_device { int chipset; const char *cfgopt; struct nvkm_volt *volt; struct nvkm_therm *therm; };
struct nvkm_subdev { struct nvkm_device *device; };
struct nvkm_clk_func {
 int (*calc)(struct nvkm_clk *,struct nvkm_cstate *);
 int (*prog)(struct nvkm_clk *);
 void (*tidy)(struct nvkm_clk *);
};
struct nvkm_clk { struct nvkm_subdev subdev; const struct nvkm_clk_func *func; int temp; };
static bool enabled=true;
static bool nvkm_boolopt(const char *config,const char *name,bool fallback)
{ (void)config;(void)name;(void)fallback;return enabled; }
#define nvkm_error(...) ((void)0)
static int boost_queries;
#define list_empty(x) ((void)(x),false)
static struct nvkm_cstate *nvkm_cstate_get(struct nvkm_clk *c,struct nvkm_pstate *p,int i)
{ (void)c;(void)i;boost_queries++;return &p->base; }
static struct nvkm_cstate *nvkm_cstate_find_best(struct nvkm_clk *c,struct nvkm_pstate *p,struct nvkm_cstate *s)
{ (void)c;(void)p;return s; }
static int fan_raise,fan_lower,volt_raise,volt_lower,calc_calls,prog_calls,tidy_calls;
static int calc_error,prog_error;
static int nvkm_therm_cstate(struct nvkm_therm *t,int f,int direction)
{ (void)t;(void)f;if(direction>0)fan_raise++;else fan_lower++;return 0; }
static int nvkm_volt_get(struct nvkm_volt *v) { return v->unreadable?-ENODEV:v->uv; }
static int nvkm_volt_map(struct nvkm_volt *v,int id,int temp) { (void)temp;if(id==42)return 950000;if(id==43)return -EIO;return v->target; }
static int nvkm_volt_set_id(struct nvkm_volt *v,int id,int min,int temp,int direction)
{ (void)id;(void)min;(void)temp;if(direction>0)volt_raise++;else volt_lower++;
  if(v->set_error)return v->set_error;
  if(direction>0 && v->uv<v->target && !v->stuck)v->uv=v->target;
  if(direction<0 && v->uv>v->target)v->uv=v->target;
  return 0; }
static int mock_calc(struct nvkm_clk *c,struct nvkm_cstate *s) { (void)c;(void)s;calc_calls++;return calc_error; }
static int mock_prog(struct nvkm_clk *c) { (void)c;prog_calls++;return prog_error; }
static void mock_tidy(struct nvkm_clk *c) { (void)c;tidy_calls++; }
'''
voltage_tests=r'''
int main(void) {
 struct nvkm_volt volt={.uv=900000,.target=850000,.max_uv=1200000,.max0_id=0xff,.max1_id=0xff,.max2_id=0xff,.vid_nr=1,.vid={{1000000}}};
 struct nvkm_therm therm={0};
 struct nvkm_device dev={.chipset=0xd7,.volt=&volt,.therm=&therm};
 struct nvkm_clk_func ops={.calc=mock_calc,.prog=mock_prog,.tidy=mock_tidy};
 struct nvkm_clk clk={.subdev={.device=&dev},.func=&ops};
 struct nvkm_pstate state={.base={.voltage=17}};
 assert(nvkm_cstate_prog(&clk,&state,0)==0 && prog_calls==1);
 assert(volt.uv==900000 && volt_lower==0 && fan_lower==0 && boost_queries==0);
 volt.target=1000000;
 assert(nvkm_cstate_prog(&clk,&state,0)==0 && volt.uv==1000000);
 int before=calc_calls;volt.unreadable=true;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ENODEV && calc_calls==before);volt.unreadable=false;
 dev.volt=NULL;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ENODEV && calc_calls==before);dev.volt=&volt;
 volt.target=-EINVAL;
 assert(nvkm_cstate_prog(&clk,&state,0)==-EINVAL && calc_calls==before);
 volt.target=1000000;volt.set_error=-ENODEV;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ENODEV && calc_calls==before);volt.set_error=0;
 volt.uv=900000;volt.stuck=true;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ERANGE && calc_calls==before);volt.stuck=false;
 prog_error=-ETIMEDOUT;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ETIMEDOUT);
 assert(volt.uv==1000000 && volt_lower==0 && fan_lower==0);
 int old_prog=prog_calls;prog_error=0;calc_error=-EINVAL;
 assert(nvkm_cstate_prog(&clk,&state,0)==-EINVAL && prog_calls==old_prog);
 assert(volt_lower==0 && fan_lower==0);
 calc_error=0;volt.uv=900000;volt.max0_id=42;int old_raise=volt_raise;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ERANGE && volt_raise==old_raise);
 volt.target=950000;volt.vid[0].uv=1000000;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ERANGE && volt_raise==old_raise);
 volt.max0_id=43;
 assert(nvkm_cstate_prog(&clk,&state,0)==-EIO && volt_raise==old_raise);
 volt.max0_id=0xff;volt.max_uv=0;
 assert(nvkm_cstate_prog(&clk,&state,0)==-ERANGE && volt_raise==old_raise);
 volt.max_uv=1200000;volt.target=1000000;
 dev.chipset=0xe0;
 assert(nvkm_cstate_prog(&clk,&state,0)==0 && boost_queries==1);
 puts("ok: actual cstate path rejects missing/unreadable/insufficient voltage before clock writes");
 puts("ok: core-only retains boot voltage/cooling and raised voltage on calculation/PLL errors");
 return 0;
}
'''
pll_prelude=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stdio.h>
typedef uint32_t u32;
struct nvkm_device { int chipset; const char *cfgopt; u32 crystal; };
struct nvkm_subdev { struct nvkm_device *device; };
struct nvkm_clk { struct nvkm_subdev subdev; };
struct gf100_clk_info { u32 freq,ssel,mdiv,dsrc,ddiv,coef; };
struct gf100_clk { struct nvkm_clk base; struct gf100_clk_info eng[16]; };
#define gf100_clk(p) ((struct gf100_clk *)(p))
#define ARRAY_SIZE(a) (int)(sizeof(a)/sizeof((a)[0]))
static bool enabled=true;
static int wait_count,fail_wait_number,final_divider_writes;
static u32 pll_coefficient=0x11401;
#define nv_clk_src_mpllsrc 1
#define nv_clk_src_mpllsrcref 2
static u32 read_div(struct gf100_clk *c,int i,u32 a,u32 b)
{ (void)c;(void)i;(void)a;(void)b;return 27000; }
static int nvkm_clk_read(struct nvkm_clk *c,int src) { (void)c;(void)src;return 27000; }
static bool nvkm_boolopt(const char *config,const char *name,bool fallback)
{ (void)config;(void)name;(void)fallback;return enabled; }
static u32 nvkm_rd32(struct nvkm_device *d,u32 reg)
{ (void)d;return (reg==0x137004 || reg==0xe804)?pll_coefficient:0x20001; }
static void nvkm_wr32(struct nvkm_device *d,u32 reg,u32 val) { (void)d;(void)reg;(void)val; }
static void nvkm_mask(struct nvkm_device *d,u32 reg,u32 mask,u32 val)
{ (void)d;(void)mask;(void)val;if(reg==0x137250)final_divider_writes++; }
static int wait_result(void) { wait_count++;return wait_count==fail_wait_number?-1:0; }
#define nvkm_msec(d,m,cond...) ({ (void)(d);(void)(m);do {cond}while(0);wait_result(); })
'''
pll_tests=r'''
int main(void) {
 struct nvkm_device dev={.chipset=0xd7,.crystal=27000};
 struct gf100_clk clk={.base={.subdev={.device=&dev}}};
 assert(read_pll(&clk,0x137000)==540000);
 pll_coefficient=0x11400;assert(read_pll(&clk,0x137000)==0);
 pll_coefficient=0x01401;assert(read_pll(&clk,0x137000)==0);
 assert(read_pll(&clk,0xe800)==540000);
 pll_coefficient=0x11401;
 clk.eng[0].freq=1548529;clk.eng[0].coef=1;clk.eng[0].ssel=1;
 for(int failure=1;failure<=3;failure++) {
  wait_count=0;fail_wait_number=failure;final_divider_writes=0;
  assert(gf100_clk_prog(&clk.base)==-ETIMEDOUT);
  assert(wait_count==failure && final_divider_writes==0);
 }
 wait_count=0;fail_wait_number=0;
 assert(gf100_clk_prog(&clk.base)==0 && final_divider_writes==1);
 dev.chipset=0xe0;wait_count=0;fail_wait_number=1;final_divider_writes=0;
 assert(gf100_clk_prog(&clk.base)==0 && final_divider_writes==1);
 dev.chipset=0xd7;enabled=false;wait_count=0;final_divider_writes=0;
 assert(gf100_clk_prog(&clk.base)==0 && final_divider_writes==1);
 puts("ok: actual PLL readback handles zero coefficients; all three timeouts stop opted-in GF117");
 return 0;
}
'''
volt_text=(a.source/'drivers/gpu/drm/nouveau/nvkm/subdev/volt/base.c').read_text()
vstart=volt_text.index('\nnvkm_volt_preflight(')+1;vend=volt_text.index('\n}',vstart)+2
common+='int\n'+volt_text[vstart:vend]+'\n'
voltage = common+function('base.c','nvkm_clk_fermi_core_only','bool')+function('base.c','nvkm_cstate_prog')+voltage_tests
pll = pll_prelude+function('gf100.c','read_pll','u32')+''.join(function('gf100.c','gf100_clk_prog_'+str(i)) for i in range(5))+function('gf100.c','gf100_clk_prog')+pll_tests
with tempfile.TemporaryDirectory(prefix='gf117-core-test-') as d:
    for name,source in [('voltage',voltage),('pll',pll)]:
        c=Path(d)/(name+'.c');exe=Path(d)/name;c.write_text(source)
        subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-fsanitize=undefined',
                        '-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
        subprocess.run([str(exe)],check=True)
