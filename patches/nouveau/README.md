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
