# Corresponding optional-mod source

GPL-3.0 source: [janblade/OptiScaler-F5-DLSSNR-Multipass](https://github.com/janblade/OptiScaler-F5-DLSSNR-Multipass), pinned commit `ce9d544d0ac72de4dab4dfe56dcd4b74ba79aa69`.

These three historical patches implement captured-image quality presets and an opt-in SDK presented-frame diagnostic for the earlier preview. They are **not** the complete corresponding source for the new native NR/interop/queue/ImGui changes.

For the current parent-validated runtime, use the full pinned-source-plus-overlay archive produced by `packaging/windows/package-optiscaler-source.py`, including its file/hash manifest, tests and documentation. See [NVIDIA packaging](../../packaging/windows/NVIDIA-PACKAGING.md). Clone the pinned repository recursively and initialize dependencies before overlaying if necessary. Compile `OptiScaler.sln`, Release x64, using MSVC 14.44 and Windows SDK 10.0.26100.0. The proxy is the resulting OptiScaler.dll renamed winmm.dll. NR weights are separately supplied and excluded from the corresponding-source archive; runtime acceptance and binary/source pairing belong to the parent.
