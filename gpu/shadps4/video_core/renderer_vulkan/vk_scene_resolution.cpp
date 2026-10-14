// SPDX-License-Identifier: GPL-2.0-or-later
#include "video_core/renderer_vulkan/vk_scene_resolution.h"
#include "video_core/renderer_vulkan/vk_instance.h"
#include "video_core/renderer_vulkan/vk_runtime.h"
#include "video_core/renderer_vulkan/vk_scheduler.h"
#include "video_core/renderer_vulkan/vk_shader_util.h"
#include "video_core/renderer_vulkan/liverpool_to_vk.h"
#include "video_core/texture_cache/texture_cache.h"
#include "video_core/host_shaders/depth_resample_frag.h"
#include "video_core/host_shaders/depth_stencil_resample_frag.h"
#include "video_core/host_shaders/depth_stencil_bits_frag.h"
#include "video_core/host_shaders/depth_resample_ms_frag.h"
#include "video_core/host_shaders/depth_stencil_resample_ms_frag.h"
#include "video_core/host_shaders/depth_stencil_bits_ms_frag.h"
#include "video_core/host_shaders/scene_color_resample_ms_frag.h"
#include "video_core/host_shaders/scene_color_resample_ms_uint_frag.h"
#include "video_core/host_shaders/scene_color_resample_ms_sint_frag.h"
#include "video_core/host_shaders/fs_tri_vert.h"
#include "gow3_toggles.h"
#include <cstdio>
#include <cstdlib>

