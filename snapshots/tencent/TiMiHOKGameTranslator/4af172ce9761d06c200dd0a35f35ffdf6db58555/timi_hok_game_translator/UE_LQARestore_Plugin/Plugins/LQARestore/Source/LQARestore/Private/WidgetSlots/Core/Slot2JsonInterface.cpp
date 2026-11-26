#include "WidgetSlots/Core/Slot2JsonInterface.h"
#include "Utils/JsonUtils.h"    // 字段名大小写对齐工具 (修复嵌套字段被静默跳过)

// 定义头文件中声明的日志分类 (与 DECLARE_LOG_CATEGORY_EXTERN 配对使用)
DEFINE_LOG_CATEGORY(LogLQARestoreSlot2Json);

/**
 * 根据 JSON 数据设置面板槽属性的通用实现
 * 通过 UE 的 JSON->UStruct 转换器, 依据反射信息把 JSON 字段写入 Slot 对象
 */
bool FSlot2JsonInterface::SetPanelSlotProperties(const TSharedPtr<FJsonObject> InJsonData, UPanelSlot* PanelSlot)
{
	// 入参合法性校验: JSON 数据必须有效, 且目标 Slot 指针不能为空
	if (!InJsonData.IsValid() || !PanelSlot)
	{
		UE_LOG(LogLQARestoreSlot2Json, Warning, TEXT("Invalid input to SetPanelSlotProperties"));
		return false;
	}

	// JsonObjectToUStruct 需要 TSharedRef<FJsonObject> 参数, 这里把 TSharedPtr 转为 TSharedRef
	TSharedRef<FJsonObject> JsonObjectRef = InJsonData.ToSharedRef();

	// 把字段名大小写对齐到目标 Slot 的反射属性名
	FJsonUtils::StandardizeCaseForImport(InJsonData, PanelSlot->GetClass());

	// 利用反射将 JSON 对象映射到 PanelSlot 对应的 UPROPERTY:
	// 参数: JSON 源数据、目标对象的 UClass、目标对象实例、
	//       CheckFlags (0 表示不限制属性标记)、SkipFlags (0 表示不跳过任何属性)
	bool bSuccess = FJsonObjectConverter::JsonObjectToUStruct(JsonObjectRef, PanelSlot->GetClass(), PanelSlot, 0, 0);

	// 返回转换结果
	return bSuccess;
}