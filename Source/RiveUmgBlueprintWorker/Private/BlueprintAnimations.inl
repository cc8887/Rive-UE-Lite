// Native source animation authoring. Unknown tracks/sections are never rebuilt.
static UWidgetAnimation* FindSourceAnimation(UWidgetBlueprint* Blueprint, const FString& Name)
{
    for (UWidgetAnimation* Animation : Blueprint->Animations)
        if (Animation && Animation->GetFName() == FName(*Name)) return Animation;
    return nullptr;
}

static TSharedRef<FJsonObject> DescribeFloatChannel(const FMovieSceneFloatChannel& Channel, FFrameRate Tick, FFrameRate Display)
{
    auto Result = MakeShared<FJsonObject>();
    if (Channel.GetDefault().IsSet()) Result->SetNumberField(TEXT("default"), Channel.GetDefault().GetValue());
    const auto Data = Channel.GetData();
    const auto Times = Data.GetTimes();
    const auto Values = Data.GetValues();
    TArray<TSharedPtr<FJsonValue>> Keys;
    for (int32 I = 0; I < Times.Num(); ++I)
    {
        auto Key = MakeShared<FJsonObject>();
        Key->SetNumberField(TEXT("tick"), Times[I].Value);
        Key->SetNumberField(TEXT("frame"), FFrameRate::TransformTime(FFrameTime(Times[I]), Tick, Display).AsDecimal());
        Key->SetNumberField(TEXT("value"), Values[I].Value);
        Key->SetStringField(TEXT("interpolation"), Values[I].InterpMode == RCIM_Linear ? TEXT("linear") :
            Values[I].InterpMode == RCIM_Constant ? TEXT("constant") : TEXT("cubic"));
        Key->SetNumberField(TEXT("arrive_tangent"), Values[I].Tangent.ArriveTangent);
        Key->SetNumberField(TEXT("leave_tangent"), Values[I].Tangent.LeaveTangent);
        Keys.Add(MakeShared<FJsonValueObject>(Key));
    }
    Result->SetArrayField(TEXT("keys"), Keys);
    return Result;
}

