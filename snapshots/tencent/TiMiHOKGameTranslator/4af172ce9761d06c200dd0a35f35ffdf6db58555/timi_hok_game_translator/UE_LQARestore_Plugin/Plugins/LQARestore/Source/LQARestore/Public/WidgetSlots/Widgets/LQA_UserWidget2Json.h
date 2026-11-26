#pragma once

#include "Blueprint/UserWidget.h"
#include "Components/CanvasPanel.h"
#include "Components/CanvasPanelSlot.h"
#include "Components/Image.h"
#include "WidgetSlots/Core/Widget2JsonInterface.h"

// For UserWidget
class FLQA_UserWidget2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	UUserWidget* CreateWidgetFromJson(const TSharedPtr<FJsonObject>& JsonObject);

	void ApplyJsonToWidget(UUserWidget* Widget, const TSharedPtr<FJsonObject>& JsonObject);

private:
	/** Create a plain UserWidget container purely in C++ (no blueprint asset dependency) */
	UUserWidget* CreateBaseUserWidget();
};