# NVIDIA setup

The executable starts the redesigned launcher. Native mode calculates internal scene size from the selected final resolution and DLSS preset. DLAA forces input = output and disables DLSS reconstruction.

## Selection versus execution

The NVIDIA tab describes the **next launch**. Selecting DLAA disables DLSS reconstruction and hides the DLSS quality control; the saved DLSS quality is retained for switching back. The final resolution control applies to the native pipeline. Compatibility processes an already rendered image and does not set the game's internal resolution through this control.

A DLSS label in the FPS overlay, a ready camera or a selected preset does **not** prove an SDK evaluation. Menus, videos and unsuitable temporal inputs can use a spatial path. The launcher displays an evaluation confirmation only when the renderer logs `GoW3 native DLSS: ... evaluation N`. This is the latest recorded confirmation, not a per-frame indicator. An explicit spatial/invalid-input message replaces that confirmation with fallback status.

GUI output is tagged with its launch ID. Messages from a previous run cannot confirm SDK execution in a new run. Confirmation resets on runtime restart and game exit; archived logs are never used to populate this status. If no evaluation is logged during a menu or video, status remains unconfirmed even if the overlay says DLSS.

### Development validation status — final acceptance pending

No live installation has been updated with these candidates. The parent reports sustained actual native DLSS SDK evaluations after loading Tomb of Ares, including all six image presets and live preset changes after the history-bootstrap fix. UI/postprocessing `FragCoord` mapping to guest coordinates at the output resolution was also corrected. These are scoped development results, not campaign-wide compatibility or a performance benchmark.

Isolated replays of `PSDNXDEATH` and `PSDNDEATH` show advancing native video, reach their end, and allow a subsequent level to load. They do **not** confirm the actual Gaia-punch quick-time-event transition from the latest save. That controlled full transition remains pending. Movie playback and subsequent level loading must also be distinguished from fresh SR/NR evaluation evidence after the transition; overlay labels and visible rendering alone are insufficient.

## Build identity and persistent diagnostics

The tab shows the preview version, whether the configurator runs from source or a packaged executable, and the expected runtime path. Source mode is not automatically the newest renderer; the executable identifies the renderer independently. Each GUI or `--play` launch writes `<saves folder>/last_run.log` (default `user/last_run.log`), retaining the previous file under `<saves folder>/log/run-*.log`. Closing the configurator leaves a background log reader alive until the game exits.

The `[GoW3 launch]` JSON header records the requested pipeline, DLSS/DLAA mode, applicable quality and internal/final dimensions, FG selection, NR requested/enabled/suspended states, runtime path and actual executable SHA-256, optional build manifest and hash comparison, config path and enabled diagnostics. The header is launch identity, not proof of SDK execution. Runtime/SDK messages follow it; the final exit code is recorded in decimal and hexadecimal. Vulkan validation or GPU profiling can reduce FPS and are explicitly listed. The logger never dumps the full inherited environment or credentials. Paths may be personal: review/redact logs before sharing them publicly.

File write or close failures are reported when forwarding output is possible and do not replace the game's exit code or stop consuming its output. Once a log stream fails, the logger closes it once and disables further writes; a closed console does not interrupt file logging. A failed log cannot guarantee that its final exit line reached disk: the GUI/`--play` return value still carries the process exit code.

Frame-generation preflight checks the selected runtime's libraries. An incomplete native-effects installation cannot be hidden by libraries in the compatibility folder. Preflight errors identify the missing runtime files. Old native builds keep NR suspended; only the gated AFTER-SR path described below can enable it. Native BEFORE-SR remains blocked after the observed interop failure.

## Optional Neural Rendering

