static bool WriteJson(const FString& Path, const TSharedRef<FJsonObject>& Object)
{
    FString Text;
    FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Text));
    return FFileHelper::SaveStringToFile(Text, *Path, FFileHelper::EEncodingOptions::ForceUTF8WithoutBOM);
}

static TArray<TSharedPtr<FJsonValue>> VectorJson(FVector2D Value)
{
    return {MakeShared<FJsonValueNumber>(Value.X), MakeShared<FJsonValueNumber>(Value.Y)};
}

static TArray<TSharedPtr<FJsonValue>> ColorJson(FLinearColor Value)
{
    return {MakeShared<FJsonValueNumber>(Value.R), MakeShared<FJsonValueNumber>(Value.G),
        MakeShared<FJsonValueNumber>(Value.B), MakeShared<FJsonValueNumber>(Value.A)};
}

static UCanvasPanelSlot* Place(UCanvasPanel* Root, UWidget* Child, FVector2D Position, FVector2D Size)
{
    UCanvasPanelSlot* Slot = Root->AddChildToCanvas(Child);
    Slot->SetAnchors(FAnchors(0.f, 0.f));
    Slot->SetAlignment(FVector2D::ZeroVector);
    Slot->SetAutoSize(false);
    Slot->SetPosition(Position);
    Slot->SetSize(Size);
    return Slot;
}

static UTextBlock* Label(UWidgetTree* Tree, const TCHAR* Name, const TCHAR* Text, int32 Points)
{
    UTextBlock* Widget = Tree->ConstructWidget<UTextBlock>(UTextBlock::StaticClass(), FName(Name));
    Widget->SetText(FText::FromString(Text));
    FSlateFontInfo Font = Widget->GetFont();
    Font.Size = Points;
    Font.TypefaceFontName = TEXT("Regular");
    Widget->SetFont(Font);
    Widget->SetColorAndOpacity(FLinearColor(0.9f, 0.95f, 1.f, 1.f));
    return Widget;
}

static bool CompileBlueprint(UWidgetBlueprint* Blueprint)
{
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_COMPILE_BEGIN asset=%ls", *Blueprint->GetPathName());
    FCompilerResultsLog Results;
    Results.bSilentMode = true;
    FKismetEditorUtilities::CompileBlueprint(Blueprint,
        EBlueprintCompileOptions::SkipGarbageCollection |
        EBlueprintCompileOptions::SkipSave |
        EBlueprintCompileOptions::SkipFiBSearchMetaUpdate, &Results);
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_COMPILE errors=%d warnings=%d status=%d class=%ls",
        Results.NumErrors, Results.NumWarnings, int32(Blueprint->Status), *GetNameSafe(Blueprint->GeneratedClass));
    return Results.NumErrors == 0 && Blueprint->GeneratedClass && Blueprint->Status != BS_Error;
}

