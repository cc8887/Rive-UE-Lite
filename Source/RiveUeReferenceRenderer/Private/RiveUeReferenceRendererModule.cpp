#include "RiveUeReferenceRenderer.h"
#include "Modules/ModuleManager.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"

void RegisterRiveUeReferenceShaderDirectory(const FString& Directory)
{
    checkf(FPaths::DirectoryExists(Directory), TEXT("Missing shared Rive shader directory: %s"), *Directory);
    AddShaderSourceDirectoryMapping(TEXT("/Plugin/Rive"), FPaths::ConvertRelativePathToFull(Directory));
}

IMPLEMENT_MODULE(FDefaultModuleImpl, RiveUeReferenceRenderer)
