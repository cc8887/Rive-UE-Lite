// Copyright Epic Games, Inc. All Rights Reserved.

#include "AutoRTFM.h"
#include "Containers/Array.h"
#include "Containers/Utf8String.h"
#include "EventLoop.h"
#include "GenericPlatform/GenericPlatformMisc.h"
#include "IOErrors.h"
#include "Misc/FileHelper.h"
#include "Misc/Paths.h"
#include "Result.h"
#include "Templates/Function.h"
#include "VerseString.h"
#include "VerseVM/VVMContentScope.h"
#include "VerseVM/VVMCoroutine.h"
#include "VerseVM/VVMExecutionContext.h"
#include "VerseValue.h"
#include <cstdint>
#include <errno.h>
#include <type_traits>

#include "Verse.access_error.gen.ipp"
#include "Verse.io_error.gen.ipp"
#include "Verse.not_found_error.gen.ipp"
#include "RiveVerseWorker.gen.h"
#include "RiveVerseWorker.gen.ipp"

namespace {

template <typename ResultType>
FVerseResult SuspendAndEnqueueThunk(TVerseCall<ResultType> Call,
                                    TFunction<void(const verse::FExecutionContext&)>&& Function)
{
    VerseCmd::EnqueueAsyncJob(MoveTemp(Function));
    return Call.Suspend(verse::FExecutionContext::GetActiveContext());
}

template <typename ResultType, typename... ArgTypes>
TFunction<void(const verse::FExecutionContext&)> MakeReturningThunk(TVerseCall<ResultType> Call,
                                                                    ResultType (*Function)(ArgTypes...),
                                                                    std::type_identity_t<ArgTypes>&&... Args)
{
    TStrongVerseCall<ResultType> StrongCall = Call;
    return [StrongCall, Function, ... Args = Forward<ArgTypes>(Args)](const verse::FExecutionContext& Context) {
        FVerseResult ReturnResult{FVerseResult::EKind::Error};
        if constexpr (std::is_same_v<ResultType, void>)
        {
            Function(Forward<ArgTypes>(Args)...);
            ReturnResult = StrongCall.Return(Context);
        }
        else
        {
            ReturnResult = StrongCall.Return(Context, Function(Forward<ArgTypes>(Args)...));
        }
        if (ReturnResult.IsError())
        {
            VerseCmd::ExitEventLoop(VerseCmd::FEventLoopExit::Error());
        }
    };
}

template <typename IOErrorType> static TInterfaceInstance<verse::result> MakeIOError()
{
    IOErrorType* IOError =
        NewObject<IOErrorType>(verse::GetInstantiationOuter(), NAME_None, verse::GetInstantiationFlags());
    return TInterfaceInstance<verse::result>(TNonNullPtr<UObject>(verse::error_result::New(FVerseValue(IOError))));
}

static TInterfaceInstance<verse::result> MakeIOErrorFromErrno(int ErrorNumber)
{
    switch (ErrorNumber)
    {
    case ENOENT:
        return MakeIOError<verse::not_found_error>();
    case EACCES:
        return MakeIOError<verse::access_error>();
    default:
        return MakeIOError<verse::io_error>();
    };
}

// UE changes the process CWD to the engine base dir on init, so resolve
// relative paths against the original launch directory.
static FString ResolveFilePath(const verse::string& Filename)
{
    FString Path(Filename);
    if (FPaths::IsRelative(Path))
    {
        Path = FPaths::Combine(FPlatformMisc::LaunchDir(), Path);
    }
    return Path;
}

static FILE* OpenFile(const verse::string& Filename, const char* Mode)
{
    FString ResolvedPath = ResolveFilePath(Filename);
#ifdef _WIN32
    return _wfopen(*ResolvedPath, ANSI_TO_TCHAR(Mode));
#else
    return fopen(TCHAR_TO_UTF8(*ResolvedPath), Mode);
#endif
}

static TInterfaceInstance<verse::result> LoadTextFileSync(const verse::string& Filename)
{
    FILE* File = OpenFile(Filename, "rb");
    if (!File)
    {
        return MakeIOErrorFromErrno(errno);
    }

    if (fseek(File, 0, SEEK_END))
    {
        fclose(File);
        return MakeIOError<verse::io_error>();
    }

    const long TellResult = ftell(File);
    if (TellResult < 0)
    {
        fclose(File);
        return MakeIOError<verse::io_error>();
    }
    const size_t NumBytesInFile = static_cast<size_t>(TellResult);

    if (fseek(File, 0, SEEK_SET))
    {
        fclose(File);
        return MakeIOError<verse::io_error>();
    }

    TArray<char8_t> Contents;
    Contents.AddDefaulted(IntCastChecked<int32>(NumBytesInFile));

    size_t NumBytesRead = fread(Contents.GetData(), 1, NumBytesInFile, File);
    if (NumBytesRead != NumBytesInFile)
    {
        fclose(File);
        return MakeIOError<verse::io_error>();
    }

    fclose(File);

    return TInterfaceInstance<verse::result>(
        TNonNullPtr<UObject>(verse::success_result::New(FVerseValue(::Verse::FNativeString(Contents)))));
}

static TInterfaceInstance<verse::result> SaveTextFileSync(const verse::string& Filename, const verse::string& Contents)
{
    FILE* File = OpenFile(Filename, "wb");
    if (!File)
    {
        return MakeIOErrorFromErrno(errno);
    }

    const size_t NumBytesToWrite = Contents.Len();
    size_t NumBytesWritten = fwrite(*Contents, 1, NumBytesToWrite, File);
    if (NumBytesWritten != NumBytesToWrite)
    {
        fclose(File);
        return MakeIOError<verse::io_error>();
    }

    fclose(File);

    return TInterfaceInstance<verse::result>(
        TNonNullPtr<UObject>(verse::success_result::New(FVerseValue(EVerseTrue::Value))));
}

static void PrintSync(const verse::string& Line)
{
    // Use fwrite, assume stdout is UTF-8, and ignore any errors.
    fwrite(*Line, 1, Line.Len(), stdout);
    fwrite("\n", 1, 1, stdout);
}

static TOptional<verse::string> InputLineSync()
{
    ::TArray<UTF8CHAR> Result;
    while (true)
    {
        // Make sure any buffered writes to stdout are flushed before we do a blocking read from stdin.
        fflush(stdout);

        const int Char = fgetc(stdin);
        if (Char == '\r')
        {
            continue;
        }
        if (Char == '\n' || (Char == EOF && Result.Num()))
        {
            return {verse::string(Result)};
        }
        else if (Char == EOF)
        {
            return {};
        }
        Result.Add(static_cast<UTF8CHAR>(Char));
    }
}

static void YieldSync() {}

} // End anonymous namespace

