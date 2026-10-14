// SPDX-FileCopyrightText: Copyright 2024 shadPS4 Emulator Project
// SPDX-License-Identifier: GPL-2.0-or-later

#include "common/logging/log.h"
#include "core/libraries/avplayer/avplayer.h"
#include "core/libraries/avplayer/avplayer_error.h"
#include "core/libraries/avplayer/avplayer_impl.h"
#include "core/libraries/libs.h"

#include <string_view>
#include <string>
#include <algorithm>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <atomic>
#include <mutex>
#include <unordered_set>

namespace Libraries::AvPlayer {

namespace {
std::mutex video_players_mutex;
std::unordered_set<AvPlayerHandle> video_players;
std::atomic<bool> video_active{false};
void TrackVideo(AvPlayerHandle handle, bool active) {
    std::scoped_lock lock{video_players_mutex};
    if (active) video_players.insert(handle);
    else video_players.erase(handle);
    video_active.store(!video_players.empty(), std::memory_order_release);
}
}
bool VideoPlaybackActive() {
    return video_active.load(std::memory_order_acquire);
}

const char* SelectTestMovieSource(std::string_view path, const char* caller) {
    const char* selected = std::getenv("GOW3_AVPLAYER_TEST_SOURCE");
    if (!selected || !*selected) return nullptr;
    const auto slash = path.find_last_of("/\\");
    const auto name = slash == std::string_view::npos ? path : path.substr(slash + 1);
    const auto same_name = [](std::string_view a, std::string_view b) {
        return a.size() == b.size() && std::equal(a.begin(), a.end(), b.begin(),
            [](unsigned char x, unsigned char y) { return std::toupper(x) == std::toupper(y); });
    };
    const bool opening_video = same_name(name, "OPENINGCREDITS.BSF");
    const bool opening_audio = same_name(name, "OPENINGCREDITS.XVAG");
    const bool opening_text = same_name(name, "OPENINGCREDITS.TXT");
    bool replace = opening_video || opening_audio || opening_text;
    const char* effective = selected;
    if (replace) {
        // The BSF video and XVAG audio are separate assets in the local dump.
        // Accept either selected asset and derive its companion in the same mount.
        static thread_local std::string companion;
        companion = selected;
        std::replace(companion.begin(), companion.end(), '\\', '/');
        const auto dot = companion.find_last_of('.');
        const auto selected_name = std::string_view(companion);
        const bool audio = dot != std::string::npos && same_name(selected_name.substr(dot), ".XVAG");
        const bool video = dot != std::string::npos && same_name(selected_name.substr(dot), ".BSF");
        replace = audio || video;
        if (replace) {
            std::string upper = companion;
            std::transform(upper.begin(), upper.end(), upper.begin(),
                [](unsigned char c) { return char(std::toupper(c)); });
            constexpr std::string_view audio_dir = "/SOUNDS/STREAMS_PS4/CINEMATICS/";
            constexpr std::string_view video_dir = "/CINEMATICS/";
            if (audio && !opening_audio) {
                const auto directory = upper.find(audio_dir);
                if (directory == std::string::npos) replace = false;
                else companion.replace(directory, audio_dir.size(), video_dir);
            } else if (video && opening_audio) {
                const auto directory = upper.find(video_dir);
                if (directory == std::string::npos) replace = false;
                else companion.replace(directory, video_dir.size(), audio_dir);
            }
            if (replace) {
                companion.replace(companion.find_last_of('.'), std::string::npos,
                    opening_audio ? ".XVAG" : opening_video ? ".BSF" : ".TXT");
                effective = companion.c_str();
            }
        }
    }
    // The guest-file hook is called for all paths. Log only opening matches
    // there; AvPlayer calls also report mismatches to expose the requested URI.
    static std::atomic<unsigned> matches{0}, mismatches{0};
    const bool trace = replace ? matches.fetch_add(1, std::memory_order_relaxed) < 16 :
        std::strcmp(caller, "guest-file") != 0 &&
        mismatches.fetch_add(1, std::memory_order_relaxed) < 8;
    if (trace) {
        std::printf("GoW3 test source [%s]: requested=%.*s selected=%s override=%d\n",
            caller, int(std::min(path.size(), size_t{1024})), path.empty() ? "" : path.data(),
            replace ? effective : selected, int(replace));
        std::fflush(stdout);
    }
    return replace ? effective : nullptr;
}

s32 PS4_SYSV_ABI sceAvPlayerAddSource(AvPlayerHandle handle, const char* filename) {
    LOG_TRACE(Lib_AvPlayer, "filename = {}", filename);
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->AddSource(filename);
}

s32 PS4_SYSV_ABI sceAvPlayerAddSourceEx(AvPlayerHandle handle, AvPlayerUriType uri_type,
                                        AvPlayerSourceDetails* source_details) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr || uri_type != AvPlayerUriType::Source || source_details == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    const auto path = std::string_view(source_details->uri.name, source_details->uri.length);
    return handle->AddSourceEx(path, source_details->source_type);
}

int PS4_SYSV_ABI sceAvPlayerChangeStream() {
    LOG_ERROR(Lib_AvPlayer, "(STUBBED) called");
    return ORBIS_OK;
}

