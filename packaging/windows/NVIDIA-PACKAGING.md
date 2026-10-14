# Parent-owned release packaging

These scripts package already built, stable inputs. They do not build, install, launch,
upload or validate the game, renderer, OptiScaler or proprietary NR model. Candidate
23fc and subsequent queue/history fixes require parent acceptance before release.

## Corresponding OptiScaler source

Use `package-optiscaler-source.py` with `--upstream-zip`, `--source` and `--output`.
The upstream ZIP root must identify commit
`ce9d544d0ac72de4dab4dfe56dcd4b74ba79aa69`. `--audit-only` inventories files without
writing an archive, audit sidecar or checksum. `work/package-optiscaler-source.py`
is a compatibility wrapper around this maintained script; pass `--audit-only` there
for the current local tree, or override the defaults with explicit arguments.

The archive combines that pinned source with every allowed modified/new local
source, shader, project, test, documentation and dependency source file. It does
not use a fixed three-file overlay. Current owned additions include `docs/GOW3-*`,
`tests/private-native-nr`, CPU regression tests/build scripts, and the actual ImGui
backend fix at `OptiScaler/include/imgui/imgui_impl_vulkan.cpp`. Source under
`external/imgui/...` is also covered if present; use the actual files named in the
agent-owned source docs rather than assuming a vendor directory.

`GOW3-SOURCE-MANIFEST.json` records the pinned ZIP hash and every added/modified
file's path, size and SHA-256. A `.audit.json` sidecar and checksum are generated
when packaging. `--checksum-file` updates just that archive's entry in a shared
release checksum file, retaining the binary ZIP's entry. Source and binary
packagers preserve each other's checksums regardless of invocation order.

The source policy excludes runtime DLLs/executables, logs/captures, generated build
headers, object/debug/build outputs, backups, NR model weights and game files.
Existing pinned vendor `.lib`/`.a` and `.spv`/`.cso` assets are retained as upstream
build inputs, with licenses/notices; locally built replacements are not overlaid.
Initialize pinned dependencies recursively if necessary. The old three patch files
describe the earlier capture-preview changes, not the full new native-NR source.

Package only after the parent freezes the intended source snapshot and confirms
it corresponds to the shipped DLL. The packaging manifest is an inventory, not
proof that an arbitrary binary was built from that snapshot.

## Portable binaries and renderer source synchronization

Run `package-nvidia-preview.py` with the base/runtime/native/output inputs,
`--native-effects-runtime` and `--receipt`. Both new inputs are required.
Use a fresh output directory. `--source-root` selects the public source checkout;
the default remains this repository. `--native-effects-runtime` explicitly selects
the parent's stable full effects stage, avoiding an accidental old capture proxy.
The capture runtime remains separately selected by `--runtime-root`.

The binary packager excludes the proprietary NR model while retaining its open
forwarder. It carries `native_nr_after_sr` only from the explicitly selected parent
manifest and only when both staged renderer and OptiScaler hashes match; it never
creates that capability from source/test results. NR/FG are disabled in the clean
distributed INI. User models are supplied separately after extraction.

Before release, pass `--renderer-source` pointing to the parent's stable renderer
checkout. This checks public copies of video-core/shader-recompiler sources,
shim sources, GPU patches and C/C++ tests, including new shader files and headers.
Missing/different files stop packaging with their paths. It never copies or edits
them: the parent must integrate the stable fixes into public source first. The
package audit records whether this optional synchronization check was performed.

Release the complete corresponding-source archive, checksum and audited portable
ZIP together. Live NR/game/QTE acceptance and final deployment remain parent-owned.

## Receipt-bound compiled source identity

`runtime_provenance.py` captures a source snapshot before compilation and binds it
to the stripped staged probe after a successful build. It does not compile or test
the game. The parent must wire these steps around the actual build; the existing
private staging helper must not retroactively assign the current source tree to
an older executable. Existing stages without complete provenance are rejected.

```powershell
python packaging/windows/runtime_provenance.py snapshot --source <renderer-checkout> --tag windows-v2.1.8 --recipe <public-build-recipe.json> --output <before-build.json>
# Run the exact commands recorded in that recipe and stage the compiled probe.
python packaging/windows/runtime_provenance.py bind --source <renderer-checkout> --snapshot <before-build.json> --stage <native-stage>
```

The recipe is a JSON object with `commands` as nonempty argv lists and `toolchain`
as public tool/version strings. Also record configuration, generator, compile/link
flags and dependency versions used by the build. Use relative paths, not local
account paths, credentials or absolute compiler locations. These are actual build
inputs supplied by the runtime owner, not inferred versions.