static UWidgetBlueprint* CreateFixture(const FString& PackageName, bool Modified)
{
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_CREATE package=%ls modified=%d", *PackageName, Modified);
    UPackage* Package = CreatePackage(*PackageName);
    UWidgetBlueprint* Blueprint = CastChecked<UWidgetBlueprint>(FKismetEditorUtilities::CreateBlueprint(
        UUserWidget::StaticClass(), Package, FName(*FPackageName::GetLongPackageAssetName(PackageName)),
        BPTYPE_Normal, UWidgetBlueprint::StaticClass(), UWidgetBlueprintGeneratedClass::StaticClass(),
        TEXT("RiveUmgBlueprintWorker")));
    if (!Blueprint->WidgetTree)
        Blueprint->WidgetTree = NewObject<UWidgetTree>(Blueprint, TEXT("WidgetTree"), RF_Transactional);
    Blueprint->bCanCallInitializedWithoutPlayerContext = true;
    UWidgetTree* Tree = Blueprint->WidgetTree;
    UCanvasPanel* Canvas = Tree->ConstructWidget<UCanvasPanel>(UCanvasPanel::StaticClass(), TEXT("RootCanvas"));
    Tree->RootWidget = Canvas;
    auto Border = [&](const TCHAR* Name, FLinearColor Color, FVector2D Position, FVector2D Size)
    {
        UBorder* Widget = Tree->ConstructWidget<UBorder>(UBorder::StaticClass(), FName(Name));
        Widget->SetBrush(FSlateColorBrush(Color));
        Place(Canvas, Widget, Position, Size);
        return Widget;
    };
    Border(TEXT("Background"), FLinearColor(0.025f, 0.045f, 0.08f, 1.f), {0, 0}, {640, 400});
    Border(TEXT("Card"), FLinearColor(0.07f, 0.12f, 0.19f, 1.f), {32, 104}, {576, 216});
    Place(Canvas, Label(Tree, TEXT("Title"), Modified ? TEXT("Saved Blueprint preview") : TEXT("UMG Blueprint preview"), 28),
        Modified ? FVector2D(84, 44) : FVector2D(48, 28),
        Modified ? FVector2D(440, 52) : FVector2D(544, 44));
    Place(Canvas, Label(Tree, TEXT("Body"), TEXT("Native WidgetTree / Slate / CPU Vulkan"), 20), {56, 140}, {520, 48});
    Place(Canvas, Label(Tree, TEXT("Detail"), TEXT("Load .uasset > edit > save > reload"), 17), {56, 204}, {520, 44});
    UBorder* Badge = Border(TEXT("Badge"), FLinearColor(0.05f, 0.32f, 0.25f, 1.f),
        Modified ? FVector2D(96, 266) : FVector2D(48, 272),
        Modified ? FVector2D(240, 42) : FVector2D(168, 32));
    Badge->SetPadding(FMargin(12, 4));
    Badge->SetVerticalAlignment(VAlign_Center);
    Badge->SetContent(Label(Tree, TEXT("BadgeLabel"), TEXT("SOURCE UASSET"), 14));
    Place(Canvas, Label(Tree, TEXT("Footer"), TEXT("No GPU | UE native offscreen renderer"), 15), {48, 350}, {544, 28});
    // Nonempty source graph fixture for edit-preservation qualification only.
    if (FParse::Param(FCommandLine::Get(), TEXT("PreservationFixture")))
    {
        UEdGraph* Graph = Blueprint->UbergraphPages.IsEmpty() ?
            FBlueprintEditorUtils::CreateNewGraph(Blueprint, TEXT("EventGraph"), UEdGraph::StaticClass(), UEdGraphSchema_K2::StaticClass()) :
            Blueprint->UbergraphPages[0].Get();
        if (Blueprint->UbergraphPages.IsEmpty()) FBlueprintEditorUtils::AddUbergraphPage(Blueprint, Graph);
        FGraphNodeCreator<UK2Node_CustomEvent> EventCreator(*Graph);
        auto* Event = EventCreator.CreateNode();
        Event->CustomFunctionName = TEXT("PreservedEvent");
        EventCreator.Finalize();
        FGraphNodeCreator<UK2Node_ExecutionSequence> SequenceCreator(*Graph);
        auto* Sequence = SequenceCreator.CreateNode();
        Sequence->NodePosX = 240;
        SequenceCreator.Finalize();
        if (!Graph->GetSchema()->TryCreateConnection(Event->FindPin(UEdGraphSchema_K2::PN_Then),
            Sequence->FindPin(UEdGraphSchema_K2::PN_Execute))) return nullptr;
        FEdGraphPinType Type; Type.PinCategory = UEdGraphSchema_K2::PC_Int;
        if (!FBlueprintEditorUtils::AddMemberVariable(Blueprint, TEXT("PreservedCounter"), Type, TEXT("41"))) return nullptr;
    }
    Blueprint->MarkPackageDirty();
    return CompileBlueprint(Blueprint) ? Blueprint : nullptr;
}

static bool SaveBlueprint(UWidgetBlueprint* Blueprint)
{
    const FString Filename = FPackageName::LongPackageNameToFilename(
        Blueprint->GetOutermost()->GetName(), FPackageName::GetAssetPackageExtension());
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename), true);
    FSavePackageArgs Args;
    Args.TopLevelFlags = RF_Public | RF_Standalone;
    Args.SaveFlags = SAVE_NoError;
    Args.bSlowTask = false;
    // No ArchiveCookData: preserve the source Blueprint and editor metadata.
    const bool OK = UPackage::SavePackage(Blueprint->GetOutermost(), Blueprint, *Filename, Args);
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_BP_SAVE ok=%d cooked=0 path=%ls bytes=%lld",
        OK, *Filename, static_cast<long long>(IFileManager::Get().FileSize(*Filename)));
    return OK;
}

