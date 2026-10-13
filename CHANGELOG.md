# NVIDIA Community Preview 1

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
