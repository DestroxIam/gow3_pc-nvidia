// SPDX-License-Identifier: GPL-2.0-or-later
// Match vk_platform.cpp's Vulkan-Hpp platform profile in this initialization-only TU.
#if defined(_WIN64)
#define VK_USE_PLATFORM_WIN32_KHR
#elif defined(__APPLE__)
#define VK_USE_PLATFORM_METAL_EXT
#else
#define VK_USE_PLATFORM_WAYLAND_KHR
#define VK_USE_PLATFORM_XLIB_KHR
#endif
#include <atomic>
#include <cstdio>
#include <cstring>
#include <memory>
#include <stdexcept>
#include <vector>
#include "scene_headless_context.h"
#include "video_core/renderer_vulkan/vk_instance.h"

namespace {
struct Context {
    std::unique_ptr<Vulkan::Instance> instance;
    vk::detail::DispatchLoaderDynamic dispatch;
};
std::atomic<unsigned>* initialization_errors = nullptr;
bool initialization_callback_installed = false;
VKAPI_ATTR vk::Bool32 VKAPI_CALL ValidationError(
    vk::DebugUtilsMessageSeverityFlagBitsEXT severity, vk::DebugUtilsMessageTypeFlagsEXT,
    const vk::DebugUtilsMessengerCallbackDataEXT* message, void* user) {
    if (severity == vk::DebugUtilsMessageSeverityFlagBitsEXT::eError) {
        static_cast<std::atomic<unsigned>*>(user)->fetch_add(1);
        std::fprintf(stderr,"Scene target validation: %s\n",message->pMessage);
    }
    return VK_FALSE;
}
}
#ifdef SCENE_WRAP_DEBUG_CALLBACK
// The GNU/MinGW linker wraps only this test executable. The renderer retains
// ownership/lifetime of its messenger, but device creation errors reach our counter.
vk::UniqueDebugUtilsMessengerEXT SceneValidationCallback(vk::Instance instance)
    asm("__wrap__ZN6Vulkan19CreateDebugCallbackEN2vk8InstanceE");
vk::UniqueDebugUtilsMessengerEXT SceneValidationCallback(vk::Instance instance) {
    if (!initialization_errors) throw std::runtime_error("Headless: missing validation counter");
    const vk::DebugUtilsMessengerCreateInfoEXT ci{
        .messageSeverity=vk::DebugUtilsMessageSeverityFlagBitsEXT::eError,
        .messageType=vk::DebugUtilsMessageTypeFlagBitsEXT::eValidation |
                     vk::DebugUtilsMessageTypeFlagBitsEXT::eGeneral,
        .pfnUserCallback=ValidationError,.pUserData=initialization_errors,
    };
    auto [result,messenger]=instance.createDebugUtilsMessengerEXTUnique(ci);
    if (result!=vk::Result::eSuccess) throw std::runtime_error("Headless: validation messenger failed");
    initialization_callback_installed=true;
    return std::move(messenger);
}
#endif
extern "C" void* SceneHeadlessCreate(void* error_counter) {
    // Require validation before creating an instance. Missing layers return a useful
    // harness error instead of silently running an unvalidated regression.
    static vk::detail::DynamicLoader loader;
    const auto get_proc = loader.getProcAddress<PFN_vkGetInstanceProcAddr>("vkGetInstanceProcAddr");
    if (!get_proc) {std::fputs("Headless: missing vkGetInstanceProcAddr\n",stderr);return nullptr;}
    const auto enumerate = reinterpret_cast<PFN_vkEnumerateInstanceLayerProperties>(
        get_proc(nullptr,"vkEnumerateInstanceLayerProperties"));
    uint32_t count=0;
    if (!enumerate || enumerate(&count,nullptr)!=VK_SUCCESS) return nullptr;
    std::vector<VkLayerProperties> layers(count);
    if (enumerate(&count,layers.data())!=VK_SUCCESS) return nullptr;
    bool validation=false;
    for (const auto& layer : layers) validation |= std::strcmp(layer.layerName,"VK_LAYER_KHRONOS_validation")==0;
    if (!validation) {
        std::fputs("Headless: VK_LAYER_KHRONOS_validation unavailable; set process-local VK_LAYER_PATH\n",stderr);
        return nullptr;
    }
    auto context=std::make_unique<Context>();
    std::puts("Headless: creating production Instance");
    initialization_errors=static_cast<std::atomic<unsigned>*>(error_counter);
    initialization_callback_installed=false;
    try {
        context->instance=std::make_unique<Vulkan::Instance>(0,true);
    } catch (const std::exception& error) {
        initialization_errors=nullptr;
        std::fprintf(stderr,"%s\n",error.what());
        return nullptr;
    }
    initialization_errors=nullptr;
    if (!initialization_callback_installed) {
        std::fputs("Headless: initialization validation callback was not installed\n",stderr);
        return nullptr;
    }
    // Copy the production dispatcher after construction. Calling init(Instance/Device)
    // in the test emitted COMDAT definitions that could replace production inline code.
    context->dispatch=VULKAN_HPP_DEFAULT_DISPATCHER;
    if (!context->dispatch.vkGetInstanceProcAddr || !context->dispatch.vkGetDeviceProcAddr ||
        !context->dispatch.vkCreateDebugUtilsMessengerEXT) return nullptr;
    std::puts("Headless: production Instance ready");
    return context.release();
}
extern "C" void* SceneHeadlessInstance(void* context) {
    return static_cast<Context*>(context)->instance.get();
}
extern "C" bool SceneHeadlessCopyDispatch(void* context,void* destination,std::size_t size) {
    if (size!=sizeof(vk::detail::DispatchLoaderDynamic)) return false;
    *static_cast<vk::detail::DispatchLoaderDynamic*>(destination)=static_cast<Context*>(context)->dispatch;
    return true;
}
extern "C" void SceneHeadlessDestroy(void* opaque) {
    auto* context=static_cast<Context*>(opaque);
    delete context;
}
