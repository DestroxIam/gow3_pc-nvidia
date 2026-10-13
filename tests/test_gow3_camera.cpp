// SPDX-License-Identifier: GPL-2.0-or-later
#include "video_core/renderer_vulkan/gow3_camera.h"
#include <cassert>
#include <iostream>
#include <limits>
using Vulkan::Gow3Camera::Decode;
int main() {
    constexpr float sx=1.9685f,sy=3.49956f,zs=1.00001f,zo=-.500002f;
    std::array<float,36> vp{};
    vp[0]=sx;vp[5]=sy;vp[10]=-zs;vp[11]=-1;vp[14]=zo;
    auto c=Decode(vp.data(),144,16.f/9);
    assert(c && std::abs(c->projection[3]-zo)<1e-5);
    assert(std::abs(-c->projection[3]/c->projection[2]-.5)<1e-3);
    // Camera translation: the recovered inverse must return a view-space origin to world.
    vp[12]=sx*2;vp[13]=sy*3;vp[14]=zs*4+zo;vp[15]=4;
    c=Decode(vp.data(),144,16.f/9);assert(c);
    for(unsigned r=0;r<3;++r) {
        float zero=c->view[r*4+3];
        for(unsigned k=0;k<3;++k)zero+=c->view[r*4+k]*c->inverse[k*4+3];
        assert(std::abs(zero)<1e-4);
    }
    // Identity/model matrices and orthographic UI constants are not cameras.
    std::array<float,36> identity{};identity[0]=identity[5]=identity[10]=identity[15]=1;
    assert(!Decode(identity.data(),144,16.f/9));
    assert(!Decode(vp.data(),64,16.f/9));
    vp[0]=std::numeric_limits<float>::quiet_NaN();assert(!Decode(vp.data(),144,16.f/9));
    std::cout<<"GoW3 camera projection, inverse, near plane and invalid-buffer rejection passed\n";
}
