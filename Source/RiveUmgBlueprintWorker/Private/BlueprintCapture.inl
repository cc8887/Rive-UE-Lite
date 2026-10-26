class FBlueprintNativeTarget final : public FRenderTarget
{
public:
    explicit FBlueprintNativeTarget(FTextureRHIRef InTexture) : Texture(MoveTemp(InTexture)) {}
    using FRenderTarget::GetRenderTargetTexture;
    const FTextureRHIRef& GetRenderTargetTexture() const override { return Texture; }
    FIntPoint GetSizeXY() const override { return Texture->GetDesc().Extent; }
private:
    FTextureRHIRef Texture;
};

static bool InitializeRenderer(const FString& ShaderArchive)
{
    if (FSlateApplication::IsInitialized()) FSlateApplication::Shutdown();
    AddShaderSourceDirectoryMapping(TEXT("/Engine"), FPlatformProcess::ShaderDir());
    const FString Autogen = FPaths::ConvertRelativePathToFull(FPaths::ProjectIntermediateDir() / TEXT("ShaderAutogen"));
    IFileManager::Get().MakeDirectory(*Autogen, true);
    AddShaderSourceDirectoryMapping(TEXT("/ShaderAutogen"), Autogen);
    FGenericDataDrivenShaderPlatformInfo::Initialize();
    FShaderParametersMetadataRegistration::CommitAll();
    FShaderTypeRegistration::CommitAll();
    FShaderParametersMetadata::InitializeAllUniformBufferStructs();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::PreRHIInit);
    RHIInit(false);
    if (GUsingNullRHI) return false;
    PipelineStateCache::Init();
    RenderUtilsInit();
    // Editor shader-type setup requires the native source/include hash cache,
    // even when all actual shader bytecode comes from a precompiled archive.
    InitializeShaderHashCache();
    InitializeShaderTypes();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::ShaderTypesReady);
    TArray<uint8> Bytes;
    if (!FFileHelper::LoadFileToArray(Bytes, *ShaderArchive)) return false;
    FShaderCodeLibrary::InitForRuntime(GMaxRHIShaderPlatform);
    FMemoryReader Reader(Bytes);
    GGlobalShaderMap[GMaxRHIShaderPlatform] = new FGlobalShaderMap(GMaxRHIShaderPlatform);
    GGlobalShaderMap[GMaxRHIShaderPlatform]->LoadFromGlobalArchive(Reader);
    if (Reader.IsError()) return false;
    GGlobalShaderMap[GMaxRHIShaderPlatform]->BeginCreateAllShaders();
    TArray<uint32> PixelBytes;
    for (int32 Index = 0; Index < PF_MAX; ++Index) PixelBytes.Add(GPixelFormats[Index].BlockBytes);
    RHIPostInit(PixelBytes);
    InitRenderingThread();
    auto& SlateModule = FModuleManager::LoadModuleChecked<ISlateRHIRendererModule>(TEXT("SlateRHIRenderer"));
    FSlateApplication::InitializeAsStandaloneApplication(SlateModule.CreateSlateRHIRenderer(),
        MakeShared<GenericApplication>(TSharedPtr<ICursor>()));
    return true;
}

static bool RenderBlueprint(UWidgetBlueprint* Blueprint, const FString& Output, FIntPoint Size,
    TSharedRef<FJsonObject>& Metadata)
{
    TStrongObjectPtr<UWidgetTree> Owner(NewObject<UWidgetTree>());
    const bool NativeDesignerReference = FParse::Param(FCommandLine::Get(), TEXT("NativeDesignerReference"));
    TStrongObjectPtr<UUserWidget> Instance;
    if (NativeDesignerReference)
    {
        // Same native source-tree preview API used in UWidgetBlueprint's
        // DetectSlateWidgetLeaks. This independent path reads the source tree,
        // whereas the normal path instantiates the compiled generated class.
        Instance.Reset(NewObject<UUserWidget>(Owner.Get(), Blueprint->GeneratedClass));
        Instance->ClearFlags(RF_Transactional);
        Instance->SetDesignerFlags(EWidgetDesignFlags::Designing);
        Instance->DuplicateAndInitializeFromWidgetTree(Blueprint->WidgetTree, TMap<FName, UWidget*>());
    }
    else
    {
        Instance.Reset(UUserWidget::CreateWidgetInstance(*Owner,
            TSubclassOf<UUserWidget>(Blueprint->GeneratedClass), TEXT("SourceAssetPreview")));
    }
    if (!Instance.IsValid() || !Instance->WidgetTree || !Instance->WidgetTree->RootWidget) return false;
    Instance->SetDesignerFlags(EWidgetDesignFlags::Designing);
    // Keep the real Slate tree alive through geometry inspection. UWidget only
    // keeps weak references; DrawWidget's temporary virtual window is released.
    const TSharedRef<SWidget> SlateWidget = Instance->TakeWidget();
    FTextureRHIRef Texture;
    ENQUEUE_RENDER_COMMAND(CreateBlueprintOutput)([&](FRHICommandListImmediate& Cmd)
    {
        Texture = Cmd.CreateTexture(FRHITextureCreateDesc::Create2D(TEXT("BlueprintOutput"), Size.X, Size.Y, PF_R8G8B8A8)
            .SetFlags(ETextureCreateFlags::RenderTargetable | ETextureCreateFlags::ShaderResource | ETextureCreateFlags::UAV)
            .SetInitialState(ERHIAccess::RTV).SetClearValue(FClearValueBinding(FLinearColor::Transparent)));
    });
    FlushRenderingCommands();
    FBlueprintNativeTarget Target(Texture);
    {
        FWidgetRenderer Renderer(false, true);
        Renderer.DrawWidget(&Target, SlateWidget, FVector2D(Size.X, Size.Y), 0.f, false);
        FlushRenderingCommands();
    }
    Metadata = DescribeBlueprint(Blueprint, Instance.Get());
    Metadata->SetArrayField(TEXT("viewport_size"), VectorJson(FVector2D(Size.X, Size.Y)));
    Metadata->SetNumberField(TEXT("dpi_scale"), 1.0);
    Metadata->SetStringField(TEXT("target_format"), TEXT("linear RGBA8, one sample"));
    Metadata->SetStringField(TEXT("preview_path"), NativeDesignerReference ?
        TEXT("UE native source WidgetTree designer preview") : TEXT("UE compiled WidgetBlueprintGeneratedClass instance"));
    TArray<FColor> Pixels;
    ENQUEUE_RENDER_COMMAND(ReadBlueprintOutput)([&](FRHICommandListImmediate& Cmd)
    {
        Cmd.Transition(FRHITransitionInfo(Texture, ERHIAccess::Unknown, ERHIAccess::CopySrc));
        FReadSurfaceDataFlags Flags(RCM_UNorm);
        Flags.SetLinearToGamma(false);
        Cmd.ReadSurfaceData(Texture, FIntRect(FIntPoint::ZeroValue, Size), Pixels, Flags);
        Cmd.SubmitAndBlockUntilGPUIdle();
    });
    FlushRenderingCommands();
    Instance->ReleaseSlateResources(true);
    FlushRenderingCommands();
    if (Pixels.Num() != Size.X * Size.Y) return false;
    auto& ImageModule = FModuleManager::LoadModuleChecked<IImageWrapperModule>(TEXT("ImageWrapper"));
    TArray64<uint8> PNG;
    return ImageModule.CompressImage(PNG, EImageFormat::PNG,
        FImageView(Pixels.GetData(), Size.X, Size.Y, EGammaSpace::Linear)) &&
        FFileHelper::SaveArrayToFile(PNG, *Output);
}