The manifest records `source_commit` (compiled checkout HEAD), `upstream_tag`,
`upstream_commit` (resolved tag), `source_dirty`, `tracked_source_diff_sha256`,
`untracked_source_sha256`, `source_tree_sha256`, `build_recipe` and `probe_sha256`.
The tracked digest compares HEAD against staged and unstaged changes across all
tracked source roots, including deletions and dependency pointers; it is not GPU
only. Bounded batches and no rename detection provide a deterministic patch digest.
The tree digest includes allowed new source files and initialized dependencies'
current commit, tracked edits and new source inventory recursively. Logs, runtime
outputs, build directories, secrets and game files are excluded. Missing initialized
source dependencies stop the snapshot. A source change between the two steps stops
binding instead of asserting that the changed source produced the earlier binary.

The explicit effects stage has its own `source-manifest.json`, the same probe
identity, `optiscaler_sha256`, and `optiscaler_source` containing
`upstream_commit`, `upstream_archive_sha256`, `overlay_sha256`, `source_tree_sha256`
and the actual OptiScaler `build_recipe`. `package-optiscaler-source.py` still
packages the pinned ce9d source plus the complete allowed overlay, including ImGui,
new shaders, project changes, tests and docs. Supply `--build-recipe` to record the
actual DLL build commands/tool versions. Without it the inventory records a null
recipe and cannot alone complete the effects runtime provenance. Capture/compare
that full source inventory around the OptiScaler build before associating it with
the staged DLL; source packaging does not certify a binary by itself.

The parent test receipt must contain `probe_sha256`, `optiscaler_sha256`,
`source_manifest_sha256` (exact raw pure-stage manifest bytes),
`effects_source_manifest_sha256` (exact raw effects-stage manifest bytes), and
`native_sr_gameplay: true`. The installer and binary packager require every binary
hash to match both its staged manifest and the receipt. Replacing a manifest while
keeping the executable unchanged invalidates an older receipt. Preserve the
original raw manifests with the private test evidence. The portable sidecars carry
only the validated public identity; their `source_manifest_sha256` refers to the
original tested raw stage manifest, not the sanitized sidecar itself. Their own
bytes are separately covered by the portable package audit/checksums.

NR is not enabled by provenance. Carrying `native_nr_after_sr` into a portable
runtime also requires an explicit parent effects capability marker and an approved
receipt flag, with matching binaries. No FG+NR or RTX 30/40 validation is inferred.
The private installer accepts `--native-runtime` for the chosen validated stage,
preserves the existing `%APPDATA%/gow3-launcher` namespace, and defaults to a dry
run. This task never invoked `--apply`, made a production package or uploaded files.

## Optional official 2.1.8 frozen base upgrade

The private installer accepts `--upstream-stage` and `--upstream-manifest`.
For the current parent-owned asset these point to `work/upstream-2.1.8-stage/gow3-windows`
and `work/upstream-2.1.8-base-manifest.json`. The parent verified the official ZIP
SHA-256 `3086d2c1b1c367630379763a217969babd85ccf1d543269f004009f39ab02cc0`.
The receipt also needs `upstream_base_manifest_sha256`, covering the exact base
inventory bytes. Every inventoried asset hash and the resolved upstream tag/commit
must match. The installer records the packaging recipe from that tag's
`packaging/windows/package.sh`; that documented recipe does not independently
attest the official publisher's actual compiler versions.

`upstream_base_upgrade.py` can prepare an inventory from a hash-verified ZIP and
extracted stage. Existing parent full inventories with `tag`, `commit`,
`archive_sha256` and path/hash entries are accepted without rewriting their evidence.
An empty Python `__init__.py` is valid; required executable/native dependency files
must be nonempty. The current official asset selects 161 of 164 files; its three
`launcher/` assets are left alone to preserve the NVIDIA presentation.

The allowlist covers the root frozen launcher and play executable, matched
`_internal` Python environment (including `iced_x86`), `run.py`, upstream `scripts/*.py`,
base `bin` tools/libraries, root patch XML files and base notices/readmes. Game,
user/save/cache folders, `gow3.ini`, preference/config JSON, custom mods, NVIDIA
folders/DLLs, `patches/optiscaler` and `launcher/` never enter this base update.
The existing native runtime update remains separate and receipt-bound.

A later explicit apply first backs up all overwritten base files, including the
original root executable. It moves the old `_internal` into the rollback backup
and installs the complete verified replacement, rather than retaining old modules
through an overlay. An interrupted base copy restores the old root/base files and
frozen environment. Installer preflight blocks an apply while executables run from
the installed port. Installed `%APPDATA%/gow3-launcher` preferences remain untouched.

Without `--upstream-stage`, root/base files remain unchanged. Merely installing two
launcher Python files does not upgrade the embedded role host or cached imports.
The official root executable supplies the official GUI, not the NVIDIA redesign;
keep the existing separate NVIDIA source configurator for this staged workflow.
For a frozen NVIDIA frontend, rebuild the fork launcher from the integrated source:
its PyInstaller recipe now explicitly includes `iced_x86` and `dataclasses` for the
2.1.8 ISA rewrite. No official/fork executable was launched or rebuilt by this task.
