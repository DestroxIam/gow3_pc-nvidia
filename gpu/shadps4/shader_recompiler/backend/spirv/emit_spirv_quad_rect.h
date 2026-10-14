// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#pragma once

#include <vector>
#include "common/types.h"

namespace Shader::Backend::SPIRV {

enum class AuxShaderType : u32 {
    RectListTCS,
    QuadListTCS,
    PassthroughTES,
};

// Physical locations and component widths declared by the preceding vertex shader.
// Keep sparse exports sparse: PS interpolation slots are consumers, not VS exports.
struct AuxTessellationInterface {
    std::array<u8, 33> components{};

    static constexpr AuxTessellationInterface FromVertexExports(
        const std::array<u8, 32>& exports, bool emulated_clip) {
        AuxTessellationInterface result;
        for (u32 i = 0; i < exports.size(); ++i) {
            result.components[i + u32(emulated_clip)] = exports[i];
        }
        if (emulated_clip) result.components[0] = 4;
        return result;
    }
};

[[nodiscard]] std::vector<u32> EmitAuxilaryTessShader(AuxShaderType type,
                                                    const AuxTessellationInterface& interface);

} // namespace Shader::Backend::SPIRV
