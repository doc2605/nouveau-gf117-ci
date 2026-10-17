#!/usr/bin/env bash
# Teste físico explícito GF117: carga temporária, sem instalar módulo.
set -euo pipefail
probe_only=0
case "${1:-}" in
    --help|-h|'')
        echo "Uso: sudo $0 --probe-only"
        echo "Lê GPIO/PWM candidato, sem solicitar mudança de clock."
        echo "Para o teste de clock: sudo $0 --apply (exige GPU ociosa e TTY)."
        exit 0 ;;
    --probe-only) [[ $# == 1 ]] || exit 2; probe_only=1 ;;
    --apply) [[ $# == 1 ]] || exit 2 ;;
    *) echo "Argumento inválido; use --help" >&2; exit 2 ;;
esac
[[ $EUID == 0 ]] || { echo "Execute com sudo." >&2; exit 2; }
module=/home/doc/Nvidia-GT720M-Fix-atualizado/artifacts/github-actions/39002141912/gf117-nouveau-7d85a2d10ebf903fa0c8cc08c835e796ee508dcd/nouveau.ko
expected_hash=a6486b2bfd84958ffa7e83b19192b5078872b4068c540a2fd8d68e9d47455344
device=/sys/bus/pci/devices/0000:08:00.0
debugfs=/sys/kernel/debug/dri/0000:08:00.0
hwmon_root=/sys/class/hwmon
temperature_path=
temperature_source=
log_dir=/home/doc/teste-logs
home_owner=$(stat -c '%u:%g' /home/doc)
install -d -m 0755 -o "${home_owner%:*}" -g "${home_owner#*:}" "$log_dir"
log_file="$log_dir/clock-$(date +%Y%m%d-%H%M%S-%N).log"
touch "$log_file"; chown "$home_owner" "$log_file"; chmod 0644 "$log_file"
exec > >(tee -a "$log_file") 2>&1
echo "log: $log_file"
echo "started: $(date --iso-8601=seconds)"
if (( probe_only )); then
    echo "SONDA FÍSICA SOMENTE LEITURA: sem solicitação de p-state/clock"
else
    echo "TESTE FÍSICO: núcleo VBIOS 0f, RAM preservada, noaccel=1, runpm=0"
fi
stock_removed=0
custom_loaded=0
clock_attempted=0
clocks_restored=0
reboot_needed=0
run_cursor=''
original_noaccel=0
original_runpm=-1
original_config=''
kernel_fault_pattern='nouveau.*(FAULT|timeout|failed|error)|WARNING:|BUG:|Oops:|general protection fault|soft lockup|hard LOCKUP|CTXSW_TIMEOUT|PRIVRING'
stock_vga_pattern='^.*nouveau 0000:08:00\.0: bus: MMIO write of [[:xdigit:]]{6}1f FAULT at 6013d4 \[ PRIVRING \]$'

# Stock GF117 GR init uses nvkm_mask(TPC_UNIT(0,0,0x05c),1,1).
# A failed read can produce badf1000, then the mask writes badf1001.
# This exception applies ONLY to the already removed original module.
stock_gr_pattern='^.*nouveau 0000:08:00\.0: bus: MMIO write of badf1001 FAULT at 50405c \[ PRIVRING \]$'

get_cursor() {
    journalctl -k -n 1 --show-cursor --no-pager -o cat |
        sed -n 's/^-- cursor: //p'
}
new_kernel_log() {
    journalctl -k --after-cursor "$1" --no-pager -o short-iso
}
check_faults() {
    local cursor=$1 lines result
    if ! lines=$(new_kernel_log "$cursor"); then
        echo "Falha lendo o journal; estado de faults não verificável." >&2
        return 1
    fi
    # No early-exit pipe: with pipefail, rg -q could give printf SIGPIPE and
    # turn a positive fault match into a false negative on a large journal.
    if rg -i "$kernel_fault_pattern" <<< "$lines" >/dev/null; then
        echo "Novos faults/erros do kernel; interrompendo o teste."
        printf '%s\n' "$lines"
        return 1
    else
        result=$?
        if (( result != 1 )); then
            echo "Falha pesquisando faults; teste interrompido." >&2
            return 1
        fi
    fi
}
check_stock_unload_faults() {
    local lines events unexpected count gr_count result
    (( stock_removed && !custom_loaded )) || return 1
    if ! lines=$(new_kernel_log "$1"); then
        echo "Falha lendo journal da remoção original." >&2; return 1
    fi
    if events=$(rg -i "$kernel_fault_pattern" <<< "$lines"); then
        :
    else
        result=$?
        if (( result == 1 )); then return 0; fi
        echo "Falha pesquisando journal original." >&2; return 1
    fi
    if unexpected=$(rg -vi "$stock_vga_pattern|$stock_gr_pattern" <<< "$events"); then
        echo "Erro inesperado removendo o módulo original; teste interrompido."
        printf '%s\n' "$lines"
        return 1
    else
        result=$?
        (( result == 1 )) || return 1
    fi
    if count=$(rg -ci "$stock_vga_pattern" <<< "$events"); then :; else
        result=$?; (( result == 1 )) || return 1; count=0
    fi
    if gr_count=$(rg -ci "$stock_gr_pattern" <<< "$events"); then :; else
        result=$?; (( result == 1 )) || return 1; gr_count=0
    fi
    if (( count <= 2 && gr_count <= 1 && count + gr_count >= 1 )); then
        echo "Falhas conhecidas do módulo ORIGINAL durante a remoção (VGA=$count GR=$gr_count):"
        printf '%s\n' "$events"
        echo "GR original não corrigido: o teste usa noaccel=1. Qualquer fault experimental continua fatal."
        return 0
    fi
    echo "Erro inesperado removendo o módulo original; teste interrompido."
    printf '%s\n' "$lines"
    return 1
}

check_voltage_plan() {
    local state line
    state=$(awk '/ requested_core_khz=775000 / { print $1 }' <<< "$plan")
    [[ "$state" =~ ^state=[0-9]+$ ]] || {
        echo "Estado alvo ausente ou ambíguo no preflight de tensão." >&2; return 1;
    }
    line=$(awk -v state="$state" '$1==state && $2 ~ /^voltage_uv=/ { print }' <<< "$plan")
    echo "voltage_preflight: $line"
    [[ "$line" =~ ^state=[0-9]+\ voltage_uv=[1-9][0-9]*\ target_uv=[1-9][0-9]*\ voltage_ready=1\ voltage_temp_c=[0-9]+$ ]] || {
        echo "Regulador/tensão alvo indisponível. Nenhum clock será solicitado." >&2
        return 1
    }
}

check_gpu_idle() {
    local node=$1 errors result
    errors=$(mktemp) || return 1
    if fuser "$node" >/dev/null 2>"$errors"; then
        rm -f "$errors"
        echo "GPU ocupada: $node"
        fuser -v "$node" || true
        echo "Feche os processos indicados; execute no TTY."
        return 1
    else
        result=$?
        # fuser uses 1 for both no users and some errors. Require empty
        # stderr as well, rather than treating every failure as an idle GPU.
        if (( result != 1 )) || [[ -s "$errors" ]]; then
            echo "Não foi possível verificar o uso da GPU: $node" >&2
            cat "$errors" >&2
            rm -f "$errors"
            return 1
        fi
    fi
    rm -f "$errors"
}

read_clocks() {
    local values
    if ! values=$(cat "$debugfs/pstate_current"); then
        echo "Falha lendo clocks; amostra parcial descartada." >&2; return 1
    fi
    core=$(awk '$1=="core" && $3=="MHz" {print $2; exit}' <<< "$values")
    memory=$(awk '$1=="memory" && $3=="MHz" {print $2; exit}' <<< "$values")
    [[ "$core" =~ ^[0-9]+$ && "$memory" =~ ^[0-9]+$ ]] || {
        echo "Leitura de clocks inválida: $values" >&2; return 1;
    }
    echo "measured: core=$core MHz memory=$memory MHz"
}
# Kernel p-state work is scheduled asynchronously. Do not treat the first
# read immediately after a request as proof that the transition has finished.
wait_target_clock() {
    local minimum=$1 maximum=$2 attempt
    for attempt in {1..20}; do
        read_clocks || return 1
        (( memory == memory_before )) || {
            echo "Memória mudou durante a transição." >&2; return 1;
        }
        check_faults "$load_cursor" || return 1
        read_temperature || return 1
        if (( core >= minimum && core <= maximum )); then
            return 0
        fi
        sleep 0.2
    done
    echo "Clock alvo não confirmado após a espera limitada." >&2
    return 1
}

select_temperature() {
    local path name label path_input
    local candidates=()
    for path in "$device"/hwmon/hwmon*/temp1_input; do
        if [[ -r "$path" ]]; then
            temperature_path=$path
            temperature_source=nouveau
            echo "temperature_source=$temperature_source path=$temperature_path"
            return 0
        fi
    done
    # Dell EC reports GPU sensors separately from CPU/Ambient. Require an
    # exact GPU label and exactly one candidate; never substitute CPU heat.
    for path in "$hwmon_root"/hwmon*; do
        [[ -r "$path/name" ]] || continue
        name=$(cat "$path/name")
        [[ "$name" == dell_smm ]] || continue
        for label in "$path"/temp*_label; do
            [[ -r "$label" ]] || continue
            [[ "$(cat "$label")" == GPU ]] || continue
            path_input="${label%_label}_input"
            [[ -r "$path_input" ]] && candidates+=("$path_input")
        done
    done
    if (( ${#candidates[@]} != 1 )); then
        echo "Temperatura GPU indisponível ou ambígua: ${#candidates[@]} sensores Dell GPU." >&2
        return 1
    fi
    temperature_path=${candidates[0]}
    temperature_source=dell_smm:GPU
    echo "temperature_source=$temperature_source path=$temperature_path"
}
read_temperature() {
    [[ -n "$temperature_path" ]] || select_temperature
    [[ -r "$temperature_path" ]] || { echo "Sensor GPU desapareceu." >&2; return 1; }
    if ! temperature=$(cat "$temperature_path"); then
        echo "Falha lendo a temperatura GPU." >&2; return 1
    fi
    [[ "$temperature" =~ ^[0-9]+$ ]] && (( temperature > 0 && temperature < 80000 )) || {
        echo "Temperatura inválida ou acima do limite de teste (80 C): $temperature" >&2
        return 1
    }
    echo "temperature_source=$temperature_source temperature_millicelsius=$temperature"
}

finish() {
    local status=$?
    trap - EXIT INT TERM
    if (( reboot_needed || (clock_attempted && !clocks_restored) )); then
        echo "Estado não confirmado. Não vou tentar outra transição ou descarregar o módulo."
        echo "Reinicie o notebook antes de outro teste: sudo reboot"
        status=1
    else
        if (( custom_loaded )); then
            echo "Descarregando o módulo de teste (sem aceleração)."
            if timeout --kill-after=2s 15s rmmod nouveau; then
                custom_loaded=0
            else
                echo "Falha/timeout na remoção. Reinicie: sudo reboot"
                reboot_needed=1; status=1
            fi
        fi
        if (( stock_removed && !reboot_needed )); then
            echo "stage=stock-restore"
            echo "Restaurando o Nouveau original."
            if modprobe nouveau "noaccel=$original_noaccel" "runpm=$original_runpm" "config=$original_config"; then
                stock_removed=0
            else
                echo "Falha ao restaurar. Reinicie: sudo reboot"
                status=1
            fi
        fi
    fi
    if [[ -n "$run_cursor" ]]; then
        echo "journal do teste:"
        new_kernel_log "$run_cursor" || true
    fi
    echo "finished: $(date --iso-8601=seconds), exit=$status"
    exit "$status"
}
trap finish EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

for command in modinfo modprobe insmod rmmod sha256sum fuser timeout journalctl rg awk; do
    command -v "$command" >/dev/null || { echo "Falta comando: $command" >&2; exit 1; }
done
[[ "$(uname -r)" == 7.2.9-2-cachyos ]] || { echo "Kernel diferente do build." >&2; exit 1; }
[[ -r "$module" && "$(sha256sum "$module" | awk '{print $1}')" == "$expected_hash" ]] || {
    echo "Módulo ausente ou hash diferente do artefato validado." >&2; exit 1;
}
[[ "$(modinfo -F vermagic "$module")" == '7.2.9-2-cachyos SMP preempt mod_unload '* ]] || {
    echo "Vermagic incompatível." >&2; exit 1;
}
[[ -d "$device" && "$(cat "$device/vendor")" == 0x10de &&
   "$(cat "$device/device")" == 0x1140 &&
   "$(cat "$device/subsystem_vendor")" == 0x1028 &&
   "$(cat "$device/subsystem_device")" == 0x05f4 ]] || {
    echo "GPU diferente da GF117 Dell esperada." >&2; exit 1;
}
[[ "$(basename "$(readlink -f "$device/driver")")" == nouveau ]] || {
    echo "O driver ativo precisa ser o Nouveau original." >&2; exit 1;
}
[[ -r /sys/module/nouveau/parameters/noaccel && ! -e "$debugfs/pstate_plan" ]] || {
    echo "Já há um módulo de teste carregado ou o driver não é o esperado; reinicie primeiro." >&2; exit 1;
}
pci_path=$(readlink -f "$device")
for node in /dev/dri/card* /dev/dri/renderD*; do
    [[ -e "$node" ]] || continue
    node_device=$(readlink -f "/sys/class/drm/$(basename "$node")/device" || true)
    if [[ "$node_device" == "$pci_path" ]]; then
        check_gpu_idle "$node" || exit 1
    fi
done
original_noaccel=$(cat /sys/module/nouveau/parameters/noaccel)
original_runpm=$(cat /sys/module/nouveau/parameters/runpm)
original_config=$(cat /sys/module/nouveau/parameters/config)
[[ "$original_config" != '(null)' ]] || original_config=''
run_cursor=$(get_cursor)
[[ -n "$run_cursor" ]] || { echo "Não consegui marcar o início do journal." >&2; exit 1; }
echo "stage=stock-unload"
echo "Removendo somente o módulo Nouveau original."
if timeout --kill-after=2s 15s rmmod nouveau; then
    stock_removed=1
else
    reboot_needed=1; exit 1
fi
check_stock_unload_faults "$run_cursor"
IFS=',' read -r -a dependencies <<< "$(modinfo -F depends "$module")"
for dependency in "${dependencies[@]}"; do
    [[ -z "$dependency" ]] || modprobe "$dependency"
done
load_cursor=$(get_cursor)
echo "stage=experimental-load"
insmod "$module" noaccel=1 runpm=0 config=NvReclockFermiCoreOnly=1
custom_loaded=1
[[ -r "$debugfs/pstate_plan" && -r "$debugfs/pstate_current" ]] || {
    echo "Interfaces do módulo de teste ausentes." >&2; exit 1;
}
cat "$debugfs/pstate"
plan=$(cat "$debugfs/pstate_plan")
printf '%s\n' "$plan"
if (( probe_only )); then
    [[ "$plan" == *gf117_pwm_diag* ]] || {
        echo "Linha de diagnóstico PWM GF117 ausente." >&2; exit 1;
    }
    check_faults "$load_cursor"
    echo "Sonda concluída: nenhum pedido de clock foi escrito."
    exit 0
fi
[[ "$plan" == allow_reclock=1* ]] || { echo "Opt-in não foi reconhecido." >&2; exit 1; }
[[ "$plan" == *'requested_core_khz=775000 '* ]] || {
    echo "O estado de 775 MHz esperado não foi encontrado." >&2; exit 1;
}
check_faults "$load_cursor"
check_voltage_plan
read_temperature
sleep 1
read_temperature
read_clocks
(( core > 0 && memory > 0 )) || { echo "GPU sem clocks legíveis." >&2; exit 1; }
memory_before=$memory
check_faults "$load_cursor"
echo "stage=experimental-clock"
echo "Solicitando estado 0f: primeiro pedido de alteração de clock."
clock_attempted=1
printf '0f\n' > "$debugfs/pstate"
wait_target_clock 750 780
for sample in 1 2 3; do
    read_clocks
    (( core >= 750 && core <= 780 && memory == memory_before )) || {
        echo "Clock alvo não confirmado ou memória mudou." >&2; exit 1;
    }
    read_temperature
    check_faults "$load_cursor"
    sleep 1
done
echo "Núcleo >=750 MHz confirmado em repouso; isto NÃO testa estabilidade em jogos."
echo "Retornando ao estado base 07 para encerrar o teste."
printf '07\n' > "$debugfs/pstate"
wait_target_clock 1 300
read_clocks
(( core > 0 && core <= 300 && memory == memory_before )) || {
    echo "Retorno ao estado baixo não confirmado." >&2; exit 1;
}
check_faults "$load_cursor"
clocks_restored=1
echo "Teste breve concluído; o driver original será restaurado."
