// Native source Texture2D assets and typed Slate brushes. No transient image
// substitution: SavePackage persists the source, and reload uses UE's texture build.
static UTexture2D* LoadBrushTexture(const FString& Path)
{
    FString Package = Path, Object;
    if (Path.Split(TEXT("."), &Package, &Object) && Object != FPackageName::GetLongPackageAssetName(Package))
    { AuthoringError(TEXT("Texture object name must match its package: ") + Path); return nullptr; }
    if ((!Package.StartsWith(TEXT("/Game/")) && !Package.StartsWith(TEXT("/Engine/"))) ||
        !FPackageName::IsValidLongPackageName(Package) || Package.Contains(TEXT("..")) ||
        !FPackageName::DoesPackageExist(Package))
    { AuthoringError(TEXT("Texture package is missing or invalid: ") + Path); return nullptr; }
    auto* Texture = LoadObject<UTexture2D>(nullptr, *(Package + TEXT(".") + FPackageName::GetLongPackageAssetName(Package)));
    if (!Texture) AuthoringError(TEXT("Expected a Texture2D: ") + Path);
    GWorkerTextureObjectsCreated |= Texture != nullptr;
    return Texture;
}

static TSharedRef<FJsonObject> DescribeTexture(UTexture2D* Texture)
{
    GWorkerTextureObjectsCreated = true;
    auto Entry = MakeShared<FJsonObject>();
    Entry->SetStringField(TEXT("asset"), Texture->GetPathName());
    Entry->SetStringField(TEXT("package"), Texture->GetOutermost()->GetName());
    Entry->SetStringField(TEXT("asset_class"), Texture->GetClass()->GetPathName());
    Entry->SetBoolField(TEXT("source_texture"), Texture->Source.IsValid());
    Entry->SetBoolField(TEXT("cooked"), Texture->GetOutermost()->HasAnyPackageFlags(PKG_Cooked));
    Entry->SetNumberField(TEXT("width"), Texture->Source.GetSizeX());
    Entry->SetNumberField(TEXT("height"), Texture->Source.GetSizeY());
    Entry->SetNumberField(TEXT("source_mips"), Texture->Source.GetNumMips());
    Entry->SetBoolField(TEXT("srgb"), Texture->SRGB);
    Entry->SetBoolField(TEXT("never_stream"), Texture->NeverStream);
    Entry->SetStringField(TEXT("filter"), Texture->Filter == TF_Nearest ? TEXT("nearest") :
        Texture->Filter == TF_Bilinear ? TEXT("linear") : TEXT("other"));
    Entry->SetNumberField(TEXT("compression_settings"), int32(Texture->CompressionSettings));
    Entry->SetStringField(TEXT("compression"), Texture->CompressionSettings == TC_EditorIcon ? TEXT("ui") :
        Texture->CompressionSettings == TC_Default ? TEXT("default") : TEXT("other"));
    return Entry;
}

