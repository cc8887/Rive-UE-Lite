#pragma once

// Shared deterministic driver. This header changes no Rive drawing or flush code.
#include "CoreMinimal.h"
#include "Dom/JsonObject.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "Misc/FileHelper.h"
#include "Misc/Parse.h"
#include "HAL/FileManager.h"
#include "Misc/Paths.h"
#pragma push_macro("PI")
#undef PI
#include "rive/file.hpp"
#include "rive/artboard.hpp"
#include "rive/animation/linear_animation.hpp"
#include "rive/animation/linear_animation_instance.hpp"
#include "rive/animation/state_machine.hpp"
#include "rive/animation/state_machine_instance.hpp"
#include "rive/animation/state_machine_input_instance.hpp"
#include "rive/animation/state_machine_bool.hpp"
#include "rive/animation/state_machine_number.hpp"
#include "rive/animation/state_machine_trigger.hpp"
#include "rive/animation/state_machine_layer.hpp"
#include "rive/animation/animation_state.hpp"
#include "rive/animation/entry_state.hpp"
#include "rive/animation/any_state.hpp"
#include "rive/animation/exit_state.hpp"
#pragma pop_macro("PI")
#include <memory>
#include <cfloat>

namespace RivePlayback
{
struct FEvent
{
    double Time = 0;
    int64 Tick = 0;
    FString Type, Name;
    bool BoolValue = false;
    double NumberValue = 0, X = 0, Y = 0;
    int32 PointerId = 0;
};

struct FScenario
{
    bool bEnabled = false;
    FString Mode, Artboard, Animation, StateMachine;
    double FixedDelta = 1.0 / 60.0, TargetTime = 0;
    int64 TargetTick = 0;
    TArray<FEvent> Events;
};

namespace Detail
{
inline FString Text(const std::string& Value) { return UTF8_TO_TCHAR(Value.c_str()); }
inline std::string Native(const FString& Value) { return TCHAR_TO_UTF8(*Value); }
inline TSharedRef<FJsonObject> Object() { return MakeShared<FJsonObject>(); }
inline TSharedPtr<FJsonValue> Value(const TSharedRef<FJsonObject>& In) { return MakeShared<FJsonValueObject>(In); }
inline bool Fail(FString& Error, const FString& Message) { Error = Message; return false; }
inline bool Named(const TSharedPtr<FJsonObject>& Json, const TCHAR* Key, FString& Out, FString& Error)
{
    return (Json->TryGetStringField(Key, Out) && !Out.IsEmpty()) || Fail(Error, FString::Printf(TEXT("Missing nonempty string '%s'"), Key));
}
inline bool Number(const TSharedPtr<FJsonObject>& Json, const TCHAR* Key, double& Out, FString& Error)
{
    return (Json->TryGetNumberField(Key, Out) && FMath::IsFinite(Out)) || Fail(Error, FString::Printf(TEXT("Missing finite number '%s'"), Key));
}
inline bool Tick(double Seconds, double Delta, int64& Out, FString& Error)
{
    if (!FMath::IsFinite(Seconds) || Seconds < 0 || Seconds / Delta > 360000)
        return Fail(Error, TEXT("Time must be nonnegative and within 360000 fixed ticks"));
    Out = FMath::RoundToInt64(Seconds / Delta);
    return FMath::Abs(Seconds - static_cast<double>(Out) * Delta) <= 1e-6 ||
        Fail(Error, TEXT("Time must align to fixed_delta within 1e-6 seconds"));
}
inline TSharedRef<FJsonObject> EventJson(const FEvent& E)
{
    auto J = Object();
    J->SetNumberField(TEXT("time"), E.Time); J->SetNumberField(TEXT("tick"), E.Tick);
    J->SetStringField(TEXT("type"), E.Type);
    if (!E.Name.IsEmpty()) J->SetStringField(TEXT("name"), E.Name);
    if (E.Type == TEXT("bool")) J->SetBoolField(TEXT("value"), E.BoolValue);
    if (E.Type == TEXT("number")) J->SetNumberField(TEXT("value"), E.NumberValue);
    if (E.Type.StartsWith(TEXT("pointer_")))
    {
        J->SetNumberField(TEXT("x"), E.X); J->SetNumberField(TEXT("y"), E.Y);
        J->SetNumberField(TEXT("pointer_id"), E.PointerId);
    }
    return J;
}
inline FString InputType(const rive::SMIInput* Input)
{
    const auto Type = Input->inputCoreType();
    if (Type == rive::StateMachineBool::typeKey) return TEXT("bool");
    if (Type == rive::StateMachineNumber::typeKey) return TEXT("number");
    if (Type == rive::StateMachineTrigger::typeKey) return TEXT("trigger");
    return TEXT("unsupported");
}
inline TSharedRef<FJsonObject> StateJson(const rive::StateMachine& Machine, const rive::LayerState* State, int64 Tick, double Time)
{
    auto J = Object();
    J->SetNumberField(TEXT("time"), Time); J->SetNumberField(TEXT("tick"), Tick);
    int32 LayerIndex = -1, StateIndex = -1;
    for (size_t L = 0; L < Machine.layerCount(); ++L)
        for (size_t S = 0; S < Machine.layer(L)->stateCount(); ++S)
            if (Machine.layer(L)->state(S) == State) { LayerIndex = static_cast<int32>(L); StateIndex = static_cast<int32>(S); }
    J->SetNumberField(TEXT("layer_index"), LayerIndex); J->SetNumberField(TEXT("state_index"), StateIndex);
    J->SetNumberField(TEXT("core_type"), State->coreType());
    FString Kind = TEXT("blend_or_other");
    if (State->is<rive::EntryState>()) Kind = TEXT("entry");
    else if (State->is<rive::AnyState>()) Kind = TEXT("any");
    else if (State->is<rive::ExitState>()) Kind = TEXT("exit");
    else if (State->is<rive::AnimationState>())
    {
        Kind = TEXT("animation");
        const auto* Animation = State->as<rive::AnimationState>()->animation();
        if (Animation) J->SetStringField(TEXT("animation"), Text(Animation->name()));
    }
    J->SetStringField(TEXT("kind"), Kind);
    return J;
}
} // namespace Detail

// Missing -Scenario preserves the old static-image command. A supplied invalid
// scenario never falls back to artboardDefault or to a different named object.
inline bool LoadScenario(const TCHAR* Cmd, FScenario& Out, FString& Error)
{
    Out = FScenario(); Error.Reset();
    FString Path;
    if (!FParse::Value(Cmd, TEXT("Scenario="), Path)) return true;
    FString Source;
    if (!FFileHelper::LoadFileToString(Source, *Path)) return Detail::Fail(Error, TEXT("Cannot read scenario: ") + Path);
    TSharedPtr<FJsonObject> Json;
    if (!FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Source), Json) || !Json.IsValid())
        return Detail::Fail(Error, TEXT("Scenario is not a JSON object"));
    Out.bEnabled = true;
    if (!Detail::Named(Json, TEXT("mode"), Out.Mode, Error) || !Detail::Named(Json, TEXT("artboard"), Out.Artboard, Error) ||
        !Detail::Number(Json, TEXT("fixed_delta"), Out.FixedDelta, Error) || !Detail::Number(Json, TEXT("target_time"), Out.TargetTime, Error)) return false;
    if (Out.FixedDelta < 1e-6 || Out.FixedDelta > 1) return Detail::Fail(Error, TEXT("fixed_delta must be in [1e-6, 1] seconds"));
    if (!Detail::Tick(Out.TargetTime, Out.FixedDelta, Out.TargetTick, Error)) return false;
    if (Out.Mode == TEXT("animation"))
    {
        if (!Detail::Named(Json, TEXT("animation"), Out.Animation, Error)) return false;
        if (Json->HasField(TEXT("state_machine"))) return Detail::Fail(Error, TEXT("animation mode cannot select state_machine"));
    }
    else if (Out.Mode == TEXT("state_machine"))
    {
        if (!Detail::Named(Json, TEXT("state_machine"), Out.StateMachine, Error)) return false;
        if (Json->HasField(TEXT("animation"))) return Detail::Fail(Error, TEXT("state_machine mode cannot select animation"));
    }
    else return Detail::Fail(Error, TEXT("mode must be animation or state_machine"));
    const TArray<TSharedPtr<FJsonValue>>* Events = nullptr;
    if (Json->HasField(TEXT("events")) && !Json->TryGetArrayField(TEXT("events"), Events)) return Detail::Fail(Error, TEXT("events must be an array"));
    if (Events)
    {
        if (Events->Num() > 10000) return Detail::Fail(Error, TEXT("At most 10000 events are allowed"));
        double Previous = -1;
        for (const auto& Raw : *Events)
        {
            if (!Raw.IsValid() || Raw->Type != EJson::Object) return Detail::Fail(Error, TEXT("Every event must be an object"));
            auto J = Raw->AsObject(); FEvent E;
            if (!Detail::Number(J, TEXT("time"), E.Time, Error) || !Detail::Named(J, TEXT("type"), E.Type, Error) ||
                !Detail::Tick(E.Time, Out.FixedDelta, E.Tick, Error)) return false;
            if (E.Time < Previous) return Detail::Fail(Error, TEXT("Events must be ordered by nondecreasing time"));
            Previous = E.Time;
            if (E.Type == TEXT("bool") || E.Type == TEXT("number") || E.Type == TEXT("trigger"))
            {
                if (!Detail::Named(J, TEXT("name"), E.Name, Error)) return false;
                if (E.Type == TEXT("bool") && !J->TryGetBoolField(TEXT("value"), E.BoolValue)) return Detail::Fail(Error, TEXT("bool event requires boolean value"));
                if (E.Type == TEXT("number") && (!Detail::Number(J, TEXT("value"), E.NumberValue, Error) || FMath::Abs(E.NumberValue) > FLT_MAX))
                    return Detail::Fail(Error, TEXT("number event requires finite float-range value"));
                if (E.Type == TEXT("trigger") && J->HasField(TEXT("value"))) return Detail::Fail(Error, TEXT("trigger event has no value; it invokes fire()"));
            }
            else if (E.Type == TEXT("pointer_down") || E.Type == TEXT("pointer_up") || E.Type == TEXT("pointer_move") || E.Type == TEXT("pointer_exit"))
            {
                if (!Detail::Number(J, TEXT("x"), E.X, Error) || !Detail::Number(J, TEXT("y"), E.Y, Error) ||
                    FMath::Abs(E.X) > FLT_MAX || FMath::Abs(E.Y) > FLT_MAX) return Detail::Fail(Error, TEXT("Pointer requires finite float-range artboard x/y"));
                if (J->HasField(TEXT("pointer_id")))
                {
                    double Id = 0;
                    if (!Detail::Number(J, TEXT("pointer_id"), Id, Error) || Id < 0 || Id > MAX_int32 || Id != FMath::FloorToDouble(Id))
                        return Detail::Fail(Error, TEXT("pointer_id must be a nonnegative int32"));
                    E.PointerId = static_cast<int32>(Id);
                }
            }
            else return Detail::Fail(Error, TEXT("Unknown event type: ") + E.Type);
            Out.Events.Add(MoveTemp(E));
        }
    }
    if (Out.Mode == TEXT("animation") && !Out.Events.IsEmpty()) return Detail::Fail(Error, TEXT("animation mode does not accept state-machine input events"));
    return true;
}