namespace Vulkan {
SceneTargets::SceneTargets(const Instance& i, Scheduler& s, Runtime& r,
                           VideoCore::TextureCache& t)
    : SceneTargets(i, s, r, [&t](VideoCore::ImageId id, u64 uid) {
        return t.TryGetImage(id, uid);
    }) {}
SceneTargets::SceneTargets(const Instance& i, Scheduler& s, Runtime& r, Lookup get)
    : instance{i}, scheduler{s}, runtime{r}, lookup{std::move(get)} {
    runtime.scene_targets = this;
    const char* force = std::getenv("GOW3_SCENE_STENCIL_BITS");
    force_stencil_bits = force && force[0] == '1';
    CreateResampleResources();
}
SceneTargets::~SceneTargets() {
    scheduler.Finish();
    runtime.scene_targets = nullptr;
}
vk::FormatFeatureFlags SceneTargets::Features(vk::Format format) const {
    // Called for every attachment of every draw: the driver query was ~5% of the GPU thread.
    // Core formats index a flat table; extension formats (large enum values) use the map.
    const auto index = u32(format);
    if (index < format_table.size() && format_known[index]) return format_table[index];
    if (index >= format_table.size()) {
        if (const auto it = format_features.find(format); it != format_features.end()) {
            return it->second;
        }
    }
    const auto features =
        instance.GetPhysicalDevice().getFormatProperties(format).optimalTilingFeatures;
    if (index < format_table.size()) {
        format_table[index] = features;
        format_known[index] = true;
    } else {
        format_features.emplace(format, features);
    }
    return features;
}
bool SceneTargets::Blittable(vk::Format format) const {
    const auto features = Features(format);
    const auto required = vk::FormatFeatureFlagBits::eBlitSrc | vk::FormatFeatureFlagBits::eBlitDst;
    return (features & required) == required;
}
bool SceneTargets::ShaderResampled(const VideoCore::Image& image) const {
    if (!image.backing) return false;
    const auto format = image.backing->image.image_ci.format;
    const bool ms = image.backing->image.image_ci.samples != vk::SampleCountFlagBits::e1;
    if (!image.info.props.is_depth || (!ms && Blittable(format) && !force_stencil_bits)) return false;
    const auto features = Features(format);
    const auto required = vk::FormatFeatureFlagBits::eSampledImage |
                          vk::FormatFeatureFlagBits::eDepthStencilAttachment;
    // Without shader stencil export (e.g. Pascal) depth/stencil stays native: the eight-draw
    // stencil resampler costs too much on such GPUs. GOW3_SCENE_STENCIL_BITS=1 forces it (tests).
    return (features & required) == required &&
           (!(image.aspect_mask & vk::ImageAspectFlagBits::eStencil) ||
            instance.IsShaderStencilExportSupported() || force_stencil_bits || ms);
}
// 1 for the scene size, 2 for half resolution (the game's post-processing chain), else 0.
// Half resolution needs a scene size that halves exactly: the proxy keeps the scene's factor,
// so the shaders' FragCoord conversion (1920 / scene width) stays correct for it.
static u32 SizeDivisor(const VideoCore::ImageInfo& i, SceneResolution::Size scene) {
    if (i.size.width == 1920 && i.size.height == 1080) return 1;
    if (i.size.width == 960 && i.size.height == 540 && scene.width % 2 == 0 &&
        scene.height % 2 == 0 && !Gow3Toggle::Disabled(Gow3Toggle::SceneHalfRes)) {
        return 2;
    }
    return 0;
}
bool SceneTargets::Eligible(const VideoCore::Image& image) const {
    const auto& i = image.info;
    const u32 div = SizeDivisor(i, size);
    if (!div || i.size.depth != 1 || i.resources.layers != 1 ||
        i.props.is_block || !image.backing) {
        return false;
    }
    const auto& ci = image.backing->image.image_ci;
    // The guest description can outlive a host backing switch (resolve/MSAA alias).
    // Both the actual resource and the guest description must permit the same copies.
    constexpr auto transfers = vk::ImageUsageFlagBits::eTransferSrc |
                               vk::ImageUsageFlagBits::eTransferDst;
    const u32 samples = u32(ci.samples);
    if (!samples || samples > 64 || (samples & (samples - 1)) ||
        samples != image.backing->num_samples ||
        (samples > 1 && (!instance.IsSampleRateShadingEnabled() || ci.mipLevels != 1))) return false;
    if (!image.GetImage() ||
        ci.imageType != vk::ImageType::e2D || ci.tiling != vk::ImageTiling::eOptimal ||
        ci.extent != vk::Extent3D{i.size.width, i.size.height, 1} || ci.arrayLayers != 1 ||
        ci.mipLevels != i.resources.levels || !ci.mipLevels || ci.mipLevels > 16 ||
        (ci.usage & transfers) != transfers) return false;
    const auto attachment = i.props.is_depth ? vk::ImageUsageFlagBits::eDepthStencilAttachment
                                             : vk::ImageUsageFlagBits::eColorAttachment;
    const auto usages = vk::ImageUsageFlagBits::eSampled | attachment;
    const auto features = i.props.is_depth
        ? vk::FormatFeatureFlagBits::eSampledImage | vk::FormatFeatureFlagBits::eDepthStencilAttachment
        : vk::FormatFeatureFlagBits::eSampledImage | vk::FormatFeatureFlagBits::eColorAttachment;
    if ((ci.usage & usages) != usages || (Features(ci.format) & features) != features) return false;
    if (i.resources.levels != 1) {
        // Mip chains (the bloom pyramid at half resolution): one blitted proxy per level.
        return div == 2 && i.resources.levels <= 16 && !i.props.is_depth &&
               Blittable(image.backing->image.image_ci.format);
    }
    if (samples > 1) {
        // Native and proxy keep the same samples. No MSAA blit or implicit resolve.
        return i.props.is_depth ? ShaderResampled(image) : true;
    }
    return Blittable(image.backing->image.image_ci.format) || ShaderResampled(image);
}
bool SceneTargets::EligibleScene(const VideoCore::Image& image) const {
    return image.info.size.width == 1920 && image.info.size.height == 1080 && Eligible(image);
}
SceneResolution::Size SceneTargets::ProxySize(const VideoCore::Image& image, u32 level) const {
    const u32 div = std::max(1u, SizeDivisor(image.info, size));
    return {std::max(1u, size.width / div >> level), std::max(1u, size.height / div >> level)};
}
bool SceneTargets::SetSize(SceneResolution::Size next) {
    if (next == size) return false;
    ResolveAll();
    scheduler.Finish();
    ++generation;
    recent = {};
    entries.clear(); // no command buffer can still reference these images/views
    tracked.clear();
    size = next;
    std::printf("Scene resolution: raster %ux%u, half-resolution targets %ux%u, UI 1920x1080 "
                "(live)\n", size.width, size.height, size.width / 2, size.height / 2);
    return true;
}
void SceneTargets::ResolveAll() {
    std::vector<u64> stale;
    for (auto& [key, entry] : entries) {
        auto* image = lookup(entry->source, entry->uid);
        if (!image || !Matches(*entry, *image) || !Eligible(*image)) {
            stale.push_back(entry->uid);
        } else if (entry->state.dirty) {
            Copy(*entry, *image, true);
        }
    }
    for (const auto uid : stale) Invalidate(uid);
}
void SceneTargets::NativeAccess(VideoCore::Image& image, vk::AccessFlags2 access) {
    if (copying || !image.scene_proxy) return; // most images never had a proxy
    InvalidateStale(image);
    if (!tracked.contains(image.image_uid)) {
        image.scene_proxy = false;
        return;
    }
    constexpr auto writes = vk::AccessFlagBits2::eShaderWrite | vk::AccessFlagBits2::eTransferWrite |
        vk::AccessFlagBits2::eColorAttachmentWrite | vk::AccessFlagBits2::eDepthStencilAttachmentWrite |
        vk::AccessFlagBits2::eMemoryWrite | vk::AccessFlagBits2::eShaderStorageWrite;
    const u32 levels = std::min(16u, image.info.resources.levels);
    for (u32 level = 0; level < levels; ++level) {
        const auto it = entries.find(Key(image.image_uid, level));
        if (it == entries.end()) continue;
        auto& entry = *it->second;
        if (entry.state.dirty) Copy(entry, image, true);
        if (access & writes) entry.state.NativeWrite();
    }
}
void SceneTargets::Transition(Entry& e, vk::ImageAspectFlags aspect, vk::ImageLayout layout,
                               vk::PipelineStageFlags2 stages, vk::AccessFlags2 access) {
    scheduler.EndRendering();
    const vk::ImageMemoryBarrier2 barrier{
        .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
        .srcAccessMask = vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite,
        .dstStageMask = stages, .dstAccessMask = access,
        .oldLayout = e.layout, .newLayout = layout,
        .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
        .image = e.image, .subresourceRange = {aspect, 0, 1, 0, 1},
    };
    scheduler.Record([barrier](vk::CommandBuffer cmd) {
        cmd.pipelineBarrier2({.imageMemoryBarrierCount = 1, .pImageMemoryBarriers = &barrier});
    });
    e.layout = layout;
}
void SceneTargets::Copy(Entry& e, VideoCore::Image& original, bool to_native) {
    // Never resolve old proxy content into a replacement backing, or run a single-sample
    // blit/resampler on a resource that changed capabilities since its last attachment.
    if (!Matches(e, original) || !Eligible(original)) {
        e.state.NativeWrite();
        return;
    }
    copying = true;
    scheduler.EndRendering();
    const Runtime::TransferMark mark{runtime, to_native ? "scene proxy resolve" : "scene proxy fill",
                                     original};
    if (debug) {
        std::printf("Scene %s: %s %ux%u level %u\n", to_native ? "resolve" : "fill",
                    vk::to_string(original.info.pixel_format).c_str(), original.info.size.width,
                    original.info.size.height, e.level);
    }
    const vk::Image src = to_native ? vk::Image(e.image) : original.GetImage();
    const vk::Image dst = to_native ? original.GetImage() : vk::Image(e.image);
    const bool depth = original.info.props.is_depth;
    if (ShaderResampled(original) || original.backing->image.image_ci.samples != vk::SampleCountFlagBits::e1) {
        constexpr auto read_layout = vk::ImageLayout::eShaderReadOnlyOptimal;
        const auto write_layout = depth ? vk::ImageLayout::eDepthStencilAttachmentOptimal
                                        : vk::ImageLayout::eColorAttachmentOptimal;
        constexpr auto read_stage = vk::PipelineStageFlagBits2::eFragmentShader;
        const auto write_stage = depth
            ? vk::PipelineStageFlagBits2::eEarlyFragmentTests | vk::PipelineStageFlagBits2::eLateFragmentTests
            : vk::PipelineStageFlags2(vk::PipelineStageFlagBits2::eColorAttachmentOutput);
        constexpr auto read_access = vk::AccessFlagBits2::eShaderSampledRead;
        const auto write_access = depth
            ? vk::AccessFlagBits2::eDepthStencilAttachmentRead | vk::AccessFlagBits2::eDepthStencilAttachmentWrite
            : vk::AccessFlagBits2::eColorAttachmentRead | vk::AccessFlagBits2::eColorAttachmentWrite;
        runtime.Transit(&original, to_native ? write_layout : read_layout,
                        to_native ? write_stage : read_stage,
                        to_native ? write_access : read_access);
        runtime.FlushBarriers();
        Transition(e, original.aspect_mask, to_native ? read_layout : write_layout,
                   to_native ? read_stage : write_stage, to_native ? read_access : write_access);
        const auto& proxy = e.image.image_ci.extent;
        Resample(src, dst, original,
                 to_native ? vk::Extent2D{original.info.size.width, original.info.size.height}
                           : vk::Extent2D{proxy.width, proxy.height});
        // Shader-resampled/MS proxies are single-level: Eligible.
        if (to_native) e.state.Resolved(); else e.state.CopiedToProxy();
        copying = false;
        return;
    }
    const VideoCore::SubresourceRange level_range{.base = {e.level, 0}, .extent = {1, 1}};
    runtime.Transit(&original, to_native ? vk::ImageLayout::eTransferDstOptimal
                                       : vk::ImageLayout::eTransferSrcOptimal,
                    vk::PipelineStageFlagBits2::eTransfer,
                    to_native ? vk::AccessFlagBits2::eTransferWrite : vk::AccessFlagBits2::eTransferRead,
                    level_range);
    runtime.FlushBarriers();
    Transition(e, original.aspect_mask,
               to_native ? vk::ImageLayout::eTransferSrcOptimal : vk::ImageLayout::eTransferDstOptimal,
               vk::PipelineStageFlagBits2::eTransfer,
               to_native ? vk::AccessFlagBits2::eTransferRead : vk::AccessFlagBits2::eTransferWrite);
    const vk::Offset3D native{s32(std::max(1u, original.info.size.width >> e.level)),
                              s32(std::max(1u, original.info.size.height >> e.level)), 1};
    const vk::Offset3D reduced{s32(e.image.image_ci.extent.width),
                               s32(e.image.image_ci.extent.height), 1};
    for (auto aspect : {vk::ImageAspectFlagBits::eColor, vk::ImageAspectFlagBits::eDepth,
                        vk::ImageAspectFlagBits::eStencil}) {
        if (!(original.aspect_mask & aspect)) continue;
        const vk::ImageBlit region{
            .srcSubresource = {aspect, to_native ? 0u : e.level, 0, 1},
            .srcOffsets = std::array{vk::Offset3D{}, to_native ? reduced : native},
            .dstSubresource = {aspect, to_native ? e.level : 0u, 0, 1},
            .dstOffsets = std::array{vk::Offset3D{}, to_native ? native : reduced},
        };
        // Nearest preserves depth/stencil and avoids assuming linear blit support for
        // integer G-buffer formats. FSR reconstructs color at the HDR scene boundary.
        scheduler.Record([src,dst,region](vk::CommandBuffer cmd) {
            cmd.blitImage(src, vk::ImageLayout::eTransferSrcOptimal, dst,
                          vk::ImageLayout::eTransferDstOptimal, region, vk::Filter::eNearest);
        });
    }
    if (to_native) e.state.Resolved(); else e.state.CopiedToProxy();
    copying = false;
}
void SceneTargets::Resample(vk::Image src, vk::Image dst, const VideoCore::Image& original,
                            vk::Extent2D dst_size) {
    const auto samples = original.backing->image.image_ci.samples;
    ResampleImages(src, dst, original.backing->image.image_ci.format, original.info.props.is_depth,
                   bool(original.aspect_mask & vk::ImageAspectFlagBits::eStencil),
                   samples, samples, dst_size);
}
bool SceneTargets::ResampleDepthTo(const Target& source, const Target& destination,
                                   vk::Format format, bool stencil) {
    const bool source_ms = source.samples != vk::SampleCountFlagBits::e1;
    if (!source.image || !destination.image || source.image == destination.image ||
        !source.width || !source.height || !destination.width || !destination.height ||
        source.layout == vk::ImageLayout::eUndefined || destination.layout == vk::ImageLayout::eUndefined ||
        !(source.usage & vk::ImageUsageFlagBits::eSampled) ||
        !(destination.usage & vk::ImageUsageFlagBits::eDepthStencilAttachment) ||
        (source_ms && (source.samples != destination.samples || !instance.IsSampleRateShadingEnabled()))) {
        return false;
    }
    const auto required = vk::FormatFeatureFlagBits::eSampledImage |
                          vk::FormatFeatureFlagBits::eDepthStencilAttachment;
    if ((Features(format) & required) != required) return false;
    const bool has_stencil = format == vk::Format::eD32SfloatS8Uint ||
                            format == vk::Format::eD24UnormS8Uint || format == vk::Format::eD16UnormS8Uint;
    if (stencil && !has_stencil) {
        return false;
    }
    const auto aspect = vk::ImageAspectFlagBits::eDepth |
        (has_stencil ? vk::ImageAspectFlags(vk::ImageAspectFlagBits::eStencil) : vk::ImageAspectFlags{});
    scheduler.EndRendering();
    // These external images have a caller-owned layout tracker. Restore both supplied
    // layouts after the draw, so the caller's state and its recorded descriptors stay valid.
    const auto transition = [&](vk::Image image, vk::ImageLayout from, vk::ImageLayout to) {
        const vk::ImageMemoryBarrier2 barrier{
            .srcStageMask = vk::PipelineStageFlagBits2::eAllCommands,
            .srcAccessMask = vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite,
            .dstStageMask = vk::PipelineStageFlagBits2::eAllCommands,
            .dstAccessMask = vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite,
            .oldLayout = from, .newLayout = to,
            .srcQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED, .dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED,
            .image = image, .subresourceRange = {aspect, 0, 1, 0, 1},
        };
        scheduler.Record([barrier](vk::CommandBuffer cmd) {
            cmd.pipelineBarrier2({.imageMemoryBarrierCount = 1, .pImageMemoryBarriers = &barrier});
        });
    };
    constexpr auto read = vk::ImageLayout::eShaderReadOnlyOptimal;
    constexpr auto write = vk::ImageLayout::eDepthStencilAttachmentOptimal;
    transition(source.image, source.layout, read);
    transition(destination.image, destination.layout, write);
    ResampleImages(source.image, destination.image, format, true, stencil,
                   source.samples, destination.samples, {destination.width, destination.height});
    transition(source.image, read, source.layout);
    transition(destination.image, write, destination.layout);
    return true;
}
struct SceneResampleConstants {
    u32 bit = 0, width, height, reserved = 0;
};
void SceneTargets::ResampleImages(vk::Image src, vk::Image dst, vk::Format format,
                                  bool depth, bool stencil,
                                  vk::SampleCountFlagBits source_samples,
                                  vk::SampleCountFlagBits dest_samples, vk::Extent2D dst_size) {
    const auto device = instance.GetDevice();
    const bool source_ms = source_samples != vk::SampleCountFlagBits::e1;
    const bool stencil_bits = stencil && !(source_ms ? depth_stencil_ms_frag : depth_stencil_frag);
    const auto make_view = [&](vk::Image image, vk::ImageAspectFlags aspect,
                               vk::ImageUsageFlags usage) {
        const vk::ImageViewUsageCreateInfo usage_ci{.usage = usage};
        return Check(device.createImageView({
            .pNext = &usage_ci, .image = image, .viewType = vk::ImageViewType::e2D,
            .format = format, .subresourceRange = {aspect, 0, 1, 0, 1},
        }));
    };
    const auto depth_view = make_view(src, depth ? vk::ImageAspectFlagBits::eDepth : vk::ImageAspectFlagBits::eColor,
                                      vk::ImageUsageFlagBits::eSampled);
    const auto stencil_view = stencil ? make_view(src, vk::ImageAspectFlagBits::eStencil,
                                                  vk::ImageUsageFlagBits::eSampled)
                                      : vk::ImageView{};
    const auto target_aspect = depth
        ? vk::ImageAspectFlagBits::eDepth | (stencil ? vk::ImageAspectFlags(vk::ImageAspectFlagBits::eStencil)
                                                  : vk::ImageAspectFlags{})
        : vk::ImageAspectFlags(vk::ImageAspectFlagBits::eColor);
    const auto target_view = make_view(dst, target_aspect, depth
        ? vk::ImageUsageFlagBits::eDepthStencilAttachment : vk::ImageUsageFlagBits::eColorAttachment);
    scheduler.DeferOperation([device, depth_view, stencil_view, target_view] {
        device.destroyImageView(depth_view);
        if (stencil_view) device.destroyImageView(stencil_view);
        device.destroyImageView(target_view);
    });
    const auto pipeline = ResamplePipeline({format, depth, stencil, source_ms, dest_samples});
    const auto layout = *resample_layout;
    scheduler.Record([=](vk::CommandBuffer cmd) {
        const vk::RenderingAttachmentInfo attachment{
            .imageView = target_view,
            .imageLayout = depth ? vk::ImageLayout::eDepthStencilAttachmentOptimal
                                 : vk::ImageLayout::eColorAttachmentOptimal,
            .loadOp = vk::AttachmentLoadOp::eDontCare,
            .storeOp = vk::AttachmentStoreOp::eStore,
        };
        auto stencil_attachment = attachment;
        if (stencil_bits) {
            stencil_attachment.loadOp = vk::AttachmentLoadOp::eClear;
            stencil_attachment.clearValue.depthStencil = vk::ClearDepthStencilValue{0.f, 0};
        }
        cmd.beginRendering({
            .renderArea = {{0, 0}, dst_size}, .layerCount = 1,
            .colorAttachmentCount = depth ? 0u : 1u,
            .pColorAttachments = depth ? nullptr : &attachment,
            .pDepthAttachment = depth ? &attachment : nullptr,
            .pStencilAttachment = stencil ? &stencil_attachment : nullptr,
        });
        const std::array infos{
            vk::DescriptorImageInfo{{}, depth_view, vk::ImageLayout::eShaderReadOnlyOptimal},
            vk::DescriptorImageInfo{{}, stencil_view, vk::ImageLayout::eShaderReadOnlyOptimal},
        };
        const std::array writes{
            vk::WriteDescriptorSet{.dstBinding = 0, .descriptorCount = 1,
                                   .descriptorType = vk::DescriptorType::eSampledImage,
                                   .pImageInfo = &infos[0]},
            vk::WriteDescriptorSet{.dstBinding = 1, .descriptorCount = 1,
                                   .descriptorType = vk::DescriptorType::eSampledImage,
                                   .pImageInfo = &infos[1]},
        };
        cmd.pushDescriptorSetKHR(vk::PipelineBindPoint::eGraphics, layout, 0,
                                 vk::ArrayProxy<const vk::WriteDescriptorSet>(
                                     stencil ? 2u : 1u, writes.data()));
        cmd.bindPipeline(vk::PipelineBindPoint::eGraphics, pipeline);
        cmd.setViewportWithCount(vk::Viewport{0.f, 0.f, float(dst_size.width),
                                              float(dst_size.height), 0.f, 1.f});
        cmd.setScissorWithCount(vk::Rect2D{{0, 0}, dst_size});
        SceneResampleConstants constants{.width = dst_size.width, .height = dst_size.height};
        if (stencil_bits) {
            // Copy depth first, then reconstruct all eight stencil bits without needing
            // VK_EXT_shader_stencil_export (e.g. Pascal). Discard keeps unset bits clear.
            for (u32 bit : {0u, 1u, 2u, 4u, 8u, 16u, 32u, 64u, 128u}) {
                constants.bit = bit;
                cmd.pushConstants(layout, vk::ShaderStageFlagBits::eFragment, 0, sizeof(constants), &constants);
                cmd.setStencilWriteMask(vk::StencilFaceFlagBits::eFrontAndBack, bit);
                cmd.setStencilReference(vk::StencilFaceFlagBits::eFrontAndBack, bit);
                cmd.draw(3, 1, 0, 0);
            }
        } else {
            cmd.pushConstants(layout, vk::ShaderStageFlagBits::eFragment, 0, sizeof(constants), &constants);
            cmd.draw(3, 1, 0, 0);
        }
        cmd.endRendering();
    });
    // The guest pipelines' dynamic state must be emitted again after this pipeline.
    scheduler.GetDynamicState().Invalidate();
}
void SceneTargets::CreateResampleResources() {
    const auto device = instance.GetDevice();
    fs_tri_vert = vk::UniqueShaderModule(CompileSPV(FS_TRI_VERT, device), device);
    depth_frag = vk::UniqueShaderModule(CompileSPV(DEPTH_RESAMPLE_FRAG, device), device);
    if (instance.IsSampleRateShadingEnabled()) {
        depth_ms_frag = vk::UniqueShaderModule(CompileSPV(DEPTH_RESAMPLE_MS_FRAG, device), device);
        color_ms_frag = vk::UniqueShaderModule(CompileSPV(SCENE_COLOR_RESAMPLE_MS_FRAG, device), device);
        color_ms_uint_frag = vk::UniqueShaderModule(CompileSPV(SCENE_COLOR_RESAMPLE_MS_UINT_FRAG, device), device);
        color_ms_sint_frag = vk::UniqueShaderModule(CompileSPV(SCENE_COLOR_RESAMPLE_MS_SINT_FRAG, device), device);
    }
    if (instance.IsShaderStencilExportSupported() && !force_stencil_bits) {
        depth_stencil_frag =
            vk::UniqueShaderModule(CompileSPV(DEPTH_STENCIL_RESAMPLE_FRAG, device), device);
        if (instance.IsSampleRateShadingEnabled()) {
            depth_stencil_ms_frag = vk::UniqueShaderModule(CompileSPV(DEPTH_STENCIL_RESAMPLE_MS_FRAG, device), device);
        }
    }
    if (!depth_stencil_frag) {
        stencil_bits_frag =
            vk::UniqueShaderModule(CompileSPV(DEPTH_STENCIL_BITS_FRAG, device), device);
        if (instance.IsSampleRateShadingEnabled()) {
            stencil_bits_ms_frag = vk::UniqueShaderModule(CompileSPV(DEPTH_STENCIL_BITS_MS_FRAG, device), device);
        }
    }
    const std::array bindings{
        vk::DescriptorSetLayoutBinding{0, vk::DescriptorType::eSampledImage, 1,
                                       vk::ShaderStageFlagBits::eFragment},
        vk::DescriptorSetLayoutBinding{1, vk::DescriptorType::eSampledImage, 1,
                                       vk::ShaderStageFlagBits::eFragment},
    };
    resample_set_layout = Check(device.createDescriptorSetLayoutUnique({
        .flags = vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,
        .bindingCount = u32(bindings.size()), .pBindings = bindings.data(),
    }));
    const auto set_layout = *resample_set_layout;
    const vk::PushConstantRange push{vk::ShaderStageFlagBits::eFragment, 0, sizeof(SceneResampleConstants)};
    resample_layout = Check(device.createPipelineLayoutUnique({
        .setLayoutCount = 1, .pSetLayouts = &set_layout,
        .pushConstantRangeCount = 1, .pPushConstantRanges = &push,
    }));
}
// Integer color attachments need matching integer fragment outputs, including packed G-buffers.
static int ColorScalar(vk::Format format) {
    switch (format) {
    case vk::Format::eR8Uint: case vk::Format::eR8G8Uint: case vk::Format::eR8G8B8Uint:
    case vk::Format::eB8G8R8Uint: case vk::Format::eR8G8B8A8Uint: case vk::Format::eB8G8R8A8Uint:
    case vk::Format::eA8B8G8R8UintPack32: case vk::Format::eA2R10G10B10UintPack32:
    case vk::Format::eA2B10G10R10UintPack32: case vk::Format::eR16Uint: case vk::Format::eR16G16Uint:
    case vk::Format::eR16G16B16Uint: case vk::Format::eR16G16B16A16Uint: case vk::Format::eR32Uint:
    case vk::Format::eR32G32Uint: case vk::Format::eR32G32B32Uint: case vk::Format::eR32G32B32A32Uint:
        return 1;
    case vk::Format::eR8Sint: case vk::Format::eR8G8Sint: case vk::Format::eR8G8B8Sint:
    case vk::Format::eB8G8R8Sint: case vk::Format::eR8G8B8A8Sint: case vk::Format::eB8G8R8A8Sint:
    case vk::Format::eA8B8G8R8SintPack32: case vk::Format::eA2R10G10B10SintPack32:
    case vk::Format::eA2B10G10R10SintPack32: case vk::Format::eR16Sint: case vk::Format::eR16G16Sint:
    case vk::Format::eR16G16B16Sint: case vk::Format::eR16G16B16A16Sint: case vk::Format::eR32Sint:
    case vk::Format::eR32G32Sint: case vk::Format::eR32G32B32Sint: case vk::Format::eR32G32B32A32Sint:
        return -1;
    default: return 0;
    }
}
vk::Pipeline SceneTargets::ResamplePipeline(const ResampleKey& key) {
    const auto format = key.format;
    const bool stencil = key.stencil;
    const bool stencil_bits = stencil && !(key.source_ms ? depth_stencil_ms_frag : depth_stencil_frag);
    for (const auto& [k, pipeline] : resample_pipelines) if (k == key) return *pipeline;
    const vk::PipelineInputAssemblyStateCreateInfo input_assembly{
        .topology = vk::PrimitiveTopology::eTriangleList,
    };
    const vk::PipelineMultisampleStateCreateInfo multisampling{
        .rasterizationSamples = key.samples,
        .sampleShadingEnable = key.source_ms,
        .minSampleShading = key.source_ms ? 1.f : 0.f,
    };
    // Reference, compare and write masks are static; the exported value replaces the reference.
    const vk::StencilOpState stencil_op{
        .failOp = vk::StencilOp::eReplace, .passOp = vk::StencilOp::eReplace,
        .depthFailOp = vk::StencilOp::eReplace, .compareOp = vk::CompareOp::eAlways,
        .compareMask = 0xff, .writeMask = 0xff, .reference = 0,
    };
    const vk::PipelineDepthStencilStateCreateInfo depth_state{
        .depthTestEnable = key.depth, .depthWriteEnable = key.depth,
        .depthCompareOp = vk::CompareOp::eAlways,
        .stencilTestEnable = stencil, .front = stencil_op, .back = stencil_op,
    };
    const std::array dynamic_states{vk::DynamicState::eViewportWithCount,
                                    vk::DynamicState::eScissorWithCount,
                                    vk::DynamicState::eStencilWriteMask,
                                    vk::DynamicState::eStencilReference};
    const vk::PipelineDynamicStateCreateInfo dynamic_info{
        .dynamicStateCount = stencil_bits ? 4u : 2u, .pDynamicStates = dynamic_states.data(),
    };
    const auto scalar = ColorScalar(format);
    const vk::ShaderModule fragment = !key.depth
        ? scalar > 0 ? *color_ms_uint_frag : scalar < 0 ? *color_ms_sint_frag : *color_ms_frag
        : key.source_ms
            ? stencil ? stencil_bits ? *stencil_bits_ms_frag : *depth_stencil_ms_frag : *depth_ms_frag
            : stencil ? stencil_bits ? *stencil_bits_frag : *depth_stencil_frag : *depth_frag;
    const std::array stages{
        vk::PipelineShaderStageCreateInfo{.stage = vk::ShaderStageFlagBits::eVertex,
                                          .module = *fs_tri_vert, .pName = "main"},
        vk::PipelineShaderStageCreateInfo{.stage = vk::ShaderStageFlagBits::eFragment,
                                          .module = fragment,
                                          .pName = "main"},
    };
    const vk::PipelineRenderingCreateInfo rendering{
        .colorAttachmentCount = key.depth ? 0u : 1u,
        .pColorAttachmentFormats = key.depth ? nullptr : &format,
        .depthAttachmentFormat = key.depth ? format : vk::Format::eUndefined,
        .stencilAttachmentFormat = stencil ? format : vk::Format::eUndefined,
    };
    const vk::PipelineColorBlendAttachmentState color_attachment{
        .colorWriteMask = vk::ColorComponentFlagBits::eR | vk::ColorComponentFlagBits::eG |
                          vk::ColorComponentFlagBits::eB | vk::ColorComponentFlagBits::eA,
    };
    const vk::PipelineColorBlendStateCreateInfo color_blending{
        .attachmentCount = key.depth ? 0u : 1u,
        .pAttachments = key.depth ? nullptr : &color_attachment,
    };
    const vk::PipelineViewportStateCreateInfo viewport_info{};
    const vk::PipelineVertexInputStateCreateInfo vertex_input{};
    const vk::PipelineRasterizationStateCreateInfo raster{.lineWidth = 1.f};
    auto pipeline = Check(instance.GetDevice().createGraphicsPipelineUnique(VK_NULL_HANDLE, {
        .pNext = &rendering, .stageCount = u32(stages.size()), .pStages = stages.data(),
        .pVertexInputState = &vertex_input, .pInputAssemblyState = &input_assembly,
        .pViewportState = &viewport_info, .pRasterizationState = &raster,
        .pMultisampleState = &multisampling, .pDepthStencilState = &depth_state,
        .pColorBlendState = &color_blending, .pDynamicState = &dynamic_info,
        .layout = *resample_layout,
    }));
    const auto result = *pipeline;
    resample_pipelines.emplace_back(key, std::move(pipeline));
    return result;
}
bool SceneTargets::Matches(const Entry& e, const VideoCore::Image& original) const {
    if (!original.backing || e.backing != original.backing ||
        e.source_image != original.GetImage() || e.aspect != original.aspect_mask) return false;
    const auto& ci = original.backing->image.image_ci;
    return e.source_ci.format == ci.format && e.source_ci.extent == ci.extent &&
           e.source_ci.samples == ci.samples && e.source_ci.usage == ci.usage &&
           e.source_ci.flags == ci.flags && e.source_ci.imageType == ci.imageType &&
           e.source_ci.tiling == ci.tiling && e.source_ci.mipLevels == ci.mipLevels &&
           e.source_ci.arrayLayers == ci.arrayLayers;
}
void SceneTargets::Invalidate(u64 uid) {
    bool removed = false;
    for (u32 level = 0; level < 16; ++level) {
        const auto it = entries.find(Key(uid, level));
        if (it == entries.end()) continue;
        if (!removed) {
            recent = {};
            ++generation; // invalidate cached handles before releasing their ownership
            removed = true;
        }
        scheduler.EndRendering();
        // Recorded/in-flight commands may still contain these views. Retire the entire
        // entry at the scheduler tick instead of destroying it on a backing switch.
        scheduler.DeferOperation([entry = std::move(it->second)] {});
        entries.erase(it);
    }
    tracked.erase(uid);
}
void SceneTargets::InvalidateStale(const VideoCore::Image& original) {
    if (!tracked.contains(original.image_uid)) return;
    // Every level of a UID is created against the same backing; checking one suffices.
    for (u32 level = 0; level < 16; ++level) {
        const auto it = entries.find(Key(original.image_uid, level));
        if (it == entries.end()) continue;
        if (!Matches(*it->second, original) || !Eligible(original)) Invalidate(original.image_uid);
        return;
    }
}
SceneTargets::Entry* SceneTargets::Get(VideoCore::ImageId id, u32 level) {
    auto* source = lookup(id, 0);
    if (!source) return nullptr;
    auto& original = *source;
    InvalidateStale(original);
    if (!Eligible(original) || level >= original.info.resources.levels) return nullptr;
    const u64 key = Key(original.image_uid, level);
    // A draw has up to six targets, mostly the same as the previous draw's.
    for (const auto& [recent_key, recent_entry] : recent) {
        if (recent_entry && recent_key == key) {
            if (!recent_entry->state.valid) Copy(*recent_entry, original, false);
            return recent_entry;
        }
    }
    auto& entry = entries[key];
    original.scene_proxy = true;
    if (!entry) {
        entry = std::make_unique<Entry>();
        entry->source = id;
        entry->uid = original.image_uid;
        entry->level = level;
        entry->backing = original.backing;
        entry->source_image = original.GetImage();
        entry->source_ci = original.backing->image.image_ci;
        entry->source_ci.pNext = nullptr;
        entry->source_ci.pQueueFamilyIndices = nullptr;
        entry->aspect = original.aspect_mask;
        entry->image = VideoCore::UniqueImage(instance.GetDevice(), instance.GetAllocator());
        auto ci = original.backing->image.image_ci;
        ci.pNext = nullptr;
        const auto proxy = ProxySize(original, level);
        ci.extent = vk::Extent3D{proxy.width, proxy.height, 1};
        ci.mipLevels = 1;
        ci.samples = original.backing->image.image_ci.samples;
        entry->image.Create(ci);
        tracked.insert(original.image_uid);
    }
    recent[recent_next++ % recent.size()] = {key, entry.get()};
    if (!entry->state.valid) Copy(*entry, original, false);
    return entry.get();
}
static vk::Format StorageFormat(vk::Format format) {
    switch (format) {
    case vk::Format::eR8Srgb: return vk::Format::eR8Unorm;
    case vk::Format::eR8G8Srgb: return vk::Format::eR8G8Unorm;
    case vk::Format::eR8G8B8A8Srgb: return vk::Format::eR8G8B8A8Unorm;
    case vk::Format::eB8G8R8A8Srgb: return vk::Format::eB8G8R8A8Unorm;
    case vk::Format::eA8B8G8R8SrgbPack32: return vk::Format::eA8B8G8R8UnormPack32;
    default: return format;
    }
}
static vk::Format ViewFormat(const VideoCore::Image& image,
                            const VideoCore::ImageViewInfo& info, bool storage) {
    const auto backing_format = image.backing->image.image_ci.format;
    const auto format = image.info.props.is_depth || info.format == image.info.pixel_format
        ? backing_format : info.format;
    return storage ? StorageFormat(format) : format;
}
static vk::ImageAspectFlags SampleAspect(const VideoCore::Image& image,
                                         const VideoCore::ImageViewInfo& info) {
    if (!image.info.props.is_depth) return vk::ImageAspectFlagBits::eColor;
    return LiverpoolToVK::IsFormatStencilCompatible(info.format)
        ? vk::ImageAspectFlagBits::eStencil : vk::ImageAspectFlagBits::eDepth;
}
bool SceneTargets::ViewEligible(const VideoCore::Image& original,
                                const VideoCore::ImageViewInfo& info, ViewUse use) const {
    if (!Eligible(original) || info.range.extent.levels != 1 || info.range.extent.layers != 1 ||
        info.range.base.layer != 0 || info.range.base.level >= original.info.resources.levels ||
        (info.type != AmdGpu::ImageType::Color2D && info.type != AmdGpu::ImageType::Color2DArray &&
         info.type != AmdGpu::ImageType::Color2DMsaa && info.type != AmdGpu::ImageType::Color2DMsaaArray)) {
        return false;
    }
    if (use == ViewUse::Storage && (original.info.props.is_depth ||
        original.backing->image.image_ci.samples != vk::SampleCountFlagBits::e1)) return false;
    const auto& ci = original.backing->image.image_ci;
    const auto format = ViewFormat(original, info, use == ViewUse::Storage);
    // The common sRGB/UNORM pair is safe on mutable images. Other reinterpretations
    // use the native cache rather than inventing a proxy view with unknown compatibility.
    if (format != ci.format &&
        (!(ci.flags & vk::ImageCreateFlagBits::eMutableFormat) ||
         StorageFormat(format) != StorageFormat(ci.format))) return false;
    const auto usage = use == ViewUse::Attachment
        ? original.info.props.is_depth ? vk::ImageUsageFlagBits::eDepthStencilAttachment
                                       : vk::ImageUsageFlagBits::eColorAttachment
        : use == ViewUse::Storage ? vk::ImageUsageFlagBits::eStorage : vk::ImageUsageFlagBits::eSampled;
    const auto feature = use == ViewUse::Attachment
        ? original.info.props.is_depth ? vk::FormatFeatureFlagBits::eDepthStencilAttachment
                                       : vk::FormatFeatureFlagBits::eColorAttachment
        : use == ViewUse::Storage ? vk::FormatFeatureFlagBits::eStorageImage
                                 : vk::FormatFeatureFlagBits::eSampledImage;
    const auto aspect = use == ViewUse::Attachment ? original.aspect_mask : SampleAspect(original, info);
    return bool(ci.usage & usage) && bool(Features(format) & feature) &&
           (original.aspect_mask & aspect) == aspect;
}
vk::ImageView SceneTargets::View(Entry& e, const VideoCore::Image& original,
                                 const VideoCore::ImageViewInfo& info, ViewUse use) {
    for (const auto& cached : e.views) {
        if (cached.info == info && cached.use == use) return *cached.view;
    }
    const auto aspect = use == ViewUse::Attachment ? original.aspect_mask : SampleAspect(original, info);
    const auto format = ViewFormat(original, info, use == ViewUse::Storage);
    // Attachment, sampled and storage views have distinct usages/cache keys. In particular,
    // a color attachment is not a storage image, and a sampled D/S view selects one aspect.
    const vk::ImageViewUsageCreateInfo usage{
        .usage = use == ViewUse::Attachment
            ? original.info.props.is_depth ? vk::ImageUsageFlagBits::eDepthStencilAttachment
                                           : vk::ImageUsageFlagBits::eColorAttachment
            : use == ViewUse::Storage ? vk::ImageUsageFlagBits::eStorage : vk::ImageUsageFlagBits::eSampled,
    };
    auto view = Check(instance.GetDevice().createImageViewUnique({
        .pNext = &usage, .image = e.image,
        .viewType = info.type == AmdGpu::ImageType::Color2DArray ||
                    info.type == AmdGpu::ImageType::Color2DMsaaArray
            ? vk::ImageViewType::e2DArray : vk::ImageViewType::e2D,
        .format = format,
        .components = use == ViewUse::Sampled ? info.mapping : vk::ComponentMapping{},
        .subresourceRange = {aspect,0,1,0,1},
    }));
    const auto result = *view;
    e.views.push_back({info, use, std::move(view)});
    return result;
}
SceneTargets::Target SceneTargets::Native(VideoCore::Image& original,
                                          const VideoCore::ImageViewInfo& info, ViewUse use,
                                          vk::ImageLayout layout, vk::PipelineStageFlags2 stages,
                                          vk::AccessFlags2 access) {
    if (!original.backing || !original.GetImage()) return {};
    const auto& ci = original.backing->image.image_ci;
    const auto& range = info.range;
    if (!range.extent.levels || !range.extent.layers || range.base.level >= ci.mipLevels ||
        range.extent.levels > ci.mipLevels - range.base.level || range.base.layer >= ci.arrayLayers ||
        range.extent.layers > ci.arrayLayers - range.base.layer ||
        range.base.level >= original.info.resources.levels ||
        range.extent.levels > original.info.resources.levels - range.base.level ||
        range.base.layer >= original.info.resources.layers ||
        range.extent.layers > original.info.resources.layers - range.base.layer) return {};
    const auto usage = use == ViewUse::Attachment
        ? original.info.props.is_depth ? vk::ImageUsageFlagBits::eDepthStencilAttachment
                                       : vk::ImageUsageFlagBits::eColorAttachment
        : use == ViewUse::Storage ? vk::ImageUsageFlagBits::eStorage : vk::ImageUsageFlagBits::eSampled;
    if (!(ci.usage & usage) || (use == ViewUse::Storage &&
        (original.info.props.is_depth || ci.samples != vk::SampleCountFlagBits::e1))) return {};
    if (use == ViewUse::Storage &&
        !(Features(ViewFormat(original, info, true)) & vk::FormatFeatureFlagBits::eStorageImage)) {
        return {};
    }
    auto native_info = info;
    native_info.is_storage = use == ViewUse::Storage ||
                             (use == ViewUse::Attachment && original.info.props.is_depth);
    if (use != ViewUse::Sampled) native_info.mapping = vk::ComponentMapping{};
    if (use == ViewUse::Sampled && original.info.props.is_depth) {
        // FindView's compatible format selectors produce a single depth/stencil aspect,
        // while retaining the original supported host format for the actual Vulkan view.
        const auto aspect = SampleAspect(original, info);
        if (!(original.aspect_mask & aspect)) return {};
        native_info.format = aspect == vk::ImageAspectFlagBits::eStencil
            ? vk::Format::eR8Uint : vk::Format::eR32Sfloat;
    }
    runtime.Transit(&original, layout, stages, access, range);
    runtime.FlushBarriers();
    // false is essential: the fallback must not swap a resolved backing back to guest MSAA.
    const auto view = *original.FindView(native_info, false).image_view;
    return {original.GetImage(), view, layout, ci.usage,
            std::max(1u, ci.extent.width >> range.base.level),
            std::max(1u, ci.extent.height >> range.base.level), ci.samples};
}
SceneTargets::Target SceneTargets::Attachment(VideoCore::ImageId id,
                                               const VideoCore::ImageViewInfo& info) {
    auto* source = lookup(id, 0);
    if (!source) return {};
    auto& original = *source;
    InvalidateStale(original);
    const bool depth = original.info.props.is_depth;
    const auto layout = depth ? vk::ImageLayout::eDepthStencilAttachmentOptimal
                              : vk::ImageLayout::eColorAttachmentOptimal;
    const auto stages = depth
        ? vk::PipelineStageFlagBits2::eEarlyFragmentTests | vk::PipelineStageFlagBits2::eLateFragmentTests
        : vk::PipelineStageFlags2(vk::PipelineStageFlagBits2::eColorAttachmentOutput);
    const auto access = depth
        ? vk::AccessFlagBits2::eDepthStencilAttachmentRead | vk::AccessFlagBits2::eDepthStencilAttachmentWrite
        : vk::AccessFlagBits2::eColorAttachmentRead | vk::AccessFlagBits2::eColorAttachmentWrite;
    if (!ViewEligible(original, info, ViewUse::Attachment)) {
        return Native(original, info, ViewUse::Attachment, layout, stages, access);
    }
    auto* entry = Get(id, info.range.base.level);
    if (!entry) return Native(original, info, ViewUse::Attachment, layout, stages, access);
    auto& e = *entry;
    // Consecutive draws can stay in the same render pass.
    if (e.layout != layout) {
        Transition(e, original.aspect_mask, layout, stages, access);
    }
    e.state.ProxyWrite();
    return {e.image, View(e, original, info, ViewUse::Attachment), e.layout, e.image.image_ci.usage,
            e.image.image_ci.extent.width, e.image.image_ci.extent.height, e.image.image_ci.samples};
}
bool SceneTargets::ProxyCurrent(const VideoCore::Image& image, u32 level, u32 levels) const {
    if (copying || !image.scene_proxy || image.info.props.is_depth || levels != 1 ||
        level >= 16 || level >= image.info.resources.levels || !Eligible(image)) {
        return false;
    }
    const auto it = entries.find(Key(image.image_uid, level));
    return it != entries.end() && Matches(*it->second, image) && it->second->state.valid;
}
vk::ImageLayout SceneTargets::PrepareSample(const VideoCore::Image& image, u32 level) {
    InvalidateStale(image);
    if (!ProxyCurrent(image, level)) return vk::ImageLayout::eUndefined;
    auto& e = *entries.find(Key(image.image_uid, level))->second;
    constexpr auto layout = vk::ImageLayout::eShaderReadOnlyOptimal;
    if (e.layout != layout) {
        Transition(e, image.aspect_mask, layout,
                   vk::PipelineStageFlagBits2::eVertexShader |
                       vk::PipelineStageFlagBits2::eFragmentShader |
                       vk::PipelineStageFlagBits2::eComputeShader,
                   vk::AccessFlagBits2::eShaderSampledRead);
    }
    return layout;
}
std::optional<SceneTargets::Target> SceneTargets::SampleProxy(
    const VideoCore::Image& image, const VideoCore::ImageViewInfo& info) {
    InvalidateStale(image);
    const u32 level = info.range.base.level;
    if (info.is_storage || !ViewEligible(image, info, ViewUse::Sampled) ||
        !ProxyCurrent(image, level, info.range.extent.levels)) {
        return std::nullopt;
    }
    const bool view_ms = info.type == AmdGpu::ImageType::Color2DMsaa ||
                         info.type == AmdGpu::ImageType::Color2DMsaaArray;
    if (view_ms != (image.backing->image.image_ci.samples != vk::SampleCountFlagBits::e1)) {
        return std::nullopt; // do not give a single-sample guest shader an MSAA proxy descriptor
    }
    auto& e = *entries.find(Key(image.image_uid, level))->second;
    const auto layout = PrepareSample(image, level);
    return Target{e.image, View(e, image, info, ViewUse::Sampled), layout, e.image.image_ci.usage,
                  e.image.image_ci.extent.width, e.image.image_ci.extent.height, e.image.image_ci.samples};
}
SceneTargets::Target SceneTargets::Read(VideoCore::ImageId id,
                                       const VideoCore::ImageViewInfo& info,
                                       vk::PipelineStageFlags2 stages, vk::AccessFlags2 access) {
    auto* source = lookup(id, 0);
    if (!source) return {};
    auto& original = *source;
    InvalidateStale(original);
    const auto use = info.is_storage ? ViewUse::Storage : ViewUse::Sampled;
    if (!ViewEligible(original, info, use)) {
        return Native(original, info, use, vk::ImageLayout::eGeneral, stages, access);
    }
    auto* entry = Get(id, info.range.base.level);
    if (!entry) return Native(original, info, use, vk::ImageLayout::eGeneral, stages, access);
    auto& e = *entry;
    Transition(e, original.aspect_mask, vk::ImageLayout::eGeneral, stages, access);
    constexpr auto writes = vk::AccessFlagBits2::eShaderWrite | vk::AccessFlagBits2::eShaderStorageWrite |
        vk::AccessFlagBits2::eTransferWrite | vk::AccessFlagBits2::eMemoryWrite;
    if (access & writes) e.state.ProxyWrite();
    return {e.image, View(e, original, info, use), e.layout, e.image.image_ci.usage,
            e.image.image_ci.extent.width, e.image.image_ci.extent.height, e.image.image_ci.samples};
}
} // namespace Vulkan
