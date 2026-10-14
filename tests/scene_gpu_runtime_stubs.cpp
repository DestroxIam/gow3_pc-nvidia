// SPDX-License-Identifier: GPL-2.0-or-later
// Headless services with the current renderer ABI; guest accesses deliberately abort.
#include "gow3_toggles.h"
#include <cstddef>
extern "C" {
__thread sigjmp_buf* runtime_fault_recover = nullptr;
std::uint64_t runtime_disabled_optimizations = 0;
std::uint64_t runtime_tsc_frequency() { return 1000000000; }
int runtime_file_translate(const char*, char*, size_t) { std::abort(); }
std::uint64_t runtime_memory_clamp(uintptr_t, std::uint64_t) { std::abort(); }
std::uint64_t runtime_process_time_us() {
    return std::chrono::duration_cast<std::chrono::microseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}
int runtime_memory_region(uintptr_t, uintptr_t*, uintptr_t*, int*) { std::abort(); }
void runtime_memory_set_gpu_hooks(void (*)(uintptr_t, std::uint64_t),
    void (*)(uintptr_t, std::uint64_t), void (*)(uintptr_t, std::uint64_t)) { std::abort(); }
void runtime_thread_attach_host(const char*) {}
void runtime_memory_gpu_protect(uintptr_t, std::uint64_t, int, int) { std::abort(); }
void runtime_restart() { std::abort(); }
std::uint64_t runtime_process_time_counter() { return runtime_process_time_us() * 1000; }
int32_t* runtime_errno() { std::abort(); }
int runtime_memory_write_backing(uintptr_t, const void*, std::uint64_t) { std::abort(); }
}