static bool ParseVector(const TSharedPtr<FJsonValue>& Value, FVector2D& Result)
{
    if (!Value.IsValid() || Value->Type != EJson::Array) return false;
    const auto& Values = Value->AsArray();
    if (Values.Num() != 2 || Values[0]->Type != EJson::Number || Values[1]->Type != EJson::Number) return false;
    Result = {Values[0]->AsNumber(), Values[1]->AsNumber()};
    return FMath::IsFinite(Result.X) && FMath::IsFinite(Result.Y);
}

#include "BlueprintAuthoring.inl"

static bool PatchBlueprint(UWidgetBlueprint* Blueprint, const FString& Path)
{
    TSharedPtr<FJsonObject> Json;
    if (!ReadAuthoringJson(Path, Json)) return false;
    const TArray<TSharedPtr<FJsonValue>>* Edits = nullptr;
    if (Json->Values.Num() != 1 || !Json->TryGetArrayField(TEXT("widgets"), Edits) || Edits->IsEmpty()) return false;
    TArray<TPair<UWidget*, FWidgetProperties>> Validated;
    TSet<FName> Seen;
    for (const TSharedPtr<FJsonValue>& Edit : *Edits)
    {
        if (!Edit || Edit->Type != EJson::Object) return false;
        const TSharedPtr<FJsonObject>& Object = Edit->AsObject();
        FString Name;
        if (!Object->TryGetStringField(TEXT("name"), Name) || Name.IsEmpty() || Seen.Contains(FName(*Name)))
            return AuthoringError(TEXT("Missing/duplicate widget name"));
        Seen.Add(FName(*Name));
        UWidget* Widget = Blueprint->WidgetTree->FindWidget(FName(*Name));
        if (!Widget || Object->Values.Num() < 2) return AuthoringError(TEXT("Unknown widget or empty edit: ") + Name);
        FWidgetProperties Properties;
        if (!ValidateWidgetProperties(Object, Widget->GetClass(), Cast<UCanvasPanelSlot>(Widget->Slot) != nullptr,
            false, Properties, GetWidgetTextureBrush(Widget))) return false;
        Validated.Emplace(Widget, MoveTemp(Properties));
    }
    // Validate the complete request before modifying any native object.
    Blueprint->Modify();
    for (const auto& Item : Validated) ApplyWidgetProperties(Item.Key, Item.Value);
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    return CompileBlueprint(Blueprint) && SaveBlueprint(Blueprint);
}