static TArray<TSharedPtr<FJsonValue>> DescribeAnimations(UWidgetBlueprint* Blueprint)
{
    TArray<TSharedPtr<FJsonValue>> Entries;
    for (UWidgetAnimation* Animation : Blueprint->Animations)
    {
        if (!Animation || !Animation->MovieScene) continue;
        const UMovieScene* Scene = Animation->MovieScene;
        const FFrameRate Tick = Scene->GetTickResolution(), Display = Scene->GetDisplayRate();
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("name"), Animation->GetName());
        Entry->SetStringField(TEXT("display_label"), Animation->GetDisplayLabel());
        Entry->SetStringField(TEXT("source_object"), Animation->GetPathName());
        if (const FGuid* Guid = Blueprint->WidgetVariableNameToGuidMap.Find(Animation->GetFName()))
            Entry->SetStringField(TEXT("variable_guid"), Guid->ToString());
        Entry->SetNumberField(TEXT("fps_numerator"), Display.Numerator);
        Entry->SetNumberField(TEXT("fps_denominator"), Display.Denominator);
        Entry->SetNumberField(TEXT("tick_numerator"), Tick.Numerator);
        Entry->SetNumberField(TEXT("tick_denominator"), Tick.Denominator);
        Entry->SetNumberField(TEXT("start_tick"), Scene->GetPlaybackRange().GetLowerBoundValue().Value);
        Entry->SetNumberField(TEXT("end_tick_exclusive"), Scene->GetPlaybackRange().GetUpperBoundValue().Value);
        Entry->SetNumberField(TEXT("end_seconds"), Animation->GetEndTime());
        TArray<TSharedPtr<FJsonValue>> Bindings, Tracks;
        for (const FWidgetAnimationBinding& Binding : Animation->GetBindings())
        {
            auto Item = MakeShared<FJsonObject>();
            Item->SetStringField(TEXT("guid"), Binding.AnimationGuid.ToString());
            Item->SetStringField(TEXT("widget"), Binding.WidgetName.ToString());
            Item->SetStringField(TEXT("slot"), Binding.SlotWidgetName.ToString());
            Item->SetBoolField(TEXT("root"), Binding.bIsRootWidget);
            Bindings.Add(MakeShared<FJsonValueObject>(Item));
        }
        for (const FMovieSceneBinding& Binding : Scene->GetBindings())
        {
            for (UMovieSceneTrack* Track : Binding.GetTracks())
            {
                auto Item = MakeShared<FJsonObject>();
                Item->SetStringField(TEXT("binding_guid"), Binding.GetObjectGuid().ToString());
                Item->SetStringField(TEXT("class"), Track->GetClass()->GetPathName());
                Item->SetStringField(TEXT("object_name"), Track->GetName());
                const auto* Property = Cast<UMovieScenePropertyTrack>(Track);
                if (Property)
                {
                    Item->SetStringField(TEXT("property"), Property->GetPropertyName().ToString());
                    Item->SetStringField(TEXT("property_path"), Property->GetPropertyPath().ToString());
                }
                const bool Supported = Property && ((Cast<UMovieSceneFloatTrack>(Track) &&
                    Property->GetPropertyName() == TEXT("RenderOpacity") && Property->GetPropertyPath() == TEXT("RenderOpacity")) ||
                    (Cast<UMovieScene2DTransformTrack>(Track) && Property->GetPropertyName() == TEXT("RenderTransform") &&
                        Property->GetPropertyPath() == TEXT("RenderTransform")));
                Item->SetBoolField(TEXT("read_only"), !Supported);
                TArray<TSharedPtr<FJsonValue>> Sections;
                for (UMovieSceneSection* Section : Track->GetAllSections())
                {
                    auto Part = MakeShared<FJsonObject>();
                    Part->SetStringField(TEXT("class"), Section->GetClass()->GetPathName());
                    Part->SetStringField(TEXT("object_name"), Section->GetName());
                    Part->SetNumberField(TEXT("completion_mode"), int32(Section->GetCompletionMode()));
                    Part->SetNumberField(TEXT("row"), Section->GetRowIndex());
                    if (Section->GetRange().HasLowerBound()) Part->SetNumberField(TEXT("start_tick"), Section->GetRange().GetLowerBoundValue().Value);
                    if (Section->GetRange().HasUpperBound()) Part->SetNumberField(TEXT("end_tick_exclusive"), Section->GetRange().GetUpperBoundValue().Value);
                    auto Channels = MakeShared<FJsonObject>();
                    if (const auto* Float = Cast<UMovieSceneFloatSection>(Section))
                        Channels->SetObjectField(TEXT("value"), DescribeFloatChannel(Float->GetChannel(), Tick, Display));
                    else if (const auto* Transform = Cast<UMovieScene2DTransformSection>(Section))
                    {
                        Part->SetNumberField(TEXT("mask"), uint32(Transform->GetMask().GetChannels()));
                        Channels->SetObjectField(TEXT("translation_x"), DescribeFloatChannel(Transform->Translation[0], Tick, Display));
                        Channels->SetObjectField(TEXT("translation_y"), DescribeFloatChannel(Transform->Translation[1], Tick, Display));
                        Channels->SetObjectField(TEXT("angle"), DescribeFloatChannel(Transform->Rotation, Tick, Display));
                        Channels->SetObjectField(TEXT("scale_x"), DescribeFloatChannel(Transform->Scale[0], Tick, Display));
                        Channels->SetObjectField(TEXT("scale_y"), DescribeFloatChannel(Transform->Scale[1], Tick, Display));
                        Channels->SetObjectField(TEXT("shear_x"), DescribeFloatChannel(Transform->Shear[0], Tick, Display));
                        Channels->SetObjectField(TEXT("shear_y"), DescribeFloatChannel(Transform->Shear[1], Tick, Display));
                    }
                    else
                    {
                        // Diagnostic readback for opaque sections, without round-tripping them.
                        auto Properties = MakeShared<FJsonObject>();
                        for (TFieldIterator<FProperty> It(Section->GetClass()); It; ++It)
                        {
                            FString Value;
                            It->ExportText_InContainer(0, Value, Section, nullptr, Section, PPF_None);
                            Properties->SetStringField(It->GetName(), Value);
                        }
                        Part->SetObjectField(TEXT("native_properties"), Properties);
                    }
                    Part->SetObjectField(TEXT("channels"), Channels);
                    Sections.Add(MakeShared<FJsonValueObject>(Part));
                }
                Item->SetArrayField(TEXT("sections"), Sections);
                Tracks.Add(MakeShared<FJsonValueObject>(Item));
            }
        }
        Entry->SetArrayField(TEXT("bindings"), Bindings);
        Entry->SetArrayField(TEXT("tracks"), Tracks);
        Entries.Add(MakeShared<FJsonValueObject>(Entry));
    }
    return Entries;
}

