// Typed source WidgetTree authoring. Included after native compile/save helpers.
struct FWidgetProperties
{
    TOptional<FString> Text;
    TOptional<FVector2D> Position, Size, Alignment;
    TOptional<FLinearColor> Color;
    TOptional<FMargin> Padding;
    TOptional<float> Opacity;
    TOptional<int32> FontSize;
    TOptional<bool> Enabled, Variable;
    TOptional<ESlateVisibility> Visibility;
    TOptional<FSlateBrush> Brush;
};

static bool AuthoringError(const FString& Message)
{
    UE_LOGF(LogUmgBlueprintWorker, Error, "WIDGET_BP_VALIDATION: %ls", *Message);
    return false;
}

static bool ReadAuthoringJson(const FString& Path, TSharedPtr<FJsonObject>& Json)
{
    FString Text;
    return (FFileHelper::LoadFileToString(Text, *Path) &&
        FJsonSerializer::Deserialize(TJsonReaderFactory<>::Create(Text), Json) && Json.IsValid()) ||
        AuthoringError(TEXT("Cannot read JSON object: ") + Path);
}

static UClass* SupportedWidgetClass(const FString& Type)
{
    if (Type == TEXT("CanvasPanel")) return UCanvasPanel::StaticClass();
    if (Type == TEXT("Border")) return UBorder::StaticClass();
    if (Type == TEXT("Button")) return UButton::StaticClass();
    if (Type == TEXT("TextBlock")) return UTextBlock::StaticClass();
    if (Type == TEXT("Image")) return UImage::StaticClass();
    return nullptr;
}

static FString VisibilityName(ESlateVisibility Value)
{
    switch (Value)
    {
    case ESlateVisibility::Visible: return TEXT("Visible");
    case ESlateVisibility::Hidden: return TEXT("Hidden");
    case ESlateVisibility::Collapsed: return TEXT("Collapsed");
    case ESlateVisibility::HitTestInvisible: return TEXT("HitTestInvisible");
    case ESlateVisibility::SelfHitTestInvisible: return TEXT("SelfHitTestInvisible");
    }
    return TEXT("Unknown");
}

static bool NumberArray(const TSharedPtr<FJsonValue>& Value, int32 Count, TArray<double>& Out)
{
    if (!Value || Value->Type != EJson::Array || Value->AsArray().Num() != Count) return false;
    for (const auto& Item : Value->AsArray())
    {
        if (!Item || Item->Type != EJson::Number || !FMath::IsFinite(Item->AsNumber())) return false;
        Out.Add(Item->AsNumber());
    }
    return true;
}

#include "BlueprintTextures.inl"

