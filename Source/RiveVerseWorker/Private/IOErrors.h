// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Verse.access_error.gen.h"
#include "Verse.io_error.gen.h"
#include "Verse.not_found_error.gen.h"

namespace verse {
class io_error : public UObject
{
    IO_ERROR_BODY()
};

class access_error : public io_error
{
    ACCESS_ERROR_BODY()
};

class not_found_error : public io_error
{
    NOT_FOUND_ERROR_BODY()
};
}