static UTexture2D* ImportTextureAsset(const FString& PackageName, const FString& Input,
    bool SRGB, const FString& Filter, bool Replace, bool DefaultCompression)
{
    const FString Filename = FPackageName::LongPackageNameToFilename(PackageName, FPackageName::GetAssetPackageExtension());
    const bool Exists = IFileManager::Get().FileExists(*Filename);
    if ((Exists && !Replace) || (Filter != TEXT("nearest") && Filter != TEXT("linear")))
    { AuthoringError(TEXT("Texture exists without explicit replace, or invalid filter")); return nullptr; }
    const int64 InputBytes = IFileManager::Get().FileSize(*Input);
    if (InputBytes <= 0 || InputBytes > 64 * 1024 * 1024)
    { AuthoringError(TEXT("PNG/JPEG input must be 1..64 MiB")); return nullptr; }
    TArray64<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *Input)) return nullptr;
    auto& Module = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    const EImageFormat Format = Module.DetectImageFormat(Bytes.GetData(), Bytes.Num());
    if (Format != EImageFormat::PNG && Format != EImageFormat::JPEG)
    { AuthoringError(TEXT("Texture import supports PNG and JPEG")); return nullptr; }
    auto Decoder = Module.CreateImageWrapper(Format);
    if (!Decoder || !Decoder->SetCompressed(Bytes.GetData(), Bytes.Num()) ||
        Decoder->GetWidth() < 1 || Decoder->GetHeight() < 1 || Decoder->GetWidth() > 4096 || Decoder->GetHeight() > 4096)
    { AuthoringError(TEXT("Invalid image or dimensions outside 1..4096")); return nullptr; }
    FImage Decoded, BGRA;
    if (!Decoder->GetRawImage(Decoded))
    { AuthoringError(TEXT("Image decode failed")); return nullptr; }
    // Preserve 8-bit sample values; --linear chooses sampling interpretation,
    // rather than applying an extra colour transform to the imported bytes.
    Decoded.CopyTo(BGRA, ERawImageFormat::BGRA8, Decoded.GammaSpace);
    UTexture2D* Texture = Exists ? LoadBrushTexture(PackageName) : NewObject<UTexture2D>(
        CreatePackage(*PackageName), FName(*FPackageName::GetLongPackageAssetName(PackageName)), RF_Public | RF_Standalone);
    if (!Texture) return nullptr;
    GWorkerTextureObjectsCreated = true;
    Texture->Modify();
    Texture->Source.Init(BGRA.SizeX, BGRA.SizeY, 1, 1, TSF_BGRA8, BGRA.RawData.GetData());
    Texture->SRGB = SRGB;
    Texture->CompressionSettings = DefaultCompression ? TC_Default : TC_EditorIcon;
    Texture->LODGroup = TEXTUREGROUP_UI;
    Texture->MipGenSettings = TMGS_NoMipmaps;
    Texture->NeverStream = true;
    Texture->Filter = Filter == TEXT("nearest") ? TF_Nearest : TF_Bilinear;
    Texture->MarkPackageDirty();
    IFileManager::Get().MakeDirectory(*FPaths::GetPath(Filename), true);
    FSavePackageArgs Args;
    Args.TopLevelFlags = RF_Public | RF_Standalone;
    Args.SaveFlags = SAVE_NoError;
    Args.bSlowTask = false;
    if (!UPackage::SavePackage(Texture->GetOutermost(), Texture, *Filename, Args)) return nullptr;
    UE_LOGF(LogUmgBlueprintWorker, Display, "UMG_TEXTURE_SAVE path=%ls width=%d height=%d srgb=%d",
        *Filename, BGRA.SizeX, BGRA.SizeY, SRGB);
    return Texture;
}

static const FSlateBrush* GetWidgetTextureBrush(UWidget* Widget)
{
    if (auto* Image = Cast<UImage>(Widget)) return &Image->GetBrush();
    if (auto* Border = Cast<UBorder>(Widget)) return &Border->Background;
    return nullptr;
}