namespace verse {
namespace Verse {
FVerseResult LoadTextFile(TVerseCall<TInterfaceInstance<result>> Call, const string& Filename)
{
    return SuspendAndEnqueueThunk(Call, MakeReturningThunk(Call, LoadTextFileSync, Filename));
}

FVerseResult SaveTextFile(TVerseCall<TInterfaceInstance<result>> Call, const string& Filename, const string& Contents)
{
    return SuspendAndEnqueueThunk(Call, MakeReturningThunk(Call, SaveTextFileSync, Filename, Contents));
}

FVerseResult Print(TVerseCall<void> Call, const string& Line)
{
    return SuspendAndEnqueueThunk(Call, MakeReturningThunk(Call, PrintSync, Line));
}

FVerseResult InputLine(TVerseCall<::TOptional<string>> Call)
{
    return SuspendAndEnqueueThunk(Call, MakeReturningThunk(Call, InputLineSync));
}

FVerseResult Yield(TVerseCall<void> Call) { return SuspendAndEnqueueThunk(Call, MakeReturningThunk(Call, YieldSync)); }

FVerseResult Exit(TVerseCall<EVerseFalse> Call, int64 ExitCode)
{
    // We can't use MakeReturningThunk for Exit, because that assumes that the call should return after the thunk
    // executes.
    return SuspendAndEnqueueThunk(MoveTemp(Call), [ExitCode](const FExecutionContext&) {
        VerseCmd::ExitEventLoop(VerseCmd::FEventLoopExit::ExitCalled(ExitCode));
    });
}
}
}