# Windows 2.1.8 validation

RTX 5070 / i5-14600KF, CUSA01623 01.02, renderer SHA-256
`30bfba3cca51dd2513332466440d2733334e7487f3273e53206d43d159d30c0d`,
OptiScaler SHA-256 `90c9e3e3d059ffd3f90c46445278a93288beb385ac7eb83a1d9df978501e4de2`.

Actual SDK evaluations resumed after video playback and continued in Entrance to
Ares Tomb with native scene camera, depth, motion and jitter. The Poseidon death
video was visible in a diagnostic replay using these binaries; SR, NR and FG 2x
resumed afterwards. This replay does not validate the entire boss sequence or campaign.

Active SR with Vulkan validation in the menu and loaded gameplay produced zero
VUIDs after the auxiliary shader fix. The final headless scene-safety run passed
148 checks over six presets. Auxiliary-interface fixtures covered 1,536 shader
modules; 15 Vulkan 1.3 SPIR-V fixtures validated. OptiScaler command-registration
lifetime tests passed nine cases, including concurrent contention.

SR reconstructed 1920x1080 to 3840x2160. The windowed presentation canvas was
1920x1080; fullscreen follows the desktop resolution. FG operates on that canvas,
not necessarily the SR target. A 4K reconstruction target is not proof of a 4K
physical display. DLSSG obtains its dimensions from the actual swapchain, and
normalizes motion with the tagged guide dimensions; no speculative vector scaling
was applied.

With NR and FG 2x, the SDK reported frames=2 and result/status=0 across more than
six minutes of sampled gameplay reports. FG suspended briefly as expected when
closing the old configurator changed focus. The earlier duplicate-command-buffer
freeze did not recur during this interval; controls remained responsive. Initial
Streamline/Reflex transition warnings occurred before recovery.

Observed stationary diagnostic samples were 52-53 rendered FPS with NR model
scale 25%, and 44-47 with scale 50%. Later samples at 50% reached about54FPS;
movement initially fell near40FPS. Combining renderer counters with SDK frames=2
gives generated-rate estimates, not a measured physical display rate or controlled
average. Vulkan validation was disabled for these performance samples. The earlier
93-96 FPS SR-only observation used a preceding renderer candidate and is not a
separate final-build benchmark.

One NR pass with NVIDIA FG2 on RTX5070 is the tested combination. RTX30/40,
multipliers3-6, additional NR passes, moving-object coverage and full-campaign
stability remain unverified. NR depth/model units, normal/albedo approximations,
motion guide calibration and disocclusions can still cause visual artifacts.
Missing or mismatched runtime markers keep native NR suspended.

The frozen 2.1.8 frontend passed native iced-x86/Pillow imports, source-code role
checks and license checks. No game data, player saves, diagnostic logs, private
paths or proprietary NR weights are distributed.

## Historical Windows 2.1.7 preview evidence

All five DLSS modes and DLAA evaluated to a 3840×2160 final image through the installed PLAY button, on RTX 5070 and CUSA01623 01.02. Internal dimensions are in README and VALIDATION.json. Native scene depth, camera and jitter were present. FG 2× was observed in the final image with the optional bridge enabled.

The C++ camera test passed projection/inverse/near-plane recovery and invalid-buffer rejection. Python profile checks passed output dimensions, runtime selection, DLAA exclusion, compatibility return and native NR suspension. Original game bytes were unchanged; live tests used private saves.

The earlier capture-only extension observed SDK presented counts of 2 and 6. That does **not** validate native-path 6×. The native test used a 120 FPS engine/port cap; no benchmark was performed. NR + native SR failed interoperability and is suspended. A startup Reflex warning was observed while native SR/FG continued. Other cards, builds, full campaign and complete animated-object motion coverage remain unverified.

Private paths, personal logs, saves and extracted game data have been excluded from this public report.

The freshly frozen portable executable also confirmed native 1920×1080 → 3840×2160 without the NR model, with private saves. The optional FG bridge emitted missing-depth/motion-tag and Reflex warnings during transitions; generation can pause there. Native SR continued in the recorded interval. Disable FG if a transition is affected. This remains a preview, not a campaign-stability claim.