static bool ValidateWidgetProperties(const TSharedPtr<FJsonObject>& Json, UClass* Class,
    bool CanvasSlot, bool Spec, FWidgetProperties& Out, const FSlateBrush* ExistingBrush = nullptr)
{
    for (const auto& Pair : Json->Values)
    {
        const FString Key(Pair.Key);
        const auto& Value = Pair.Value;
        if (Key == TEXT("name") || (Spec && (Key == TEXT("type") || Key == TEXT("parent")))) continue;
        bool Valid = false;
        if (Key == TEXT("text") && Class->IsChildOf(UTextBlock::StaticClass()) && Value->Type == EJson::String)
        { Out.Text = Value->AsString(); Valid = true; }
        else if ((Key == TEXT("position") || Key == TEXT("size") || Key == TEXT("alignment")) && CanvasSlot)
        {
            FVector2D Vector;
            if (ParseVector(Value, Vector) && (Key != TEXT("size") || (Vector.X > 0 && Vector.Y > 0)))
            {
                if (Key == TEXT("position")) Out.Position = Vector;
                else if (Key == TEXT("size")) Out.Size = Vector;
                else Out.Alignment = Vector;
                Valid = true;
            }
        }
        else if (Key == TEXT("color") && (Class->IsChildOf(UTextBlock::StaticClass()) ||
            Class->IsChildOf(UBorder::StaticClass()) || Class->IsChildOf(UButton::StaticClass()) || Class->IsChildOf(UImage::StaticClass())))
        {
            TArray<double> Numbers;
            if (NumberArray(Value, 4, Numbers) && Algo::AllOf(Numbers, [](double N) { return N >= 0 && N <= 1; }))
            { Out.Color = FLinearColor(Numbers[0], Numbers[1], Numbers[2], Numbers[3]); Valid = true; }
        }
        else if (Key == TEXT("brush") && Value->Type == EJson::Object &&
            (Class->IsChildOf(UImage::StaticClass()) || Class->IsChildOf(UBorder::StaticClass())))
        {
            FSlateBrush Brush;
            Brush.DrawAs = ESlateBrushDrawType::Image;
            if (ExistingBrush) Brush = *ExistingBrush;
            if (!ReadTextureBrush(Value->AsObject(), Brush)) return false;
            Out.Brush = Brush; Valid = true;
        }
        else if (Key == TEXT("padding") && Class->IsChildOf(UBorder::StaticClass()))
        {
            TArray<double> Numbers;
            if (NumberArray(Value, 4, Numbers) && Algo::AllOf(Numbers, [](double N) { return N >= 0; }))
            { Out.Padding = FMargin(Numbers[0], Numbers[1], Numbers[2], Numbers[3]); Valid = true; }
        }
        else if (Key == TEXT("font_size") && Class->IsChildOf(UTextBlock::StaticClass()) && Value->Type == EJson::Number)
        {
            const double N = Value->AsNumber();
            if (FMath::IsFinite(N) && N >= 1 && N <= 256 && FMath::FloorToDouble(N) == N)
            { Out.FontSize = static_cast<int32>(N); Valid = true; }
        }
        else if (Key == TEXT("opacity") && Value->Type == EJson::Number)
        {
            const double N = Value->AsNumber();
            if (FMath::IsFinite(N) && N >= 0 && N <= 1) { Out.Opacity = N; Valid = true; }
        }
        else if ((Key == TEXT("enabled") || Key == TEXT("is_variable")) && Value->Type == EJson::Boolean)
        {
            if (Key == TEXT("enabled")) Out.Enabled = Value->AsBool(); else Out.Variable = Value->AsBool();
            Valid = true;
        }
        else if (Key == TEXT("visibility") && Value->Type == EJson::String)
        {
            for (ESlateVisibility Item : {ESlateVisibility::Visible, ESlateVisibility::Hidden, ESlateVisibility::Collapsed,
                ESlateVisibility::HitTestInvisible, ESlateVisibility::SelfHitTestInvisible})
                if (Value->AsString() == VisibilityName(Item)) { Out.Visibility = Item; Valid = true; }
        }
        if (!Valid) return AuthoringError(TEXT("Unsupported property/value/slot: ") + Key);
    }
    return true;
}

static void ApplyWidgetProperties(UWidget* Widget, const FWidgetProperties& Properties)
{
    Widget->Modify();
    if (Properties.Brush)
    {
        if (auto* Image = Cast<UImage>(Widget)) Image->SetBrush(*Properties.Brush);
        else CastChecked<UBorder>(Widget)->SetBrush(*Properties.Brush);
    }
    if (Properties.Text) CastChecked<UTextBlock>(Widget)->SetText(FText::FromString(*Properties.Text));
    if (Properties.FontSize)
    {
        auto* Text = CastChecked<UTextBlock>(Widget);
        FSlateFontInfo Font = Text->GetFont(); Font.Size = *Properties.FontSize; Text->SetFont(Font);
    }
    if (Properties.Color)
    {
        if (auto* Text = Cast<UTextBlock>(Widget)) Text->SetColorAndOpacity(*Properties.Color);
        else if (auto* Image = Cast<UImage>(Widget)) Image->SetColorAndOpacity(*Properties.Color);
        else if (auto* Border = Cast<UBorder>(Widget))
        {
            // A tint edit must not discard an existing texture, UV or box margins.
            FSlateBrush Brush = Border->Background;
            Brush.TintColor = *Properties.Color; Border->SetBrush(Brush);
        }
        else CastChecked<UButton>(Widget)->SetBackgroundColor(*Properties.Color);
    }
    if (Properties.Padding)
    {
        CastChecked<UBorder>(Widget)->SetPadding(*Properties.Padding);
    }
    if (Properties.Enabled) Widget->SetIsEnabled(*Properties.Enabled);
    if (Properties.Variable) Widget->bIsVariable = *Properties.Variable;
    if (Properties.Visibility) Widget->SetVisibility(*Properties.Visibility);
    if (Properties.Opacity) Widget->SetRenderOpacity(*Properties.Opacity);
    if (auto* Slot = Cast<UCanvasPanelSlot>(Widget->Slot))
    {
        Slot->Modify();
        if (Properties.Position) Slot->SetPosition(*Properties.Position);
        if (Properties.Size) Slot->SetSize(*Properties.Size);
        if (Properties.Alignment) Slot->SetAlignment(*Properties.Alignment);
    }
}

