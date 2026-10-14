// SPDX-License-Identifier: GPL-2.0-or-later
// Nearest per-sample scene resampling, with compatible float/uint/sint color outputs.
#version 450 core
#extension GL_EXT_samplerless_texture_functions : require
#if defined(COLOR_UINT)
layout (binding = 0, set = 0) uniform utexture2DMS src_color;
layout (location = 0) out uvec4 out_color;
#elif defined(COLOR_SINT)
layout (binding = 0, set = 0) uniform itexture2DMS src_color;
layout (location = 0) out ivec4 out_color;
#else
layout (binding = 0, set = 0) uniform texture2DMS src_color;
layout (location = 0) out vec4 out_color;
#endif
layout (push_constant) uniform SceneResample {
    uint bit; uint width; uint height; uint reserved;
} pc;
void main() {
    const ivec2 size = textureSize(src_color);
    const vec2 normalized = (floor(gl_FragCoord.xy) + vec2(0.5)) / vec2(pc.width, pc.height);
    const ivec2 coord = clamp(ivec2(normalized * vec2(size)), ivec2(0), size - 1);
    out_color = texelFetch(src_color, coord, gl_SampleID);
}
