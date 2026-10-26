// Native core bootstrap derived from the isolated canonical shader cooker.
// Asset-only operations use native NullRHI; captures explicitly use real Vulkan.
static void CreateReferencePool(FQueuedThreadPool*& Pool, int32 Threads, EThreadPriority Priority, const TCHAR* Name)
{
    Pool = FQueuedThreadPool::Allocate();
    verify(Pool->Create(Threads, 1024 * 1024, Priority, Name));
}

static void BootstrapWorkerCore(bool AssetOnly)
{
    GGameThreadId = FPlatformTLS::GetCurrentThreadId();
    GIsGameThreadIdInitialized = true;
    FApp::SetProjectName(TEXT("UmgBlueprintWorker"));
    GIsClient = !AssetOnly;
    GIsEditor = true;
    PRIVATE_GIsRunningCommandlet = true;
    PRIVATE_GIsRunningCookCommandlet = false;
    PRIVATE_GAllowCommandletRendering = !AssetOnly;
    GUsingNullRHI = AssetOnly;
    GIsServer = false;
    FPlatformMisc::PlatformPreInit();
    FPlatformApplicationMisc::PreInit();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::StartOfEnginePreInit);

    GError = FPlatformApplicationMisc::GetErrorOutputDevice();
    GWarn = FPlatformApplicationMisc::GetFeedbackContext();
    FPlatformOutputDevices::SetupOutputDevices();
#if UE_ALLOW_ENGINE_STDIO_OUTPUT
    GWorkerStdOut = MakeUnique<FOutputDeviceStdOutput>();
    GLog->AddOutputDevice(GWorkerStdOut.Get());
#endif
    if (!FIoDispatcher::IsInitialized())
    {
        const FIoStatus Status = FIoDispatcher::Initialize();
        if (!Status.IsOk())
            UE_LOGF(LogUmgBlueprintWorker, Fatal, "Real I/O dispatcher initialization failed: %ls", *Status.ToString());
    }
    FPlatformFileManager::Get().InitializeNewAsyncIO();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::FileSystemReady);
    FTaskGraphInterface::Startup(4);
    FTaskGraphInterface::Get().AttachToThread(ENamedThreads::GameThread);
    CreateReferencePool(GIOThreadPool, 2, TPri_AboveNormal, TEXT("ReferenceIO"));
    GLargeThreadPool = new FQueuedLowLevelThreadPool();
    GThreadPool = new FQueuedThreadPoolWrapper(GLargeThreadPool, 4);
    CreateReferencePool(GBackgroundPriorityThreadPool, 1, TPri_Lowest, TEXT("ReferenceBackground"));
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::TaskGraphSystemReady);
#if STATS
    FThreadStats::StartThread();
#endif
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::StatSystemReady);
    RegisterModularObjectsProcessing();
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("CoreUObject"));
    InitializeRenderingCVarsCaching();
    FConfigCacheIni::InitializeConfigSystem();
    FCoreDelegates::OnInit.Broadcast();
    for (const TCHAR* Section : {
        TEXT("/Script/Engine.RendererSettings"),
        TEXT("/Script/Engine.RendererOverrideSettings"),
        TEXT("/Script/Engine.StreamingSettings"),
        TEXT("/Script/Engine.GarbageCollectionSettings"),
        TEXT("/Script/Engine.NetworkSettings"),
        TEXT("/Script/UnrealEd.CookerSettings")})
        UE::ConfigUtilities::ApplyCVarSettingsFromIni(Section, *GEngineIni, ECVF_SetByProjectSetting);
    Scalability::InitScalabilitySystem();
#if UE_WITH_CONSTINIT_UOBJECT
    UE::CoreUObject::ConstructCompiledInObjects();
#endif
    UDeviceProfileManager::InitializeCVarsForActiveDeviceProfile();
    Scalability::LoadState(GGameUserSettingsIni);
    FConfigCacheIni::LoadConsoleVariablesFromINI();
    FDelayedAutoRegisterHelper::RunAndClearDelayedAutoRegisterDelegates(EDelayedRegisterRunPhase::IniSystemReady);
    FIoDispatcher::InitializePostSettings();
    FPlatformMisc::PlatformInit();
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("Engine"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("Renderer"));
    FModuleManager::LoadModuleChecked<IModuleInterface>(TEXT("RenderCore"));
    FPackageLocalizationManager::Get().InitializeFromLazyCallback([](FPackageLocalizationManager& Manager)
    {
        Manager.InitializeFromCache(MakeShareable(new FEnginePackageLocalizationCache()));
    });
    FPackageName::RegisterShortPackageNamesForUObjectModules();
    IPackageResourceManager::Initialize();

    GIsRunning = true;
}
