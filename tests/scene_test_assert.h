// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cstdio>
#include <cstdlib>

// Keep Vulkan-Hpp's NDEBUG-dependent ABI identical to gow3gpu while retaining
// the regression's checks in release and RelWithDebInfo configurations.
namespace SceneTest { inline unsigned checks = 0; }
#define SCENE_CHECK(condition)                                                                  \
    do {                                                                                        \
        ++SceneTest::checks;                                                                     \
        if (!(condition)) {                                                                     \
            std::fprintf(stderr, "Scene regression check failed: %s (%s:%d)\n", #condition,     \
                         __FILE__, __LINE__);                                                   \
            std::fflush(stderr);                                                                \
            std::_Exit(EXIT_FAILURE);                                                           \
        }                                                                                       \
    } while (false)
