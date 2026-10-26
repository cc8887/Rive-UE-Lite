// Copyright Epic Games, Inc. All Rights Reserved.

#if PLATFORM_WINDOWS

    #include "Env.h"

    #include "Windows/AllowWindowsPlatformTypes.h"

    #include <Windows.h>

    #include "Windows/HideWindowsPlatformTypes.h"

TMap<verse::string, verse::string> VerseCmd::GetProcessEnvironment()
{
    TMap<verse::string, verse::string> Result;

    LPWCH EnvBlock = GetEnvironmentStringsW();
    if (!EnvBlock)
    {
        return Result;
    }

    for (LPCWSTR Entry = EnvBlock; *Entry != L'\0'; Entry += wcslen(Entry) + 1)
    {
        // Find the first '=' separator. Skip entries where '=' is at position 0
        // (Windows has special env vars like "=C:=C:\").
        const WCHAR* Equals = wcschr(Entry, L'=');
        if (!Equals || Equals == Entry)
        {
            continue;
        }

        FString Key = FString::ConstructFromPtrSize(Entry, UE_PTRDIFF_TO_INT32(Equals - Entry));
        FString Value(Equals + 1);
        Result.Add(verse::string(FUtf8String(TCHAR_TO_UTF8(*Key))), verse::string(FUtf8String(TCHAR_TO_UTF8(*Value))));
    }

    FreeEnvironmentStringsW(EnvBlock);
    return Result;
}

#endif
