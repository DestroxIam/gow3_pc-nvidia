# NVIDIA integration — Windows 2.1.8

Extends [Felipe Prado's original port](https://github.com/FelipePrado0/gow3_pc).
Upstream `windows-v2.1.8` is `bb74e41cc3c9435c89e3bbd3994b608ad3cff627`.
This experimental preview retains the upstream port and dependency credits.

- Integrate upstream CPU/ISA rewrite, dump validation/repair, UTF-8 logging and MSAA selection. The frozen role host includes iced-x86; missing mandatory imports or PyInstaller ERROR messages now fail the build even with exit code zero.
- Retain DLSS preset-derived internal rendering, native-resolution DLAA, FSR fallback and the NVIDIA launcher design. DLAA and DLSS reconstruction are mutually exclusive.
- Improve native scene completion/camera-history bootstrap, preset changes, MSAA input handling, UI coordinates and video presentation. Refresh auxiliary tessellation varying locations/components/clip data and invalidate incompatible shader-cache serialization.
- Enable experimental native Neural Rendering AFTER-SR only with an approved runtime manifest matching both renderer and OptiScaler hashes, plus the separately supplied user model and forwarder. BEFORE-SR stays blocked.
- Parent observed actual SR + NR + NVIDIA FG 2× with one NR pass on RTX 5070 using renderer `30bf…` and OptiScaler `90c9…`. The optional receipt/marker field `native_nr_fg_tested_multipliers: [2]` identifies this specific tested combination. Other multipliers, providers, extra passes and RTX 30/40 remain unvalidated; this is not whole-campaign validation.
- Add receipt-bound source/build provenance, complete OptiScaler corresponding-source inventory, and optional hash-verified official 2.1.8 base upgrade with backup/rollback. Preserve game data, saves, preferences, NVIDIA files and license notices.

Parent-reported stationary gameplay diagnostic samples, one pass with FG 2×:

| NR model scale | Reported rendered rate | SDK/generated-rate estimate |
|---|---:|---:|
| 25% | 52–53 FPS | about 104–106 FPS |
| 50% | 44–47 FPS | about 88–94 FPS |

These counters are diagnostic estimates, not measured physical displayed-frame
rates or a controlled performance benchmark. The test is windowed, with a 4K SR
target on a 1440p monitor. It does not establish native 4K physical display or
whole-campaign stability. NR adds inference cost; generated frames do not increase
the game's rendered simulation rate. No game files or proprietary NR model weights
are distributed. All original port and dependency credits remain intact.

# Previous preview — Windows 2.1.7

Based on FelipePrado0/gow3_pc Windows v2.1.7, commit b907d8a9f2324ba5f514fbfe7de803e027c6ca26.

- Recover GoW3 camera projection from Z-prepass constants and track the immutable ring snapshot during parallel rendering.
- Delimit GoW3 frames by their actual display-copy shaders; dispatch reconstruction before HUD composition.
- Render to preset-derived internal targets and compose the final image/HUD at the selected output size.
- Add a custom Ultra Quality ratio while preserving existing preset indices; DLAA uses native resolution.
- Centralize NVIDIA controls, show internal → output sizes, preserve FSR, and add the redesigned native launcher.
- Optional Streamline/OptiScaler frame-generation bridge; 2× observed with native SR. Existing 3×–6× options remain experimental on this path.
- Preserve the capture Compatibility path for experimental NR; user-supplied model required, native NR suspended.
- Portable Game placeholder and autodetection, isolated launcher preferences, safe preview defaults and manual fork updates.

No game files, Sony binaries, personal logs, saves, game shaders or NR model weights are distributed. No benchmark or full-campaign claim.
