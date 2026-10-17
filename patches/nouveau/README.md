# Patches experimentais Nouveau/Fermi

Estes patches são destinados ao código do kernel Nouveau para a GF117. Módulos
temporários anteriores foram testados no notebook e restaurados ao driver stock.
Builds usam a fonte/headers exatos do CachyOS; compilação não prova reclocking físico.

## 0001 `pstate_current`

Adiciona `/sys/kernel/debug/dri/<PCI>/pstate_current`, somente leitura. O
arquivo consulta `NVIF_CONTROL_PSTATE_ATTR_V0_STATE_CURRENT`, que percorre
`nvkm_clk_read()` para os domínios expostos. Isso não cria nenhuma operação de
escrita, mas a informação é **redundante**: a linha `AC` de `pstate` já usa a
mesma consulta no `ctrl.c`. O patch pode ser útil para uma API mais explícita,
mas não deve ser contado como nova telemetria ou como avanço de reclocking.

Fonte de referência usada na VPS: Linux commit
`3857c2fe5449541e24afc5efdb0f81a8a8f9a3a0` (árvore de análise; não é uma
prova de identidade com o kernel CachyOS do notebook).

## 0002 `gf100-clock-dryrun`

Baseado diretamente na release CachyOS `cachyos-7.2.9-2`. Adiciona o callback
`nvkm_clk_func.dryrun`, a API `nvkm_clk_dryrun()` e o arquivo debugfs
`pstate_plan`. A implementação copia o objeto `gf100_clk` e reutiliza
`gf100_clk_calc()` para validar PLL/divisores com leituras de VBIOS/MMIO.
Também reutiliza os parsers reais `nvbios_rammapEm()`,
`nvbios_ramcfg_index()` e `nvbios_timingEe()` através de `nvkm_ram_dryrun()`.
Os intermediários do cálculo `gt215_pll_calc()` usam 64 bits e rejeitam
frequências ou referências nulas antes de dividir. O numerador é preservado
separadamente do quociente e do resto, incluindo o caminho `pfN != NULL`.
Estados `min_p`/`max_p` nulos ou invertidos são rejeitados, assim como um
valor calculado de `P == 0`; o retorno final usa multiplicação larga antes das
divisões e verifica o limite de `int`.
O ponteiro `info` também é validado antes de qualquer acesso.
Nenhum callback `prog`, `ramgf100`/RAMFUC, GPIO ou escrita de registrador é
alcançado; `allow_reclock` continua `false`. O patch depende do `0001` apenas
porque ambos alteram `nouveau_debugfs.c`; pode ser aplicado após ele.

O patch foi aplicado a uma árvore limpa e comparado byte a byte com a árvore
usada no build. O módulo resultante foi compilado na VPS com vermagic
`7.2.9-2-cachyos` e não foi instalado em nenhum notebook.

## 0003 `gf117-reclock-optin`

Acrescenta `NvReclockFermi` como chave de configuração Nouveau, desligada por
padrão. Ela só passa `allow_reclock=true` quando o chipset é exatamente
GF117 e a opção foi ligada. O ID `0x117` deste patch estava incorreto;
aplique também 0005, que usa o ID interno `0xd7`. A chave usa a opção existente
`nouveau.config`; sem ela, o caminho de programação continua bloqueado como
antes. Isso não seleciona sozinho um clock, não valida estabilidade e não
torna a flag apropriada para outras GPUs.

Compilado em 2026-10-16 no módulo temporário para `7.2.9-2-cachyos`, junto dos
patches 0001/0002. Foi carregado uma vez com o opt-in desligado; o driver stock
foi restaurado. O dry-run encontrou RAMMAP `0x11`, rejeitada pelo caminho
GF100 atual, e a descarga gerou timeouts FIFO. O opt-in físico fica bloqueado
até auditar RAMMAP `0x11` e resolver os faults/avisos do caminho Nouveau.

O helper `/home/doc/teste.sh` agora coleta somente leituras e logs em
`/home/doc/teste-logs/`, sem carregar/descarregar módulos. A versão antiga
foi preservada em `/home/doc/teste.sh.antes-rammap11-20261016`.

## 0004 `gf117-pstate-plan-units`

Corrige a telemetria do plano para reportar o clock físico do núcleo em kHz;
GF100 armazena o domínio GPC em uma escala interna 2x. Também registra a versão
da RAMMAP quando o dry-run recusa uma versão. A captura de 2026-10-16 mostrou
RAMMAP `0x11`; o caminho GF100 atual rejeita versões diferentes de `0x10`, então
isso melhora o diagnóstico, sem habilitar programação de memória ou clocks.
O plano requer auditoria específica do formato `0x11` antes de qualquer suporte
de reclocking à memória.

## 0005 `gf117-rammap-inspection-and-preflight`

