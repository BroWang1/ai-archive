#include "WidgetSlots/Widgets/LQA_UserWidget2Json.h"

#include "Blueprint/UserWidget.h"
#include "Core/LQAContainerWidget.h"
#include "WidgetSlots/Core/WidgetDefines.h"

using namespace LQAWidgetConstants;

void FLQA_UserWidget2Json::ApplyJsonToWidget(UUserWidget* Widget, const TSharedPtr<FJsonObject>& JsonObject)
{
	if (!Widget || !JsonObject.IsValid())
	{
		return;
	}

	// Ignored fields list
	static const TSet<FString> IgnoredFields = {TEXT("AutoLoadList"), TEXT("AnimsValiable"), TEXT("PresetAnimSettings"),
		TEXT("AnimBindingSettings"), TEXT("AnimAutoPlaySettings"), TEXT("AudioEventCfg")};

	// Iterate through Json fields
	for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : JsonObject->Values)
	{
		const FString& Key = Pair.Key;

		if (IgnoredFields.Contains(Key))
		{
			continue;  // Skip ignored fields
		}

		else if (Key == TEXT("ColorAndOpacity"))
		{
			TSharedPtr<FJsonObject> ColorObj = JsonObject->GetObjectField(Key);
			if (ColorObj.IsValid())
			{
				float R = ColorObj->GetNumberField(TEXT("r"));
				float G = ColorObj->GetNumberField(TEXT("g"));
				float B = ColorObj->GetNumberField(TEXT("b"));
				float A = ColorObj->GetNumberField(TEXT("a"));
				Widget->SetColorAndOpacity(FLinearColor(R, G, B, A));
			}
		}
		
		else if (Key == TEXT("Visibility"))
		{
			FString VisibilityStr = JsonObject->GetStringField(Key);
			ESlateVisibility Visibility = ESlateVisibility::Visible;

			if (VisibilityStr == "SelfHitTestInvisible")
				Visibility = ESlateVisibility::SelfHitTestInvisible;
			else if (VisibilityStr == "Visible")
				Visibility = ESlateVisibility::Visible;
			else if (VisibilityStr == "Collapsed")
				Visibility = ESlateVisibility::Collapsed;
			else if (VisibilityStr == "Hidden")
				Visibility = ESlateVisibility::Hidden;
			else if (VisibilityStr == "HitTestInvisible")
				Visibility = ESlateVisibility::HitTestInvisible;

			Widget->SetVisibility(Visibility);
		}
		else if (Key == TEXT("RenderTransform"))
		{
			TSharedPtr<FJsonObject> TransformObj = JsonObject->GetObjectField(Key);
			if (TransformObj.IsValid())
			{
				FVector2D Translation(0.f, 0.f);
				FVector2D Scale(1.f, 1.f);
				FVector2D Shear(0.f, 0.f);
				float Angle = 0.f;

				if (TransformObj->HasField(TEXT("translation")))
				{
					TSharedPtr<FJsonObject> TransObj = TransformObj->GetObjectField(TEXT("translation"));
					Translation.X = TransObj->GetNumberField(TEXT("x"));
					Translation.Y = TransObj->GetNumberField(TEXT("y"));
				}
				if (TransformObj->HasField(TEXT("scale")))
				{
					TSharedPtr<FJsonObject> ScaleObj = TransformObj->GetObjectField(TEXT("scale"));
					Scale.X = ScaleObj->GetNumberField(TEXT("x"));
					Scale.Y = ScaleObj->GetNumberField(TEXT("y"));
				}
				if (TransformObj->HasField(TEXT("shear")))
				{
					TSharedPtr<FJsonObject> ShearObj = TransformObj->GetObjectField(TEXT("shear"));
					Shear.X = ShearObj->GetNumberField(TEXT("x"));
					Shear.Y = ShearObj->GetNumberField(TEXT("y"));
				}
				if (TransformObj->HasField(TEXT("angle")))
				{
					Angle = TransformObj->GetNumberField(TEXT("angle"));
				}

				FWidgetTransform WidgetTransform(Translation, Scale, Shear, Angle);
				Widget->SetRenderTransform(WidgetTransform);
			}
		}
		else if (Key == TEXT("RenderTransformPivot"))
		{
			TSharedPtr<FJsonObject> PivotObj = JsonObject->GetObjectField(Key);
			if (PivotObj.IsValid())
			{
				float PX = PivotObj->GetNumberField(TEXT("x"));
				float PY = PivotObj->GetNumberField(TEXT("y"));
				Widget->SetRenderTransformPivot(FVector2D(PX, PY));
			}
		}
		else if (Key == TEXT("bIsEnabled"))
		{
			bool bEnabled = JsonObject->GetBoolField(Key);
			Widget->SetIsEnabled(bEnabled);
		}
		else if (Key == TEXT("Cursor"))
		{
			FString CursorStr = JsonObject->GetStringField(Key);
			// Simple example, only supports Default and None
			if (CursorStr == "Default")
				Widget->SetCursor(EMouseCursor::Default);
			else if (CursorStr == "None")
				Widget->SetCursor(EMouseCursor::None);
			// You can extend more Cursor types
		}

		// You can continue adding more field mappings
	}

	if (JsonObject->HasField(TEXT("PageWidth")) && JsonObject->HasField(TEXT("PageHeight")))
	{
		int32 Width = JsonObject->GetIntegerField(TEXT("PageWidth"));
		int32 Height = JsonObject->GetIntegerField(TEXT("PageHeight"));
		Widget->SetDesiredSizeInViewport(FVector2D(Width, Height));
	}
}