s32 PS4_SYSV_ABI sceAvPlayerClose(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    TrackVideo(handle, false);
    delete handle;
    return ORBIS_OK;
}

u64 PS4_SYSV_ABI sceAvPlayerCurrentTime(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->CurrentTime();
}

s32 PS4_SYSV_ABI sceAvPlayerDisableStream(AvPlayerHandle handle, u32 stream_id) {
    LOG_ERROR(Lib_AvPlayer, "(STUBBED) called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return ORBIS_OK;
}

s32 PS4_SYSV_ABI sceAvPlayerEnableStream(AvPlayerHandle handle, u32 stream_id) {
    LOG_TRACE(Lib_AvPlayer, "stream_id = {}", stream_id);
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->EnableStream(stream_id);
}

bool PS4_SYSV_ABI sceAvPlayerGetAudioData(AvPlayerHandle handle, AvPlayerFrameInfo* p_info) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr || p_info == nullptr) {
        return false;
    }
    return handle->GetAudioData(*p_info);
}

s32 PS4_SYSV_ABI sceAvPlayerGetStreamInfo(AvPlayerHandle handle, u32 stream_id,
                                          AvPlayerStreamInfo* p_info) {
    LOG_TRACE(Lib_AvPlayer, "stream_id = {}", stream_id);
    if (handle == nullptr || p_info == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->GetStreamInfo(stream_id, *p_info);
}

bool PS4_SYSV_ABI sceAvPlayerGetVideoData(AvPlayerHandle handle, AvPlayerFrameInfo* video_info) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr || video_info == nullptr) {
        return false;
    }
    const bool got_frame = handle->GetVideoData(*video_info);
    if (got_frame) TrackVideo(handle, true);
    else if (!handle->IsActive()) TrackVideo(handle, false);
    return got_frame;
}

bool PS4_SYSV_ABI sceAvPlayerGetVideoDataEx(AvPlayerHandle handle,
                                            AvPlayerFrameInfoEx* video_info) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr || video_info == nullptr) {
        return false;
    }
    const bool got_frame = handle->GetVideoData(*video_info);
    if (got_frame) TrackVideo(handle, true);
    else if (!handle->IsActive()) TrackVideo(handle, false);
    return got_frame;
}

AvPlayerHandle PS4_SYSV_ABI sceAvPlayerInit(AvPlayerInitData* data) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (data == nullptr) {
        return nullptr;
    }

    if (data->memory_replacement.allocate == nullptr ||
        data->memory_replacement.allocate_texture == nullptr ||
        data->memory_replacement.deallocate == nullptr ||
        data->memory_replacement.deallocate_texture == nullptr) {
        LOG_ERROR(Lib_AvPlayer, "All allocators are required for AvPlayer Initialisation.");
        return nullptr;
    }

    return new AvPlayer(*data);
}

s32 PS4_SYSV_ABI sceAvPlayerInitEx(const AvPlayerInitDataEx* p_data, AvPlayerHandle* p_player) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (p_data == nullptr || p_player == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }

    if (p_data->memory_replacement.allocate == nullptr ||
        p_data->memory_replacement.allocate_texture == nullptr ||
        p_data->memory_replacement.deallocate == nullptr ||
        p_data->memory_replacement.deallocate_texture == nullptr) {
        LOG_ERROR(Lib_AvPlayer, "All allocators are required for AvPlayer Initialisation.");
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }

    AvPlayerInitData data = {};
    data.memory_replacement = p_data->memory_replacement;
    data.file_replacement = p_data->file_replacement;
    data.event_replacement = p_data->event_replacement;
    data.default_language = p_data->default_language;
    data.num_output_video_framebuffers = p_data->num_output_video_framebuffers;
    data.auto_start = p_data->auto_start;

    *p_player = new AvPlayer(data);
    return ORBIS_OK;
}

bool PS4_SYSV_ABI sceAvPlayerIsActive(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return false;
    }
    const bool active = handle->IsActive();
    if (!active) TrackVideo(handle, false);
    return active;
}

s32 PS4_SYSV_ABI sceAvPlayerJumpToTime(AvPlayerHandle handle, uint64_t time) {
    LOG_ERROR(Lib_AvPlayer, "(STUBBED) called, time (msec) = {}", time);
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return ORBIS_OK;
}

s32 PS4_SYSV_ABI sceAvPlayerPause(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->Pause();
}

s32 PS4_SYSV_ABI sceAvPlayerPostInit(AvPlayerHandle handle, AvPlayerPostInitData* data) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr || data == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->PostInit(*data);
}

s32 PS4_SYSV_ABI sceAvPlayerPrintf(const char* format, ...) {
    LOG_ERROR(Lib_AvPlayer, "(STUBBED) called");
    return ORBIS_OK;
}

s32 PS4_SYSV_ABI sceAvPlayerResume(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->Resume();
}

s32 PS4_SYSV_ABI sceAvPlayerSetAvSyncMode(AvPlayerHandle handle, AvPlayerAvSyncMode sync_mode) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->SetAvSyncMode(sync_mode);
}

