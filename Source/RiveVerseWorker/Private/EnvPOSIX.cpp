// Copyright Epic Games, Inc. All Rights Reserved.

#if !PLATFORM_WINDOWS

    #include "Env.h"
    #include <cstring>

extern "C" char** environ;

TMap<verse::string, verse::string> VerseCmd::GetProcessEnvironment()
{
    TMap<verse::string, verse::string> Result;

    for (char** Entry = environ; *Entry != nullptr; ++Entry)
    {
        // Find the first '=' separator.
        const char* Equals = strchr(*Entry, '=');
        if (!Equals)
        {
            continue;
        }

        verse::string Key(FUtf8String::ConstructFromPtrSize(*Entry, UE_PTRDIFF_TO_INT32(Equals - *Entry)));
        verse::string Value(FUtf8String(Equals + 1));
        Result.Add(MoveTemp(Key), MoveTemp(Value));
    }

    return Result;
}

#endif
