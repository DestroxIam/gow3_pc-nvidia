// SPDX-License-Identifier: GPL-2.0-or-later
// Bounded headless Vulkan regression: no game, window, NGX or user saves.
// The opaque context isolates production Vulkan-Hpp initialization from test inlines.
#include <array>
#include <atomic>
#include <cassert>
#include <cstdio>
#include <cstring>
#include "common/slot_vector.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_scene_resolution.h"
#include "video_core/texture_cache/blit_helper.h"
#include <vk_mem_alloc.h>
#include "scene_test_assert.h"
#include "scene_ms_samples.h"
#include "scene_headless_context.h"

int main() {
    using namespace Vulkan;
    std::setvbuf(stdout,nullptr,_IONBF,0);
    std::setvbuf(stderr,nullptr,_IONBF,0);
    std::atomic<unsigned> errors = 0;
    auto* context=SceneHeadlessCreate(&errors);
    if (!context) return 2;
    auto& instance=*static_cast<Instance*>(SceneHeadlessInstance(context));
    vk::detail::DispatchLoaderDynamic dispatch;
    SCENE_CHECK(SceneHeadlessCopyDispatch(context,&dispatch,sizeof(dispatch)));
    {
        Scheduler scheduler(instance);
        Runtime runtime(instance, scheduler);
        Common::SlotVector<VideoCore::ImageView> views;
        Common::SlotVector<VideoCore::Image> images;
        SceneTargets targets(instance, scheduler, runtime, [&](VideoCore::ImageId id, u64 uid) {
            if (!id || !images.is_allocated(id)) return static_cast<VideoCore::Image*>(nullptr);
            return !uid || images[id].image_uid == uid ? &images[id] : nullptr;
        });
        targets.SetSize({960, 540});
        VideoCore::ImageInfo color_info;
        color_info.size = {1920, 1080, 1};
        color_info.resources = {1, 1};
        color_info.type = AmdGpu::ImageType::Color2D;
        color_info.pixel_format = vk::Format::eR8G8B8A8Unorm;
        color_info.num_bits = 32;
        VideoCore::ImageViewInfo color_view;
        color_view.format = color_info.pixel_format;
        SCENE_CHECK(!targets.Read({}, color_view).image);
        SCENE_CHECK(!targets.Attachment({}, color_view).image);

        // Actual 2x MSAA: scaled proxies retain samples; fallback reports native extents.
        for (const bool depth : {false, true}) {
            auto info = color_info;
            info.num_samples = 2;
            info.props.is_depth = info.props.has_stencil = depth;
            if (depth) info.pixel_format = vk::Format::eD32SfloatS8Uint;
            const auto id = images.insert(instance, runtime, views, info);
            auto& image = images[id];
            const bool eligible = targets.Eligible(image);
            if (image.backing->image.image_ci.samples == vk::SampleCountFlagBits::e2 &&
                instance.IsSampleRateShadingEnabled()) SCENE_CHECK(eligible);
            auto view = color_view;
            view.format = info.pixel_format;
            const auto* backing = image.backing;
            const auto sample_count = backing->image.image_ci.samples;
            const auto read = targets.Read(id, view);
            SCENE_CHECK(read.view && (read.image != image.GetImage()) == eligible);
            SCENE_CHECK(read.width == (eligible ? 960u : 1920u) && read.height == (eligible ? 540u : 1080u));
            SCENE_CHECK(read.samples == sample_count);
            SCENE_CHECK(read.layout == vk::ImageLayout::eGeneral);
            SCENE_CHECK(image.backing == backing && image.backing->image.image_ci.samples == sample_count);
            SCENE_CHECK(targets.Tracks(image.image_uid) == eligible && image.scene_proxy == eligible);
            const auto attachment = targets.Attachment(id, view);
            SCENE_CHECK(attachment.view && (attachment.image != image.GetImage()) == eligible);
            SCENE_CHECK(attachment.width == read.width && attachment.height == read.height && attachment.samples == sample_count);
            SCENE_CHECK(attachment.layout == (depth ? vk::ImageLayout::eDepthStencilAttachmentOptimal
                                               : vk::ImageLayout::eColorAttachmentOptimal));
            SCENE_CHECK(!targets.SampleProxy(image, view));
            if (eligible && !depth) {
                view.type = AmdGpu::ImageType::Color2DMsaa;
                SCENE_CHECK(targets.SampleProxy(image, view));
            } else SCENE_CHECK(targets.PrepareSample(image) == vk::ImageLayout::eUndefined);
            if (sample_count == vk::SampleCountFlagBits::e2) {
                // A stale guest/backing counter must not hide the actual Vulkan sample count.
                image.info.num_samples = 1;
                image.backing->num_samples = 1;
                SCENE_CHECK(!targets.Eligible(image));
                image.info.num_samples = image.backing->num_samples = 2;
            } else {
                std::fprintf(stderr, "2x %s allocation unsupported: metadata fallback checked\n",
                             depth ? "depth" : "color");
            }
        }
        // A resource outside the scene shape stays native even on MSAA-capable devices.
        auto fallback_info = color_info;
        fallback_info.size = {1280, 720, 1};
        fallback_info.num_samples = 2;
        const auto fallback_id = images.insert(instance, runtime, views, fallback_info);
        const auto fallback = targets.Read(fallback_id, color_view);
        SCENE_CHECK(fallback.image == images[fallback_id].GetImage());
        SCENE_CHECK(fallback.width == 1280 && fallback.height == 720);
        SCENE_CHECK(fallback.samples == images[fallback_id].backing->image.image_ci.samples);

        VkBuffer readback{};
        VmaAllocation allocation{};
        VmaAllocationInfo mapped{};
        const VkBufferCreateInfo buffer_ci{.sType = VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,
            .size = 4, .usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT};
        const VmaAllocationCreateInfo allocation_ci{
            .flags = VMA_ALLOCATION_CREATE_MAPPED_BIT | VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT,
            .usage = VMA_MEMORY_USAGE_AUTO, .requiredFlags = VK_MEMORY_PROPERTY_HOST_COHERENT_BIT,
        };
        SCENE_CHECK(vmaCreateBuffer(instance.GetAllocator(), &buffer_ci, &allocation_ci,
                               &readback, &allocation, &mapped) == VK_SUCCESS);
        const auto pixel = [&](vk::Image image, vk::ImageLayout layout, u32 level, u32 w, u32 h) {
            scheduler.EndRendering();
            const auto cmd = scheduler.CommandBuffer();
            const vk::MemoryBarrier2 read_barrier{
                .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
                .srcAccessMask = vk::AccessFlagBits2::eMemoryWrite,
                .dstStageMask = vk::PipelineStageFlagBits2::eTransfer,
                .dstAccessMask = vk::AccessFlagBits2::eTransferRead,
            };
            cmd.pipelineBarrier2({.memoryBarrierCount = 1, .pMemoryBarriers = &read_barrier}, dispatch);
            const vk::BufferImageCopy copy{.imageSubresource = {vk::ImageAspectFlagBits::eColor, level, 0, 1},
                .imageOffset = {s32(w - 1), s32(h - 1), 0}, .imageExtent = {1, 1, 1}};
            cmd.copyImageToBuffer(image, layout, readback, copy, dispatch);
            const vk::MemoryBarrier2 host_barrier{
                .srcStageMask = vk::PipelineStageFlagBits2::eTransfer,
                .srcAccessMask = vk::AccessFlagBits2::eTransferWrite,
                .dstStageMask = vk::PipelineStageFlagBits2::eHost,
                .dstAccessMask = vk::AccessFlagBits2::eHostRead,
            };
            cmd.pipelineBarrier2({.memoryBarrierCount = 1, .pMemoryBarriers = &host_barrier}, dispatch);
            scheduler.Finish();
            u32 rgba;
            std::memcpy(&rgba, mapped.pMappedData, sizeof(rgba));
            return rgba;
        };
        const auto clear_native = [&](VideoCore::Image& image, std::array<float, 4> rgba) {
            const vk::ClearValue value{.color = {.float32 = rgba}};
            runtime.ClearImage(&image, {}, value);
        };
        const auto clear_attachment = [&](const SceneTargets::Target& target, u32 w, u32 h) {
            const vk::RenderingAttachmentInfo attachment{
                .imageView = target.view, .imageLayout = target.layout,
                .loadOp = vk::AttachmentLoadOp::eClear, .storeOp = vk::AttachmentStoreOp::eStore,
                .clearValue = {.color = {.float32 = std::array{1.f, 0.f, 0.f, 1.f}}},
            };
            auto cmd = scheduler.CommandBuffer();
            cmd.beginRendering({.renderArea = {{0, 0}, {w, h}}, .layerCount = 1,
                .colorAttachmentCount = 1, .pColorAttachments = &attachment}, dispatch);
            cmd.endRendering(dispatch);
        };

        // sRGB attachment, sampled and UNORM storage views must not share inherited usages.
        for (const auto format : {vk::Format::eR8G8B8A8Unorm, vk::Format::eR8G8B8A8Srgb}) {
            auto info = color_info;
            info.pixel_format = format;
            const auto id = images.insert(instance, runtime, views, info);
            auto& image = images[id];
            SCENE_CHECK(targets.Eligible(image));
            clear_native(image, {0.f, 0.f, 1.f, 1.f});
            auto view = color_view;
            view.format = format;
            const auto sampled = targets.Read(id, view);
            const auto attachment = targets.Attachment(id, view);
            SCENE_CHECK(sampled.image != image.GetImage() && sampled.view != attachment.view);
            clear_attachment(attachment, 960, 540);
            runtime.Transit(&image, vk::ImageLayout::eTransferSrcOptimal,
                vk::PipelineStageFlagBits2::eTransfer, vk::AccessFlagBits2::eTransferRead);
            runtime.FlushBarriers();
            SCENE_CHECK(pixel(image.GetImage(), vk::ImageLayout::eTransferSrcOptimal, 0, 1920, 1080) == 0xff0000ff);
            auto storage_view = view;
            storage_view.is_storage = true;
            const auto storage = targets.Read(id, storage_view,
                vk::PipelineStageFlagBits2::eTransfer, vk::AccessFlagBits2::eTransferWrite);
            SCENE_CHECK(storage.view != sampled.view && storage.view != attachment.view);
            scheduler.CommandBuffer().clearColorImage(storage.image, storage.layout,
                vk::ClearColorValue{.float32 = std::array{0.f, 1.f, 0.f, 1.f}},
                vk::ImageSubresourceRange{vk::ImageAspectFlagBits::eColor, 0, 1, 0, 1}, dispatch);
            runtime.Transit(&image, vk::ImageLayout::eTransferSrcOptimal,
                vk::PipelineStageFlagBits2::eTransfer, vk::AccessFlagBits2::eTransferRead);
            runtime.FlushBarriers();
            // Read(write) must make the proxy dirty: green must be resolved back to native.
            SCENE_CHECK(pixel(image.GetImage(), vk::ImageLayout::eTransferSrcOptimal, 0, 1920, 1080) == 0xff00ff00);

            // Replace the handle inside the same BackingImage object. Dirty red from the old
            // proxy must neither be sampled nor be written into the replacement native image.
            clear_attachment(targets.Attachment(id, view), 960, 540);
            scheduler.Finish();
            const auto old_generation = targets.Generation();
            const auto old_proxy = targets.Read(id, view).image;
            scheduler.Finish();
            auto retired_native = std::move(image.backing->image);
            image.backing->image = VideoCore::UniqueImage(instance.GetDevice(), instance.GetAllocator());
            image.backing->image.Create(retired_native.image_ci);
            image.backing->state = {};
            image.backing->subresource_states.clear();
            image.backing->image_view_infos.clear();
            image.backing->image_view_ids.clear();
            SCENE_CHECK(!targets.ProxyCurrent(image));
            SCENE_CHECK(!targets.SampleProxy(image, view));
            SCENE_CHECK(targets.Generation() > old_generation && !targets.Tracks(image.image_uid));
            SCENE_CHECK(targets.PrepareSample(image) == vk::ImageLayout::eUndefined);
            clear_native(image, {0.f, 0.f, 1.f, 1.f});
            const auto replacement = targets.Read(id, view);
            SCENE_CHECK(replacement.image != old_proxy);
            SCENE_CHECK(pixel(replacement.image, replacement.layout, 0, 960, 540) == 0xffff0000);
            scheduler.Finish();
        }

        // Reading a bloom mip must use that level, not silently fetch proxy level zero.
        auto bloom_info = color_info;
        bloom_info.size = {960, 540, 1};
        bloom_info.resources.levels = 4;
        const auto bloom_id = images.insert(instance, runtime, views, bloom_info);
        auto& bloom = images[bloom_id];
        auto level_view = color_view;
        level_view.range.base.level = 2;
        const auto level_attachment = targets.Attachment(bloom_id, level_view);
        clear_attachment(level_attachment, 120, 67);
        const auto level_read = targets.Read(bloom_id, level_view);
        SCENE_CHECK(level_read.image == level_attachment.image);
        SCENE_CHECK(pixel(level_read.image, level_read.layout, 0, 120, 67) == 0xff0000ff);
        auto bad_range = color_view;
        bad_range.range.base.level = 16;
        SCENE_CHECK(!targets.Read(bloom_id, bad_range).image);
        SCENE_CHECK(!targets.Attachment(bloom_id, bad_range).image);
        SCENE_CHECK(TestSceneMsSamples(instance,scheduler,runtime,targets,images,views,dispatch)==6);
        scheduler.Finish();
        vmaDestroyBuffer(instance.GetAllocator(), readback, allocation);
    }
    SceneHeadlessDestroy(context);
    SCENE_CHECK(errors == 0);
    std::printf("SceneTargets safety: MSAA scaling/fallback, actual extents, sRGB usage, writes, backing lifetime, mip reads PASS (6 presets, %u checks, %u validation errors)\n",
                SceneTest::checks,errors.load());
    return 0;
}
