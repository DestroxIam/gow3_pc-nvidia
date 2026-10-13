# Corresponding optional-mod source

GPL-3.0 source: [janblade/OptiScaler-F5-DLSSNR-Multipass](https://github.com/janblade/OptiScaler-F5-DLSSNR-Multipass), pinned commit `ce9d544d0ac72de4dab4dfe56dcd4b74ba79aa69`.

Clone that repository recursively, check out the commit, then apply these three patches with `git apply`. They implement captured-image quality presets and an opt-in SDK presented-frame diagnostic. Compile `OptiScaler.sln`, Release x64, using MSVC 14.44 and Windows SDK 10.0.26100.0. The packaged proxy is the resulting OptiScaler.dll renamed winmm.dll. NR weights are separately supplied and are not part of this corresponding source.
