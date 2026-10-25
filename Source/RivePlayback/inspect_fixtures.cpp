// Metadata/pose inspection only. NoOpFactory never supplies rendering evidence.
#include "rive/file.hpp"
#include "rive/artboard.hpp"
#include "rive/animation/linear_animation.hpp"
#include "rive/animation/state_machine.hpp"
#include "rive/animation/state_machine_layer.hpp"
#include "rive/animation/layer_state.hpp"
#include "rive/animation/layer_state_flags.hpp"
#include "rive/animation/state_machine_instance.hpp"
#include "rive/animation/state_machine_input_instance.hpp"
#include "rive/animation/state_machine_bool.hpp"
#include "rive/animation/state_machine_number.hpp"
#include "rive/animation/state_machine_trigger.hpp"
#include "utils/no_op_factory.hpp"
#include <cstdio>
#include <fstream>
#include <iterator>
#include <vector>

int main(int argc, char** argv)
{
    rive::NoOpFactory factory;
    for (int arg = 1; arg < argc; ++arg)
    {
        std::ifstream stream(argv[arg], std::ios::binary);
        std::vector<uint8_t> bytes((std::istreambuf_iterator<char>(stream)), {});
        auto file = rive::File::import(rive::Span<const uint8_t>(bytes.data(), bytes.size()), &factory);
        if (!file) { std::fprintf(stderr, "IMPORT FAILED %s\n", argv[arg]); return 1; }
        std::printf("FILE %s\n", argv[arg]);
        for (size_t i = 0; i < file->artboardCount(); ++i)
        {
            auto a = file->artboardAt(i);
            std::printf(" ARTBOARD %zu [%s] %gx%g\n", i, a->name().c_str(), a->width(), a->height());
            for (size_t j = 0; j < a->animationCount(); ++j)
            {
                auto anim = a->animationAt(j);
                std::printf("  ANIMATION %zu [%s] duration=%g fps=%u loop=%d\n", j, anim->name().c_str(), anim->durationSeconds(), anim->fps(), anim->loopValue());
            }
            for (size_t j = 0; j < a->stateMachineCount(); ++j)
            {
                auto sm = a->stateMachineAt(j);
                std::printf("  SM %zu [%s]\n", j, sm->name().c_str());
                size_t randomStates = 0;
                for (size_t layer = 0; layer < sm->stateMachine()->layerCount(); ++layer)
                    for (size_t state = 0; state < sm->stateMachine()->layer(layer)->stateCount(); ++state)
                        if ((sm->stateMachine()->layer(layer)->state(state)->flags() & static_cast<uint32_t>(rive::LayerStateFlags::Random)) != 0)
                            ++randomStates;
                std::printf("   RANDOM_TRANSITION_STATES %zu\n", randomStates);
                for (size_t k = 0; k < sm->inputCount(); ++k)
                {
                    auto* in = sm->input(k);
                    std::printf("   INPUT %zu [%s] type=%u", k, in->name().c_str(), in->inputCoreType());
                    if (in->inputCoreType() == rive::StateMachineBool::typeKey) std::printf(" bool=%d", static_cast<rive::SMIBool*>(in)->value());
                    if (in->inputCoreType() == rive::StateMachineNumber::typeKey) std::printf(" number=%g", static_cast<rive::SMINumber*>(in)->value());
                    std::printf("\n");
                }
            }
        }
    }
}