s32 PS4_SYSV_ABI sceAvPlayerSetLogCallback(AvPlayerLogCallback log_cb, void* user_data) {
    LOG_ERROR(Lib_AvPlayer, "(STUBBED) called");
    return ORBIS_OK;
}

s32 PS4_SYSV_ABI sceAvPlayerSetLooping(AvPlayerHandle handle, bool loop_flag) {
    LOG_TRACE(Lib_AvPlayer, "called, looping = {}", loop_flag);
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    if (!handle->SetLooping(loop_flag)) {
        return ORBIS_AVPLAYER_ERROR_OPERATION_FAILED;
    }
    return ORBIS_OK;
}

s32 PS4_SYSV_ABI sceAvPlayerSetTrickSpeed(AvPlayerHandle handle, s32 trick_speed) {
    LOG_ERROR(Lib_AvPlayer, "(STUBBED) called speed = {}", trick_speed);
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return ORBIS_OK;
}

s32 PS4_SYSV_ABI sceAvPlayerStart(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    const auto result = handle->Start();
    if (result == ORBIS_OK) TrackVideo(handle, true);
    return result;
}

s32 PS4_SYSV_ABI sceAvPlayerStop(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    // gow3: guest code calls this and cannot unwind a C++ exception.
    try {
    const auto result = handle->Stop();
    if (result == ORBIS_OK) TrackVideo(handle, false);
    return result;
    } catch (const std::exception& error) {
        LOG_ERROR(Lib_AvPlayer, "Stop failed: {}", error.what());
        return ORBIS_AVPLAYER_ERROR_OPERATION_FAILED;
    }
}

s32 PS4_SYSV_ABI sceAvPlayerStreamCount(AvPlayerHandle handle) {
    LOG_TRACE(Lib_AvPlayer, "called");
    if (handle == nullptr) {
        return ORBIS_AVPLAYER_ERROR_INVALID_PARAMS;
    }
    return handle->GetStreamCount();
}

s32 PS4_SYSV_ABI sceAvPlayerVprintf(const char* format, va_list args) {
    LOG_ERROR(Lib_AvPlayer, "(STUBBED) called");
    return ORBIS_OK;
}

void RegisterLib(Core::Loader::SymbolsResolver* sym) {
    if (const char* selected = std::getenv("GOW3_AVPLAYER_TEST_SOURCE"); selected && *selected) {
        static std::atomic<bool> reported{false};
        if (!reported.exchange(true, std::memory_order_relaxed)) {
            std::printf("GoW3 test source: override armed selected=%s\n", selected);
            std::fflush(stdout);
        }
    }
    LIB_FUNCTION("KMcEa+rHsIo", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerAddSource);
    LIB_FUNCTION("x8uvuFOPZhU", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerAddSourceEx);
    LIB_FUNCTION("buMCiJftcfw", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerChangeStream);
    LIB_FUNCTION("NkJwDzKmIlw", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerClose);
    LIB_FUNCTION("wwM99gjFf1Y", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerCurrentTime);
    LIB_FUNCTION("BOVKAzRmuTQ", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerDisableStream);
    LIB_FUNCTION("ODJK2sn9w4A", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerEnableStream);
    LIB_FUNCTION("Wnp1OVcrZgk", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerGetAudioData);
    LIB_FUNCTION("d8FcbzfAdQw", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerGetStreamInfo);
    LIB_FUNCTION("o3+RWnHViSg", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerGetVideoData);
    LIB_FUNCTION("JdksQu8pNdQ", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerGetVideoDataEx);
    LIB_FUNCTION("aS66RI0gGgo", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerInit);
    LIB_FUNCTION("o9eWRkSL+M4", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerInitEx);
    LIB_FUNCTION("UbQoYawOsfY", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerIsActive);
    LIB_FUNCTION("XC9wM+xULz8", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerJumpToTime);
    LIB_FUNCTION("9y5v+fGN4Wk", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerPause);
    LIB_FUNCTION("HD1YKVU26-M", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerPostInit);
    // LIB_FUNCTION("agig-iDRrTE", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerPrintf);
    LIB_FUNCTION("w5moABNwnRY", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerResume);
    LIB_FUNCTION("k-q+xOxdc3E", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerSetAvSyncMode);
    LIB_FUNCTION("eBTreZ84JFY", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerSetLogCallback);
    LIB_FUNCTION("OVths0xGfho", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerSetLooping);
    LIB_FUNCTION("av8Z++94rs0", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerSetTrickSpeed);
    LIB_FUNCTION("ET4Gr-Uu07s", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerStart);
    LIB_FUNCTION("ZC17w3vB5Lo", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerStop);
    LIB_FUNCTION("hdTyRzCXQeQ", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerStreamCount);
    LIB_FUNCTION("yN7Jhuv8g24", "libSceAvPlayer", 1, "libSceAvPlayer", sceAvPlayerVprintf);
};

} // namespace Libraries::AvPlayer

extern "C" const char* gow3_avplayer_test_source_path(const char* requested) {
    return requested ? Libraries::AvPlayer::SelectTestMovieSource(requested, "guest-file") : nullptr;
}
