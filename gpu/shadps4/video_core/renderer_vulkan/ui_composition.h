// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include <array>
#include <cmath>
#include <cstdint>

namespace Vulkan::UiComposition {

enum class Background { None, Copy, Temporal };

// UI composition must not require scene depth/camera or an active FSR context.
constexpr Background Choose(bool scaled, bool ui_draw, bool scene_ready, bool fsr_active) {
    if (!scaled || !ui_draw) {
        return Background::None;
    }
    return scene_ready && fsr_active ? Background::Temporal : Background::Copy;
}

inline bool NativeViewport(float width, float height) {
    return std::abs(std::abs(width) - 1920.0f) < 0.5f &&
           std::abs(std::abs(height) - 1080.0f) < 0.5f;
}

// Scaleform draws, including the first stencil/movie pass. A native-size viewport
// alone also matches every fullscreen post pass when guest targets stay at 1080p.
constexpr bool MovieShader(uint64_t hash) {
    const auto gow3=uint32_t(hash);
    if (gow3==0x299c282c || gow3==0xb4c8fcb8) return true;
    return hash == 0x34e8a281 || hash == 0x81d336ce || hash == 0x09957251 ||
           hash == 0x24042a9b || hash == 0xa400228b;
}

// GoW3 decoded Y/UV planes -> RGBA. This is a video conversion, not UI:
// the native post-processing chain must still consume the converted guest image.
constexpr bool VideoShader(uint64_t hash) {
    return uint32_t(hash) == 0xb4c8fcb8;
}

// Vertex programs for the game's final display-copy paths (including the
// general fullscreen-post variant); classify programs, never game areas/saves.
constexpr bool SceneCopyShader(uint64_t hash) {
    const auto code = uint32_t(hash);
    return code == 0x56d7530b || code == 0x3167b1ca || code == 0x77985107;
}

inline std::array<float, 2> Scale(uint32_t guest_width, uint32_t guest_height,
                                uint32_t output_width, uint32_t output_height,
                                bool native_coordinates) {
    return {float(output_width) / float(native_coordinates ? 1920 : guest_width),
            float(output_height) / float(native_coordinates ? 1080 : guest_height)};
}

} // namespace Vulkan::UiComposition
