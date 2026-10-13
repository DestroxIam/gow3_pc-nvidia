# GoW3 PC — NVIDIA Community Preview

An extension of **[Felipe Prado's God of War III Remastered PC port](https://github.com/FelipePrado0/gow3_pc)**, based on upstream **Windows v2.1.7**. Bring your own extracted PS4 game dump. **No game files are included.**

**[Download the Windows preview](https://github.com/DestroxIam/gow3_pc-nvidia/releases)** · [NVIDIA setup](docs/NVIDIA.md) · [Changes](CHANGELOG.md) · [Build/source](docs/BUILD-NVIDIA.md) · [Português](README.pt-BR.md)

## What's changed

| Feature | This fork |
|---|---|
| DLSS Super Resolution | Adapted to GoW3's actual scene/depth/camera pipeline. Internal raster size follows the preset, then reconstructs to the selected final size. |
| DLAA | Native-resolution NVIDIA AA, mutually exclusive with DLSS reconstruction. |
| Frame generation / MFG | Optional OptiScaler/Streamline bridge. 2× observed with the native path; 3×–6× exposed but not revalidated on this path. |
| “DLSS5” Neural Rendering | Experimental community mod in **Compatibility** mode, with a separately supplied runtime. Suspended in native mode because that combination failed device interoperability. |
| Launcher | Redesigned NVIDIA page, internal → final resolution status, preserved FSR fallback and game controls. |
| Portable layout | `Game/` placeholder, local dump detection, separate fork preferences and no included saves/caches. |

The previous local capture setup reconstructed an already rendered picture and did not reduce the original scene size. This preview moves DLSS/DLAA into the renderer. It extends upstream's experimental upscaler support; it does not claim to invent the original DLSS bridge.

## Download and play

1. Download the ZIP from **Releases** and extract it into a writable folder.
2. Put your own **extracted, updated CUSA01623 v01.02** dump in `Game/CUSA01623/`. It must contain `eboot.bin`, `sce_module` and `sce_sys`. ISO/PKG images must be extracted locally first; they are not directly mounted.
3. Open **God of War III.exe**. The NVIDIA configurator is the default launcher. Select the dump manually if several are present.
4. NVIDIA → **Native** → **DLSS** → final resolution and quality preset. Save, then **PLAY**.
5. To use the game's normal FSR path, turn NVIDIA image processing, NR and frame generation off. FSR remains in Display/Graphics.

The package starts without cheats and has no game data. Your dump is never copied into the repository. The game's original executable remains unchanged; compatible patches are applied in memory.

### Game and hardware

**Validated for this fork: CUSA01623, full update 01.02**, eboot SHA-256 `6e72330e9092e5164049b865e5568f2d450904001a73fe0a2f4b39194c195b3c`. Upstream supports additional builds, but this NVIDIA adaptation was not retested on them. Do not interpret upstream campaign validation as campaign validation of this fork.

Windows 10/11 x64, Vulkan 1.3 and a current compatible driver are required. DLSS/DLAA require GeForce RTX. Actual execution was tested on **RTX 5070**. RTX 30/40 routing is exposed, but those devices were not physically tested here. NVIDIA FG is restricted by GPU generation; experimental bypass options stay off by default.

## Presets with 4K output

| Mode | Internal scene | Final image |
|---|---:|---:|
| Ultra Quality (custom 1.3× factor) | 2954×1662 | 3840×2160 |
| Quality | 2560×1440 | 3840×2160 |
| Balanced | 2258×1270 | 3840×2160 |
| Performance | 1920×1080 | 3840×2160 |
| Ultra Performance | 1280×720 | 3840×2160 |
| DLAA | 3840×2160 | 3840×2160 |

All six were confirmed during the installed-launcher test. Other output sizes scale proportionally, rounded to even dimensions. A 4K final buffer does not turn a 1440p monitor into a physical 4K display. Prerecorded cutscenes retain their source resolution.

## Preview limits

This is a community preview, not a full-campaign or performance benchmark. Camera-derived native motion, scene depth and jitter were validated; complete animated-object motion coverage and artifact-free rendering were not. NR adds cost and may change the look or produce artifacts. A Reflex warning was observed during startup; native SR and FG continued in the recorded test. Frame multipliers and a 240 FPS engine limit are not guarantees of sustained FPS.

**NR is not bundled:** obtain the appropriate `nvngx_dlssnr.dll` separately, following the [mod author's guide](https://github.com/janblade/OptiScaler-F5-DLSSNR-Multipass/blob/ce9d544d0ac72de4dab4dfe56dcd4b74ba79aa69/INSTALL-DLSSNR.md), then use Compatibility mode. See [setup and exact runtime locations](docs/NVIDIA.md).

Update this preview manually from this fork's Releases. Upstream automatic updates are disabled so they cannot replace the NVIDIA launcher. Preserve `Game/` and `user/` when updating.

## Credits

**The original GoW3 PC port is Felipe Prado's [FelipePrado0/gow3_pc](https://github.com/FelipePrado0/gow3_pc).** This community fork extends his work; it is not the original port and is not an official Sony, Santa Monica Studio or NVIDIA release.

- Felipe Prado: GoW3 runtime integration, launcher, patches and upstream Windows releases.
- [cuesta4](https://github.com/cuesta4/shadPS4/tree/eltutz): essential GoW3 rendering fixes; community patches with kvicken.
- [shadPS4 team](https://github.com/shadps4-emu/shadPS4): PS4 graphics/shader translation to Vulkan.
- [Supermedo](https://github.com/Supermedo/bloodborne_pc) and [deadinside28](https://github.com/deadinside28/bloodborne_pc): the Windows/native port lineage.
- kvicken, cuesta4 and illusion0001: the patch lineage; Felipe Prado adapted the 240 FPS patch. Celogamez/GoldHEN: cheat lineage.
- [IFreemz](https://github.com/IFreemz/shadPS4-Bloodborne-DLSS-FSR): DLSS bridge lineage, credited in its MIT-licensed sources.
- [janblade](https://github.com/janblade/OptiScaler-F5-DLSSNR-Multipass), [OptiScaler](https://github.com/optiscaler/OptiScaler), [Dagherbou](https://github.com/Dagherbou/OptiScaler_DLSSNR), [wilsjo2](https://github.com/wilsjo2/OptiScaler-DLSSNR-PreSR-Multipass), [ShortFuse/RenoDX](https://github.com/clshortfuse/renodx): the optional community Neural Rendering/frame-generation stack.
- NVIDIA: DLSS, NGX and Streamline; Intel: optional XeSS Frame Generation. Their binaries retain their vendor licenses.
- All additional upstream contributors and dependencies: preserved in [the original credits](docs/upstream/README.md#credits).

Renderer/launcher changes retain GPL-2.0-or-later. OptiScaler modifications retain its GPL-3.0 license. The separate bridge retains MIT. Vendor SDKs are not relicensed under GPL; keep the supplied notices. Generated launcher panoramas are presentation assets, not files extracted from the game.
