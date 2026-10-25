// Generated from Epic UE source; Copyright Epic Games, Inc. All Rights Reserved.
static void GenerateUniformBufferStructMember(FString& Result, const FShaderParametersMetadata::FMember& Member, EShaderPlatform ShaderPlatform)
{
	// Generate the base type name.
	FString TypeName;
	Member.GenerateShaderParameterType(TypeName, ShaderPlatform);

	// Generate array dimension post fix
	FString ArrayDim;
	if (Member.GetNumElements() > 0)
	{
		ArrayDim = FString::Printf(TEXT("[%u]"), Member.GetNumElements());
	}

	Result = FString::Printf(TEXT("%s %s%s"), *TypeName, Member.GetName(), *ArrayDim);
}

static void GenerateInstancedStereoCode(FString& Result, EShaderPlatform ShaderPlatform)
{
	// Find the InstancedView uniform buffer struct
	const FShaderParametersMetadata* View = nullptr;
	const FShaderParametersMetadata* InstancedView = nullptr;

	for (TLinkedList<FShaderParametersMetadata*>::TIterator StructIt(FShaderParametersMetadata::GetStructList()); StructIt; StructIt.Next())
	{
		if (StructIt->GetShaderVariableName() == FString("View"))
		{
			View = *StructIt;
		}

		if (StructIt->GetShaderVariableName() == FString("InstancedView"))
		{
			InstancedView = *StructIt;
		}

		if (View && InstancedView)
		{
			break;
		}
	}
	checkSlow(View != nullptr);
	checkSlow(InstancedView != nullptr);

	const TArray<FShaderParametersMetadata::FMember>& StructMembersView = View->GetMembers();
	const TArray<FShaderParametersMetadata::FMember>& StructMembersInstanced = InstancedView->GetMembers();

	static const auto CVarViewHasTileOffsetData = IConsoleManager::Get().FindTConsoleVariableDataInt(TEXT("r.ViewHasTileOffsetData"));
	const bool bViewHasTileOffsetData = CVarViewHasTileOffsetData ? (CVarViewHasTileOffsetData->GetValueOnAnyThread() != 0) : false;

	Result = "";
	if (bViewHasTileOffsetData)
	{
		Result +=  "struct ViewStateTileOffsetData\r\n";
		Result += "{\r\n";
		Result += "\tFLWCVector3 WorldCameraOrigin;\r\n";
		Result += "\tFLWCVector3 WorldViewOrigin;\r\n";
		Result += "\tFLWCVector3 PrevWorldCameraOrigin;\r\n";
		Result += "\tFLWCVector3 PrevWorldViewOrigin;\r\n";
		Result += "\tFLWCVector3 PreViewTranslation;\r\n";
		Result += "\tFLWCVector3 PrevPreViewTranslation;\r\n";
		Result += "};\r\n";
	}

	// ViewState definition
	Result +=  "struct ViewState\n";
	Result += "{\n";
	for (int32 MemberIndex = 0; MemberIndex < StructMembersInstanced.Num(); ++MemberIndex)
	{
		FString MemberDecl;
		// ViewState is only supposed to contain InstancedView members however we want their original type and array-length instead of their representation in the instanced array
		// SceneRendererPrimaryViewId for example needs to return 	uint SceneRendererPrimaryViewId; and not uint4 InstancedView_SceneRendererPrimaryViewId[2];
		// and that initial representation is in StructMembersView
		GenerateUniformBufferStructMember(MemberDecl, StructMembersView[MemberIndex], ShaderPlatform);
		Result += FString::Printf(TEXT("\t%s;\n"), *MemberDecl);
	}
	Result += "\tFDFInverseMatrix WorldToClip;\n";
	Result += "\tFDFMatrix ClipToWorld;\n";
	Result += "\tFDFMatrix ScreenToWorld;\n";
	Result += "\tFDFMatrix PrevClipToWorld;\n";
	Result += "\tFDFVector3 WorldCameraOrigin;\n";
	Result += "\tFDFVector3 WorldViewOrigin;\n";
	Result += "\tFDFVector3 PrevWorldCameraOrigin;\n";
	Result += "\tFDFVector3 PrevWorldViewOrigin;\n";
	Result += "\tFDFVector3 PreViewTranslation;\n";
	Result += "\tFDFVector3 PrevPreViewTranslation;\n";

	if (bViewHasTileOffsetData)
	{
		Result += "\tViewStateTileOffsetData TileOffset;\n";
	}

	Result += "};\n";

	Result += "\tvoid FinalizeViewState(inout ViewState InOutView);\n";

	// GetPrimaryView definition
	Result += "ViewState GetPrimaryView()\n";
	Result += "{\n";
	Result += "\tViewState Result;\n";
	for (int32 MemberIndex = 0; MemberIndex < StructMembersInstanced.Num(); ++MemberIndex)
	{
		const FShaderParametersMetadata::FMember& Member = StructMembersView[MemberIndex];
		Result += FString::Printf(TEXT("\tResult.%s = View.%s;\n"), Member.GetName(), Member.GetName());
	}
	Result += "\tFinalizeViewState(Result);\n";
	Result += "\treturn Result;\n";
	Result += "}\n";

	// GetInstancedView definition
	Result += "#if INSTANCED_STEREO || MOBILE_MULTI_VIEW\n";
	Result += "ViewState GetInstancedView(uint ViewIndex)\n";
	Result += "{\n";
	Result += "\tViewState Result;\n";
	for (int32 MemberIndex = 0; MemberIndex < StructMembersInstanced.Num(); ++MemberIndex)
	{
		const FShaderParametersMetadata::FMember& ViewMember = StructMembersView[MemberIndex];
		const FShaderParametersMetadata::FMember& InstancedViewMember = StructMembersInstanced[MemberIndex];

		FString ViewMemberTypeName;
		ViewMember.GenerateShaderParameterType(ViewMemberTypeName, ShaderPlatform);

		// this code avoids an assumption that instanced buffer only supports 2 views, to be future-proof
		if (ViewMember.GetNumElements() >= 1 && (InstancedViewMember.GetNumElements() >= 2 * ViewMember.GetNumElements()))
		{
			// if View has an array (even 1-sized) for this index, and InstancedView has Nx (N>=2) the element count -> per-view array
			// Result.TranslucencyLightingVolumeMin[0] = (float4) InstancedView_TranslucencyLightingVolumeMin[ViewIndex * 2 + 0];
			checkf((InstancedViewMember.GetNumElements() % ViewMember.GetNumElements()) == 0, TEXT("Per-view arrays are expected to be stored in an array that is an exact multiple of the original array."));
			for (uint32 ElementIndex = 0; ElementIndex < ViewMember.GetNumElements(); ElementIndex++)
			{
				Result += FString::Printf(
					TEXT("\tResult.%s[%u] = (%s) InstancedView.%s[ViewIndex * %u + %u];\n"),
					ViewMember.GetName(),
					ElementIndex,
					*ViewMemberTypeName,
					InstancedViewMember.GetName(), 
					ViewMember.GetNumElements(), 
					ElementIndex);
			}
		}
		else if (InstancedViewMember.GetNumElements() > 1 && ViewMember.GetNumElements() == 0)
		{
			// if View has a scalar field for this index, and InstancedView has an array with >1 elements -> per-view scalar
			// 	Result.TranslatedWorldToClip = (float4x4) InstancedView_TranslatedWorldToClip[ViewIndex];
			Result += FString::Printf(
				TEXT("\tResult.%s = (%s) InstancedView.%s[ViewIndex];\n"),
				ViewMember.GetName(), 
				*ViewMemberTypeName, 
				InstancedViewMember.GetName());
		}
		else if (InstancedViewMember.GetNumElements() == ViewMember.GetNumElements())
		{
			// if View has the same number of elements for this index as InstancedView, it's backed by a view-dependent array, assume a view-independent field
			// 	Result.TemporalAAParams = InstancedView_TemporalAAParams;
			Result += FString::Printf(
				TEXT("\tResult.%s = InstancedView.%s;\n"),
				ViewMember.GetName(), 
				InstancedViewMember.GetName());
		}
		else
		{
			// something unexpected, better crash now rather than generate wrong shader code and poison DDC 
			UE_LOGF(
				LogRiveLiteShaderCompiler, 
				Fatal,
				"Don't know how to copy View buffers' field %ls (NumElements=%d) from InstancedView field %ls (NumElements=%d)",
				ViewMember.GetName(), 
				ViewMember.GetNumElements(), 
				InstancedViewMember.GetName(), 
				InstancedViewMember.GetNumElements());
		}
	}
	Result += "\tFinalizeViewState(Result);\n";
	Result += "\treturn Result;\n";
	Result += "}\n";
	Result += "#endif\n";
}
