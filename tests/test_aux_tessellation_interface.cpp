// SPDX-License-Identifier: GPL-2.0-or-later
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <stdexcept>
#include <string>
#include "shader_recompiler/backend/spirv/emit_spirv_quad_rect.h"

using namespace Shader::Backend::SPIRV;

static unsigned checks;
static void Check(bool value, const char* message) {
    ++checks;
    if (!value) throw std::runtime_error(message);
}

// Reflect emitted SPIR-V, rather than assuming the emitter followed its arguments.
static void CheckModule(const std::vector<u32>& words, AuxShaderType stage,
                        const AuxTessellationInterface& expected) {
    struct Type { u32 opcode; std::vector<u32> args; };
    struct Variable { u32 type, storage; };
    std::map<u32, Type> types;
    std::map<u32, Variable> variables;
    std::map<u32, u32> locations, constants;
    std::vector<u32> entry;
    for (size_t i = 5; i < words.size();) {
        const u32 count = words[i] >> 16, opcode = words[i] & 0xffff;
        Check(count != 0 && i + count <= words.size(), "invalid instruction extent");
        const auto* a = words.data() + i + 1;
        if (opcode == 71 && a[1] == 30) locations[a[0]] = a[2]; // Location
        if (opcode == 59) variables[a[1]] = {a[0], a[2]}; // OpVariable
        if (opcode == 43) constants[a[1]] = a[2]; // OpConstant
        if (opcode == 22 || opcode == 23 || opcode == 28 || opcode == 32) {
            types[a[0]] = {opcode, {a + 1, a + count - 1}};
        }
        if (opcode == 15) { // OpEntryPoint's null-terminated name precedes interface IDs.
            size_t end = 2;
            while (end < count - 1) {
                const u32 name = a[end++];
                if (!(name & 0xff) || !(name & 0xff00) || !(name & 0xff0000) ||
                    !(name & 0xff000000)) break;
            }
            entry.assign(a + end, a + count - 1);
        }
        i += count;
    }
    std::array<u8, 33> inputs{}, outputs{};
    for (const u32 id : entry) {
        if (!locations.contains(id)) continue;
        const auto variable = variables.at(id);
        const auto pointer = types.at(variable.type);
        Check(pointer.opcode == 32, "interface variable is not a pointer");
        auto type = types.at(pointer.args[1]);
        const bool needs_array = variable.storage == 1 || stage != AuxShaderType::PassthroughTES;
        if (needs_array) {
            Check(type.opcode == 28, "per-vertex varying is not an array");
            const u32 count = constants.at(type.args[1]);
            Check(count == (variable.storage == 1 ? 32 : 4), "incorrect control-point extent");
            type = types.at(type.args[0]);
        }
        const u32 width = type.opcode == 23 ? type.args[1] : 1;
        if (type.opcode == 23) type = types.at(type.args[0]);
        Check(type.opcode == 22 && type.args[0] == 32, "varying is not float32");
        const u32 location = locations.at(id);
        Check(location < expected.components.size(), "varying location overflow");
        auto& slots = variable.storage == 1 ? inputs : outputs;
        Check(slots[location] == 0, "duplicate varying location");
        slots[location] = width;
    }
    Check(inputs == expected.components, "TCS/TES input differs from VS producer contract");
    Check(outputs == expected.components, "TCS/TES output lost or changed a varying");
}

int main(int argc, char** argv) {
    try {
        unsigned modules = 0;
        for (u32 mask = 0; mask < 256; ++mask) {
            std::array<u8, 32> exports{};
            for (u32 i = 0; i < 8; ++i) if (mask & (1u << i)) exports[i] = 4;
            // Include a sparse highest export and different declared component widths.
            exports[31] = (mask & 0x80) ? 4 : 0;
            for (bool clip : {false, true}) {
                const auto contract = AuxTessellationInterface::FromVertexExports(exports, clip);
                for (u32 i = 0; i < exports.size(); ++i) {
                    Check(contract.components[i + u32(clip)] == exports[i], "clip shift renumbered a VS export");
                }
                Check(!clip || contract.components[0] == 4, "generated clip vector was omitted");
                for (auto stage : {AuxShaderType::RectListTCS, AuxShaderType::QuadListTCS,
                                   AuxShaderType::PassthroughTES}) {
                    const auto words = EmitAuxilaryTessShader(stage, contract);
                    CheckModule(words, stage, contract);
                    ++modules;
                    if (argc == 2 && (mask == 0 || mask == 129)) {
                        const auto path = std::filesystem::path(argv[1]) /
                            ("aux-" + std::to_string(mask) + "-" + std::to_string(clip) + "-" +
                             std::to_string(u32(stage)) + ".spv");
                        std::ofstream file(path, std::ios::binary);
                        file.write(reinterpret_cast<const char*>(words.data()), words.size() * 4);
                        Check(bool(file), "could not write validation fixture");
                    }
                }
            }
        }
        // Real consumers may remap or duplicate inputs; defaults do not create exports.
        // Forward every existing VS location unchanged, independently of PS slot numbering.
        std::array<u8, 32> sparse{};
        sparse[0] = 1; sparse[2] = 2; sparse[7] = 3; sparse[31] = 4;
        const auto contract = AuxTessellationInterface::FromVertexExports(sparse, true);
        for (const u32 producer : {7u, 0u, 2u, 2u}) {
            Check(contract.components[producer + 1] == sparse[producer], "remapped consumer lost its producer");
        }
        Check(contract.components[2] == 0, "unproduced/default slot invented an input");
        for (auto stage : {AuxShaderType::RectListTCS, AuxShaderType::QuadListTCS,
                           AuxShaderType::PassthroughTES}) {
            const auto words = EmitAuxilaryTessShader(stage, contract);
            CheckModule(words, stage, contract);
            if (argc == 2) {
                std::ofstream file(std::filesystem::path(argv[1]) /
                                   ("aux-widths-" + std::to_string(u32(stage)) + ".spv"), std::ios::binary);
                file.write(reinterpret_cast<const char*>(words.data()), words.size() * 4);
                Check(bool(file), "could not write mixed-width fixture");
            }
        }
        std::cout << "PASS: 256 export masks x clip on/off x 3 stages; " << modules
                  << " modules, mixed widths/remaps/default holes, " << checks << " checks\n";
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "FAIL: " << e.what() << '\n';
        return 1;
    }
}
