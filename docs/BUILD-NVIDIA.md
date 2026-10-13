# Build this preview

The complete GoW3 renderer/runtime source is this fork, based on the recorded upstream commit. Initialize the existing submodules recursively and use MSYS2 CLANG64 for the normal upstream `build.sh`. The camera CPU test is `gow3-camera-test` in the GPU CMake project.

The NVIDIA bridge is separate MIT-licensed code in `gpu/dlss_bridge`. Build with MSVC, the official NVIDIA DLSS SDK and Vulkan-Headers, as documented by its CMakeLists. Keep NVIDIA's runtime/SDK notices; the SDK is not relicensed by this fork.

Optional mod source and exact local changes: [patches/optiscaler](../patches/optiscaler/README.md). Its NVIDIA/Intel/Streamline dependencies retain their own supplied licenses. The NR model is supplied separately by the player.

The launcher source is `launcher/gow3_launcher_win.py`; `gow3_launcher_dlss.py` is the equivalent script entrypoint. Freeze with Python 3.12 / PyInstaller 6.20, Windows x64, using the recipe in `packaging/windows/build-nvidia-launcher.py`. The publisher script in `packaging/windows/package-nvidia-preview.py` uses allowlisted runtime trees, excludes all game files/caches/personal data and emits SHA-256 checksums. It does not access a game dump.

Generated art in `launcher/redesign-assets` is used by the Tk presentation. Existing upstream icons/fonts keep their provenance. Upstream README and credits are preserved in `docs/upstream`.
