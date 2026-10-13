# NVIDIA setup

The executable starts the redesigned launcher. Native mode calculates internal scene size from the selected final resolution and DLSS preset. DLAA forces input = output and disables DLSS reconstruction.

## Optional Neural Rendering

The community NR runtime is **not included**. Follow the [pinned OptiScaler setup guide](https://github.com/janblade/OptiScaler-F5-DLSSNR-Multipass/blob/ce9d544d0ac72de4dab4dfe56dcd4b74ba79aa69/INSTALL-DLSSNR.md) and obtain the GPU-appropriate `nvngx_dlssnr.dll` separately. Put it in:

```
bin-dlss5/OptiScaler/nvngx_dlssnr.dll
```

Keep the open-source `nvngx.dll_dlssnr.dll` forwarder beside it; these are different files. Choose **Compatibility** in NVIDIA settings, then enable NR and adjust strength, passes and model scale. Native mode suspends NR and keeps your compatibility preferences. This is experimental community integration, not official DLSS5 support for GoW3.

The mod's pinned guide specifies driver 616.56 or newer for its NR path. DLSS/DLAA alone do not use the separate NR model. The correct runtime and older-GPU performance vary; RTX 30/40 NR and MFG extensions were not physically validated by this fork.

## Frame generation and counters

Select NVIDIA frame generation and a multiplier. 2× was observed with the native path on RTX 5070. 3×–6× are experimental on this path. The mod's left counter shows presented/generated performance versus base; the port's right counter reflects engine frames. The multiplier does not promise a matching increase in measured FPS. The Home mod overlay and loss of focus can suspend generation.

## Portability and return

`bin-native-dlss` is selected for SR/DLAA without FG, `bin-native-effects` for SR/DLAA with FG and `bin-dlss5` for the capture compatibility path. Launch configuration is generated in `user/NVIDIA-renderer.ini`; choose lasting settings in the configurator. No absolute machine path is required.

Preferences are in `%APPDATA%/gow3-nvidia-launcher/settings.json`, separate from upstream. Saves and shader caches are created in `user/`. Game files belong only in `Game/` or your selected dump folder; keep them locally. To use FSR, disable NVIDIA image processing, NR and FG. To return to the capture mod, choose Compatibility and restart.
