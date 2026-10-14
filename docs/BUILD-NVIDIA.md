# Build this preview

The complete GoW3 renderer/runtime source is this fork, based on the recorded upstream commit. Initialize the existing submodules recursively and use MSYS2 CLANG64 for the normal upstream `build.sh`. The camera CPU test is `gow3-camera-test` in the GPU CMake project.

The NVIDIA bridge is separate MIT-licensed code in `gpu/dlss_bridge`. Build with MSVC, the official NVIDIA DLSS SDK and Vulkan-Headers, as documented by its CMakeLists. Keep NVIDIA's runtime/SDK notices; the SDK is not relicensed by this fork.

Optional mod source and exact local changes: [patches/optiscaler](../patches/optiscaler/README.md). Its NVIDIA/Intel/Streamline dependencies retain their own supplied licenses. The NR model is supplied separately by the player.

The launcher source is `launcher/gow3_launcher_win.py`; `gow3_launcher_dlss.py` is the equivalent script entrypoint. Freeze with Python 3.12 / PyInstaller 6.20, Windows x64, using the recipe in `packaging/windows/build-nvidia-launcher.py`. The publisher script in `packaging/windows/package-nvidia-preview.py` uses allowlisted runtime trees, excludes all game files/caches/personal data and emits SHA-256 checksums. It does not access a game dump.

Generated art in `launcher/redesign-assets` is used by the Tk presentation. Existing upstream icons/fonts keep their provenance. Upstream README and credits are preserved in `docs/upstream`.

Compiled-source provenance and required receipt fields: [packaging procedure](../packaging/windows/NVIDIA-PACKAGING.md#receipt-bound-compiled-source-identity). Source snapshots must be captured before compilation, then bound to the staged binary after an unchanged-source check.

Public renderer synchronization includes commit `d60025abf3603a1b123f2b35a58c5195ff0913fa` (`d60025a`), retaining the 2.1.8 upstream `bb74e41` ancestry. It refreshes the auxiliary tessellation/pipeline interfaces and `test_aux_tessellation_interface.cpp` beyond `3c9417f`. The older `419399…` binary had VUID08743; the final `30bf…` candidate passed active-SR validation without those errors. Limited RTX5070 SR+NR+FG2 evidence is recorded in [Validation](VALIDATION.md); other combinations remain unvalidated.

Serialization checkpoint `dfd8f5ff15b09ce3800754129979106416fb7ae9` replaces unsupported array container read/write calls with raw array-buffer read/write. It is the source checkpoint recorded for the compiled `30bf…` candidate. Receipt-bound manifests identify the tested renderer, OptiScaler DLL, effective source tree and build commands.

For a clean source checkout, the FSR synchronization check compares an isolated Git index built from the pinned dependency plus declared patches against the parent effective tracked tree. It does not change either real index/worktree. Apply the declared dependency patches before capturing build-time provenance.
