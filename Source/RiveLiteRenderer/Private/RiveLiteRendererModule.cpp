#include "RiveLiteRenderer.h"
#include "Modules/ModuleManager.h"
#include "Misc/Paths.h"
#include "ShaderCore.h"

void RegisterRiveLiteShaderDirectory(const FString& Directory)
{
    checkf(FPaths::DirectoryExists(Directory), TEXT("RiveLite shader directory does not exist: %s"), *Directory);
    AddShaderSourceDirectoryMapping(TEXT("/Plugin/Rive"), FPaths::ConvertRelativePathToFull(Directory));
}

IMPLEMENT_MODULE(FDefaultModuleImpl, RiveLiteRenderer)
