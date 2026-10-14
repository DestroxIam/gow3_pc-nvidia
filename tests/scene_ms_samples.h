// SPDX-License-Identifier: GPL-2.0-or-later
// Headless integration fixture. Fixed-function sample masks seed different stencil values
// without shader stencil export; a compute probe reads both samples independently.
#pragma once
#include "video_core/renderer_vulkan/vk_shader_util.h"
#include "video_core/host_shaders/fs_tri_vert.h"
#include "video_core/host_shaders/scene_ms_test_seed_frag.h"
#include "video_core/host_shaders/scene_ms_test_probe_comp.h"
#include "scene_test_assert.h"

inline unsigned TestSceneMsSamples(const Vulkan::Instance& instance, Vulkan::Scheduler& scheduler,
                              Vulkan::Runtime& runtime, Vulkan::SceneTargets& targets,
                              Common::SlotVector<VideoCore::Image>& images,
                              Common::SlotVector<VideoCore::ImageView>& views,
                              const vk::detail::DispatchLoaderDynamic& dispatch) {
    using namespace Vulkan;
    if (!instance.IsSampleRateShadingEnabled()) {
        std::puts("MSAA per-sample roundtrip SKIP: sampleRateShading unsupported");
        return 0;
    }
    const auto device = instance.GetDevice();
    VideoCore::ImageInfo ci;
    ci.size = {1920,1080,1}; ci.resources = {1,1}; ci.num_samples = 2;
    ci.type = AmdGpu::ImageType::Color2D; ci.pixel_format = vk::Format::eR8G8B8A8Unorm; ci.num_bits = 32;
    const auto color_id = images.insert(instance,runtime,views,ci);
    ci.pixel_format = vk::Format::eD32SfloatS8Uint;
    ci.props.is_depth = ci.props.has_stencil = true;
    const auto depth_id = images.insert(instance,runtime,views,ci);
    auto& color = images[color_id]; auto& depth = images[depth_id];
    if (color.backing->image.image_ci.samples != vk::SampleCountFlagBits::e2 ||
        depth.backing->image.image_ci.samples != vk::SampleCountFlagBits::e2) {
        std::puts("MSAA per-sample roundtrip SKIP: 2x color/depth unavailable");
        return 0;
    }
    SCENE_CHECK(targets.Eligible(color) && targets.Eligible(depth));
    VideoCore::ImageViewInfo cv, dv;
    cv.format = color.info.pixel_format; dv.format = depth.info.pixel_format;
    const auto module = [&](auto& code) {
        return vk::UniqueShaderModule(CompileSPV(code,device),device);
    };
    auto vertex = module(FS_TRI_VERT), seed = module(SCENE_MS_TEST_SEED_FRAG);
    auto probe_shader = module(SCENE_MS_TEST_PROBE_COMP);
    const vk::PushConstantRange seed_pc{vk::ShaderStageFlagBits::eFragment,0,16};
    auto seed_layout = device.createPipelineLayoutUnique({.pushConstantRangeCount=1,.pPushConstantRanges=&seed_pc},nullptr,dispatch);
    SCENE_CHECK(seed_layout.result == vk::Result::eSuccess);
    std::array<vk::UniquePipeline,2> seed_pipelines;
    const vk::SampleMask sample_masks[] = {1,2};
    const std::array shader_stages{
        vk::PipelineShaderStageCreateInfo{.stage=vk::ShaderStageFlagBits::eVertex,.module=*vertex,.pName="main"},
        vk::PipelineShaderStageCreateInfo{.stage=vk::ShaderStageFlagBits::eFragment,.module=*seed,.pName="main"},
    };
    const vk::PipelineVertexInputStateCreateInfo vi{};
    const vk::PipelineInputAssemblyStateCreateInfo ia{.topology=vk::PrimitiveTopology::eTriangleList};
    const vk::PipelineViewportStateCreateInfo viewport{};
    const vk::PipelineRasterizationStateCreateInfo raster{.lineWidth=1.f};
    const vk::StencilOpState stencil{.failOp=vk::StencilOp::eReplace,.passOp=vk::StencilOp::eReplace,
        .depthFailOp=vk::StencilOp::eReplace,.compareOp=vk::CompareOp::eAlways,.compareMask=255,.writeMask=255};
    const vk::PipelineDepthStencilStateCreateInfo ds{.depthTestEnable=true,.depthWriteEnable=true,
        .depthCompareOp=vk::CompareOp::eAlways,.stencilTestEnable=true,.front=stencil,.back=stencil};
    const vk::PipelineColorBlendAttachmentState blend_attachment{.colorWriteMask=vk::ColorComponentFlagBits::eR |
        vk::ColorComponentFlagBits::eG | vk::ColorComponentFlagBits::eB | vk::ColorComponentFlagBits::eA};
    const vk::PipelineColorBlendStateCreateInfo blend{.attachmentCount=1,.pAttachments=&blend_attachment};
    const std::array dynamics{vk::DynamicState::eViewportWithCount,vk::DynamicState::eScissorWithCount,
                              vk::DynamicState::eStencilReference};
    const vk::PipelineDynamicStateCreateInfo dynamic{.dynamicStateCount=u32(dynamics.size()),.pDynamicStates=dynamics.data()};
    const auto color_format = color.backing->image.image_ci.format;
    const auto depth_format = depth.backing->image.image_ci.format;
    const vk::PipelineRenderingCreateInfo rendering{.colorAttachmentCount=1,.pColorAttachmentFormats=&color_format,
        .depthAttachmentFormat=depth_format,.stencilAttachmentFormat=depth_format};
    for (u32 sample=0;sample<2;++sample) {
        const vk::PipelineMultisampleStateCreateInfo ms{.rasterizationSamples=vk::SampleCountFlagBits::e2,
            .sampleShadingEnable=true,.minSampleShading=1.f,.pSampleMask=&sample_masks[sample]};
        auto pipeline = device.createGraphicsPipelineUnique({}, {.pNext=&rendering,.stageCount=2,.pStages=shader_stages.data(),
            .pVertexInputState=&vi,.pInputAssemblyState=&ia,.pViewportState=&viewport,.pRasterizationState=&raster,
            .pMultisampleState=&ms,.pDepthStencilState=&ds,.pColorBlendState=&blend,.pDynamicState=&dynamic,
            .layout=*seed_layout.value},nullptr,dispatch);
        SCENE_CHECK(pipeline.result == vk::Result::eSuccess);
        seed_pipelines[sample] = std::move(pipeline.value);
    }
    const auto draw_seed = [&](const SceneTargets::Target& c,const SceneTargets::Target& d,u32 flip) {
        SCENE_CHECK(c.width==d.width && c.height==d.height && c.samples==d.samples && c.samples==vk::SampleCountFlagBits::e2);
        const vk::RenderingAttachmentInfo ca{.imageView=c.view,.imageLayout=c.layout,
            .loadOp=vk::AttachmentLoadOp::eClear,.storeOp=vk::AttachmentStoreOp::eStore};
        const vk::RenderingAttachmentInfo da{.imageView=d.view,.imageLayout=d.layout,
            .loadOp=vk::AttachmentLoadOp::eClear,.storeOp=vk::AttachmentStoreOp::eStore,
            .clearValue={.depthStencil={1.f,0}}};
        auto cmd = scheduler.CommandBuffer();
        cmd.beginRendering({.renderArea={{0,0},{c.width,c.height}},.layerCount=1,.colorAttachmentCount=1,
            .pColorAttachments=&ca,.pDepthAttachment=&da,.pStencilAttachment=&da},dispatch);
        cmd.setViewportWithCount(vk::Viewport{0,0,float(c.width),float(c.height),0,1},dispatch);
        cmd.setScissorWithCount(vk::Rect2D{{0,0},{c.width,c.height}},dispatch);
        const std::array<u32,4> params{flip,c.width,c.height,0};
        cmd.pushConstants(*seed_layout.value,vk::ShaderStageFlagBits::eFragment,0,16,params.data(),dispatch);
        for (u32 sample=0;sample<2;++sample) {
            cmd.bindPipeline(vk::PipelineBindPoint::eGraphics,*seed_pipelines[sample],dispatch);
            cmd.setStencilReference(vk::StencilFaceFlagBits::eFrontAndBack,flip ? (sample ? 204 : 51) : (sample ? 170 : 85),dispatch);
            cmd.draw(3,1,0,0,dispatch);
        }
        cmd.endRendering(dispatch);
        scheduler.GetDynamicState().Invalidate();
    };
    const std::array probe_bindings{
        vk::DescriptorSetLayoutBinding{0,vk::DescriptorType::eSampledImage,1,vk::ShaderStageFlagBits::eCompute},
        vk::DescriptorSetLayoutBinding{1,vk::DescriptorType::eSampledImage,1,vk::ShaderStageFlagBits::eCompute},
        vk::DescriptorSetLayoutBinding{2,vk::DescriptorType::eSampledImage,1,vk::ShaderStageFlagBits::eCompute},
        vk::DescriptorSetLayoutBinding{3,vk::DescriptorType::eStorageImage,1,vk::ShaderStageFlagBits::eCompute},
    };
    auto probe_set = device.createDescriptorSetLayoutUnique({.flags=vk::DescriptorSetLayoutCreateFlagBits::ePushDescriptorKHR,
        .bindingCount=4,.pBindings=probe_bindings.data()},nullptr,dispatch);
    SCENE_CHECK(probe_set.result == vk::Result::eSuccess);
    const vk::PushConstantRange probe_pc{vk::ShaderStageFlagBits::eCompute,0,16};
    const auto set = *probe_set.value;
    auto probe_layout = device.createPipelineLayoutUnique({.setLayoutCount=1,.pSetLayouts=&set,
        .pushConstantRangeCount=1,.pPushConstantRanges=&probe_pc},nullptr,dispatch);
    SCENE_CHECK(probe_layout.result == vk::Result::eSuccess);
    auto probe_pipeline = device.createComputePipelineUnique({}, {.stage={.stage=vk::ShaderStageFlagBits::eCompute,
        .module=*probe_shader,.pName="main"},.layout=*probe_layout.value},nullptr,dispatch);
    SCENE_CHECK(probe_pipeline.result == vk::Result::eSuccess);
    VideoCore::UniqueImage output(device,instance.GetAllocator());
    output.Create({.imageType=vk::ImageType::e2D,.format=vk::Format::eR32G32B32A32Sfloat,.extent={2,1,1},
        .mipLevels=1,.arrayLayers=1,.samples=vk::SampleCountFlagBits::e1,.tiling=vk::ImageTiling::eOptimal,
        .usage=vk::ImageUsageFlagBits::eStorage | vk::ImageUsageFlagBits::eTransferSrc,.initialLayout=vk::ImageLayout::eUndefined});
    const auto view = [&](vk::Image image,vk::Format format,vk::ImageAspectFlags aspect,vk::ImageUsageFlags usage) {
        const vk::ImageViewUsageCreateInfo use{.usage=usage};
        auto result = device.createImageViewUnique({.pNext=&use,.image=image,.viewType=vk::ImageViewType::e2D,
            .format=format,.subresourceRange={aspect,0,1,0,1}},nullptr,dispatch);
        SCENE_CHECK(result.result == vk::Result::eSuccess);
        return std::move(result.value);
    };
    auto output_view = view(output,vk::Format::eR32G32B32A32Sfloat,vk::ImageAspectFlagBits::eColor,vk::ImageUsageFlagBits::eStorage);
    VkBuffer readback{}; VmaAllocation allocation{}; VmaAllocationInfo mapped{};
    const VkBufferCreateInfo buffer_ci{.sType=VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO,.size=32,.usage=VK_BUFFER_USAGE_TRANSFER_DST_BIT};
    const VmaAllocationCreateInfo allocation_ci{.flags=VMA_ALLOCATION_CREATE_MAPPED_BIT | VMA_ALLOCATION_CREATE_HOST_ACCESS_RANDOM_BIT,
        .usage=VMA_MEMORY_USAGE_AUTO,.requiredFlags=VK_MEMORY_PROPERTY_HOST_COHERENT_BIT};
    SCENE_CHECK(vmaCreateBuffer(instance.GetAllocator(),&buffer_ci,&allocation_ci,&readback,&allocation,&mapped)==VK_SUCCESS);
    vk::ImageLayout output_layout = vk::ImageLayout::eUndefined;
    const auto probe = [&](const SceneTargets::Target& c,const SceneTargets::Target& d,u32 flip) {
        SCENE_CHECK(c.width==d.width && c.height==d.height && c.samples==vk::SampleCountFlagBits::e2 && d.samples==c.samples);
        auto c_view = view(c.image,color_format,vk::ImageAspectFlagBits::eColor,vk::ImageUsageFlagBits::eSampled);
        auto d_view = view(d.image,depth_format,vk::ImageAspectFlagBits::eDepth,vk::ImageUsageFlagBits::eSampled);
        auto s_view = view(d.image,depth_format,vk::ImageAspectFlagBits::eStencil,vk::ImageUsageFlagBits::eSampled);
        const vk::ImageMemoryBarrier2 barrier{.srcStageMask=vk::PipelineStageFlagBits2::eAllCommands,
            .srcAccessMask=vk::AccessFlagBits2::eMemoryRead | vk::AccessFlagBits2::eMemoryWrite,
            .dstStageMask=vk::PipelineStageFlagBits2::eComputeShader,.dstAccessMask=vk::AccessFlagBits2::eShaderWrite,
            .oldLayout=output_layout,.newLayout=vk::ImageLayout::eGeneral,
            .srcQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,.dstQueueFamilyIndex=VK_QUEUE_FAMILY_IGNORED,
            .image=output,.subresourceRange={vk::ImageAspectFlagBits::eColor,0,1,0,1}};
        auto cmd = scheduler.CommandBuffer();
        cmd.pipelineBarrier2({.imageMemoryBarrierCount=1,.pImageMemoryBarriers=&barrier},dispatch);
        const std::array infos{vk::DescriptorImageInfo{{},*c_view,c.layout},vk::DescriptorImageInfo{{},*d_view,d.layout},
            vk::DescriptorImageInfo{{},*s_view,d.layout},vk::DescriptorImageInfo{{},*output_view,vk::ImageLayout::eGeneral}};
        std::array<vk::WriteDescriptorSet,4> writes{};
        for (u32 i=0;i<4;++i) writes[i]={.dstBinding=i,.descriptorCount=1,
            .descriptorType=i==3 ? vk::DescriptorType::eStorageImage : vk::DescriptorType::eSampledImage,.pImageInfo=&infos[i]};
        cmd.bindPipeline(vk::PipelineBindPoint::eCompute,*probe_pipeline.value,dispatch);
        cmd.pushDescriptorSetKHR(vk::PipelineBindPoint::eCompute,*probe_layout.value,0,writes,dispatch);
        const std::array<u32,4> params{c.width,c.height,0,0};
        cmd.pushConstants(*probe_layout.value,vk::ShaderStageFlagBits::eCompute,0,16,params.data(),dispatch);
        cmd.dispatch(1,1,1,dispatch);
        auto transfer = barrier;
        transfer.srcStageMask=vk::PipelineStageFlagBits2::eComputeShader; transfer.srcAccessMask=vk::AccessFlagBits2::eShaderWrite;
        transfer.dstStageMask=vk::PipelineStageFlagBits2::eTransfer; transfer.dstAccessMask=vk::AccessFlagBits2::eTransferRead;
        transfer.oldLayout=vk::ImageLayout::eGeneral; transfer.newLayout=vk::ImageLayout::eTransferSrcOptimal;
        cmd.pipelineBarrier2({.imageMemoryBarrierCount=1,.pImageMemoryBarriers=&transfer},dispatch);
        const vk::BufferImageCopy copy{.imageSubresource={vk::ImageAspectFlagBits::eColor,0,0,1},.imageExtent={2,1,1}};
        cmd.copyImageToBuffer(output,vk::ImageLayout::eTransferSrcOptimal,readback,copy,dispatch);
        const vk::MemoryBarrier2 host{.srcStageMask=vk::PipelineStageFlagBits2::eTransfer,.srcAccessMask=vk::AccessFlagBits2::eTransferWrite,
            .dstStageMask=vk::PipelineStageFlagBits2::eHost,.dstAccessMask=vk::AccessFlagBits2::eHostRead};
        cmd.pipelineBarrier2({.memoryBarrierCount=1,.pMemoryBarriers=&host},dispatch);
        scheduler.Finish(); output_layout=vk::ImageLayout::eTransferSrcOptimal;
        std::array<float,8> got{}; std::memcpy(got.data(),mapped.pMappedData,32);
        const std::array<float,8> expected = flip ? std::array{0.f,1.f,0.375f,51.f,1.f,0.f,0.625f,204.f}
            : std::array{1.f,0.f,0.25f,85.f,0.f,1.f,0.75f,170.f};
        SCENE_CHECK(got==expected);
    };
    const auto native = [&](VideoCore::Image& image,bool attachment) {
        const bool is_depth=image.info.props.is_depth;
        runtime.Transit(&image,attachment ? (is_depth ? vk::ImageLayout::eDepthStencilAttachmentOptimal : vk::ImageLayout::eColorAttachmentOptimal)
            : vk::ImageLayout::eGeneral,vk::PipelineStageFlagBits2::eAllCommands,
            attachment ? vk::AccessFlagBits2::eMemoryWrite : vk::AccessFlagBits2::eShaderRead);
        runtime.FlushBarriers();
        auto info = is_depth ? dv : cv;
        info.is_storage=is_depth && attachment;
        if (is_depth && !attachment) info.format=vk::Format::eR32Sfloat;
        const auto& backing=image.backing->image.image_ci;
        return SceneTargets::Target{image.GetImage(),*image.FindView(info,false).image_view,image.backing->state.layout,
            backing.usage,backing.extent.width,backing.extent.height,backing.samples};
    };
    unsigned completed_cases=0;
    for (const int preset : {4,3,2,1,5,0}) {
        const auto size = SceneResolution::ForPreset(preset,{3840,2160});
        targets.SetSize(size);
        draw_seed(native(color,true),native(depth,true),0);
        const auto c=targets.Read(color_id,cv), d=targets.Read(depth_id,dv);
        SCENE_CHECK(c.width==size.width && c.height==size.height && d.width==size.width && d.height==size.height);
        probe(c,d,0); // native -> proxy, at the last pixel of both samples
        draw_seed(targets.Attachment(color_id,cv),targets.Attachment(depth_id,dv),1);
        probe(native(color,false),native(depth,false),1); // dirty proxy -> native
        std::printf("MSAA2 samples/color/depth/stencil %ux%u bidirectional PASS\n",size.width,size.height);
        ++completed_cases;
    }
    scheduler.Finish();
    vmaDestroyBuffer(instance.GetAllocator(),readback,allocation);
    return completed_cases;
}