static UWidgetBlueprint* CreateBlueprintFromSpec(const FString& PackageName, const FString& Path)
{
    TSharedPtr<FJsonObject> Json;
    const TArray<TSharedPtr<FJsonValue>>* Widgets = nullptr;
    if (!ReadAuthoringJson(Path, Json) || Json->Values.Num() != 1 ||
        !Json->TryGetArrayField(TEXT("widgets"), Widgets) || Widgets->IsEmpty() || Widgets->Num() > 512)
    { AuthoringError(TEXT("Spec requires 1..512 widgets")); return nullptr; }
    struct FSpec { FName Name; FName Parent; UClass* Class; FWidgetProperties Properties; };
    TArray<FSpec> Specs;
    TMap<FName, UClass*> Classes;
    TMap<FName, int32> ChildCounts;
    for (const auto& Entry : *Widgets)
    {
        if (!Entry || Entry->Type != EJson::Object) return nullptr;
        const auto& Object = Entry->AsObject();
        FString Name, Type, Parent;
        if (!Object->TryGetStringField(TEXT("name"), Name) || Name.IsEmpty() ||
            !FName::IsValidXName(Name, INVALID_OBJECTNAME_CHARACTERS) ||
            !Object->TryGetStringField(TEXT("type"), Type)) return nullptr;
        FSpec Item{FName(*Name), NAME_None, SupportedWidgetClass(Type), {}};
        if (!Item.Class || Item.Name.IsNone() || Classes.Contains(Item.Name)) return nullptr;
        const bool HasParent = Object->TryGetStringField(TEXT("parent"), Parent);
        if (Specs.IsEmpty())
        {
            if (HasParent || Item.Class != UCanvasPanel::StaticClass()) return nullptr;
        }
        else
        {
            if (!HasParent || Parent.IsEmpty()) return nullptr;
            Item.Parent = FName(*Parent);
            UClass** ParentClass = Classes.Find(Item.Parent);
            if (!ParentClass || !(*ParentClass)->IsChildOf(UPanelWidget::StaticClass())) return nullptr;
            if (*ParentClass != UCanvasPanel::StaticClass() && ++ChildCounts.FindOrAdd(Item.Parent) > 1) return nullptr;
        }
        const bool CanvasSlot = !Item.Parent.IsNone() && Classes[Item.Parent] == UCanvasPanel::StaticClass();
        if (!ValidateWidgetProperties(Object, Item.Class, CanvasSlot, true, Item.Properties)) return nullptr;
        Classes.Add(Item.Name, Item.Class); Specs.Add(MoveTemp(Item));
    }
    UPackage* Package = CreatePackage(*PackageName);
    auto* Blueprint = CastChecked<UWidgetBlueprint>(FKismetEditorUtilities::CreateBlueprint(
        UUserWidget::StaticClass(), Package, FName(*FPackageName::GetLongPackageAssetName(PackageName)),
        BPTYPE_Normal, UWidgetBlueprint::StaticClass(), UWidgetBlueprintGeneratedClass::StaticClass(),
        TEXT("RiveUmgBlueprintWorker")));
    if (!Blueprint->WidgetTree) Blueprint->WidgetTree = NewObject<UWidgetTree>(Blueprint, TEXT("WidgetTree"), RF_Transactional);
    Blueprint->bCanCallInitializedWithoutPlayerContext = true;
    TMap<FName, UWidget*> Created;
    for (const FSpec& Spec : Specs)
    {
        UWidget* Widget = Blueprint->WidgetTree->ConstructWidget<UWidget>(Spec.Class, Spec.Name);
        if (Spec.Parent.IsNone()) Blueprint->WidgetTree->RootWidget = Widget;
        else if (auto* Canvas = Cast<UCanvasPanel>(Created[Spec.Parent])) Place(Canvas, Widget, {0, 0}, {100, 30});
        else CastChecked<UPanelWidget>(Created[Spec.Parent])->AddChild(Widget);
        ApplyWidgetProperties(Widget, Spec.Properties);
        Created.Add(Spec.Name, Widget);
    }
    FBlueprintEditorUtils::MarkBlueprintAsStructurallyModified(Blueprint);
    return CompileBlueprint(Blueprint) ? Blueprint : nullptr;
}
