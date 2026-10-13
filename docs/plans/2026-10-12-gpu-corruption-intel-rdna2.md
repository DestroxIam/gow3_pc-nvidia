# Corrupção gráfica na Intel Arc e linhas pretas nas RX 6600 (RDNA2 de 8 GB)

Diagnóstico de 2026-10-12, feito só por leitura do código, dos relatos e dos logs. Nenhuma das
duas placas está disponível localmente (a máquina de desenvolvimento tem uma GTX 1650, a de
teste uma RX 6700 XT), então a confirmação depende de quem reportou. Este documento registra o
que foi apurado, o que foi refutado e o plano de bisseção.

## 1. Sintomas

| | Sintoma A (Intel) | Sintoma B (AMD RDNA2 de 8 GB) |
|---|---|---|
| Placas | Arc B580 (driver 32.0.101.9033), Arc G3 Extreme (MSI Claw 8) | RX 6600, 6600M, 6600 XT, 6650 XT |
| Issues | [#39](https://github.com/FelipePrado0/gow3_pc/issues/39), [#28](https://github.com/FelipePrado0/gow3_pc/issues/28); shadPS4 eltutz: cuesta4/shadPS4#11 | [#65](https://github.com/FelipePrado0/gow3_pc/issues/65), [#61](https://github.com/FelipePrado0/gow3_pc/issues/61), [#43](https://github.com/FelipePrado0/gow3_pc/issues/43), [#27](https://github.com/FelipePrado0/gow3_pc/issues/27); shadPS4 eltutz: [cuesta4/shadPS4#8](https://github.com/cuesta4/shadPS4/issues/8) |
| Aparência | A cena 3D inteira retalhada em faixas horizontais de cerca de 32 px; dentro de cada faixa, tiles de cerca de 64 px deslocados. HUD, Scaleform e vídeos H.264 intactos. | Linhas pretas finas em blocos retangulares, só em áreas claras (céu, fogo, brilho do HUD, pele do Kratos no menu). Medido no print 1920x1080 de #61: blocos de 8x4 px alinhados ao grid de resolução cheia. |
| Comportamento | Determinístico. | Aleatório por lançamento (quase sempre aparece), persistente durante a execução. Desligar "Use pipeline binary cache" resolveu para alguns, não para outros; um precisou apagar o cache de shaders também. |
| Em outros builds | Igual no shadPS4 eltutz. HD 630 (Gen9) mostra outro defeito (3D preto ou só azul). | Igual no shadPS4 eltutz. Um usuário de cuesta4#8 diz que o shadPS4 0.19.0 oficial não tem as linhas. |

Logs públicos dos reporters (do shadPS4, anexados nas issues do cuesta4): o B580 reporta
`subgroup size 32`, driver Intel 101.9033; a RX 6600 reporta `subgroup size 64`, driver AMD
2.0.353, com `VK_KHR_pipeline_binary` e `VK_EXT_subgroup_size_control`. Nenhum dos dois tem
avisos relevantes do `Render.Vulkan` além de formatos sem suporte com fallback (Intel:
`R8Srgb`, `R8G8Srgb`, `D16UnormS8Uint`).

## 2. Fatos apurados

- O quadro do jogo (docs/upscaler.md): pré-passe de profundidade, luz e sombras, materiais,
  transparências, pós com pirâmide de bloom em meia resolução, combine da pós em **compute**
  (hash `9a9cf8a9`) para a cor da cena RGBA8 sRGB, HUD por cima na mesma imagem.
- Só a Intel fica sem as duas proteções que os shaders wave64 do PS4 precisam no host:
  - `needs_lds_barriers` liga só para NVIDIA e KosmicKrisp
    (`gpu/shadps4/video_core/renderer_vulkan/vk_pipeline_cache.cpp`). O passe
    `shared_memory_barrier_pass.cpp` retorna cedo sem a flag. Igual no upstream.
  - O pin de subgrupo em 64 (`IsSubgroupSize64Supported()`) só existe onde o máximo é 64. Na
    Intel o máximo é 32, e os módulos são SPIR-V 1.6, então o driver pode compilar compute em
    SIMD16. O lowering de wave64 (`lower_wave64_pass.cpp`) assume 32 lanes fixas (`>> 5`,
    `& 31`) e só roda para compute.
- Na AMD o pin em 64 vai para todos os estágios gráficos sem consultar
  `requiredSubgroupSizeStages`. Se o driver não lista o fragment, o pin é inválido e o driver
  escolhe wave32 ou wave64 sozinho. Não verificado: o que a AMD reporta na Navi 23 e na Navi 22.
- O eltutz tem 104 commits próprios sobre a base de 2026-08-21 (256 atrás do main). O fork
  vendora o upstream `b4e7ae7` (2026-10-02, a data do 0.19.0) mais três correções do eltutz:
  alias de imagens (`189ca3b6`), depth sem uso não anexado (`eccbeae3`) e blend MIN/MAX com
  escala, com um "square pass" (`45f3d1f9`, chave `GOW3_SQUARE_PASS=0`). O eltutz também tem
  gravação em thread, copy workers e compilação assíncrona parecidos com os do fork.
- Limiares do coletor de VRAM numa placa discreta de 8 GB (`texture_cache.cpp`, construtor):
  `trigger_gc_memory = 0` (o coletor roda a cada submissão), pressão em cerca de 2,7 GB e
  crítico em cerca de 5,4 GB. Nos 12 GB: gatilho cerca de 1,35 GB, pressão 5,9 GB. Imagens
  tiled escritas pela GPU nunca são despejadas; alvos por frame nunca entram na LRU.
- O pacote de release não inclui cache de shaders; cada reporter compila o próprio.
- Não há CI no repositório e esta máquina não tem MSYS2: builds de teste dependem do mantenedor.

## 3. Hipóteses para a Intel

Veredictos de três verificadores adversariais por hipótese (sobrevive com 2 de 3).

### A-1 (sobreviveu): workgroups de 64 threads com LDS rodam sem barreira

No GCN um workgroup de 64 threads é uma wave só, em lockstep, e o compilador do PS4 omite o
`s_barrier` entre `ds_write` e `ds_read`. Na Intel o workgroup vira 2 a 4 subgrupos e a leitura
pode preceder a escrita. Ressalvas: não há dump de shader que prove que algum compute do jogo
tem workgroup de 64, LDS e nenhum `s_barrier`; o padrão (tiles coerentes deslocados, névoa e
partículas limpas por cima) lembra mais erro de endereçamento; a PR upstream #1801 que criou o
passe causou device lost numa Iris Xe em 2024, provavelmente o motivo da flag ficar só na NVIDIA.

### A-2 (sobreviveu numa variante): lowering de wave64 assume 32 lanes

`profile.subgroup_size` é o `subgroupSize` reportado (32), não a largura real. Em SIMD16, dois
subgrupos gravam no mesmo slot do scratch do ballot e `readlane` com índice de 16 em diante fica
indefinido. O Xe2 não tem SIMD8; o mínimo é 16. Dawn (Chromium) registrou o mesmo problema:
drivers Intel escolhiam 8, 16 ou 32 lanes e quebravam compute shaders com layout dependente do
tamanho do subgrupo.

### Refutadas

- Alinhamento zero nos staging do tiling (`tile_manager.cpp`): todo `guest_size` tiled é
  múltiplo de 64 ou 256.
- Formato sRGB em vez de UNORM da cor da cena (HD 630): decidido pelo primeiro descritor que
  cria a imagem, não pelo fornecedor. Vale olhar no log do HD 630 se
  `image format VK_FORMAT_R8G8B8A8_SRGB ... is not supported` aparece (`image.cpp` remove o uso
  STORAGE e a view UNORM do compute fica inválida).
- Concorrência do port: o sintoma reproduz no eltutz, e nenhum recurso tem ramo por fornecedor.

## 4. Hipóteses para a RX 6600

Nenhuma sobreviveu. Motivos, para não repetir o trabalho:

| Hipótese | Por que caiu |
|---|---|
| Draws pulados pela compilação assíncrona deixam alvos indefinidos | Imagens novas nascem `Dirty` e passam por `RefreshImage` antes do primeiro uso; alvos de bloom são refeitos a cada frame; só existe no fork, não no eltutz; o primeiro uso de um pipeline é pulado em toda máquina, inclusive na 6700 XT. |
| Coletor de VRAM em 8 GB | A conta está certa, mas alvos tiled escritos pela GPU nunca são despejados, só imagens paradas há 16 a 160 ticks entram, imagens recriadas voltam da memória do guest, e o sintoma aparece no menu com pouca memória em uso. |
| VMA derramando para RAM | Só custa desempenho. Endurecimento: passar `VMA_ALLOCATOR_CREATE_EXT_MEMORY_BUDGET_BIT` em `vk_instance.cpp` (a extensão está ligada, a flag não). |
| Cópia de alias (`aliasing.cpp`) ou memo com imagem velha | Cópias de extensão inteira a partir da origem, só com layout igual. Não geram blocos de 8x4. |
| Memos, draw pipe, gravação em thread | Determinísticos e iguais na 6700 XT. Lacuna real confirmada, mas de outro efeito: uma meta-clear via compute ou `FillBuffer` com o render pass aberto e acerto no `begin_memo` pula `IsMetaCleared/TouchMeta` (alvo inteiro sem clear, não linhas). |
| Chave do cache de binários | `CreateCachedGraphicsPipeline` recebe a `GraphicsPipelineKey` e não a usa; o arquivo leva só a chave do driver (`vk_pipeline_serialization.cpp`). Efeito seria determinístico, na 6700 XT também, e não existe no eltutz. Endurecimento: incluir o hash da chave no nome e remover `LoadLegacyBinary`. |
| Toggle de binários sem efeito | Verdadeiro só sem `VK_KHR_pipeline_binary`; o log da RX 6600 tem a extensão. |
| Combine `9a9cf8a9` em wave32 | Todo compute passa pelo mesmo caminho com `requiredSubgroupSize=64`; compute não usa binários. |

Pista não verificada, a mais forte: o pin de 64 nos estágios gráficos pode ser inválido na AMD
se `requiredSubgroupSizeStages` não incluir o fragment. Um pixel shader em wave32 cobre 8x4 px,
metade do footprint 8x8 da wave64, e as operações de subgrupo do fragment
(`emit_spirv_warp.cpp`) assumem 64 lanes sem passar pelo lowering. Não explica a diferença entre
Navi 23 e Navi 22 nem a aleatoriedade. Alternativa igualmente não verificada: 8x4 em RGBA8 são
128 bytes, o tamanho de um bloco de DCC.

## 5. O que foi feito

- Comentários pedindo dados e testes, postados em 2026-10-12: #65, #43 (texto completo), #61,
  #27 (ponteiro para #65), #39 (completo, em inglês) e #28 (ponteiro para #39).
- Nesta branch, a política de subgrupo ficou em um helper puro
  (`gpu/shadps4/video_core/renderer_vulkan/vk_subgroup_policy.h`) com teste
  (`tests/test_subgroup_policy.cpp`, alvo `subgroup-policy-test`):
  - `needs_lds_barriers` passa a valer em todo host que não fixa 64 lanes (Intel), além da
    NVIDIA e do KosmicKrisp; `GOW3_LDS_BARRIERS=0/1` força o valor.
  - Compute é fixado em 32 lanes na Intel (`requiredSubgroupSize = subgroupSize` quando a
    largura pode variar e o estágio aceita pin). AMD continua em 64 em todos os estágios, NVIDIA
    continua sem pin.
  - `ShaderBinaryVersion` subiu para 8, para o cache de SPIR-V não reaproveitar módulos sem as
    barreiras. O log passa a imprimir a faixa de subgrupo, os estágios que aceitam pin e a
    política escolhida (`gow3: subgroup policy: ...`).
  - O teste compila e passa aqui com `zig c++`; o núcleo gráfico não foi compilado nesta máquina
    (sem MSYS2). Precisa de build do mantenedor e de teste nos B580 e Claw.

## 6. Bisseção com quem reportou

RX 6600 (um teste de cada vez, 5 aberturas, cache de shaders limpo antes; variáveis por um
`teste.bat` com `set VAR=valor` e `start "" "God of War III.exe"`):

| # | Teste | Como |
|---|---|---|
| 1 | Sem cache de binários e sem carga em segundo plano | desmarcar "Use pipeline binary cache" e "Load shader cache in the background" |
| 2 | Sem compilação em segundo plano | desmarcar "Compile new shaders in the background" |
| 3 | Sem o square pass do MIN/MAX | `GOW3_SQUARE_PASS=0` |
| 4 | Sem o coletor de VRAM | `GOW3_GC_BUDGET_MB=20000` |
| 5 | Draw pipe desligado | "Pipeline de GPU em dois estágios" = Off |
| 6 | Gravação na thread principal | `GOW3_VK_RECORD_THREAD=0` |
| 7 | Leituras com espera | desmarcar "Game reads GPU data without waiting" e "Deferred GPU readbacks" |

Pedidos: `user\last_run.log`, versão do Adrenalin, resolução, se as linhas ficam paradas ou
piscam, captura RenderDoc do primeiro passe com blocos 8x4 (estágio e wave size). No lado do
mantenedor, `GOW3_GC_BUDGET_MB=3000` na 6700 XT força os caminhos de evicção de 8 GB; a imagem
deve continuar limpa.

Intel: `last_run.log`, driver, se os tiles ficam parados ou mudam a cada frame, e um build desta
branch. Ordem de teste do build: `GOW3_LDS_BARRIERS=1` sozinho confirma A-1; se não resolver, o
pin de compute em 32 (já no build) confirma A-2; se nada mudar, as duas caem e a investigação
vai para tiling, formato ou alias. Numa captura RenderDoc, o primeiro evento cuja saída já sai
retalhada decide: dispatch de compute com `LocalSize` 64, variáveis Workgroup e sem
`OpControlBarrier` confirma A-1; draw, cópia ou detile antes de qualquer compute descarta as
duas.

## 7. Endurecimentos opcionais (não são a causa)

- Invalidar o `begin_memo` em `TextureCache::ClearMeta` e em `TouchMeta(is_clear=true)`.
- `VMA_ALLOCATOR_CREATE_EXT_MEMORY_BUDGET_BIT` quando `supports_memory_budget`.
- Registrar no log os limiares do coletor ao iniciar; `DownloadImageMemory` só grava o mip 0.
- Nome do arquivo de binário com o hash da `GraphicsPipelineKey`; remover `LoadLegacyBinary`.
- Conferir e portar do upstream: #5310 (barreiras de storage buffer quando subgroup != 64),
  #5285 (subgroup barrier de LDS) e #5116 (ballot e MBCNT lowered em par). Citados pelos agentes,
  não conferidos.

## 7b. Atualização de 2026-10-13 (logs e testes dos reporters)

- **Bisseção na RX 6600 (FilipiEPTeixeira, #65): os 7 testes falharam**, 5 aberturas cada,
  linhas em todas. Eliminados: cache de binários, warm-up em segundo plano, compilação
  assíncrona, square pass (`GOW3_SQUARE_PASS=0`), coletor de VRAM (`GOW3_GC_BUDGET_MB=20000`),
  draw pipe, gravação em thread, readbacks sem espera. A causa está no núcleo compartilhado ou
  no driver, não nas otimizações do port.
- **Oito logs lidos por inteiro** (seis reporters; Intel B390 e seis RX 6600/6600M): execuções
  saudáveis, sem erro, sem pressão de memória, duas versões do Adrenalin (26.6.4 e 26.8.1),
  Fifo e Immediate, janela e tela cheia, quatro builds de eboot diferentes. Nenhuma linha se
  correlaciona com o defeito; falta um log de controle da 6700 XT com `GOW3_GPU_LOG=info`.
- **`teste.log` (MarcosAlexandre30, build de teste 1, RX 6600):**
  `Physical device subgroup size 64 (32 to 64, pinnable stages { Compute })`. O driver AMD só
  aceita `requiredSubgroupSize` em compute; o pin de 64 nos estágios gráficos (herdado do
  shadPS4) é inválido na AMD e o driver escolhe o wave size do pixel shader por conta própria.
  Uma wave32 de PS cobre 8x4 px, a geometria medida nos prints. O print do wyz-ez (#65) mostra
  as linhas só nas fontes de luz e nos brilhos especulares.
- **Intel:** o log do yisus230291 (#28, "não funcionou") era do binário 2.1.6 na pasta antiga,
  não do build de teste (sem a faixa de subgrupo na linha, cache não limpo). A GPU é uma Arc
  B390 integrada (Panther Lake), driver 101.9034, sem `VK_KHR_pipeline_binary`.
- **O port só grava linhas de GPU em nível Warning** (`gpu/shim/common/logging/log.cpp`);
  `GOW3_GPU_LOG=info` libera. Marcadores para testers precisam ser `std::printf`.
- **Mudanças na branch depois do build 1:** `GPU: subgroup policy: ...` por printf
  (`adf0aea`); `GOW3_SUBGROUP_PIN=all|allowed|none` (`342d3b5`); barreiras de LDS pelo pin
  efetivo do compute (`c8665df`); `GOW3_WAVE_STATS=1` liga
  `VK_KHR_pipeline_executable_properties` e grava um histograma de (estágio, lanes) por
  pipeline, `GPU: wave sizes after N pipelines: ...` (`408fafc`, `vk_wave_stats.h`,
  `tests/test_wave_stats.cpp`).
- **Build de teste 2 (`windows-v2.1.6-test2`):** RX 6600 roda três vezes com cache limpo:
  (1) `GOW3_WAVE_STATS=1 GOW3_GPU_LOG=info`, (2) mais `GOW3_SUBGROUP_PIN=allowed`, (3)
  `GOW3_SUBGROUP_PIN=none GOW3_LDS_BARRIERS=1`. O histograma diz se o fragment roda em wave32
  na Navi 23; o mantenedor deve rodar (1) na 6700 XT para comparar.
- Ferramentas de build nesta máquina: MSYS2 CLANG64 em `C:\msys64`; o worktree precisa do
  alias `subst G:` para o ninja (caminhos acima de 260 caracteres) e `bash build.sh` falha no
  `git apply` do submódulo sob o alias (gitfile relativo), então o build usa cmake e ninja
  direto (`scratchpad/build_g.sh` da sessão) e `package.sh` roda no caminho longo.

## 7c. Atualização de 2026-10-13, segunda rodada (RX 6650 XT, jleandrocampos em #65)

- **Pin de subgrupo descartado:** execuções 1 (`all`) e 3 (`none` + barreiras de LDS) com cache
  limpo, linhas iguais nas duas; o log confirma a política aplicada. Mesmo resultado nos três
  logs do MarcosAlexandre30 (RX 6600).
- **`GOW3_WAVE_STATS` é cego na AMD:** `VkPipelineExecutablePropertiesKHR::subgroupSize` vem 0
  para todo executável gráfico, 64 só em compute. O build 3 acrescentou `VK_AMD_shader_info`
  (VGPRs físicos na chave, ISA em `user\shaders\wave_dumps`), ainda sem resultado.
- **Nenhum fragment shader depende do tamanho da wave:** o reporter varreu 1152 módulos SPIR-V
  do cache: 76 `OpGroupNonUniformQuadBroadcast` (quad, independe da wave) e 4 ballots, todos em
  compute.
- **O shadPS4 0.19.0 oficial reproduz** as linhas na 6650 XT (binários distintos, mesma cena).
  Não há regressão do eltutz a procurar; a causa está no núcleo compartilhado ou no driver.
- **42 toggles desligados ao vivo** (`GOW3_TOGGLE_FILE` = 182395781688328191) e
  `GOW3_SQUARE_PASS=0`: linhas continuam.
- **`last_run.log` só era gravado pelo `--play`** (`Play God of War III.exe`); o PLAY da janela
  mandava a saída para a aba Log. Corrigido em `8a4e890` (ambos gravam o mesmo arquivo).
- **Pistas restantes:** bloco de 8x4 px em RGBA8 = 128 bytes = bloco de DCC; o driver AMD não
  expõe `VK_EXT_image_compression_control`. Barreira faltando entre uma escrita única (LUT ou
  textura gerada por shader) e a primeira leitura explicaria estático por execução, aleatório
  por lançamento, dependente de timing e cache (Infinity Cache 32 MB na Navi 23, 96 MB na Navi
  22) e restrito à iluminação. Teste: `GOW3_FULL_BARRIERS=1` (`4fcd91f`, build de teste 4
  `windows-v2.1.7-test4`) e validação de sincronização (`GOW3_VK_VALIDATION=1`
  `GOW3_VK_VALIDATION_SYNC=1`, exige o Vulkan SDK).

## 8. Perguntas em aberto

1. Algum compute antes do passe translúcido tem workgroup de 64, LDS e nenhum `s_barrier`?
   `GOW3_DUMP_SHADERS=1` na 6700 XT lista `LocalSize`, `shared_memory_size` e ballot/readlane
   por pipeline.
2. Na Intel, o padrão é estável ou cintila?
3. O que explica o HD 630?
4. O relato "0.19.0 limpo, eltutz ruim" na RX 6600 é confiável? Se for, elimina tudo que só
   existe no fork.
5. O que a AMD reporta em `requiredSubgroupSizeStages` na Navi 23 e na Navi 22? O log desta
   branch imprime isso.
6. O primeiro evento com blocos 8x4 é draw ou dispatch, e em que wave size?
