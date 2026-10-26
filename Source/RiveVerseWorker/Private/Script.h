// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "AutoRTFM.h"
#include "Containers/Array.h"
#include "Containers/UnrealString.h"
#include "Templates/SharedPointer.h"
#include "Templates/UnrealTemplate.h"
#include "VerseString.h"
#include "VerseVM/VVMNativeFunction.h"

namespace VerseCmd {
struct FEventLoopExit;

struct FMount
{
    FUtf8String VersePath;
    FUtf8String Directory;
};

struct FScript;

AUTORTFM_DISABLE TSharedPtr<FScript> BuildScript(const FUtf8String& ScriptFilePath, const TArray<FMount>& Mounts);

AUTORTFM_DISABLE FEventLoopExit RunScript(const TSharedPtr<FScript>& Script,
                                          const TArray<verse::string>& Args,
                                          const TMap<verse::string, verse::string>& Env);
}