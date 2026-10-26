// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "AutoRTFM.h"
#include "HAL/Platform.h"
#include "Templates/Function.h"
#include <cstdio>

namespace verse {
struct FExecutionContext;
}

namespace VerseCmd {
void EnqueueAsyncJob(TFunction<void(const verse::FExecutionContext&)>&& JobThunk);

struct FEventLoopExit
{
    enum class EReason
    {
        ExitCalled,
        ScriptCompleted,
        Error
    };
    EReason Reason{EReason::Error};
    int64 ExitCode{1};

    static constexpr FEventLoopExit ExitCalled(int64 ExitCode)
    {
        return {.Reason = EReason::ExitCalled, .ExitCode = ExitCode};
    }
    static constexpr FEventLoopExit ScriptCompleted() { return {.Reason = EReason::ScriptCompleted, .ExitCode = 0}; }
    static constexpr FEventLoopExit Error() { return {.Reason = EReason::Error, .ExitCode = 1}; }
};

void ExitEventLoop(FEventLoopExit Reason);

AUTORTFM_DISABLE FEventLoopExit RunEventLoop(const verse::FExecutionContext& ExecContext);
}