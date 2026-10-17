#!/usr/bin/env python3
"""Exercise real pstate worker/completion with a deliberately stalled pthread."""
import argparse,subprocess,tempfile
from pathlib import Path
ap=argparse.ArgumentParser();ap.add_argument('source',type=Path);a=ap.parse_args()
s=(a.source/'drivers/gpu/drm/nouveau/nvkm/subdev/clk/base.c').read_text()
def function(name,kind):
 start=s.index('\n'+name+'(')+1;end=s.index('\n}',start)+2
 return kind+'\n'+s[start:end]+'\n'
prelude=r"""
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdatomic.h>
#include <pthread.h>
#include <errno.h>
#include <stdio.h>
struct work_struct {int unused;};
struct nvkm_device {int unused;};
struct nvkm_subdev {struct nvkm_device *device;};
struct nvkm_clk {struct work_struct work;struct nvkm_subdev subdev;atomic_int waiting;
 int wait,pwrsrc,pstate,ustate_ac,ustate_dc,astate,dstate,state_nr,temp,fermi_reclock_error;};
#define container_of(p,t,m) ((t*)((char*)(p)-offsetof(t,m)))
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define READ_ONCE(x) __atomic_load_n(&(x),__ATOMIC_ACQUIRE)
#define WRITE_ONCE(x,v) __atomic_store_n(&(x),(v),__ATOMIC_RELEASE)
#define atomic_xchg(p,v) atomic_exchange((p),(v))
#define atomic_set(p,v) atomic_store((p),(v))
#define atomic_read(p) atomic_load((p))
#define wait_event(w,c) do{(void)(w);assert(c);}while(0)
#define nvkm_trace(...) ((void)0)
#define nvkm_error(...) ((void)0)
static bool enabled=true;
static int prog_calls,prog_error,scheduled,flushed,started,release_worker,wakes;
static pthread_t thread;
static pthread_mutex_t lock=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t cond=PTHREAD_COND_INITIALIZER;
static bool nvkm_clk_fermi_core_only(struct nvkm_clk *c){(void)c;return enabled;}
static int power_supply_is_system_supplied(void){
 pthread_mutex_lock(&lock);started=1;pthread_cond_broadcast(&cond);
 while(!release_worker)pthread_cond_wait(&cond,&lock);
 pthread_mutex_unlock(&lock);return 1;
}
static int nvkm_pstate_prog(struct nvkm_clk *c,int p){prog_calls++;if(!prog_error)c->pstate=p;return prog_error;}
static void wake_up_all(int *p){(void)p;wakes++;}
static void nvkm_pstate_work(struct work_struct *work);
static void *entry(void *w){nvkm_pstate_work(w);return NULL;}
static void schedule_work(struct work_struct *w){
 scheduled++;started=release_worker=0;assert(!pthread_create(&thread,NULL,entry,w));
 pthread_mutex_lock(&lock);while(!started)pthread_cond_wait(&cond,&lock);pthread_mutex_unlock(&lock);
}
static void flush_work(struct work_struct *w){
 (void)w;flushed++;pthread_mutex_lock(&lock);release_worker=1;
 pthread_cond_broadcast(&cond);pthread_mutex_unlock(&lock);assert(!pthread_join(thread,NULL));
}
"""
body=prelude+function('nvkm_pstate_work','static void')+function('nvkm_pstate_calc','static int')+r"""
int main(void){
 struct nvkm_clk clk={.state_nr=2,.pstate=-1,.ustate_ac=1,.ustate_dc=1};atomic_init(&clk.waiting,0);
 assert(nvkm_pstate_calc(&clk,true)==0);assert(flushed==1 && prog_calls==1 && clk.pstate==1);
 clk.pstate=-1;prog_error=-ETIMEDOUT;
 assert(nvkm_pstate_calc(&clk,true)==-ETIMEDOUT);assert(clk.fermi_reclock_error==-ETIMEDOUT);
 int before=scheduled,old_prog=prog_calls;
 assert(nvkm_pstate_calc(&clk,false)==-ETIMEDOUT);
 assert(nvkm_pstate_calc(&clk,true)==-ETIMEDOUT);
 assert(scheduled==before && prog_calls==old_prog);
 atomic_store(&clk.waiting,1);nvkm_pstate_work(&clk.work);assert(prog_calls==old_prog);
 /* Legacy GPUs retain their old wait contract; release the stalled worker manually. */
 enabled=false;clk.fermi_reclock_error=0;clk.pstate=-1;prog_error=0;
 before=flushed;assert(nvkm_pstate_calc(&clk,true)==0);
 assert(flushed==before && prog_calls==old_prog);flush_work(&clk.work);
 assert(prog_calls==old_prog+1 && wakes>=4);
 puts("ok: real GF117 worker completes before return, propagates errors and prevents automatic retries");
}
"""
with tempfile.TemporaryDirectory(prefix='gf117-worker-') as d:
 c=Path(d)/'test.c';exe=Path(d)/'test';c.write_text(body)
 subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-variable','-pthread','-fsanitize=undefined','-fno-sanitize-recover=all',str(c),'-o',str(exe)],check=True)
 subprocess.run([str(exe)],check=True,timeout=10)
