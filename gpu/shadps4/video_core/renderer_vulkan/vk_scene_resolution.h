// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <array>
#include <memory>
#include <optional>
#include <functional>
#include <unordered_map>
#include <unordered_set>
#include "video_core/renderer_vulkan/scene_resolution.h"
#include "video_core/texture_cache/image.h"

namespace VideoCore { class TextureCache; }
namespace Vulkan {
class Instance;
class Runtime;
class Scheduler;

// Reduced raster targets, with native-size images retained for unmodified guest compute,
// integer texture loads, copies and CPU readbacks. All native access passes Runtime::Transit.
class SceneTargets {
public:
    SceneTargets(const Instance&, Scheduler&, Runtime&, VideoCore::TextureCache&);
    using Lookup = std::function<VideoCore::Image*(VideoCore::ImageId, u64)>;
    SceneTargets(const Instance&, Scheduler&, Runtime&, Lookup);
    ~SceneTargets();
    bool SetSize(SceneResolution::Size);
    SceneResolution::Size Size() const { return size; }
    bool Reduced() const { return size != SceneResolution::Size{}; }
    /// A reduced proxy can stand in for the image: a 1920x1080 scene target or, scaled by
    /// the same factor, a half-resolution (960x540) one (toggle SceneHalfRes).
    bool Eligible(const VideoCore::Image&) const;
    /// Eligible at the full scene size (1920x1080): the upscaler's inputs, the scene start.
    bool EligibleScene(const VideoCore::Image&) const;
    /// The proxy size of an eligible image: the scene size divided like the native size.
    SceneResolution::Size ProxySize(const VideoCore::Image&, u32 level = 0) const;
    struct Target {
        vk::Image image;
        vk::ImageView view;
        vk::ImageLayout layout;
        vk::ImageUsageFlags usage;
        u32 width = 0, height = 0; ///< actual view's base-mip extent, including native fallback
        vk::SampleCountFlagBits samples = vk::SampleCountFlagBits::e1;
    };
    Target Attachment(VideoCore::ImageId, const VideoCore::ImageViewInfo&);
    /// Ineligible images/views stay native, without a copy or a change of sample count.
    /// The caller must check eligibility before assuming proxy dimensions or single sampling.
    Target Read(VideoCore::ImageId, const VideoCore::ImageViewInfo&,
                vk::PipelineStageFlags2 = vk::PipelineStageFlagBits2::eComputeShader,
                vk::AccessFlags2 = vk::AccessFlagBits2::eShaderRead);
    void NativeAccess(VideoCore::Image&, vk::AccessFlags2);
    /// The proxy of `image` for sampling when it holds the current content (else nullopt: the
    /// native image is current). Transitions only after other use (attachment, copy).
    /// Mipmapped targets have one proxy per level: views of one level only.
    std::optional<Target> SampleProxy(const VideoCore::Image& image,
                                      const VideoCore::ImageViewInfo& info);
    /// Whether SampleProxy would return the proxy of `image` for these levels.
    [[nodiscard]] bool ProxyCurrent(const VideoCore::Image& image, u32 level = 0,
                                    u32 levels = 1) const;
    /// SampleProxy for a view obtained before (valid while Generation() is unchanged): the
    /// layout to sample it in.
    vk::ImageLayout PrepareSample(const VideoCore::Image& image, u32 level = 0);
    /// Changes when proxies/views are retired (size or source backing changes).
    [[nodiscard]] u64 Generation() const noexcept {
        return generation;
    }
    /// Whether NativeAccess has work for this image (a reduced-size proxy exists).
    [[nodiscard]] bool Tracks(u64 image_uid) const {
        return !copying && tracked.contains(image_uid);
    }
    void ResolveAll();
    /// Resample externally owned depth (e.g. UI), retaining the supplied layouts on return.
    /// MS sources require matching destination samples; 1x sources may be replicated to MS.
    /// Caller supplies valid tracked layouts/usage and the common depth/stencil format.
    bool ResampleDepthTo(const Target& source, const Target& destination, vk::Format,
                         bool stencil);
    bool debug = false; ///< GOW3_SCENE_DEBUG frame: print resolves and fills
private:
    enum class ViewUse { Sampled, Storage, Attachment };
    struct CachedView {
        VideoCore::ImageViewInfo info;
        ViewUse use;
        vk::UniqueImageView view;
    };
    struct Entry {
        VideoCore::ImageId source{};
        u64 uid = 0;
        u32 level = 0; ///< mip level of the native image this proxy stands for
        const VideoCore::Image::BackingImage* backing = nullptr;
        vk::Image source_image{};
        vk::ImageCreateInfo source_ci{};
        vk::ImageAspectFlags aspect{};
        VideoCore::UniqueImage image;
        std::vector<CachedView> views;
        vk::ImageLayout layout = vk::ImageLayout::eUndefined;
        SceneResolution::Coherence state;
    };
    static constexpr u64 Key(u64 uid, u32 level) {
        return uid << 4 | level;
    }
    Entry* Get(VideoCore::ImageId, u32 level = 0);
    bool Matches(const Entry&, const VideoCore::Image&) const;
    void Invalidate(u64 uid);
    void InvalidateStale(const VideoCore::Image&);
    bool ViewEligible(const VideoCore::Image&, const VideoCore::ImageViewInfo&, ViewUse) const;
    vk::ImageView View(Entry&, const VideoCore::Image&, const VideoCore::ImageViewInfo&, ViewUse);
    Target Native(VideoCore::Image&, const VideoCore::ImageViewInfo&, ViewUse,
                  vk::ImageLayout, vk::PipelineStageFlags2, vk::AccessFlags2);
    void Copy(Entry&, VideoCore::Image&, bool to_native);
    // Depth/stencil formats without blit support (D32S8 on RADV) are resampled by a
    // fullscreen draw writing gl_FragDepth and, with stencil export, the stencil value.
    vk::FormatFeatureFlags Features(vk::Format) const;
    bool Blittable(vk::Format) const;
    bool ShaderResampled(const VideoCore::Image&) const;
    void Resample(vk::Image src, vk::Image dst, const VideoCore::Image& original,
                  vk::Extent2D dst_size);
    void ResampleImages(vk::Image src, vk::Image dst, vk::Format, bool depth, bool stencil,
                        vk::SampleCountFlagBits source_samples, vk::SampleCountFlagBits dest_samples,
                        vk::Extent2D dst_size);
    struct ResampleKey {
        vk::Format format;
        bool depth, stencil, source_ms;
        vk::SampleCountFlagBits samples;
        bool operator==(const ResampleKey&) const = default;
    };
    vk::Pipeline ResamplePipeline(const ResampleKey&);
    void CreateResampleResources();
    void Transition(Entry&, vk::ImageAspectFlags, vk::ImageLayout,
                    vk::PipelineStageFlags2, vk::AccessFlags2);
    const Instance& instance;
    Scheduler& scheduler;
    Runtime& runtime;
    Lookup lookup;
    SceneResolution::Size size;
    std::unordered_map<u64, std::unique_ptr<Entry>> entries; ///< by Key(uid, level)
    std::unordered_set<u64> tracked; ///< uids with proxies
    bool copying = false;
    bool force_stencil_bits = false; ///< test the portable resampler on any driver
    u64 generation = 0;
    mutable std::unordered_map<vk::Format, vk::FormatFeatureFlags> format_features;
    mutable std::array<vk::FormatFeatureFlags, 256> format_table{};
    mutable std::array<bool, 256> format_known{};
    std::array<std::pair<u64, Entry*>, 8> recent{}; ///< last entries by Key
    u32 recent_next = 0;
    vk::UniqueShaderModule fs_tri_vert, depth_frag, depth_stencil_frag, stencil_bits_frag;
    vk::UniqueShaderModule depth_ms_frag, depth_stencil_ms_frag, stencil_bits_ms_frag;
    vk::UniqueShaderModule color_ms_frag, color_ms_uint_frag, color_ms_sint_frag;
    vk::UniqueDescriptorSetLayout resample_set_layout;
    vk::UniquePipelineLayout resample_layout;
    std::vector<std::pair<ResampleKey, vk::UniquePipeline>> resample_pipelines;
};
} // namespace Vulkan