O dry-run inspeciona RAMMAP/RAMCFG 0x11 e timing 0x20, respeitando tamanhos e o
ID de timing no byte 0 da RAMCFG 0x11. A sequência de escrita GF100 continua
inadequada para essas tabelas; o resultado é `-EOPNOTSUPP` e
`stage=ram-sequence-unimplemented`, com strap e timing selecionados no log.

Corrige o ID interno GF117 de `0x117` para `0xd7`. Antes de programar pstate,
PCIe, núcleo ou tensão na GF117, exige que o dry-run de RAM tenha sucesso.
Falhas posteriores na programação de RAM também interrompem a transição,
e o estado só é atualizado quando a programação de núcleo tem sucesso.
Essas mudanças no tratamento de erros são limitadas à GF117.

`tools/test-gf117-ram-source.py /caminho/para/kernel-patcheado` compila as
funções reais `gf100_ram_dryrun` e `nvkm_pstate_prog` com BIOS/hardware simulados.
Verifica o layout moderno, limites, seleção de timing e ausência de chamadas
de programação quando a sequência está indisponível. Não acessa a GPU.

## 0006 `gf117-experimental-core-only`

Adiciona `NvReclockFermiCoreOnly`, falso por padrão e limitado a `0xd7`.
Seleciona o estado base VBIOS para os motores e preserva o clock de memória,
sem programação de PCIe/RAM. Exige tensão legível/suficiente, preflight dos
motores e readback; propaga timeouts de PLL neste modo. Mantém tensão e
refrigeração elevadas em caso de falha. Não inclui rollback garantido nem
validação física. Veja `docs/gf117-core-only-2026-10-16.md`.

O teste `tools/test-gf117-core-source.py` compila as rotinas reais de tensão,
programação e readback PLL com mocks e UBSan. Não altera clocks do notebook.

## 0007 `gf117-skip-legacy-vga-lock`

Evita o acesso CRTC VGA feito por `nvkm_lockvgac()` na GF117 headless, inclusive
a escrita implícita do índice `0x1f` em `0x6013d4`. Os dois chamadores devinit
(preinit/dtor) ignoram o valor retornado; para GF117 o helper retorna falso sem
I/O. Outros chipsets mantêm a rotina anterior. Teste com a função real e UBSan:
`tools/test-gf117-vga-source.py /caminho/para/kernel-patcheado`.
Ainda requer validação física de ausência do fault.

## 0008 `gf117-filter-headless-crtc-accesses`

Estende o guard headless GF117 às portas CRTC 03d4/03d5 e ao word MMIO
6013d4 via callback devinit do interpretador VBIOS. O callback usa o sentinela
existente `~0U` para evitar o acesso. Outros chipsets e endereços são preservados.
Teste real com mocks/UBSan: `tools/test-gf117-crtc-source.py`.
Ainda exige validação física: o log anterior manteve o fault após 0007.


## 0009 `gf117-guard-drm-crtc-and-trace-pending-faults`

Protege também `NVReadVgaCrtc`, `NVWriteVgaCrtc` e `NVLockVgaCrtcs` no lado DRM,
que usa NVIF MMIO diretamente e não passa pelos guards NVKM. O teste das funções
reais verifica zero I/O para GF117 e mantém GF119/NV11. Isso fecha uma rota de
software, mas não identifica por si só a origem do fault físico anterior.

Antes do acknowledgement normal do bus init, registra status/endereço/dado de
um fault já pendente. Não muda o acknowledgement, não ignora erros e não prova
que um fault pendente pertence ao módulo anterior. O helper continua bloqueando
faults durante a inicialização experimental, inclusive esse diagnóstico.

## 0010 `gf117-readonly-voltage-preflight`

Acrescenta ao debugfs de plano a tensão derivada do VID lido, o alvo mapeado da
VBIOS, a temperatura usada pelo modelo e a existência de VID suficiente.
Nenhum setter é chamado pelo diagnóstico. O helper exige leitura/alvo positivos
e um plano válido do estado nominal antes de solicitar p-state. Leitura de VID
não é medição física da alimentação da GPU e não garante que uma escrita futura
terá sucesso. O caminho real mantém as validações após a programação.

## 0011 `gf117-completion-and-failure-latch`

No modo experimental GF117, espera a conclusão do worker antes de retornar o
resultado ao usuário. O flag `waiting` era consumido na entrada do worker e
permitia retornar enquanto a programação continuava. Uma falha fica registrada
até reconstruir o dispositivo e bloqueia novas tentativas automáticas.

Também rejeita índices de p-state fora da lista e intervalos PLL sem nenhum M
válido, limites de entrada invertidos e frequências que excedam o retorno `int`.
Os testes `test-gf117-worker-source.py` e `test-gf117-pll-source.py` compilam as
funções reais; o primeiro força uma pausa do worker após consumir o flag.

## 0012 `gf117-validate-voltage-ceilings`

O caminho experimental usa o estado base da VBIOS. Aplica os limites `max_uv` e
`max0_id/max1_id/max2_id` antes de programar tensão, incluindo o arredondamento
para um VID existente. Valida a leitura após a programação contra o alvo e o
limite. Falha na leitura ou no mapeamento impede continuar.

