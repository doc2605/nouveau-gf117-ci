#!/usr/bin/env python3
"""Regression tests of the actual PLL calculator, rather than a duplicated model."""
import argparse,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);a=ap.parse_args()
s=(a.source/'drivers/gpu/drm/nouveau/nvkm/subdev/clk/pllgt215.c').read_text();start=s.index('\ngt215_pll_calc(')+1
body=r"""
#include <assert.h>
#include <stdint.h>
#include <stdbool.h>
#include <limits.h>
#include <errno.h>
#include <stdio.h>
typedef uint8_t u8;typedef uint32_t u32;typedef uint64_t u64;typedef int64_t s64;
struct nvkm_subdev {int unused;};
struct nvbios_pll {u32 refclk;u8 min_p,max_p;struct {u32 max_freq,min_inputfreq,max_inputfreq;u8 min_m,max_m,min_n,max_n;}vco1;};
#define max(a,b) ((a)>(b)?(a):(b))
#define min(a,b) ((a)<(b)?(a):(b))
#define div_u64(n,d) ((n)/(d))
#define unlikely(x) (x)
#define nvkm_error(...) ((void)(subdev))
"""+'int\n'+s[start:]+r"""
int main(void){
 struct nvkm_subdev sd={0};int n,m,p,f;
 struct nvbios_pll i={.refclk=27000,.min_p=1,.max_p=8,
 .vco1={.max_freq=1200000,.min_inputfreq=10000,.max_inputfreq=27000,.min_m=1,.max_m=8,.min_n=16,.max_n=255}};
 int ret=gt215_pll_calc(&sd,&i,775000,&n,NULL,&m,&p);assert(ret>750000 && ret<800000);
 assert(m>=1 && m<=8 && n>=16 && n<=255 && p>=1 && p<=8);
 assert((u64)i.vco1.min_inputfreq*m<=i.refclk && (u64)i.vco1.max_inputfreq*m>=i.refclk);
 assert(gt215_pll_calc(&sd,&i,775000,&n,&f,&m,&p)==775000);
 assert(f>=0 && f<=65535);
 i.vco1.min_inputfreq=i.vco1.max_inputfreq=27000;
 assert(gt215_pll_calc(&sd,&i,810000,&n,NULL,&m,&p)==810000 && m==1);
 i.vco1.min_inputfreq=10000;i.vco1.max_inputfreq=20000;
 assert(gt215_pll_calc(&sd,&i,775000,&n,NULL,&m,&p)>0 && m==2);
 assert(gt215_pll_calc(&sd,&i,UINT32_MAX,&n,&f,&m,&p)==-ERANGE);
 i.vco1.min_m=3;i.vco1.min_inputfreq=100000;i.vco1.max_inputfreq=100000;
 assert(gt215_pll_calc(&sd,&i,775000,&n,NULL,&m,&p)==-ERANGE);
 i.vco1.min_inputfreq=200000;
 assert(gt215_pll_calc(&sd,&i,775000,&n,NULL,&m,&p)==-EINVAL);
 assert(gt215_pll_calc(&sd,NULL,775000,&n,NULL,&m,&p)==-EINVAL);
 puts("ok: actual PLL calculator rejects empty M intervals, inverted input bounds and oversized return values");
}
"""
with tempfile.TemporaryDirectory(prefix='gf117-pll-') as d:
 c=Path(d)/'test.c';exe=Path(d)/'test';c.write_text(body)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-sign-compare','-fsanitize=undefined','-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True)