UUserWidget* FLQA_UserWidget2Json::CreateBaseUserWidget()
{
	if (!GEngine)
		return nullptr;

	UWorld* World = nullptr;
	for (const FWorldContext& Context : GEngine->GetWorldContexts())
	{
		if (Context.WorldType == EWorldType::Game || Context.WorldType == EWorldType::PIE)
		{
			World = Context.World();
			break;
		}
	}

	if (!World)
	{
		UE_LOG(LogLQARestoreWidget2Json, Warning, TEXT("No valid game world found"));
		return nullptr;
	}

	APlayerController* PC = World->GetFirstPlayerController();
	if (!PC)
	{
		UE_LOG(LogLQARestoreWidget2Json, Warning, TEXT("No player controller found"));
		return nullptr;
	}

	// Create a concrete container UserWidget purely in C++ (base UUserWidget is abstract)
	UUserWidget* WidgetInstance = CreateWidget<ULQAContainerWidget>(PC, ULQAContainerWidget::StaticClass());
	if (!WidgetInstance)
	{
		UE_LOG(LogLQARestoreWidget2Json, Warning, TEXT("Failed to create UserWidget"));
	}

	return WidgetInstance;
}

UUserWidget* FLQA_UserWidget2Json::CreateWidgetFromJson(const TSharedPtr<FJsonObject>& JsonObject)
{
	UUserWidget* WidgetInstance = CreateBaseUserWidget();
	if (!WidgetInstance)
	{
		return nullptr;
	}

	ApplyJsonToWidget(WidgetInstance, JsonObject);

	return WidgetInstance;
}

UWidget* FLQA_UserWidget2Json::FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy)
{
	if (!JsonData.IsValid())
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("JsonData is invalid for UserWidget"));
		return nullptr;
	}

	UUserWidget* Widget = nullptr;

	if (JsonData->HasField(CommonObjectKey))
	{
		const TSharedPtr<FJsonObject> ObjectData = JsonData->GetObjectField(CommonObjectKey);
		if (ObjectData.IsValid())
		{
			Widget = CreateWidgetFromJson(ObjectData);
		}
	}
	else
	{
		Widget = CreateBaseUserWidget();
	}

	if (!Widget)
	{
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Try Restore UUserWidget Failed!"));
		return nullptr;
	}

	return Widget;
}
