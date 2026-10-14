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

Run `package-nvidia-preview.py` with the existing base/runtime/native/output inputs.
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
