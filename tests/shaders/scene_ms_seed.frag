// SPDX-License-Identifier: GPL-2.0-or-later
#version 450
#if defined(EXPORT_STENCIL)
#extension GL_ARB_shader_stencil_export : require
#endif
layout(location = 0) out vec4 color;
layout(push_constant) uniform Seed { uint flip; uint width; uint height; uint reserved; } pc;
void main() {
    bool second = gl_SampleID == 1;
    bool green = second != (pc.flip != 0u);
    // The right-hand band detects an unscaled gl_FragCoord fetch when downsampling.
    color = gl_FragCoord.x < float(pc.width) * 0.75 ? vec4(0,0,1,1)
        : green ? vec4(0,1,0,1) : vec4(1,0,0,1);
    gl_FragDepth = pc.flip == 0u ? (second ? 0.75 : 0.25) : (second ? 0.625 : 0.375);
#if defined(EXPORT_STENCIL)
    gl_FragStencilRefARB = pc.flip == 0u ? (second ? 170 : 85) : (second ? 204 : 51);
#endif
}
