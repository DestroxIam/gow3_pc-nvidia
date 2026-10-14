# GoW3 PC — prévia comunitária NVIDIA

Fork do port de **Felipe Prado**, baseado na versão Windows **2.1.8**. [Leia os requisitos, limites e créditos completos em inglês](README.md).

Esta prévia 2.1.8 inclui SR/NR e FG 2× observados em testes limitados de gameplay na RTX 5070. Consulte as condições medidas e as limitações em [Validação](docs/VALIDATION.md) e [Alterações](CHANGELOG.md).

Baixe o ZIP em [Releases](https://github.com/DestroxIam/gow3_pc-nvidia/releases). Coloque seu próprio dump **extraído**, **CUSA01623 / atualização 01.02**, em `Game/CUSA01623/`. Não incluímos jogos, ISO, PKG, firmware, saves ou caches de shaders.

Abra **God of War III.exe** → **NVIDIA**. A resolução final e o preset calculam a resolução interna. DLAA exclui o DLSS. SR + NR + geração 2× foram observados com uma passada de NR na RTX 5070; 3×–6× e outras passadas continuam sem validação. Neural Rendering é uma integração comunitária experimental em Compatibilidade ou no caminho nativo AFTER-SR, habilitado apenas com hashes aprovados do renderer/OptiScaler e modelo/forwarder fornecidos pelo usuário. BEFORE-SR continua bloqueado.

FSR continua disponível. Não houve benchmark nem validação da campanha inteira. O monitor limita a resolução física. Todos os créditos ao port original e aos seus colaboradores estão no [README](README.md#credits).
