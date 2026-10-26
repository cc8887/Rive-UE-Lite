// Copyright Epic Games, Inc. All Rights Reserved.

#include "EventLoop.h"
#include "AutoRTFM.h"
#include "Containers/Queue.h"
#include "Misc/AssertionMacros.h"
#include "Misc/Optional.h"
#include "Templates/UnrealTemplate.h"
#include "UObject/GarbageCollection.h"
#include "UObject/ReachabilityAnalysis.h"
#include "UObject/UObjectArray.h"

static TQueue<TFunction<void(const verse::FExecutionContext&)>> EnqueuedAsyncJobs;
static TOptional<VerseCmd::FEventLoopExit> PendingExit;

void VerseCmd::ExitEventLoop(VerseCmd::FEventLoopExit Reason)
{
    checkf(!PendingExit.IsSet(),
           TEXT("Expected ExitEventLoop to be called at most once, but there is already a pending exit."));
    PendingExit.Emplace(MoveTemp(Reason));
}

void VerseCmd::EnqueueAsyncJob(TFunction<void(const verse::FExecutionContext&)>&& JobThunk)
{
    AutoRTFM::OnCommit(
        [JobThunk = MoveTemp(JobThunk)]() mutable { verify(EnqueuedAsyncJobs.Enqueue(MoveTemp(JobThunk))); });
}

AUTORTFM_DISABLE static void TickGC()
{
    const int32 ObjectArrayFreeSlots = GUObjectArray.GetObjectArrayEstimatedAvailable();

    if (IsIncrementalReachabilityAnalysisPending())
    {
        PerformIncrementalReachabilityAnalysis(GetReachabilityAnalysisTimeLimit());
    }
    else if (IsIncrementalPurgePending())
    {
        IncrementalPurgeGarbage(true);
    }
    else if (ObjectArrayFreeSlots < 10000 || UE::GC::ShouldFrankenGCRun())
    {
        CollectGarbage(GARBAGE_COLLECTION_KEEPFLAGS, /*bPerformFullPurge*/ false);
    }
}

AUTORTFM_DISABLE VerseCmd::FEventLoopExit VerseCmd::RunEventLoop(const verse::FExecutionContext& ExecContext)
{
    check(!PendingExit.IsSet()); // Assume RunEventLoop will be called at most once.

    TFunction<void(const verse::FExecutionContext&)> JobThunk;
    while (EnqueuedAsyncJobs.Dequeue(JobThunk))
    {
        if (!PendingExit.IsSet())
        {
            TickGC();

            JobThunk(ExecContext);
        }
    }

    if (!ensureMsgf(PendingExit.IsSet(), TEXT("Job queue was drained without an exit reason being triggered.")))
    {
        return VerseCmd::FEventLoopExit::Error();
    }

    return *PendingExit;
}
