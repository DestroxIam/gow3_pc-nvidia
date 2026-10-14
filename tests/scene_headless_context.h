// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstddef>
// Opaque boundary: the caller must not emit Vulkan-Hpp dispatcher init definitions.
extern "C" {
void* SceneHeadlessCreate(void* error_counter);
void* SceneHeadlessInstance(void* context);
bool SceneHeadlessCopyDispatch(void* context, void* destination, std::size_t size);
void SceneHeadlessDestroy(void* context);
}