static bool ReadTextureBrush(const TSharedPtr<FJsonObject>& Json, FSlateBrush& Brush)
{
    if (Json->Values.IsEmpty()) return AuthoringError(TEXT("Empty brush edit"));
    for (const auto& Pair : Json->Values)
    {
        const FString Key(Pair.Key);
        const auto& Value = Pair.Value;
        if (Key == TEXT("texture"))
        {
            if (Value->Type == EJson::Null) Brush.SetResourceObject(nullptr);
            else if (Value->Type == EJson::String)
            {
                UTexture2D* Texture = LoadBrushTexture(Value->AsString());
                if (!Texture) return false;
                Brush.SetResourceObject(Texture);
                Brush.ImageType = Texture->SRGB ? ESlateBrushImageType::FullColor : ESlateBrushImageType::Linear;
                if (!Json->HasField(TEXT("image_size")))
                    Brush.ImageSize = FVector2D(Texture->Source.GetSizeX(), Texture->Source.GetSizeY());
            }
            else return AuthoringError(TEXT("brush.texture must be a package/object path or null"));
        }
        else if (Key == TEXT("image_size"))
        {
            FVector2D Size;
            if (!ParseVector(Value, Size) || Size.X <= 0 || Size.Y <= 0 || Size.X > 4096 || Size.Y > 4096)
                return AuthoringError(TEXT("Invalid brush.image_size"));
            Brush.ImageSize = Size;
        }
        else if (Key == TEXT("tint") || Key == TEXT("margin"))
        {
            TArray<double> Numbers;
            if (!NumberArray(Value, 4, Numbers) || !Algo::AllOf(Numbers, [](double N) { return N >= 0 && N <= 1; }))
                return AuthoringError(TEXT("Brush tint/margin requires four values in 0..1"));
            if (Key == TEXT("tint")) Brush.TintColor = FLinearColor(Numbers[0], Numbers[1], Numbers[2], Numbers[3]);
            else Brush.Margin = FMargin(Numbers[0], Numbers[1], Numbers[2], Numbers[3]);
        }
        else if (Key == TEXT("draw_as") && Value->Type == EJson::String)
        {
            const FString S = Value->AsString();
            if (S == TEXT("Image")) Brush.DrawAs = ESlateBrushDrawType::Image;
            else if (S == TEXT("Box")) Brush.DrawAs = ESlateBrushDrawType::Box;
            else if (S == TEXT("Border")) Brush.DrawAs = ESlateBrushDrawType::Border;
            else if (S == TEXT("NoDrawType")) Brush.DrawAs = ESlateBrushDrawType::NoDrawType;
            else return AuthoringError(TEXT("Unsupported brush.draw_as"));
        }
        else if (Key == TEXT("tiling") && Value->Type == EJson::String)
        {
            const FString S = Value->AsString();
            if (S == TEXT("NoTile")) Brush.Tiling = ESlateBrushTileType::NoTile;
            else if (S == TEXT("Horizontal")) Brush.Tiling = ESlateBrushTileType::Horizontal;
            else if (S == TEXT("Vertical")) Brush.Tiling = ESlateBrushTileType::Vertical;
            else if (S == TEXT("Both")) Brush.Tiling = ESlateBrushTileType::Both;
            else return AuthoringError(TEXT("Unsupported brush.tiling"));
        }
        else return AuthoringError(TEXT("Unsupported brush property/value: ") + Key);
    }
    return true;
}

static TSharedRef<FJsonObject> DescribeTextureBrush(const FSlateBrush& Brush)
{
    auto Entry = MakeShared<FJsonObject>();
    UObject* Resource = Brush.GetResourceObject();
    if (auto* Texture = Cast<UTexture2D>(Resource))
    {
        GWorkerTextureObjectsCreated = true;
        Entry->SetStringField(TEXT("texture"), Texture->GetPathName());
    }
    else Entry->SetField(TEXT("texture"), MakeShared<FJsonValueNull>());
    Entry->SetStringField(TEXT("resource_class"), Resource ? Resource->GetClass()->GetPathName() : TEXT("None"));
    Entry->SetStringField(TEXT("resource_path"), GetPathNameSafe(Resource));
    Entry->SetStringField(TEXT("resource_name"), Brush.GetResourceName().ToString());
    Entry->SetArrayField(TEXT("image_size"), VectorJson(Brush.ImageSize));
    Entry->SetArrayField(TEXT("tint"), ColorJson(Brush.TintColor.GetSpecifiedColor()));
    Entry->SetArrayField(TEXT("margin"), {MakeShared<FJsonValueNumber>(Brush.Margin.Left), MakeShared<FJsonValueNumber>(Brush.Margin.Top),
        MakeShared<FJsonValueNumber>(Brush.Margin.Right), MakeShared<FJsonValueNumber>(Brush.Margin.Bottom)});
    Entry->SetStringField(TEXT("draw_as"), Brush.DrawAs == ESlateBrushDrawType::Image ? TEXT("Image") :
        Brush.DrawAs == ESlateBrushDrawType::Box ? TEXT("Box") : Brush.DrawAs == ESlateBrushDrawType::Border ? TEXT("Border") :
        Brush.DrawAs == ESlateBrushDrawType::NoDrawType ? TEXT("NoDrawType") : TEXT("Other"));
    Entry->SetStringField(TEXT("tiling"), Brush.Tiling == ESlateBrushTileType::NoTile ? TEXT("NoTile") :
        Brush.Tiling == ESlateBrushTileType::Horizontal ? TEXT("Horizontal") :
        Brush.Tiling == ESlateBrushTileType::Vertical ? TEXT("Vertical") : TEXT("Both"));
    return Entry;
}