inline bool Execute(rive::File& File, const FScenario& S, float LegacySeconds,
    std::unique_ptr<rive::ArtboardInstance>& OutArtboard, TSharedPtr<FJsonObject>& Metadata, FString& Error)
{
    using namespace Detail;
    Error.Reset(); Metadata.Reset(); OutArtboard.reset();
    auto M = Object(); auto Calls = Object();
    const TCHAR* CallNames[] = { TEXT("animation_advance"), TEXT("animation_apply"), TEXT("artboard_advance"),
        TEXT("state_machine_advance_and_apply"), TEXT("pointer_down"), TEXT("pointer_up"), TEXT("pointer_move"), TEXT("pointer_exit"),
        TEXT("bool_set"), TEXT("number_set"), TEXT("trigger_fire") };
    for (const auto* Name : CallNames) Calls->SetNumberField(Name, 0);
    auto Count = [&](const TCHAR* Name) { Calls->SetNumberField(Name, Calls->GetNumberField(Name) + 1); };
    M->SetNumberField(TEXT("schema_version"), 1); M->SetObjectField(TEXT("api_calls"), Calls);
    if (!S.bEnabled)
    {
        if (!FMath::IsFinite(LegacySeconds) || LegacySeconds < 0) return Fail(Error, TEXT("Legacy Seconds must be finite and nonnegative"));
        OutArtboard = File.artboardDefault();
        if (!OutArtboard) return Fail(Error, TEXT("File contains no default artboard"));
        OutArtboard->advance(LegacySeconds); Count(TEXT("artboard_advance"));
        M->SetStringField(TEXT("mode"), TEXT("legacy")); M->SetStringField(TEXT("artboard"), Text(OutArtboard->name()));
        M->SetNumberField(TEXT("target_time"), LegacySeconds); M->SetStringField(TEXT("status"), TEXT("completed"));
        Metadata = M; return true;
    }
    int32 ArtboardIndex = -1;
    for (size_t I = 0; I < File.artboardCount(); ++I)
        if (Text(File.artboardNameAt(I)) == S.Artboard) { if (ArtboardIndex != -1) return Fail(Error, TEXT("Ambiguous artboard name")); ArtboardIndex = static_cast<int32>(I); }
    if (ArtboardIndex < 0) return Fail(Error, TEXT("Artboard does not exist: ") + S.Artboard);
    OutArtboard = File.artboardAt(static_cast<size_t>(ArtboardIndex));
    if (!OutArtboard) return Fail(Error, TEXT("Cannot instantiate selected artboard"));
    auto& Artboard = *OutArtboard;
    std::unique_ptr<rive::LinearAnimationInstance> Animation;
    std::unique_ptr<rive::StateMachineInstance> Machine;
    int32 Selected = -1;
    if (S.Mode == TEXT("animation"))
    {
        for (size_t I = 0; I < Artboard.animationCount(); ++I)
            if (Text(Artboard.animation(I)->name()) == S.Animation) { if (Selected != -1) return Fail(Error, TEXT("Ambiguous animation name")); Selected = static_cast<int32>(I); }
        if (Selected < 0) return Fail(Error, TEXT("Animation does not exist: ") + S.Animation);
        Animation = Artboard.animationAt(Selected);
        M->SetStringField(TEXT("animation"), S.Animation);
    }
    else if (S.Mode == TEXT("state_machine"))
    {
        for (size_t I = 0; I < Artboard.stateMachineCount(); ++I)
            if (Text(Artboard.stateMachine(I)->name()) == S.StateMachine) { if (Selected != -1) return Fail(Error, TEXT("Ambiguous state-machine name")); Selected = static_cast<int32>(I); }
        if (Selected < 0) return Fail(Error, TEXT("State machine does not exist: ") + S.StateMachine);
        Machine = Artboard.stateMachineAt(Selected);
        M->SetStringField(TEXT("state_machine"), S.StateMachine);
    }
    else return Fail(Error, TEXT("Unsupported playback mode"));
    // Validate the complete timeline, even events later than this sample.
    for (const auto& E : S.Events)
    {
        if (E.Type.StartsWith(TEXT("pointer_"))) continue;
        bool Found = false;
        for (size_t I = 0; Machine && I < Machine->inputCount(); ++I)
            if (Text(Machine->input(I)->name()) == E.Name)
            {
                if (Found) return Fail(Error, TEXT("Ambiguous input name: ") + E.Name);
                Found = true;
                if (InputType(Machine->input(I)) != E.Type) return Fail(Error, TEXT("Input type mismatch: ") + E.Name);
            }
        if (!Found) return Fail(Error, TEXT("Input does not exist: ") + E.Name);
    }
    TArray<TSharedPtr<FJsonValue>> Applied, StateChanges, FinalInputs, CurrentAnimations;
    TMap<FString, int32> FireCounts;
    int32 NextEvent = 0;
    int32 EventSettleCount = 0;
    auto Advance = [&](float Delta, int64 TickIndex, double Time)
    {
        if (Animation)
        {
            Animation->advance(Delta); Count(TEXT("animation_advance"));
            Animation->apply(1.f); Count(TEXT("animation_apply"));
            Artboard.advance(Delta); Count(TEXT("artboard_advance"));
        }
        else
        {
            Machine->advanceAndApply(Delta); Count(TEXT("state_machine_advance_and_apply"));
            for (size_t I = 0; I < Machine->stateChangedCount(); ++I)
            {
                const auto* State = Machine->stateChangedByIndex(I);
                if (State) StateChanges.Add(Value(StateJson(*Machine->stateMachine(), State, TickIndex, Time)));
            }
        }
    };
    for (int64 TickIndex = 0; TickIndex <= S.TargetTick; ++TickIndex)
    {
        const double Time = TickIndex * S.FixedDelta;
        // Reach the event's actual time before applying it. A zero-duration
        // settle then processes immediate transitions without borrowing dt.
        if (TickIndex > 0) Advance(static_cast<float>(S.FixedDelta), TickIndex, Time);
        const int32 EventStart = NextEvent;
        while (NextEvent < S.Events.Num() && S.Events[NextEvent].Tick == TickIndex)
        {
            const auto& E = S.Events[NextEvent++]; const auto Name = Native(E.Name);
            if (E.Type == TEXT("bool")) { Machine->getBool(Name)->value(E.BoolValue); Count(TEXT("bool_set")); }
            else if (E.Type == TEXT("number")) { Machine->getNumber(Name)->value(static_cast<float>(E.NumberValue)); Count(TEXT("number_set")); }
            else if (E.Type == TEXT("trigger")) { Machine->getTrigger(Name)->fire(); ++FireCounts.FindOrAdd(E.Name); Count(TEXT("trigger_fire")); }
            else
            {
                rive::Vec2D Position(static_cast<float>(E.X), static_cast<float>(E.Y));
                if (E.Type == TEXT("pointer_down")) Machine->pointerDown(Position, E.PointerId);
                else if (E.Type == TEXT("pointer_up")) Machine->pointerUp(Position, E.PointerId);
                else if (E.Type == TEXT("pointer_move")) Machine->pointerMove(Position, static_cast<float>(Time), E.PointerId);
                else if (E.Type == TEXT("pointer_exit")) Machine->pointerExit(Position, E.PointerId);
                Count(*E.Type);
            }
            Applied.Add(Value(EventJson(E)));
        }
        if (TickIndex == 0) Advance(0.f, TickIndex, Time);
        else if (NextEvent != EventStart) { Advance(0.f, TickIndex, Time); ++EventSettleCount; }
    }
    if (Animation)
    {
        M->SetNumberField(TEXT("animation_duration_seconds"), Animation->durationSeconds());
        M->SetNumberField(TEXT("animation_time"), Animation->time());
        M->SetNumberField(TEXT("animation_total_time"), Animation->totalTime());
        M->SetNumberField(TEXT("animation_fps"), Animation->fps());
        M->SetBoolField(TEXT("animation_did_loop"), Animation->didLoop());
    }
    else
    {
        for (size_t I = 0; I < Machine->inputCount(); ++I)
        {
            const auto* Input = Machine->input(I); auto J = Object(); const auto Type = InputType(Input);
            J->SetStringField(TEXT("name"), Text(Input->name())); J->SetStringField(TEXT("type"), Type);
            if (Type == TEXT("bool")) J->SetBoolField(TEXT("value"), static_cast<const rive::SMIBool*>(Input)->value());
            else if (Type == TEXT("number")) J->SetNumberField(TEXT("value"), static_cast<const rive::SMINumber*>(Input)->value());
            else if (Type == TEXT("trigger")) J->SetNumberField(TEXT("fire_count"), FireCounts.FindRef(Text(Input->name())));
            FinalInputs.Add(Value(J));
        }
        for (size_t I = 0; I < Machine->currentAnimationCount(); ++I)
        {
            const auto* A = Machine->currentAnimationByIndex(I); auto J = Object();
            J->SetStringField(TEXT("name"), Text(A->name())); J->SetNumberField(TEXT("time"), A->time());
            J->SetNumberField(TEXT("duration_seconds"), A->durationSeconds()); CurrentAnimations.Add(Value(J));
        }
    }
    M->SetStringField(TEXT("status"), TEXT("completed")); M->SetStringField(TEXT("mode"), S.Mode);
    M->SetStringField(TEXT("artboard"), S.Artboard); M->SetNumberField(TEXT("artboard_index"), ArtboardIndex);
    M->SetNumberField(TEXT("selected_index"), Selected); M->SetNumberField(TEXT("fixed_delta"), S.FixedDelta);
    M->SetNumberField(TEXT("target_time"), S.TargetTime); M->SetNumberField(TEXT("advanced_time"), S.TargetTick * S.FixedDelta);
    M->SetNumberField(TEXT("advance_count"), S.TargetTick); M->SetNumberField(TEXT("initialization_advance_count"), 1);
    M->SetNumberField(TEXT("event_settle_advance_count"), EventSettleCount);
    M->SetArrayField(TEXT("events_applied"), Applied); M->SetArrayField(TEXT("state_changes"), StateChanges);
    M->SetArrayField(TEXT("final_inputs"), FinalInputs); M->SetArrayField(TEXT("current_animations"), CurrentAnimations);
    Metadata = M;
    return true;
}

inline bool SaveMetadata(const FJsonObject& Metadata, const FString& Path, FString& Error)
{
    FString Source;
    auto Copy = MakeShared<FJsonObject>(); Copy->Values = Metadata.Values;
    if (!FJsonSerializer::Serialize(Copy, TJsonWriterFactory<>::Create(&Source))) return Detail::Fail(Error, TEXT("Cannot serialize playback metadata"));
    const FString Parent = FPaths::GetPath(Path);
    if (!Parent.IsEmpty() && !IFileManager::Get().MakeDirectory(*Parent, true)) return Detail::Fail(Error, TEXT("Cannot create playback metadata directory"));
    return FFileHelper::SaveStringToFile(Source, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM) || Detail::Fail(Error, TEXT("Cannot save playback metadata"));
}
} // namespace RivePlayback
