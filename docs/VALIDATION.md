# Recorded validation

All five DLSS modes and DLAA evaluated to a 3840×2160 final image through the installed PLAY button, on RTX 5070 and CUSA01623 01.02. Internal dimensions are in README and VALIDATION.json. Native scene depth, camera and jitter were present. FG 2× was observed in the final image with the optional bridge enabled.

The C++ camera test passed projection/inverse/near-plane recovery and invalid-buffer rejection. Python profile checks passed output dimensions, runtime selection, DLAA exclusion, compatibility return and native NR suspension. Original game bytes were unchanged; live tests used private saves.

The earlier capture-only extension observed SDK presented counts of 2 and 6. That does **not** validate native-path 6×. The native test used a 120 FPS engine/port cap; no benchmark was performed. NR + native SR failed interoperability and is suspended. A startup Reflex warning was observed while native SR/FG continued. Other cards, builds, full campaign and complete animated-object motion coverage remain unverified.

Private paths, personal logs, saves and extracted game data have been excluded from this public report.