The community NR runtime is **not included**. Follow the [pinned OptiScaler setup guide](https://github.com/janblade/OptiScaler-F5-DLSSNR-Multipass/blob/ce9d544d0ac72de4dab4dfe56dcd4b74ba79aa69/INSTALL-DLSSNR.md) and obtain the GPU-appropriate `nvngx_dlssnr.dll` separately. Put it in:

```
bin-dlss5/OptiScaler/nvngx_dlssnr.dll
```

Keep the open-source `nvngx.dll_dlssnr.dll` forwarder beside it; these are different files. Choose **Compatibility** for the capture path, then enable NR and adjust strength, passes and model scale. Native mode on old builds suspends NR and keeps your preferences. This is experimental community integration, not official DLSS5 support for GoW3.

### Gated native NR AFTER-SR

The parent reports that AFTER-SR NR candidate `23fc` sustained one-pass execution on RTX 5070 in Tomb of Ares with the Performance preset and FG disabled. Evidence includes more than 1,200 native SR evaluations after loading together with fresh NR timing messages. Reported NR processing totals were 9.73 and 10.12 ms, with model portions of 7.39 and 8.21 ms. These are diagnostic samples, not an FPS benchmark, a timing guarantee or whole-campaign validation. Menu execution was also observed.

A live change to Quality currently recreates the D3D12 queue: the NR history guard then suppresses NR with `history belongs to another D3D12queue`, while SR continues. The queue/history lifecycle fix remains under investigation. Pure-SR preset-change results therefore do not establish equivalent NR preset-change support. FG 2× + NR testing is in progress; no combination result is claimed yet. Final acceptance and the UI's pending wording remain unchanged until the parent reviews the completed tests. RTX 30/40, extra passes and other visual presets remain physically unvalidated or experimental. NR adds inference cost after reconstruction; it does not itself promise more FPS.

The launcher enables this path only when `bin-native-effects/renderer-build.json` contains all three fields:

```json
{
  "native_nr_after_sr": true,
  "optiscaler_sha256": "<SHA-256 of the parent-validated bin-native-effects/winmm.dll>",
  "probe_sha256": "<SHA-256 of the parent-validated bin-native-effects/gow3-probe.exe>"
}
```

Both hashes must be 64 hexadecimal characters and match the respective nonempty runtime files. These fields are supplied by the runtime owner after validation; adding a flag or hashing arbitrary binaries does not validate them. This launcher change does not create/update production manifests or install runtime binaries. Missing/old manifests and mismatched DLLs or renderers leave native NR suspended, preserving `dlss5_enabled`. Launch preflight recomputes both hashes independently of the UI cache; a verified OptiScaler alone cannot enable NR with an unverified renderer.

Provide the correct model and retain the forwarder in **this runtime**, independently of Compatibility:

```
bin-native-effects/OptiScaler/nvngx_dlssnr.dll
bin-native-effects/OptiScaler/nvngx.dll_dlssnr.dll
```

Both must exist and be nonempty. An otherwise verified build with a requested NR profile fails preflight explicitly if these files are missing. Restore the recommended profile to disable NR without supplying the model. The selected UI state and launch header do not prove model execution; verify the current run's SDK messages and NR timing/evaluation messages in `user/NVIDIA.log`.

With native DLSS/DLAA and NR enabled, the runtime is `bin-native-effects` even when FG is off. The generated mod profile uses the DLSS_on12 bridge (`VulkanUpscaler=dlss_12`), `VulkanInterop/InputsInGeneral=true`, and `DlssNr/NativeFrameGenerationOnly=true`. Native motion/input/upscaler/depth-finder flags are false and `RunBeforeSR=false`. It retains the user's visual settings, defaults to one pass, and records Info logs (`LogLevel=2`). FG-off sets both `FGInput` and `FGOutput` to `nofg`; FG+NR may be selected experimentally but has not been validated. Disable FG to reproduce the tested path. RTX 30/40 require the explicit experimental option and remain physically unvalidated.

The mod's pinned guide specifies driver 616.56 or newer for its NR path. DLSS/DLAA alone do not use the separate NR model. The correct runtime and older-GPU performance vary; RTX 30/40 NR and MFG extensions were not physically validated by this fork.

## Frame generation and counters

Select NVIDIA frame generation and a multiplier. 2× was observed with the native path on RTX 5070. 3×–6× are experimental on this path. The mod's left counter shows presented/generated performance versus base; the port's right counter reflects engine frames. The multiplier does not promise a matching increase in measured FPS. The Home mod overlay and loss of focus can suspend generation.

## Portability and return

`bin-native-dlss` is selected for SR/DLAA without FG or available requested native NR. `bin-native-effects` is selected for SR/DLAA with FG or gated native AFTER-SR NR, including NR with FG off. `bin-dlss5` is used for the capture compatibility path. Launch configuration is generated in `user/NVIDIA-renderer.ini`; choose lasting settings in the configurator. No absolute machine path is required.

Preferences are in `%APPDATA%/gow3-nvidia-launcher/settings.json`, separate from upstream. Saves and shader caches are created in `user/`. Game files belong only in `Game/` or your selected dump folder; keep them locally. To use FSR, disable NVIDIA image processing, NR and FG. To return to the capture mod, choose Compatibility and restart.
