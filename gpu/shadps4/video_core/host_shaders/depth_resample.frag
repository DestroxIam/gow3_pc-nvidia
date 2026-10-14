// SPDX-License-Identifier: GPL-2.0-or-later
// gow3: nearest resample of a depth/stencil image between native and reduced scene
// targets. Used where the format has no blit support (D32S8 on RADV).

#version 450 core
#extension GL_EXT_samplerless_texture_functions : require
#if defined(HAS_STENCIL) || defined(STENCIL_BITS)
#if defined(HAS_STENCIL)
#extension GL_ARB_shader_stencil_export : require
#endif
#if defined(SRC_MSAA)
layout (binding = 1, set = 0) uniform utexture2DMS src_stencil;
#else
layout (binding = 1, set = 0) uniform utexture2D src_stencil;
#endif
#endif
layout (push_constant) uniform SceneResample {
    uint bit; uint width; uint height; uint reserved;
} pc;

#if defined(SRC_MSAA)
layout (binding = 0, set = 0) uniform texture2DMS src_depth;
#else
layout (binding = 0, set = 0) uniform texture2D src_depth;
#endif

layout (location = 0) in vec2 uv;

void main() {
#if defined(SRC_MSAA)
    const ivec2 size = textureSize(src_depth);
    const int source_sample = gl_SampleID;
#else
    const ivec2 size = textureSize(src_depth, 0);
    const int source_sample = 0;
#endif
    // Pixel-centre mapping is independent of the destination sample position. All samples
    // in a destination pixel fetch the same source pixel but retain their own sample ID.
    const vec2 normalized = (floor(gl_FragCoord.xy) + vec2(0.5)) / vec2(pc.width, pc.height);
    const ivec2 coord = clamp(ivec2(normalized * vec2(size)), ivec2(0), size - 1);
#if defined(STENCIL_BITS)
    // Fixed-function stencil replacement writes one bit per draw. The first draw
    // (bit=0, writeMask=0) copies depth everywhere, including zero-stencil pixels.
    if (pc.bit != 0u && (texelFetch(src_stencil, coord, source_sample).r & pc.bit) == 0u) discard;
#endif
    gl_FragDepth = texelFetch(src_depth, coord, source_sample).r;
#if defined(HAS_STENCIL)
    gl_FragStencilRefARB = int(texelFetch(src_stencil, coord, source_sample).r);
#endif
}
