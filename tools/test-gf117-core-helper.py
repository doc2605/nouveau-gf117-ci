#!/usr/bin/env python3
"""Exercise helper journal/clock parsing with fixtures, never execute --apply."""
from pathlib import Path
import subprocess
import tempfile
s=Path(__file__).with_name('test-gf117-core-once.sh').read_text()
probe_start=s.index('if (( probe_only )); then', s.index('plan=$(cat "$debugfs/pstate_plan")'))
clock_request=s.index('clock_attempted=1', probe_start)
probe_branch=s[probe_start:clock_request]
assert 'gf117_pwm_diag' in probe_branch
assert 'Sonda concluída: nenhum pedido de clock foi escrito.' in probe_branch
assert "printf '0f\\n'" not in probe_branch
def function(name):
    a=s.index(name+'() {');b=s.index('\n}',a)+2
    return s[a:b]+'\n'
constants='\n'.join(x for x in s.splitlines() if x.startswith(('kernel_fault_pattern=','stock_vga_pattern=','stock_gr_pattern=')))
body='set -euo pipefail\n'+constants+'''
stock_removed=1;custom_loaded=0
new_kernel_log() { printf '%s\\n' "$journal_fixture"; }
'''+function('check_voltage_plan')+function('check_faults')+function('check_stock_unload_faults')+function('check_gpu_idle')+function('read_clocks')+function('select_temperature')+function('read_temperature')+function('wait_target_clock')+'''
(
 fuser() { return 1; }
 check_gpu_idle fake
 fuser() { return 0; }
 if check_gpu_idle fake; then echo 'GPU ocupada aceita';exit 1;fi
 fuser() { echo 'cannot stat GPU' >&2;return 1; }
 if check_gpu_idle fake; then echo 'erro fuser aceito';exit 1;fi
 fuser() { return 2; }
 if check_gpu_idle fake; then echo 'erro fatal fuser aceito';exit 1;fi
)
plan='state=1 id=0 voltage=17 requested_core_khz=775000 calculated_core_khz=774264 requested_memory_khz=1001000
state=1 voltage_uv=850000 target_uv=850000 voltage_ready=1 voltage_temp_c=90'
check_voltage_plan
valid_plan=$plan
for plan in "${valid_plan/voltage_uv=850000/voltage_uv=-19}" "${valid_plan/voltage_ready=1/voltage_ready=0}" "${valid_plan/target_uv=850000/target_uv=0}" "${valid_plan/state=1 voltage_uv/state=0 voltage_uv}" "$valid_plan
$valid_plan"; do
 if check_voltage_plan; then echo 'preflight invalido aceito';exit 1;fi
done
known='2026-10-16T19:53:14-03:00 cachyos kernel: nouveau 0000:08:00.0: bus: MMIO write of ffff8e1f FAULT at 6013d4 [ PRIVRING ]'
gr_known='2026-10-16T20:13:00-03:00 cachyos kernel: nouveau 0000:08:00.0: bus: MMIO write of badf1001 FAULT at 50405c [ PRIVRING ]'
journal_fixture="$known
$gr_known"
check_stock_unload_faults fake
if check_faults fake; then echo 'GR novo aceito';exit 1;fi
for bad in "${gr_known/badf1001/badf1003}" "${gr_known/08:00.0/09:00.0}" "$gr_known
$gr_known"; do
 journal_fixture="$known
$bad"
 if check_stock_unload_faults fake; then echo 'GR inesperado aceito';exit 1;fi
done
journal_fixture=$known
check_stock_unload_faults fake
if check_faults fake; then echo 'falha VGA nova aceita';exit 1;fi
for new in 'nouveau 0000:08:00.0: MMIO FAULT at 50405c [PRIVRING]' 'WARNING: nvkm/engine/fifo/runl.c:257' 'BUG: kernel failure' 'nouveau: fifo: CTXSW_TIMEOUT'; do
 journal_fixture="$known
$new"
 if check_stock_unload_faults fake; then echo 'falha adicional aceita';exit 1;fi
done
journal_fixture=${known/ffff8e1f/ffff8e3f}
if check_stock_unload_faults fake; then echo 'index diferente aceito';exit 1;fi
journal_fixture=${known/08:00.0/09:00.0}
if check_stock_unload_faults fake; then echo 'outra GPU aceita';exit 1;fi
journal_fixture="$known
$known
$known"
if check_stock_unload_faults fake; then echo 'falhas repetidas aceitas';exit 1;fi
journal_fixture="$known
$(printf '%1048576s' x)"
if check_faults fake; then echo 'journal grande com fault aceito';exit 1;fi
(
 new_kernel_log() { return 2; }
 if check_faults fake; then echo 'erro journal experimental aceito';exit 1;fi
 if check_stock_unload_faults fake; then echo 'erro journal original aceito';exit 1;fi
)
(
 journal_fixture=$known
 rg() { return 2; }
 if check_faults fake; then echo 'erro rg experimental aceito';exit 1;fi
 if check_stock_unload_faults fake; then echo 'erro rg original aceito';exit 1;fi
)
custom_loaded=1;journal_fixture=$known
if check_stock_unload_faults fake; then echo 'exceção aplicada no módulo novo';exit 1;fi
debugfs=$1
printf 'core 774 MHz\\nmemory 324 MHz\\n' > "$debugfs/pstate_current"
read_clocks
[[ $core == 774 && $memory == 324 ]]
printf 'core unknown MHz\\nmemory 324 MHz\\n' > "$debugfs/pstate_current"
if read_clocks; then echo 'clock inválido aceito';exit 1;fi
(
 cat() { printf 'core 774 MHz\\nmemory 324 MHz\\n';return 2; }
 if read_clocks; then echo 'amostra parcial com erro aceita';exit 1;fi
)
device="$1/gpu";hwmon_root="$1/hwmon";temperature_path='';temperature_source=''
mkdir -p "$device" "$hwmon_root/hwmon4"
printf 'dell_smm\\n' > "$hwmon_root/hwmon4/name"
printf 'CPU\\n' > "$hwmon_root/hwmon4/temp1_label"
printf '90000\\n' > "$hwmon_root/hwmon4/temp1_input"
printf 'GPU\\n' > "$hwmon_root/hwmon4/temp5_label"
printf '42000\\n' > "$hwmon_root/hwmon4/temp5_input"
read_temperature
[[ $temperature_path == "$hwmon_root/hwmon4/temp5_input" && $temperature == 42000 && $temperature_source == dell_smm:GPU ]]
for value in 0 80000 193000 invalid; do
 printf '%s\\n' "$value" > "$temperature_path"
 if read_temperature; then echo 'temperatura inválida aceita';exit 1;fi
done
printf '42000\\n' > "$hwmon_root/hwmon4/temp5_input"
printf 'GPU\\n' > "$hwmon_root/hwmon4/temp6_label"
printf '44000\\n' > "$hwmon_root/hwmon4/temp6_input"
temperature_path=''
if select_temperature; then echo 'sensores ambíguos aceitos';exit 1;fi
rm "$hwmon_root/hwmon4/temp6_label" "$hwmon_root/hwmon4/temp6_input"
rm "$hwmon_root/hwmon4/temp5_label" "$hwmon_root/hwmon4/temp5_input"
if select_temperature; then echo 'CPU usada como GPU';exit 1;fi
mkdir -p "$device/hwmon/hwmon9"
printf '47000\\n' > "$device/hwmon/hwmon9/temp1_input"
read_temperature
[[ $temperature_path == "$device/hwmon/hwmon9/temp1_input" && $temperature_source == nouveau && $temperature == 47000 ]]
(
 cat() { printf '47000\\n';return 2; }
 if read_temperature; then echo 'erro de leitura da temperatura aceito';exit 1;fi
)
(
 memory_before=324;load_cursor=fake;reads=0
 sleep() { :; }
 read_clocks() { reads=$((reads+1));memory=324;core=270;(( reads < 3 )) || core=774; }
 check_faults() { return 0; }
 read_temperature() { return 0; }
 wait_target_clock 750 780
 [[ $reads == 3 ]]
 reads=0
 read_clocks() { reads=$((reads+1));memory=324;core=270; }
 if wait_target_clock 750 780; then echo 'timeout aceito';exit 1;fi
 [[ $reads == 20 ]]
 read_clocks() { memory=405;core=774; }
 if wait_target_clock 750 780; then echo 'memoria alterada aceita';exit 1;fi
 read_clocks() { memory=324;core=774; }
 check_faults() { return 1; }
 if wait_target_clock 750 780; then echo 'fault durante espera aceito';exit 1;fi
)
echo 'ok: espera de clock limitada, timeout, memoria e faults verificados'
echo 'ok: fontes de temperatura GPU, limite de 80 C, ambiguidade e ausência verificados'
echo 'ok: exceções exatas de VGA/GR stock; falhas novas e outras GPUs bloqueadas; clocks validados'
'''
with tempfile.TemporaryDirectory(prefix='gf117-helper-test-') as d:
    r=subprocess.run(['bash','-c',body,'fixture',d],capture_output=True,text=True)
    if r.returncode:
        raise RuntimeError(r.stdout+r.stderr)
    print(r.stdout.splitlines()[-1])
