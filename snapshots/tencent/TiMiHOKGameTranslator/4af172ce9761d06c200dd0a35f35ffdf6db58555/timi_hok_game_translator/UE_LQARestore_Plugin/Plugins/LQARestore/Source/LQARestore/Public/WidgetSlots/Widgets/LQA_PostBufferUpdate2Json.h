#pragma once

#include "WidgetSlots/Core/Widget2JsonInterface.h"

class UPostBufferUpdate;

// For PostBufferUpdate
// 说明: 该控件无视觉表现, 采集端只导出其 UPROPERTY, 还原时按 ObjectData 原样重建即可
class FLQA_PostBufferUpdate2Json : public FWidget2JsonInterface
{
public:
	virtual UWidget* FromJson(const TSharedPtr<FJsonObject> JsonData, URestoreWindowProxy* RestoreWindowProxy) override;

	virtual ELQAWidgetType GetType() override;
};
