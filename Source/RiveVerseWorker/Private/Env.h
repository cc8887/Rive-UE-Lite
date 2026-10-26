// Copyright Epic Games, Inc. All Rights Reserved.

#pragma once

#include "Containers/Map.h"
#include "VerseString.h"

namespace VerseCmd {
TMap<verse::string, verse::string> GetProcessEnvironment();
}