static TSharedRef<FJsonObject> DescribeBlueprint(UWidgetBlueprint* Blueprint, UUserWidget* Instance)
{
    auto Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("asset_class"), Blueprint->GetClass()->GetPathName());
    Result->SetStringField(TEXT("asset"), Blueprint->GetPathName());
    Result->SetStringField(TEXT("generated_class"), GetPathNameSafe(Blueprint->GeneratedClass));
    Result->SetStringField(TEXT("root_widget"), GetNameSafe(Blueprint->WidgetTree->RootWidget));
    Result->SetNumberField(TEXT("variable_count"), Blueprint->NewVariables.Num());
    TArray<TSharedPtr<FJsonValue>> Variables;
    for (const auto& Variable : Blueprint->NewVariables)
    {
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("name"), Variable.VarName.ToString());
        Entry->SetStringField(TEXT("type"), Variable.VarType.PinCategory.ToString());
        Entry->SetStringField(TEXT("declared_default"), Variable.DefaultValue);
        FString ActualDefault;
        if (FProperty* Property = FindFProperty<FProperty>(Blueprint->GeneratedClass, Variable.VarName))
            Property->ExportText_InContainer(0, ActualDefault, Blueprint->GeneratedClass->GetDefaultObject(), nullptr,
                Blueprint->GeneratedClass->GetDefaultObject(), PPF_None);
        else ActualDefault = Variable.DefaultValue;
        Entry->SetStringField(TEXT("default"), ActualDefault);
        Variables.Add(MakeShared<FJsonValueObject>(Entry));
    }
    Result->SetArrayField(TEXT("variables"), Variables);
    TArray<UEdGraph*> Graphs;
    Blueprint->GetAllGraphs(Graphs);
    TArray<TSharedPtr<FJsonValue>> GraphEntries;
    for (UEdGraph* Graph : Graphs)
    {
        auto GraphEntry = MakeShared<FJsonObject>();
        GraphEntry->SetStringField(TEXT("name"), Graph->GetName());
        GraphEntry->SetStringField(TEXT("guid"), Graph->GraphGuid.ToString());
        TArray<TSharedPtr<FJsonValue>> Nodes;
        for (UEdGraphNode* Node : Graph->Nodes)
        {
            auto NodeEntry = MakeShared<FJsonObject>();
            NodeEntry->SetStringField(TEXT("class"), Node->GetClass()->GetPathName());
            NodeEntry->SetStringField(TEXT("guid"), Node->NodeGuid.ToString());
            TArray<TSharedPtr<FJsonValue>> Pins;
            for (UEdGraphPin* Pin : Node->Pins)
            {
                auto PinEntry = MakeShared<FJsonObject>();
                PinEntry->SetStringField(TEXT("name"), Pin->PinName.ToString());
                PinEntry->SetStringField(TEXT("id"), Pin->PinId.ToString());
                PinEntry->SetStringField(TEXT("default"), Pin->DefaultValue);
                TArray<TSharedPtr<FJsonValue>> Links;
                for (UEdGraphPin* Other : Pin->LinkedTo)
                    Links.Add(MakeShared<FJsonValueString>(Other->PinId.ToString()));
                PinEntry->SetArrayField(TEXT("links"), Links);
                Pins.Add(MakeShared<FJsonValueObject>(PinEntry));
            }
            NodeEntry->SetArrayField(TEXT("pins"), Pins);
            Nodes.Add(MakeShared<FJsonValueObject>(NodeEntry));
        }
        GraphEntry->SetArrayField(TEXT("nodes"), Nodes);
        GraphEntries.Add(MakeShared<FJsonValueObject>(GraphEntry));
    }
    Result->SetArrayField(TEXT("graphs"), GraphEntries);
    Result->SetArrayField(TEXT("animations"), DescribeAnimations(Blueprint));
    Result->SetBoolField(TEXT("source_blueprint"), true);
    Result->SetBoolField(TEXT("cooked"), Blueprint->GetOutermost()->HasAnyPackageFlags(PKG_Cooked));
    Result->SetBoolField(TEXT("rendered_generated_class"), Instance != nullptr);
    Result->SetStringField(TEXT("adapter"), Instance ? GRHIAdapterName : TEXT("asset-only operation"));
    Result->SetBoolField(TEXT("using_null_rhi"), GUsingNullRHI);
    Result->SetStringField(TEXT("renderer"), Instance ? TEXT("Native UE FWidgetRenderer / SlateRHIRenderer / Vulkan") : TEXT("not rendered"));
    Result->SetBoolField(TEXT("full_editor_viewport"), false);
    Result->SetNumberField(TEXT("slate_window_count"), FSlateApplication::IsInitialized() ?
        FSlateApplication::Get().GetTopLevelWindows().Num() : 0);
    TArray<UWidget*> Widgets;
    Blueprint->WidgetTree->GetAllWidgets(Widgets);
    TArray<TSharedPtr<FJsonValue>> Entries;
    TMap<FString, UTexture2D*> TextureDependencies;
    for (UWidget* Widget : Widgets)
    {
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("name"), Widget->GetName());
        Entry->SetStringField(TEXT("class"), Widget->GetClass()->GetPathName());
        Entry->SetStringField(TEXT("parent"), GetNameSafe(Widget->GetParent()));
        Entry->SetStringField(TEXT("visibility"), VisibilityName(Widget->GetVisibility()));
        Entry->SetNumberField(TEXT("opacity"), Widget->GetRenderOpacity());
        Entry->SetBoolField(TEXT("enabled"), Widget->GetIsEnabled());
        Entry->SetBoolField(TEXT("is_variable"), Widget->bIsVariable);
        if (const FSlateBrush* Brush = GetWidgetTextureBrush(Widget))
        {
            Entry->SetObjectField(TEXT("brush"), DescribeTextureBrush(*Brush));
            if (auto* Texture = Cast<UTexture2D>(Brush->GetResourceObject()))
                TextureDependencies.Add(Texture->GetPathName(), Texture);
        }
        if (auto* Image = Cast<UImage>(Widget))
            Entry->SetArrayField(TEXT("color"), ColorJson(Image->GetColorAndOpacity()));
        if (auto* LabelWidget = Cast<UTextBlock>(Widget))
        {
            Entry->SetStringField(TEXT("text"), LabelWidget->GetText().ToString());
            Entry->SetNumberField(TEXT("font_size"), LabelWidget->GetFont().Size);
            Entry->SetArrayField(TEXT("color"), ColorJson(LabelWidget->GetColorAndOpacity().GetSpecifiedColor()));
        }
        if (auto* Border = Cast<UBorder>(Widget))
        {
            Entry->SetArrayField(TEXT("color"), ColorJson(Border->Background.TintColor.GetSpecifiedColor()));
            const FMargin Padding = Border->GetPadding();
            Entry->SetArrayField(TEXT("padding"), {MakeShared<FJsonValueNumber>(Padding.Left),
                MakeShared<FJsonValueNumber>(Padding.Top), MakeShared<FJsonValueNumber>(Padding.Right), MakeShared<FJsonValueNumber>(Padding.Bottom)});
        }
        if (auto* Button = Cast<UButton>(Widget)) Entry->SetArrayField(TEXT("color"), ColorJson(Button->GetBackgroundColor()));
        if (auto* Button = Cast<UButton>(Widget))
            for (const FSlateBrush* Brush : {&Button->GetStyle().Normal, &Button->GetStyle().Hovered,
                &Button->GetStyle().Pressed, &Button->GetStyle().Disabled})
                if (auto* Texture = Cast<UTexture2D>(Brush->GetResourceObject()))
                    TextureDependencies.Add(Texture->GetPathName(), Texture);
        if (auto* Slot = Cast<UCanvasPanelSlot>(Widget->Slot))
        {
            Entry->SetArrayField(TEXT("position"), VectorJson(Slot->GetPosition()));
            Entry->SetArrayField(TEXT("size"), VectorJson(Slot->GetSize()));
            Entry->SetArrayField(TEXT("alignment"), VectorJson(Slot->GetAlignment()));
            Entry->SetBoolField(TEXT("auto_size"), Slot->GetAutoSize());
        }
        if (Instance && Instance->WidgetTree)
        {
            if (UWidget* RuntimeWidget = Instance->WidgetTree->FindWidget(Widget->GetFName()))
            {
                const FGeometry& PaintGeometry = RuntimeWidget->GetPaintSpaceGeometry();
                Entry->SetArrayField(TEXT("rendered_size"), VectorJson(PaintGeometry.GetLocalSize()));
                Entry->SetArrayField(TEXT("rendered_position"), VectorJson(PaintGeometry.GetAbsolutePosition()));
                Entry->SetNumberField(TEXT("rendered_opacity"), RuntimeWidget->GetRenderOpacity());
                const FWidgetTransform Transform = RuntimeWidget->GetRenderTransform();
                auto TransformJson = MakeShared<FJsonObject>();
                TransformJson->SetArrayField(TEXT("translation"), VectorJson(Transform.Translation));
                TransformJson->SetArrayField(TEXT("scale"), VectorJson(Transform.Scale));
                TransformJson->SetNumberField(TEXT("angle"), Transform.Angle);
                TransformJson->SetArrayField(TEXT("shear"), VectorJson(Transform.Shear));
                Entry->SetObjectField(TEXT("rendered_transform"), TransformJson);
                if (auto* LabelWidget = Cast<UTextBlock>(RuntimeWidget))
                    Entry->SetStringField(TEXT("rendered_text"), LabelWidget->GetText().ToString());
            }
        }
        Entries.Add(MakeShared<FJsonValueObject>(Entry));
    }
    Result->SetArrayField(TEXT("widgets"), Entries);
    TArray<FString> TexturePaths; TextureDependencies.GetKeys(TexturePaths); TexturePaths.Sort();
    TArray<TSharedPtr<FJsonValue>> Textures;
    for (const FString& Path : TexturePaths)
        Textures.Add(MakeShared<FJsonValueObject>(DescribeTexture(TextureDependencies[Path])));
    Result->SetArrayField(TEXT("texture_dependencies"), Textures);
    return Result;
}