O debugfs usa o mesmo preflight somente leitura e informa limite, máscara e
quantidade de VIDs. O teste de core verifica alvos acima do teto, arredondamento
inviável e limites inválidos, sem chamadas de escrita nesses casos.

## 0013 `pll-respect-input-frequency-bounds`

Corrige o intervalo do divisor M: o mínimo usa `ceil(refclk/max_inputfreq)`
e o máximo usa `floor(refclk/min_inputfreq)`. As expressões anteriores somavam
o denominador nas duas divisões, podendo excluir um limite exato válido e
admitir M que deixa a frequência de entrada abaixo do mínimo da VBIOS.

O teste da função real reproduziu a violação antes da correção. Verifica os
limites inclusivos, referência não divisível e o produto `min_input*M <= refclk
<= max_input*M`, além dos casos já cobertos pelo patch 0011.

## 0014 `gf117-pwm-readback-and-crtc-guard`

A VBIOS ativa desta GF117, lida somente pelo debugfs, declara tensão PWM
650000–1150000 µV, frequência 172800 Hz e um GPIO `VID_PWM` na linha 11.
Os estados 07 e 0f usam o mesmo mapa de 850000 µV. O backend anterior era
somente GPIO VID e deixava `vid_count=0`, explicando `voltage_uv=-22`.

O patch seleciona um getter PWM somente leitura quando VBIOS e GPIO concordam.
Ele valida divisor/duty e limites de tensão. Não implementa setter PWM: se a
tensão lida for inferior ao alvo, o preflight continua bloqueando o reclock.
O endereço de leitura `0x20340/0x20344` vem do caminho PWM existente GK104;
se a GF117 tiver layout diferente, a leitura falhará de modo conservador.

Também bloqueia escritas por acessores NVKM no CRTC `0x6013d4–0x6013d7`
inexistente na GF117 e registra o chamador. A origem do fault anterior só
será confirmada por um novo log físico. O helper ainda aborta se houver fault.
Compilação e plano de p-state não provam 750 MHz.

## 0015 `vmap-bound-max2-by-header`

O parser VBIOS 0x20 consultava o ID `max2` em `table+0x0c` quando o tamanho
da **entrada** era pelo menos 12, embora esse campo pertença ao cabeçalho.
Nesta ROM o cabeçalho tem 10 bytes e a entrada tem 38: o byte lido era o
primeiro `min_uv`, interpretado como ID 80. O mapa de ID 80 não existe;
o fallback produziria um teto falso de 800000 µV e bloquearia o alvo
legítimo de 850000 µV. A checagem agora exige cabeçalho de pelo menos 13
bytes antes de consultar `max2`. Sem esse campo, o ID é `0xff`.

## 0016 `gf117-trace-pwm-and-blocked-crtc-accesses`

A leitura PWM anterior falhou com `-ERANGE` sem mostrar os registradores brutos.
Este patch registrava divisor e duty do getter PWM somente leitura e qual dos
guards VGA/DRM/VBIOS de GF117 foi acionado para o CRTC legado. A leitura PWM foi
desativada pelo patch 0017 após retornar `0/0` no hardware; a instrumentação do
CRTC continua útil e não prova que o fault em `6013d4` foi eliminado.

## 0017 `gf117-disable-unverified-pwm-readback`

O teste físico mostrou `0x20340=0` e `0x20344=0` na GF117. Esse par veio do
backend GK104 e não tem layout validado para GF117. O driver agora deixa o
subdevice de tensão ausente quando a VBIOS pede PWM, evitando tratar esses dados
como tensão ou cair para GPIO VID. O preflight de reclocking falha fechado; o
clock permanece bloqueado até existir um backend PWM/VID comprovado. O fault
`PRIVRING` em `0x6013d4` também permanece sem origem identificada.


## 0018 `gf117-readonly-gf119-pwm-probe`

GF117 (`0xd7`) seleciona `gf119_therm_new()`. O caminho PWM térmico GF119
consulta o mux do GPIO em `0xd610 + linha*4`, usa os canais `0xe114/0xe118`
e `0xe11c/0xe120`, e também reconhece um canal PTHERM em `0x200d8/0x200dc`.
O teste anterior leu `0x20340/0x20344`, usados pelo backend de tensão GK104; os
zeros observados ali não descartam o caminho PWM GF119.

O patch 0018 expõe somente leituras desses registradores para a linha 11 no
`pstate_plan`; não grava MMIO, não converte duty em tensão e não habilita
reclock. O mapeamento do PWM térmico é uma pista candidata para a saída
`VID_PWM` da VBIOS, ainda precisa de confirmação física por telemetria.

O teste `tools/test-gf117-pwm-probe.py` verifica os endereços e a ausência de
qualquer accessor de escrita no bloco diagnóstico.
