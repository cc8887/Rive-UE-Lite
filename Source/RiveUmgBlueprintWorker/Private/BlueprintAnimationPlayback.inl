// One explicit animation clock; DrawWidget always receives zero delta.
static bool GWorkerAnimationObjectsCreated = false;
class FBlueprintAnimationSession
{
public:
    explicit FBlueprintAnimationSession(UUserWidget* InWidget) : Widget(InWidget) {}
    ~FBlueprintAnimationSession()
    {
        if (!Manager) return;
        for (const auto& Item : States)
        {
            Item->GetOnWidgetAnimationFinished().Remove(FinishedHandles[Item.Get()]);
            Item->TearDown();
        }
        Manager->ForceFlush();
        Manager->RemoveWidget(Widget);
        States.Reset();
        State.Reset();
        if (EngineOwner.IsValid())
        {
            // Main's normal garbage collection, before Slate/RHI shutdown,
            // removes this unreachable manager's native Slate delegates.
            GEngine = nullptr;
            EngineOwner.Reset();
        }
    }

    bool Evaluate(UWidgetBlueprint* Blueprint, bool SourceReference)
    {
        FString Name, ScriptPath;
        FParse::Value(FCommandLine::Get(), TEXT("Animation="), Name);
        FParse::Value(FCommandLine::Get(), TEXT("PlaybackScript="), ScriptPath);
        if (Name.IsEmpty()) return ScriptPath.IsEmpty();
        UWidgetAnimation* Source = FindSourceAnimation(Blueprint, Name);
        if (!Source || !Source->MovieScene || !Source->MovieScene->GetTracks().IsEmpty())
            return AuthoringError(TEXT("Animation missing or contains unsupported root tracks"));
        for (const auto& Binding : Source->AnimationBindings)
            if (Binding.bIsRootWidget || !Binding.SlotWidgetName.IsNone() || Binding.DynamicBinding.Function ||
                Binding.DynamicBinding.WeakEndpoint.IsValid() || !Widget->WidgetTree->FindWidget(Binding.WidgetName))
                return AuthoringError(TEXT("Preview supports direct widget bindings only"));
        for (const auto& Binding : static_cast<const UMovieScene*>(Source->MovieScene.Get())->GetBindings())
            for (UMovieSceneTrack* Track : Binding.GetTracks())
            {
                const auto* PropertyTrack = Cast<UMovieScenePropertyTrack>(Track);
                const bool Transform = Cast<UMovieScene2DTransformTrack>(Track) && PropertyTrack &&
                    PropertyTrack->GetPropertyName() == TEXT("RenderTransform") && PropertyTrack->GetPropertyPath() == TEXT("RenderTransform");
                const bool Float = Cast<UMovieSceneFloatTrack>(Track) && PropertyTrack &&
                    PropertyTrack->GetPropertyName() == TEXT("RenderOpacity") && PropertyTrack->GetPropertyPath() == TEXT("RenderOpacity");
                if (!Transform && !Float)
                    return AuthoringError(TEXT("Unsupported tracks are preserved but not automatically played"));
                for (UMovieSceneSection* Section : Track->GetAllSections())
                    if (Transform ? !Section->IsA<UMovieScene2DTransformSection>() : !Section->IsA<UMovieSceneFloatSection>())
                        return AuthoringError(TEXT("Unsupported animation section"));
            }
        Animation = SourceReference ? Source : nullptr;
        if (!SourceReference)
        {
            for (UWidgetAnimation* Candidate : CastChecked<UWidgetBlueprintGeneratedClass>(Blueprint->GeneratedClass)->Animations)
                if (Candidate->GetFName() == FName(*(Source->GetName() + TEXT("_INST")))) Animation = Candidate;
        }
        if (!Animation) return AuthoringError(TEXT("Compiled animation clone not found"));
        double Time = 0;
        FParse::Value(FCommandLine::Get(), TEXT("AnimationTime="), Time);
        if (!FMath::IsFinite(Time) || Time < 0 || Time > Source->GetEndTime()) return false;
        TArray<TSharedPtr<FJsonValue>> Operations;
        if (!ScriptPath.IsEmpty())
        {
            TSharedPtr<FJsonObject> Script;
            const TArray<TSharedPtr<FJsonValue>>* Parsed = nullptr;
            if (!ReadAuthoringJson(ScriptPath, Script) || Script->Values.Num() != 1 ||
                !Script->TryGetArrayField(TEXT("operations"), Parsed) || Parsed->Num() > 1024) return false;
            Operations = *Parsed;
        }
        else
        {
            auto Play = MakeShared<FJsonObject>();
            Play->SetStringField(TEXT("op"), TEXT("play")); Play->SetNumberField(TEXT("time"), Time);
            Play->SetNumberField(TEXT("loops"), 0); Play->SetBoolField(TEXT("restore_state"), true);
            Operations.Add(MakeShared<FJsonValueObject>(Play));
        }
        // Reject malformed scripts before constructing a manager or playing.
        for (const auto& Value : Operations)
        {
            if (!Value || Value->Type != EJson::Object) return false;
            const auto& Op = Value->AsObject(); FString Kind;
            if (!Op->TryGetStringField(TEXT("op"), Kind) || (Kind != TEXT("play") && Kind != TEXT("tick") &&
                Kind != TEXT("seek") && Kind != TEXT("pause") && Kind != TEXT("resume") && Kind != TEXT("reverse") && Kind != TEXT("stop"))) return false;
            for (const auto& Pair : Op->Values)
            {
                const FString Key(Pair.Key);
                if (Key != TEXT("op") && Key != TEXT("label") &&
                    !(Kind == TEXT("play") && (Key == TEXT("time") || Key == TEXT("loops") || Key == TEXT("direction") || Key == TEXT("restore_state"))) &&
                    !(Kind == TEXT("tick") && (Key == TEXT("seconds") || Key == TEXT("hz"))) && !(Kind == TEXT("seek") && Key == TEXT("time"))) return false;
            }
            for (const TCHAR* Key : {TEXT("time"), TEXT("seconds"), TEXT("hz"), TEXT("loops")})
            {
                if (!Op->HasField(Key)) continue;
                double V;
                if (!Op->TryGetNumberField(Key, V) || !FMath::IsFinite(V) || V < 0 || V > 3600 ||
                    (FString(Key) == TEXT("time") && V > Source->GetEndTime()) ||
                    ((FString(Key) == TEXT("hz") || FString(Key) == TEXT("loops")) && V != FMath::FloorToDouble(V)) ||
                    (FString(Key) == TEXT("hz") && (V < 1 || V > 240))) return false;
            }
            FString Direction;
            if (Op->HasField(TEXT("direction")) && (!Op->TryGetStringField(TEXT("direction"), Direction) ||
                (Direction != TEXT("forward") && Direction != TEXT("reverse")))) return false;
            bool Restore;
            if (Op->HasField(TEXT("restore_state")) && !Op->TryGetBoolField(TEXT("restore_state"), Restore)) return false;
        }
        const double OwnerStart = FPlatformTime::Seconds();
        FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("MovieScene"));
        FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("MovieSceneTracks"));
        // UE6's const-initialized classes are lazy in this independent Program.
        // Native system constructors register their component dependencies;
        // without their CDOs a valid entity field/binding silently has no systems.
        TArray<UClass*> SystemClasses;
        GetDerivedClasses(UMovieSceneEntitySystem::StaticClass(), SystemClasses, true);
        int32 InitializedSystemCDOs = 0;
        for (UClass* Class : SystemClasses)
            if (!Class->HasAnyClassFlags(CLASS_Abstract)) { Class->GetDefaultObject(); ++InitializedSystemCDOs; }
        UMovieSceneEntitySystem::StaticInitialize();
        if (FParse::Param(FCommandLine::Get(), TEXT("AnimationDiagnostics")))
            IConsoleManager::Get().FindConsoleVariable(TEXT("UMG.AnimationDetailedLogging"))->Set(true, ECVF_SetByCode);
        if (!GEngine)
        {
            EngineOwner.Reset(NewObject<UGameEngine>(GetTransientPackage(), TEXT("AnimationPreviewEngine")));
            GEngine = EngineOwner.Get();
        }
        Manager = UUMGSequenceTickManager::Get(Widget);
        GWorkerAnimationObjectsCreated = true;
        Info = MakeShared<FJsonObject>();
        Info->SetStringField(TEXT("source_name"), Name);
        Info->SetStringField(TEXT("evaluated_object"), Animation->GetPathName());
        Info->SetStringField(TEXT("api"), TEXT("UUserWidget::PlayAnimation / FWidgetAnimationHandle / FWidgetAnimationState / native MovieScene runner"));
        Info->SetBoolField(TEXT("world_is_null"), Widget->GetWorld() == nullptr);
        if (EngineOwner.IsValid()) Info->SetBoolField(TEXT("engine_initialized"), false);
        else Info->SetField(TEXT("engine_initialized"), MakeShared<FJsonValueNull>());
        Info->SetBoolField(TEXT("engine_init_called_by_worker"), false);
        Info->SetBoolField(TEXT("owns_minimal_engine"), EngineOwner.IsValid());
        Info->SetBoolField(TEXT("manual_clock_only"), true);
        Info->SetNumberField(TEXT("native_system_cdos"), InitializedSystemCDOs);
        Info->SetNumberField(TEXT("owner_manager_init_ms"), (FPlatformTime::Seconds() - OwnerStart) * 1000.0);
        const double EvalStart = FPlatformTime::Seconds();
        TArray<TSharedPtr<FJsonValue>> Snapshots;
        for (const auto& Value : Operations)
        {
            const auto& Op = Value->AsObject(); const FString Kind = Op->GetStringField(TEXT("op"));
            if (Kind == TEXT("play"))
            {
                double Start = 0, Loops = 1; bool Restore = true; FString Direction;
                Op->TryGetNumberField(TEXT("time"), Start); Op->TryGetNumberField(TEXT("loops"), Loops);
                Op->TryGetBoolField(TEXT("restore_state"), Restore); Op->TryGetStringField(TEXT("direction"), Direction);
                State = Widget->PlayAnimation(Animation, Start, int32(Loops),
                    Direction == TEXT("reverse") ? EUMGSequencePlayMode::Reverse : EUMGSequencePlayMode::Forward, 1.f, Restore).PinAnimationState();
                if (!State) return false;
                if (!States.Contains(State))
                {
                    States.Add(State);
                    FinishedHandles.Add(State.Get(), State->GetOnWidgetAnimationFinished().AddLambda([this](FWidgetAnimationState&) { ++FinishedEvents; }));
                }
                ++StartedEvents;
            }
            else
            {
                if (!State) return AuthoringError(TEXT("Playback script must start with play"));
                if (Kind == TEXT("tick"))
                {
                    double Seconds = 0, Hz = 60;
                    if (!Op->TryGetNumberField(TEXT("seconds"), Seconds)) return false;
                    Op->TryGetNumberField(TEXT("hz"), Hz);
                    const int32 Count = FMath::Max(1, FMath::CeilToInt(Seconds * Hz));
                    if (Count > 12000) return false;
                    for (int32 I = 0; I < Count; ++I) { State->Tick(float(Seconds / Count)); Manager->ForceFlush(); }
                }
                else if (Kind == TEXT("seek"))
                {
                    double Seek;
                    if (!Op->TryGetNumberField(TEXT("time"), Seek) || State->GetPlaybackStatus() != EMovieScenePlayerStatus::Playing) return false;
                    State->SetCurrentTime(Seek); State->Tick(0.f);
                }
                else if (Kind == TEXT("pause")) State->Pause();
                else if (Kind == TEXT("resume"))
                {
                    if (State->IsPendingDelete()) return false;
                    State->SetPlaybackStatus(EMovieScenePlayerStatus::Playing);
                }
                else if (Kind == TEXT("reverse")) State->Reverse();
                else if (Kind == TEXT("stop"))
                {
                    // UE6 Pause uses Stopped status; explicitly resume without
                    // advancing so native Stop can finish and restore a paused state.
                    if (!State->IsPendingDelete()) State->SetPlaybackStatus(EMovieScenePlayerStatus::Playing);
                    State->Stop();
                }
            }
            Manager->ForceFlush();
            auto Snapshot = MakeShared<FJsonObject>();
            Snapshot->SetStringField(TEXT("op"), Kind);
            FString Label; Op->TryGetStringField(TEXT("label"), Label); Snapshot->SetStringField(TEXT("label"), Label);
            Snapshot->SetNumberField(TEXT("time_seconds"), State->GetCurrentTime().AsSeconds());
            Snapshot->SetNumberField(TEXT("native_status"), int32(State->GetPlaybackStatus()));
            Snapshot->SetBoolField(TEXT("pending_delete"), State->IsPendingDelete());
            Snapshot->SetBoolField(TEXT("forward"), State->IsPlayingForward());
            Snapshot->SetNumberField(TEXT("finished_events"), FinishedEvents);
            if (const auto Playback = State->GetSharedPlaybackState())
            {
                const auto* Field = Playback->GetCompiledDataManager()->FindEntityComponentField(Playback->GetRootCompiledDataID());
                Snapshot->SetBoolField(TEXT("native_compiled_has_entities"), Field && !Field->IsEmpty());
                Snapshot->SetNumberField(TEXT("native_system_count"), Manager->GetLinker()->SystemGraph.GetSystems().Num());
                Snapshot->SetNumberField(TEXT("queued_updates_after_flush"), Manager->GetRunner()->GetQueuedUpdateCount());
            }
            TArray<TSharedPtr<FJsonValue>> Widgets;
            for (const auto& Binding : Source->AnimationBindings)
            {
                UWidget* Bound = Widget->WidgetTree->FindWidget(Binding.WidgetName);
                auto Item = MakeShared<FJsonObject>();
                Item->SetStringField(TEXT("name"), Bound->GetName());
                if (const auto Playback = State->GetSharedPlaybackState())
                {
                    if (auto* Evaluation = Playback->FindCapability<FMovieSceneEvaluationState>())
                        Item->SetNumberField(TEXT("native_bound_count"), Evaluation->FindBoundObjects(
                            Binding.AnimationGuid, MovieSceneSequenceID::Root, Playback.ToSharedRef()).Num());
                }
                Item->SetNumberField(TEXT("opacity"), Bound->GetRenderOpacity());
                const FWidgetTransform Transform = Bound->GetRenderTransform();
                Item->SetArrayField(TEXT("translation"), VectorJson(Transform.Translation));
                Item->SetArrayField(TEXT("scale"), VectorJson(Transform.Scale));
                Item->SetNumberField(TEXT("angle"), Transform.Angle);
                Widgets.Add(MakeShared<FJsonValueObject>(Item));
            }
            Snapshot->SetArrayField(TEXT("widgets"), Widgets);
            Snapshots.Add(MakeShared<FJsonValueObject>(Snapshot));
        }
        Info->SetArrayField(TEXT("snapshots"), Snapshots);
        Info->SetNumberField(TEXT("play_calls"), StartedEvents);
        Info->SetNumberField(TEXT("finished_events"), FinishedEvents);
        Info->SetNumberField(TEXT("evaluation_ms"), (FPlatformTime::Seconds() - EvalStart) * 1000.0);
        UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_ANIMATION world_null=%d owner_ms=%.3f evaluation_ms=%.3f",
            Widget->GetWorld() == nullptr, Info->GetNumberField(TEXT("owner_manager_init_ms")), Info->GetNumberField(TEXT("evaluation_ms")));
        return true;
    }
    TSharedPtr<FJsonObject> Info;
private:
    UUserWidget* Widget;
    UWidgetAnimation* Animation = nullptr;
    UUMGSequenceTickManager* Manager = nullptr;
    TStrongObjectPtr<UGameEngine> EngineOwner;
    TSharedPtr<FWidgetAnimationState> State;
    TArray<TSharedPtr<FWidgetAnimationState>> States;
    TMap<FWidgetAnimationState*, FDelegateHandle> FinishedHandles;
    int32 FinishedEvents = 0, StartedEvents = 0;
};