struct FAnimationTrackEdit
{
    UWidget* Widget = nullptr;
    FString Property;
    bool Constant = false;
    TArray<int32> Frames;
    TArray<FVector2D> Values;
};

static bool WriteBlueprintAnimation(UWidgetBlueprint* Blueprint, const FString& Path, bool Create)
{
    TSharedPtr<FJsonObject> Json;
    if (!ReadAuthoringJson(Path, Json)) return false;
    FString Name;
    if (!Json->TryGetStringField(TEXT("name"), Name) || Name.IsEmpty() || FName(*Name).IsNone() || Name.Len() > 64 ||
        !FChar::IsAlpha(Name[0]) || Name.EndsWith(TEXT("_INST"))) return AuthoringError(TEXT("Invalid animation name"));
    for (TCHAR C : Name) if (!FChar::IsAlnum(C) && C != TEXT('_')) return AuthoringError(TEXT("Invalid animation name"));
    for (const auto& Pair : Json->Values)
    {
        const FString Key(Pair.Key);
        if (Key != TEXT("name") && Key != TEXT("tracks") && !(Create && (Key == TEXT("fps") || Key == TEXT("duration_frames"))))
            return AuthoringError(TEXT("Unknown animation field: ") + Key);
    }
    UWidgetAnimation* Animation = FindSourceAnimation(Blueprint, Name);
    if ((Create && (Animation || FindObject<UObject>(Blueprint, *Name) || Blueprint->WidgetVariableNameToGuidMap.Contains(FName(*Name)) ||
        Blueprint->NewVariables.ContainsByPredicate([&](const FBPVariableDescription& V) { return V.VarName == FName(*Name); }))) || (!Create && !Animation))
        return AuthoringError(TEXT("Animation already exists or was not found: ") + Name);
    double FpsValue = 60, DurationValue = 60;
    if (Create && (!Json->TryGetNumberField(TEXT("fps"), FpsValue) || !Json->TryGetNumberField(TEXT("duration_frames"), DurationValue) ||
        !FMath::IsFinite(FpsValue) || FpsValue != FMath::FloorToDouble(FpsValue) || FpsValue < 1 || FpsValue > 240 ||
        !FMath::IsFinite(DurationValue) || DurationValue != FMath::FloorToDouble(DurationValue) || DurationValue < 1 || DurationValue > 1000000 ||
        DurationValue / FpsValue > 3600))
        return AuthoringError(TEXT("Use integer fps 1..240, positive integer duration_frames and duration <= 1 hour"));
    const FFrameRate Display = Create ? FFrameRate(int32(FpsValue), 1) : Animation->MovieScene->GetDisplayRate();
    const FFrameRate Tick = Create ? FFrameRate(240000, 1) : Animation->MovieScene->GetTickResolution();
    const int32 LastTick = Create ? FFrameRate::TransformTime(FFrameTime(int32(DurationValue)), Display, Tick).RoundToFrame().Value :
        Animation->MovieScene->GetPlaybackRange().GetUpperBoundValue().Value - 1;
    const TArray<TSharedPtr<FJsonValue>>* Tracks = nullptr;
    if (!Json->TryGetArrayField(TEXT("tracks"), Tracks) || Tracks->IsEmpty() || Tracks->Num() > 512) return false;
    TArray<FAnimationTrackEdit> Edits;
    TSet<FString> Seen;
    for (const auto& Value : *Tracks)
    {
        if (!Value || Value->Type != EJson::Object) return false;
        const auto& Object = Value->AsObject();
        FString WidgetName, Property, Interpolation;
        if (Object->Values.Num() != 4 || !Object->TryGetStringField(TEXT("widget"), WidgetName) ||
            !Object->TryGetStringField(TEXT("property"), Property) || !Object->TryGetStringField(TEXT("interpolation"), Interpolation) ||
            (Interpolation != TEXT("linear") && Interpolation != TEXT("constant"))) return AuthoringError(TEXT("Invalid animation track schema"));
        UWidget* Widget = Blueprint->WidgetTree->FindWidget(FName(*WidgetName));
        if (!Widget || (Property != TEXT("opacity") && Property != TEXT("render_translation") && Property != TEXT("render_scale") && Property != TEXT("render_angle")))
            return AuthoringError(TEXT("Unknown widget or unsupported property: ") + WidgetName + TEXT("/") + Property);
        const FString Id = Widget->GetName() + TEXT("/") + Property;
        if (Seen.Contains(Id)) return AuthoringError(TEXT("Duplicate animation track: ") + Id);
        Seen.Add(Id);
        FAnimationTrackEdit Edit; Edit.Widget = Widget; Edit.Property = Property; Edit.Constant = Interpolation == TEXT("constant");
        const TArray<TSharedPtr<FJsonValue>>* Keys = nullptr;
        if (!Object->TryGetArrayField(TEXT("keys"), Keys) || Keys->IsEmpty() || Keys->Num() > 100000) return false;
        int32 Previous = MIN_int32;
        for (const auto& KeyValue : *Keys)
        {
            if (!KeyValue || KeyValue->Type != EJson::Object) return false;
            const auto& Key = KeyValue->AsObject(); double Frame;
            if (Key->Values.Num() != 2 || !Key->TryGetNumberField(TEXT("frame"), Frame) || !FMath::IsFinite(Frame) ||
                Frame != FMath::FloorToDouble(Frame) || Frame < 0 || Frame > 1000000 ||
                Frame * Tick.AsDecimal() / Display.AsDecimal() > MAX_int32 - 1) return false;
            const int32 KeyTick = FFrameRate::TransformTime(FFrameTime(int32(Frame)), Display, Tick).RoundToFrame().Value;
            if (KeyTick <= Previous || KeyTick > LastTick) return AuthoringError(TEXT("Keys must ascend within animation duration"));
            FVector2D KeyData;
            if (Property == TEXT("render_translation") || Property == TEXT("render_scale"))
            {
                if (!ParseVector(Key->TryGetField(TEXT("value")), KeyData)) return false;
            }
            else
            {
                double Scalar;
                if (!Key->TryGetNumberField(TEXT("value"), Scalar) || !FMath::IsFinite(Scalar) ||
                    (Property == TEXT("opacity") && (Scalar < 0 || Scalar > 1))) return false;
                KeyData = {Scalar, 0};
            }
            if (FMath::Abs(KeyData.X) > 1e6 || FMath::Abs(KeyData.Y) > 1e6) return false;
            Edit.Frames.Add(KeyTick); Edit.Values.Add(KeyData); Previous = KeyTick;
        }
        // Preserve complicated existing sections: refuse to collapse/blend them.
        if (!Create)
        {
            FGuid BindingId; int32 MatchingBindings = 0;
            for (const auto& Binding : Animation->GetBindings())
                if (Binding.WidgetName == Widget->GetFName() && !Binding.bIsRootWidget && Binding.SlotWidgetName.IsNone())
                {
                    if (Binding.DynamicBinding.Function || Binding.DynamicBinding.WeakEndpoint.IsValid())
                        return AuthoringError(TEXT("Dynamic bindings are read-only"));
                    BindingId = Binding.AnimationGuid; ++MatchingBindings;
                }
            if (MatchingBindings > 1) return AuthoringError(TEXT("Ambiguous widget binding; original preserved"));
            if (BindingId.IsValid())
            {
                UMovieScenePropertyTrack* Existing = Property == TEXT("opacity") ?
                    static_cast<UMovieScenePropertyTrack*>(Animation->MovieScene->FindTrack<UMovieSceneFloatTrack>(BindingId, TEXT("RenderOpacity"))) :
                    static_cast<UMovieScenePropertyTrack*>(Animation->MovieScene->FindTrack<UMovieScene2DTransformTrack>(BindingId, TEXT("RenderTransform")));
                if (Existing && (Existing->GetAllSections().Num() != 1 ||
                    Existing->GetAllSections()[0]->IsReadOnly() ||
                    (Property == TEXT("opacity") ? !Existing->GetAllSections()[0]->IsA<UMovieSceneFloatSection>() :
                        !Existing->GetAllSections()[0]->IsA<UMovieScene2DTransformSection>()) ||
                    !(Existing->GetAllSections()[0]->GetBlendType() == EMovieSceneBlendType::Absolute) ||
                    Existing->GetPropertyPath() != (Property == TEXT("opacity") ? TEXT("RenderOpacity") : TEXT("RenderTransform"))))
                    return AuthoringError(TEXT("Only one editable absolute section is supported; original preserved"));
            }
        }
        Edits.Add(MoveTemp(Edit));
    }
    Blueprint->Modify();
    if (Create)
    {
        Animation = NewObject<UWidgetAnimation>(Blueprint, FName(*Name), RF_Transactional);
        Animation->SetDisplayLabel(Name);
        Animation->MovieScene = NewObject<UMovieScene>(Animation, FName(*Name), RF_Transactional);
        Animation->MovieScene->SetTickResolutionDirectly(Tick);
        Animation->MovieScene->SetDisplayRate(Display);
        // Match UMG Editor: inclusive authored endpoint, exclusive upper tick.
        Animation->MovieScene->SetPlaybackRange(0, LastTick + 1);
        Blueprint->Animations.Add(Animation);
        // UE6's compiler validates the same variable identity map used by the
        // native animation panel; creating an object alone is insufficient.
        Blueprint->WidgetVariableNameToGuidMap.Add(Animation->GetFName(), FGuid::NewGuid());
    }
    Animation->Modify(); Animation->MovieScene->Modify();
    for (const FAnimationTrackEdit& Edit : Edits)
    {
        FGuid Guid;
        for (const auto& Binding : Animation->GetBindings())
            if (Binding.WidgetName == Edit.Widget->GetFName() && Binding.SlotWidgetName.IsNone() && !Binding.bIsRootWidget) Guid = Binding.AnimationGuid;
        if (!Guid.IsValid())
        {
            Guid = Animation->MovieScene->AddPossessable(Edit.Widget->GetName(), Edit.Widget->GetClass());
            FWidgetAnimationBinding Binding;
            Binding.WidgetName = Edit.Widget->GetFName(); Binding.AnimationGuid = Guid; Binding.bIsRootWidget = false;
            Animation->AnimationBindings.Add(Binding);
        }
        auto WriteChannel = [&](FMovieSceneFloatChannel& Channel, int32 Axis)
        {
            Channel.Reset();
            for (int32 I = 0; I < Edit.Frames.Num(); ++I)
            {
                const float V = Axis == 0 ? Edit.Values[I].X : Edit.Values[I].Y;
                if (Edit.Constant) Channel.AddConstantKey(FFrameNumber(Edit.Frames[I]), V);
                else Channel.AddLinearKey(FFrameNumber(Edit.Frames[I]), V);
            }
        };
        if (Edit.Property == TEXT("opacity"))
        {
            auto* Track = Animation->MovieScene->FindTrack<UMovieSceneFloatTrack>(Guid, TEXT("RenderOpacity"));
            if (!Track)
            {
                Track = Animation->MovieScene->AddTrack<UMovieSceneFloatTrack>(Guid);
                Track->SetPropertyNameAndPath(TEXT("RenderOpacity"), TEXT("RenderOpacity"));
            }
            Track->Modify();
            auto* Section = Track->GetAllSections().IsEmpty() ? CastChecked<UMovieSceneFloatSection>(Track->CreateNewSection()) :
                CastChecked<UMovieSceneFloatSection>(Track->GetAllSections()[0]);
            if (Track->GetAllSections().IsEmpty()) { static_cast<UMovieSceneTrack*>(Track)->AddSection(*Section); Section->SetRange(TRange<FFrameNumber>::All()); Section->SetCompletionMode(EMovieSceneCompletionMode::RestoreState); }
            Section->Modify(); WriteChannel(Section->GetChannel(), 0);
        }
        else
        {
            auto* Track = Animation->MovieScene->FindTrack<UMovieScene2DTransformTrack>(Guid, TEXT("RenderTransform"));
            if (!Track)
            {
                Track = Animation->MovieScene->AddTrack<UMovieScene2DTransformTrack>(Guid);
                Track->SetPropertyNameAndPath(TEXT("RenderTransform"), TEXT("RenderTransform"));
            }
            Track->Modify();
            auto* Section = Track->GetAllSections().IsEmpty() ? CastChecked<UMovieScene2DTransformSection>(Track->CreateNewSection()) :
                CastChecked<UMovieScene2DTransformSection>(Track->GetAllSections()[0]);
            if (Track->GetAllSections().IsEmpty()) { static_cast<UMovieSceneTrack*>(Track)->AddSection(*Section); Section->SetRange(TRange<FFrameNumber>::All()); Section->SetCompletionMode(EMovieSceneCompletionMode::RestoreState); Section->SetMask(EMovieScene2DTransformChannel::None); }
            Section->Modify();
            auto Mask = Section->GetMask().GetChannels();
            if (Edit.Property == TEXT("render_translation"))
            { WriteChannel(Section->Translation[0], 0); WriteChannel(Section->Translation[1], 1); Mask |= EMovieScene2DTransformChannel::Translation; }
            else if (Edit.Property == TEXT("render_scale"))
            { WriteChannel(Section->Scale[0], 0); WriteChannel(Section->Scale[1], 1); Mask |= EMovieScene2DTransformChannel::Scale; }
            else { WriteChannel(Section->Rotation, 0); Mask |= EMovieScene2DTransformChannel::Rotation; }
            Section->SetMask(Mask);
        }
    }
    if (Create && FParse::Param(FCommandLine::Get(), TEXT("AnimationOpaqueFixture")))
    {
        // Internal native preservation fixture, deliberately outside the public
        // authoring/preview whitelist. It must survive a supported channel edit.
        auto* Track = Animation->MovieScene->AddTrack<UMovieSceneBoolTrack>(Animation->AnimationBindings[0].AnimationGuid);
        Track->SetPropertyNameAndPath(TEXT("bIsEnabled"), TEXT("bIsEnabled"));
        auto* Section = CastChecked<UMovieSceneBoolSection>(Track->CreateNewSection());
        Section->GetChannel().AddKeys({FFrameNumber(0), FFrameNumber(LastTick)}, {false, true});
        Section->SetRange(TRange<FFrameNumber>::All());
        static_cast<UMovieSceneTrack*>(Track)->AddSection(*Section);
    }
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    return CompileBlueprint(Blueprint) && SaveBlueprint(Blueprint);
}
