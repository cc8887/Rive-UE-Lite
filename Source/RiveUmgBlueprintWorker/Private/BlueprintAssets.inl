static bool WriteJson(const FString& Path, const TSharedRef<FJsonObject>& Object)
{
    FString Text;
    FJsonSerializer::Serialize(Object, TJsonWriterFactory<>::Create(&Text));
    return FFileHelper::SaveStringToFile(Text, *Path);
}

static TArray<TSharedPtr<FJsonValue>> VectorJson(FVector2D Value)
{
    return {MakeShared<FJsonValueNumber>(Value.X), MakeShared<FJsonValueNumber>(Value.Y)};
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

struct FWidgetPatch
{
    UWidget* Widget = nullptr;
    UCanvasPanelSlot* Slot = nullptr;
    TOptional<FString> Text;
    TOptional<FVector2D> Position, Size;
};

static bool ParseVector(const TSharedPtr<FJsonValue>& Value, FVector2D& Result)
{
    if (!Value.IsValid() || Value->Type != EJson::Array) return false;
    const auto& Values = Value->AsArray();
    if (Values.Num() != 2 || Values[0]->Type != EJson::Number || Values[1]->Type != EJson::Number) return false;
    Result = {Values[0]->AsNumber(), Values[1]->AsNumber()};
    return FMath::IsFinite(Result.X) && FMath::IsFinite(Result.Y);
}

static bool PatchBlueprint(UWidgetBlueprint* Blueprint, const FString& Path)
{
    FString Text;
    TSharedPtr<FJsonObject> Json;
    if (!FFileHelper::LoadFileToString(Text, *Path) ||
        !FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json) || !Json) return false;
    const TArray<TSharedPtr<FJsonValue>>* Edits = nullptr;
    if (Json->Values.Num() != 1 || !Json->TryGetArrayField(TEXT("widgets"), Edits) || Edits->IsEmpty()) return false;
    TArray<FWidgetPatch> Validated;
    TSet<FString> Seen;
    for (const TSharedPtr<FJsonValue>& Edit : *Edits)
    {
        if (!Edit || Edit->Type != EJson::Object) return false;
        const TSharedPtr<FJsonObject>& Object = Edit->AsObject();
        FString Name;
        if (!Object->TryGetStringField(TEXT("name"), Name) || Seen.Contains(Name)) return false;
        Seen.Add(Name);
        FWidgetPatch Item;
        Item.Widget = Blueprint->WidgetTree->FindWidget(FName(*Name));
        if (!Item.Widget || Object->Values.Num() < 2) return false;
        Item.Slot = Cast<UCanvasPanelSlot>(Item.Widget->Slot);
        for (const auto& Pair : Object->Values)
        {
            if (Pair.Key == TEXT("name")) continue;
            if (Pair.Key == TEXT("text"))
            {
                if (!Cast<UTextBlock>(Item.Widget) || Pair.Value->Type != EJson::String) return false;
                Item.Text = Pair.Value->AsString();
            }
            else if (Pair.Key == TEXT("position") || Pair.Key == TEXT("size"))
            {
                FVector2D Value;
                if (!Item.Slot || !ParseVector(Pair.Value, Value)) return false;
                if (Pair.Key == TEXT("size"))
                {
                    if (Value.X <= 0 || Value.Y <= 0) return false;
                    Item.Size = Value;
                }
                else Item.Position = Value;
            }
            else return false;
        }
        Validated.Add(MoveTemp(Item));
    }
    // Validate the complete request before modifying any native object.
    Blueprint->Modify();
    for (const FWidgetPatch& Item : Validated)
    {
        Item.Widget->Modify();
        if (Item.Text) CastChecked<UTextBlock>(Item.Widget)->SetText(FText::FromString(*Item.Text));
        if (Item.Slot)
        {
            Item.Slot->Modify();
            if (Item.Position) Item.Slot->SetPosition(*Item.Position);
            if (Item.Size) Item.Slot->SetSize(*Item.Size);
        }
    }
    Blueprint->MarkPackageDirty();
    return CompileBlueprint(Blueprint) && SaveBlueprint(Blueprint);
}

static TSharedRef<FJsonObject> DescribeBlueprint(UWidgetBlueprint* Blueprint, UUserWidget* Instance)
{
    auto Result = MakeShared<FJsonObject>();
    Result->SetStringField(TEXT("asset_class"), Blueprint->GetClass()->GetPathName());
    Result->SetStringField(TEXT("asset"), Blueprint->GetPathName());
    Result->SetStringField(TEXT("generated_class"), GetPathNameSafe(Blueprint->GeneratedClass));
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
    for (UWidget* Widget : Widgets)
    {
        auto Entry = MakeShared<FJsonObject>();
        Entry->SetStringField(TEXT("name"), Widget->GetName());
        Entry->SetStringField(TEXT("class"), Widget->GetClass()->GetPathName());
        if (auto* LabelWidget = Cast<UTextBlock>(Widget))
            Entry->SetStringField(TEXT("text"), LabelWidget->GetText().ToString());
        if (auto* Slot = Cast<UCanvasPanelSlot>(Widget->Slot))
        {
            Entry->SetArrayField(TEXT("position"), VectorJson(Slot->GetPosition()));
            Entry->SetArrayField(TEXT("size"), VectorJson(Slot->GetSize()));
            Entry->SetBoolField(TEXT("auto_size"), Slot->GetAutoSize());
        }
        if (Instance && Instance->WidgetTree)
        {
            if (UWidget* RuntimeWidget = Instance->WidgetTree->FindWidget(Widget->GetFName()))
            {
                const FGeometry& PaintGeometry = RuntimeWidget->GetPaintSpaceGeometry();
                Entry->SetArrayField(TEXT("rendered_size"), VectorJson(PaintGeometry.GetLocalSize()));
                Entry->SetArrayField(TEXT("rendered_position"), VectorJson(PaintGeometry.GetAbsolutePosition()));
                if (auto* LabelWidget = Cast<UTextBlock>(RuntimeWidget))
                    Entry->SetStringField(TEXT("rendered_text"), LabelWidget->GetText().ToString());
            }
        }
        Entries.Add(MakeShared<FJsonValueObject>(Entry));
    }
    Result->SetArrayField(TEXT("widgets"), Entries);
    return Result;
}
