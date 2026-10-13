// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <cmath>
#include <optional>

namespace Vulkan::Gow3Camera {
struct Camera {
    std::array<float,12> view{}, inverse{};
    std::array<float,4> projection{};
};

// GoW3's Z-prepass constants start with a column-major view-projection.
// Recover the orthonormal view and D3D projection expected by the motion shader.
inline std::optional<Camera> Decode(const float* data, unsigned bytes, float aspect) {
    if (bytes < 128 || bytes > 512 || !data || aspect <= 0) return {};
    std::array<std::array<float,4>,4> rows{};
    for (unsigned r=0;r<4;++r) for(unsigned c=0;c<4;++c) {
        const float value=data[c*4+r];
        if (!std::isfinite(value)) return {};
        rows[r][c]=value;
    }
    auto dot=[](const auto& a,const auto& b){return a[0]*b[0]+a[1]*b[1]+a[2]*b[2];};
    const float x=std::sqrt(dot(rows[0],rows[0]));
    const float y=std::sqrt(dot(rows[1],rows[1]));
    const float z=std::sqrt(dot(rows[3],rows[3]));
    if (x<.01f || y<.01f || z<.01f || std::abs(x/y-1.f/aspect)>.025f) return {};
    if (std::abs(dot(rows[0],rows[1])/(x*y))>.01f ||
        std::abs(dot(rows[0],rows[3])/(x*z))>.01f ||
        std::abs(dot(rows[1],rows[3])/(y*z))>.01f) return {};
    const float zs=dot(rows[2],rows[3])/(z*z);
    const float zo=(rows[2][3]-zs*rows[3][3])/z;
    const float near=-zo/zs;
    if (zs<.9f || zs>1.1f || near<.01f || near>10.f) return {};
    Camera camera;
    camera.projection={x/z,y/z,zs,zo};
    for(unsigned c=0;c<4;++c) {
        camera.view[c]=rows[0][c]/x;
        camera.view[4+c]=rows[1][c]/y;
        camera.view[8+c]=rows[3][c]/z;
    }
    for(unsigned r=0;r<3;++r) {
        for(unsigned c=0;c<3;++c) camera.inverse[r*4+c]=camera.view[c*4+r];
        for(unsigned k=0;k<3;++k) camera.inverse[r*4+3]-=camera.inverse[r*4+k]*camera.view[k*4+3];
    }
    return camera;
}
} // namespace Vulkan::Gow3Camera
