#include "WidgetSlots/Core/RestoreWidget2JsonFactory.h"

// 各类文本控件头文件, 用于 GetText 中的类型转换
#include "Components/EditableText.h"
#include "Components/EditableTextBox.h"
#include "Components/MultiLineEditableText.h"
#include "Components/MultiLineEditableTextBox.h"
#include "Components/RichTextBlock.h"
#include "Components/TextBlock.h"
// Widget 与 JSON 互转的接口定义
#include "WidgetSlots/Core/Widget2JsonInterface.h"
// 各种具体控件类型对应的 Widget2Json 实现 (文本、图片、按钮、各类面板容器等)
#include "WidgetSlots/Widgets/LQA_BackgroundBlur2Json.h"
#include "WidgetSlots/Widgets/LQA_Border2Json.h"
#include "WidgetSlots/Widgets/LQA_Button2Json.h"
#include "WidgetSlots/Widgets/LQA_CanvasPanel2Json.h"
#include "WidgetSlots/Widgets/LQA_CheckBox2Json.h"
#include "WidgetSlots/Widgets/LQA_CircularThrobber2Json.h"
#include "WidgetSlots/Widgets/LQA_ComboBox2Json.h"
#include "WidgetSlots/Widgets/LQA_EditableTextBlock2Json.h"
#include "WidgetSlots/Widgets/LQA_EditableTextBox2Json.h"
#include "WidgetSlots/Widgets/LQA_GridPanel2Json.h"
#include "WidgetSlots/Widgets/LQA_HorizontalBox2Json.h"
#include "WidgetSlots/Widgets/LQA_Image2Json.h"
#include "WidgetSlots/Widgets/LQA_InputKeySelector2Json.h"
#include "WidgetSlots/Widgets/LQA_MenuAnchor2Json.h"
#include "WidgetSlots/Widgets/LQA_MultilineEditableTextBlock2Json.h"
#include "WidgetSlots/Widgets/LQA_MultilineEditableTextBox2Json.h"
#include "WidgetSlots/Widgets/LQA_Overlay2Json.h"
#include "WidgetSlots/Widgets/LQA_ProgressBar2Json.h"
#include "WidgetSlots/Widgets/LQA_PlatformPaddingBox2Json.h"
#include "WidgetSlots/Widgets/LQA_RetainerBox2Json.h"
#include "WidgetSlots/Widgets/LQA_RichTextBlock2Json.h"
#include "WidgetSlots/Widgets/LQA_SafeZone2Json.h"
#include "WidgetSlots/Widgets/LQA_ScaleBox2Json.h"
#include "WidgetSlots/Widgets/LQA_ScrollBar2Json.h"
#include "WidgetSlots/Widgets/LQA_ScrollBox2Json.h"
#include "WidgetSlots/Widgets/LQA_SizeBox2Json.h"
#include "WidgetSlots/Widgets/LQA_Slider2Json.h"
#include "WidgetSlots/Widgets/LQA_Spacer2Json.h"
#include "WidgetSlots/Widgets/LQA_SpinBox2Json.h"
#include "WidgetSlots/Widgets/LQA_TextBlock2Json.h"
#include "WidgetSlots/Widgets/LQA_TextScroller2Json.h"
#include "WidgetSlots/Widgets/LQA_ListView2Json.h"
#include "WidgetSlots/Widgets/LQA_PostBufferUpdate2Json.h"
#include "WidgetSlots/Widgets/LQA_Throbber2Json.h"
#include "WidgetSlots/Widgets/LQA_UniformGridPanel2Json.h"
#include "WidgetSlots/Widgets/LQA_UserWidget2Json.h"
#include "WidgetSlots/Widgets/LQA_VerticalBox2Json.h"
#include "WidgetSlots/Widgets/LQA_WidgetSwitcher2Json.h"
#include "WidgetSlots/Widgets/LQA_WindowTitleBarArea2Json.h"
#include "WidgetSlots/Widgets/LQA_WrapBox2Json.h"
#include "WidgetSlots/Widgets/LQA_ExpandableArea2Json.h"
#include "WidgetSlots/Widgets/LQA_StackBox2Json.h"
#include "WidgetSlots/Widgets/LQA_InvalidationBox2Json.h"
#include "WidgetSlots/Widgets/LQA_DynamicEntryBox2Json.h"
#include "WidgetTree/LQAWidgetNode.h"   // LQAWidgetNames 控件类型名称常量
#include "Utils/JsonUtils.h"            // JSON 反序列化辅助工具

// 根据 JSON 中的 WidgetType 字段, 创建对应类型的 Widget2Json 接口实现
TSharedPtr<FWidget2JsonInterface> FWidget2JsonFactory::MakeWidgetData(const TSharedPtr<FJsonObject> InWidgetData)
{
	// 缺少 WidgetType 字段则无法判断类型, 直接返回空
	if (!InWidgetData->HasField(TEXT("WidgetType")))
	{
		return nullptr;
	}

	// 读取控件类型名称
	const FName WidgetType = FName(*InWidgetData->GetStringField(TEXT("WidgetType")));

	// Slate 根类型复用场景需优先判定:
	if (InWidgetData->HasField(TEXT("WidgetClass")))
	{
		const FName WidgetClass = FName(*InWidgetData->GetStringField(TEXT("WidgetClass")));
		if (WidgetClass == LQAWidgetClassNames::LQA_DynamicEntryBox)
		{
			return MakeShareable(new FLQA_DynamicEntryBox2Json());
		}
	}

	// 依次匹配控件类型, 创建对应的转换器实例
	// —— 文本类控件 ——
	if (WidgetType == LQAWidgetNames::LQA_TextBlock)
	{
		return MakeShareable(new FLQA_TextBlock2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_RichTextBlock)
	{
		return MakeShareable(new FLQA_RichTextBlock2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_EditableText)
	{
		return MakeShareable(new FLQA_EditableTextBlock2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_MultilineEditableText)
	{
		return MakeShareable(new FLQA_MultilineEditableTextBlock2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_EditableTextBox)
	{
		return MakeShareable(new FLQA_EditableTextBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_MultilineEditableTextBox)
	{
		return MakeShareable(new FLQA_MultilineEditableTextBox());
	}
	// —— 图片 / 按钮 ——
	if (WidgetType == LQAWidgetNames::LQA_Image)
	{
		return MakeShareable(new FLQA_Image2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_Button)
	{
		return MakeShareable(new FLQA_Button2Json());
	}
	// —— 各类面板 / 容器控件 ——
	if (WidgetType == LQAWidgetNames::LQA_Canvas)
	{
		return MakeShareable(new FLQA_CanvasPanel2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_GridPanel)
	{
		return MakeShareable(new FLQA_GridPanel2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_ScrollBox)
	{
		return MakeShareable(new FLQA_ScrollBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_VerticalBox)
	{
		return MakeShareable(new FLQA_VerticalBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_HorizontalBox)
	{
		return MakeShareable(new FLQA_HorizontalBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_UniformGridPanel)
	{
		return MakeShareable(new FLQA_UniformGridPanel2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_ScaleBox)
	{
		return MakeShareable(new FLQA_ScaleBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_SafeZone)
	{
		return MakeShareable(new FLQA_SafeZone2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_WrapBox)
	{
		return MakeShareable(new FLQA_WrapBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_UserWidget)
	{
		return MakeShareable(new FLQA_UserWidget2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_BackgroundBlur)
	{
		return MakeShareable(new FLQA_BackgroundBlur2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_CheckBox)
	{
		return MakeShareable(new FLQA_CheckBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_SizeBox)
	{
		return MakeShareable(new FLQA_SizeBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_Border)
	{
		return MakeShareable(new FLQA_Border2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_Overlay)
	{
		return MakeShareable(new FLQA_Overlay2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_ComboBox)
	{
		return MakeShareable(new FLQA_ComboBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_RetainerBox)
	{
		return MakeShareable(new FLQA_RetainerBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_WidgetSwitcher)
	{
		return MakeShareable(new FLQA_WidgetSwitcher2Json());
	}

	if (WidgetType == LQAWidgetNames::LQA_ProgressBar)
	{
		return MakeShareable(new FLQA_ProgressBar2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_Slider)
	{
		return MakeShareable(new FLQA_Slider2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_SpinBox)
	{
		return MakeShareable(new FLQA_SpinBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_Throbber)
	{
		return MakeShareable(new FLQA_Throbber2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_CircularThrobber)
	{
		return MakeShareable(new FLQA_CircularThrobber2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_Spacer)
	{
		return MakeShareable(new FLQA_Spacer2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_ScrollBar)
	{
		return MakeShareable(new FLQA_ScrollBar2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_InputKeySelector)
	{
		return MakeShareable(new FLQA_InputKeySelector2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_MenuAnchor)
	{
		return MakeShareable(new FLQA_MenuAnchor2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_PostBufferUpdate)
	{
		return MakeShareable(new FLQA_PostBufferUpdate2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_ListView)
	{
		return MakeShareable(new FLQA_ListView2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_TileView)
	{
		return MakeShareable(new FLQA_TileView2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_TreeView)
	{
		return MakeShareable(new FLQA_TreeView2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_StackBox)
	{
		return MakeShareable(new FLQA_StackBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_WindowTitleBarArea)
	{
		return MakeShareable(new FLQA_WindowTitleBarArea2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_InvalidationBox)
	{
		return MakeShareable(new FLQA_InvalidationBox2Json());
	}
	if (WidgetType == LQAWidgetNames::LQA_ExpandableArea)
	{
		return MakeShareable(new FLQA_ExpandableArea2Json());
	}

	// 未匹配到任何已注册类型: 输出警告, 提示在此函数中补充对应 handler, 该节点将被跳过
	UE_LOG(LogLQARestoreWidget2Json, Warning, TEXT("Unsupported WidgetType '%s', node will be skipped. "
												   "Register its handler in FWidget2JsonFactory::MakeWidgetData."),*WidgetType.ToString());

	return nullptr;
}

// 移除 JSON 对象中所有的委托 (Delegate) 字段, 这些字段无法被还原
void FWidget2JsonFactory::RemoveDelegateFields(const TSharedPtr<FJsonObject>& InJsonObj)
{
	// 无效对象直接返回
	if (!InJsonObj.IsValid())
	{
		return;
	}

	// 先收集需要移除的键, 避免在遍历容器时直接修改导致迭代器失效
	TArray<FString> RemovedEntry;
	RemovedEntry.Reserve(8);  // 预分配, 按典型委托数量预留空间, 减少扩容开销

	// 遍历所有字段, 收集键名中包含 "Delegate" 的字段
	for (const TPair<FString, TSharedPtr<FJsonValue>>& Pair : InJsonObj->Values)
	{
		if (Pair.Key.Contains(TEXT("Delegate")))
		{
			RemovedEntry.Emplace(Pair.Key);
		}
	}

	// 统一移除收集到的委托字段
	for (const FString& Key : RemovedEntry)
	{
		InJsonObj->RemoveField(Key);
	}
}

// 移除 ObjectData 中的 Slots 字段, 防止还原时与父容器的插槽处理产生冲突
void FWidget2JsonFactory::RemoveSlotsFromObjectData(const TSharedPtr<FJsonObject>& InJsonObj)
{
	// 无效对象直接返回
	if (!InJsonObj.IsValid())
	{
		return;
	}

	// 尝试取出 ObjectData 子对象, 并确认其有效
	const TSharedPtr<FJsonObject>* ObjectDataJsonObjPtr = nullptr;
	if (InJsonObj->TryGetObjectField(TEXT("ObjectData"), ObjectDataJsonObjPtr) && ObjectDataJsonObjPtr &&
		ObjectDataJsonObjPtr->IsValid())
	{
		TSharedPtr<FJsonObject> ObjectDataJsonObj = *ObjectDataJsonObjPtr;
		// 若存在 Slots 字段则移除
		if (ObjectDataJsonObj->HasField(TEXT("Slots")))
		{
			ObjectDataJsonObj->RemoveField(TEXT("Slots"));
		}
	}
}

// 清理 JSON 对象: 移除无法还原的委托字段与插槽字段
void FWidget2JsonFactory::CleanJsonObject(const TSharedPtr<FJsonObject>& InJsonObj)
{
	RemoveDelegateFields(InJsonObj);     // 移除委托字段
	RemoveSlotsFromObjectData(InJsonObj); // 移除 ObjectData 中的 Slots
}

// 从 JSON 还原控件, 并填充完整元数据 (位置、尺寸、层级、附加属性)
FRestoreWidgetMeta FWidget2JsonFactory::WidgetFromJson(
	const TSharedPtr<FJsonObject>& InJsonObj, const FVector2D& InWindowSize, URestoreWindowProxy* RestoreWindowProxy)
{
	FRestoreWidgetMeta MetaData;

	// 先清理 JSON, 移除无法还原的字段
	CleanJsonObject(InJsonObj);

	// 根据控件类型创建对应的转换器接口
	const TSharedPtr<FWidget2JsonInterface> Interface = MakeWidgetData(InJsonObj);
	if (Interface.IsValid())
	{
		// 通过接口把 JSON 反序列化为真正的控件实例
		MetaData.WidgetIns = Interface->FromJson(InJsonObj, RestoreWindowProxy);
		// 解析控件位置
		MetaData.WidgetPosition = GetWidgetPos(InJsonObj, InWindowSize);

		// 构建附加属性 JSON 对象, 先设置默认标记:
		// needOCR 是否需要 OCR 识别、isImage 是否为图片、isText 是否为文本
		TSharedPtr<FJsonObject> JsonObject = MakeShareable(new FJsonObject());
		JsonObject->SetBoolField(TEXT("needOCR"), false);
		JsonObject->SetBoolField(TEXT("isImage"), false);
		JsonObject->SetBoolField(TEXT("isText"), false);

		// 记录父控件名称、源字符串、控件名称等基础信息
		JsonObject->SetStringField(
			TEXT("ParentWidget"), FJsonUtils::DeserializeFromJson_FString(InJsonObj, TEXT("ParentWidget")));
		JsonObject->SetStringField(
			TEXT("SourceString"), FJsonUtils::DeserializeFromJson_FString(InJsonObj, TEXT("SourceString")));
		JsonObject->SetStringField(
			TEXT("WidgetName"), FJsonUtils::DeserializeFromJson_FString(InJsonObj, TEXT("WidgetName")));

		// 获取控件的具体类型, 用于分支处理
		ELQAWidgetType myType = Interface->GetType();

		if (myType == ELQAWidgetType::LQA_Image || myType == ELQAWidgetType::LQA_Button)
		{
			// 图片 / 按钮: 使用绝对尺寸转换, 确保尺寸正确
			MetaData.WidgetSize = GetWidgetSize(InJsonObj, InWindowSize, true);
			// 非文本控件, 文本相关字段置空
			JsonObject->SetStringField(TEXT("textStr"), TEXT(""));
			JsonObject->SetStringField(TEXT("TextKey"), TEXT(""));
			JsonObject->SetStringField(TEXT("justification"), TEXT(""));
			JsonObject->SetStringField(TEXT("verticalJustification"), TEXT(""));

			// 默认图片需要 OCR 识别
			JsonObject->SetBoolField(TEXT("needOCR"), true);
			// 若贴图数据里带有材质路径 (MaterialPath), 说明是材质图片, 不需要 OCR
			if (InJsonObj->HasField(TEXT("TextureData")))
			{
				TSharedPtr<FJsonObject> TextureObject = InJsonObj->GetObjectField(TEXT("TextureData"));
				if (TextureObject->HasField(TEXT("MaterialPath")))
				{
					JsonObject->SetBoolField(TEXT("needOCR"), false);
				}
			}

			// 标记为图片
			JsonObject->SetBoolField(TEXT("isImage"), true);
		}
		else if (myType == ELQAWidgetType::LQA_CheckBox || myType == ELQAWidgetType::LQA_ComboBoxStringText ||
				 myType == ELQAWidgetType::LQA_RetainerBox || myType == ELQAWidgetType::LQA_WidgetSwitcher ||
				 myType == ELQAWidgetType::LQA_ListView || myType == ELQAWidgetType::LQA_TileView ||
				 myType == ELQAWidgetType::LQA_TreeView)
		{
			// 复选框 / 下拉框 / RetainerBox / WidgetSwitcher / 列表类: 使用绝对尺寸, 文本相关字段置空
			MetaData.WidgetSize = GetWidgetSize(InJsonObj, InWindowSize, true);
			JsonObject->SetStringField(TEXT("textStr"), TEXT(""));
			JsonObject->SetStringField(TEXT("TextKey"), TEXT(""));
			JsonObject->SetStringField(TEXT("justification"), TEXT(""));
			JsonObject->SetStringField(TEXT("verticalJustification"), TEXT(""));
		}
		else if (myType == ELQAWidgetType::LQA_TextBlock || myType == ELQAWidgetType::LQA_RichText ||
				 myType == ELQAWidgetType::LQA_EditableText || myType == ELQAWidgetType::LQA_MultilineEditableText ||
				 myType == ELQAWidgetType::LQA_EditableTextBox ||
				 myType == ELQAWidgetType::LQA_MultilineEditableTextBox)
		{
			// 各类文本控件: 使用相对尺寸 (LocalSize)
			MetaData.WidgetSize = GetWidgetSize(InJsonObj, InWindowSize, false);
			// 从控件实例中提取当前文本内容
			FString textStr = GetText(MetaData.WidgetIns);
			JsonObject->SetStringField(TEXT("textStr"), textStr);
			// 文本的多语言 Key
			JsonObject->SetStringField(
				TEXT("TextKey"), FJsonUtils::DeserializeFromJson_FString(InJsonObj, TEXT("TextKey")));
			// 从 ObjectData 中读取对齐信息
			const TSharedPtr<FJsonObject>* ObjectData;
			if (InJsonObj->TryGetObjectField(TEXT("ObjectData"), ObjectData))
			{
				// 水平对齐方式
				JsonObject->SetStringField(
					TEXT("justification"), FJsonUtils::DeserializeFromJson_FString(*ObjectData, TEXT("justification")));
				// 垂直对齐方式; 若 verticalJustification 为空, 则回退读取 TextAlignVertical 字段
				FString verticalJustification =
					FJsonUtils::DeserializeFromJson_FString(*ObjectData, TEXT("verticalJustification"));
				if (verticalJustification == TEXT(""))
				{
					verticalJustification =
						FJsonUtils::DeserializeFromJson_FString(*ObjectData, TEXT("TextAlignVertical"));
				}
				JsonObject->SetStringField(TEXT("verticalJustification"), verticalJustification);
				// 行高百分比
				JsonObject->SetNumberField(TEXT("lineHeightPercentage"),
					FJsonUtils::DeserializeFromJson_Float(*ObjectData, TEXT("lineHeightPercentage")));
			}
			// 文本控件需要 OCR 识别, 并标记为文本
			JsonObject->SetBoolField(TEXT("needOCR"), true);
			JsonObject->SetBoolField(TEXT("isText"), true);
			MetaData.Property = JsonObject;
		}

		// 保存附加属性与渲染层级 (LayerId)
		MetaData.Property = JsonObject;
		MetaData.ZOrder = FJsonUtils::DeserializeFromJson_Int32(InJsonObj, TEXT("LayerId"));
	}

	return MetaData;
}

// 从 JSON 还原面板 (容器) 控件, 仅填充基础元数据
FRestoreWidgetMeta FWidget2JsonFactory::WidgetFromJsonForPanel(
	const TSharedPtr<FJsonObject>& InJsonObj, const FVector2D& InWindowSize, URestoreWindowProxy* RestoreWindowProxy)
{
	// 先清理 JSON, 移除无法还原的字段
	CleanJsonObject(InJsonObj);

	// 创建面板控件实例
	const TSharedPtr<FWidget2JsonInterface> Interface = MakeWidgetData(InJsonObj);
	FRestoreWidgetMeta MetaData;
	if (Interface.IsValid())
	{
		// 反序列化出面板控件实例
		MetaData.WidgetIns = Interface->FromJson(InJsonObj, RestoreWindowProxy);
		// 解析位置与尺寸 (面板使用相对尺寸)
		MetaData.WidgetPosition = GetWidgetPos(InJsonObj, InWindowSize);
		MetaData.WidgetSize = GetWidgetSize(InJsonObj, InWindowSize, false);
		// 面板不需要附加属性
		MetaData.Property = nullptr;
		// 默认层级取 LayerId
		MetaData.ZOrder = FJsonUtils::DeserializeFromJson_Int32(InJsonObj, TEXT("LayerId"));
		// 若 ObjectData 中存在 Layer 字段, 则优先使用它作为层级
		if (InJsonObj->HasField(TEXT("ObjectData")))
		{
			TSharedPtr<FJsonObject> ObjectData = InJsonObj->GetObjectField(TEXT("ObjectData"));
			if (ObjectData->HasField(TEXT("Layer")))
			{
				MetaData.ZOrder = FJsonUtils::DeserializeFromJson_Int32(ObjectData, TEXT("Layer"));
			}
		}
		// 输出面板位置与尺寸日志, 便于调试
		UE_LOG(LogLQARestoreWidget2Json, Log, TEXT("Panel Widget Pos: %f, %f"), MetaData.WidgetPosition.X,
			MetaData.WidgetPosition.Y);
		UE_LOG(LogLQARestoreWidget2Json, Log, TEXT("Panel Widget Size: %f, %f"), MetaData.WidgetSize.X, MetaData.WidgetSize.Y);
	}

	return MetaData;
}

// 从各种文本类控件中提取文本内容; 非文本控件返回空字符串
FString FWidget2JsonFactory::GetText(UWidget* UI)
{
	// 依次尝试将控件转换为各类文本控件类型, 成功则返回其文本
	if (UTextBlock* TextBlock = Cast<UTextBlock>(UI))
	{
		return TextBlock->GetText().ToString();
	}
	if (URichTextBlock* RichTextBlock = Cast<URichTextBlock>(UI))
	{
		return RichTextBlock->GetText().ToString();
	}
	if (UEditableText* EditableText = Cast<UEditableText>(UI))
	{
		return EditableText->GetText().ToString();
	}
	if (UEditableTextBox* EditableTextBox = Cast<UEditableTextBox>(UI))
	{
		return EditableTextBox->GetText().ToString();
	}
	if (UMultiLineEditableText* MultiLineEditableText = Cast<UMultiLineEditableText>(UI))
	{
		return MultiLineEditableText->GetText().ToString();
	}
	if (UMultiLineEditableTextBox* MultiLineEditableTextBox = Cast<UMultiLineEditableTextBox>(UI))
	{
		return MultiLineEditableTextBox->GetText().ToString();
	}

	// 非文本控件, 返回空字符串
	return TEXT("");
}

// 从 JSON 根对象中解析窗口尺寸 (读取 meta.sizeX / meta.sizeY)
bool FWidget2JsonFactory::DeserializeWindowSize(const TSharedPtr<FJsonObject>& RootObj, FVector2D& OutSize)
{
	// 根对象需包含 meta 字段
	if (RootObj->HasField(TEXT("meta")))
	{
		const TSharedPtr<FJsonObject> MetaData = RootObj->GetObjectField(TEXT("meta"));
		// meta 中需同时包含 sizeX 与 sizeY
		if (MetaData->HasField(TEXT("sizeX")) && MetaData->HasField(TEXT("sizeY")))
		{
			OutSize.X = MetaData->GetNumberField(TEXT("sizeX"));
			OutSize.Y = MetaData->GetNumberField(TEXT("sizeY"));
			return true;
		}
		// 缺少尺寸字段
		UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Deserialize Window Size Failed!"));
		return false;
	}

	// 缺少 meta 字段
	UE_LOG(LogLQARestoreWidget2Json, Error, TEXT("Find Meta Data Failed!"));
	return false;
}

// 从 JSON 获取控件位置, 并进行坐标系转换
FVector2D FWidget2JsonFactory::GetWidgetPos(const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize)
{
	// 优先从 corners (四角坐标) 数组中获取位置
	TArray<TSharedPtr<FJsonValue>> SizePoint = InWidgetData->GetArrayField(TEXT("corners"));
	if (SizePoint.Num() == 4)
	{
		// 使用第 2 个角点 (corner[1]) 作为左上角位置
		return DeserializePoint(SizePoint[1]->AsObject(), InWindowSize);
	}

	// 若没有 corners, 则回退使用 ViewportPos 字段
	if (InWidgetData->HasField(TEXT("ViewportPos")))
	{
		TSharedPtr<FJsonObject> ViewportPosObj = InWidgetData->GetObjectField(TEXT("ViewportPos"));
		FVector2D Point = FVector2D::ZeroVector;
		if (ViewportPosObj->HasField(TEXT("x")))
		{
			Point.X = ViewportPosObj->GetNumberField(TEXT("x"));
		}

		if (ViewportPosObj->HasField(TEXT("y")))
		{
			Point.Y = ViewportPosObj->GetNumberField(TEXT("y"));
		}
		return Point;
	}

	// 两者都没有, 返回零向量
	return FVector2D::ZeroVector;
}

// 从 JSON 获取控件尺寸
FVector2D FWidget2JsonFactory::GetWidgetSize(
	const TSharedPtr<FJsonObject> InWidgetData, const FVector2D& InWindowSize, bool bUseAbsoluteSize)
{
	// 图片 / 按钮等: 根据四角坐标计算绝对尺寸
	if (bUseAbsoluteSize)
	{
		if (InWidgetData->HasField(TEXT("corners")))
		{
			TArray<TSharedPtr<FJsonValue>> SizePoint = InWidgetData->GetArrayField(TEXT("corners"));
			if (SizePoint.Num() == 4)
			{
				// 由左上角 (corner[1]) 与右下角 (corner[3]) 坐标差值计算尺寸
				const FVector2D LeftUpper = DeserializePoint(SizePoint[1]->AsObject(), InWindowSize);
				const FVector2D RightBottom = DeserializePoint(SizePoint[3]->AsObject(), InWindowSize);
				return RightBottom - LeftUpper;
			}
		}
		return FVector2D::ZeroVector;
	}

	// 文本等控件: 使用 LocalSize (相对尺寸)
	if (InWidgetData->HasField(TEXT("LocalSize")))
	{
		const TSharedPtr<FJsonObject> LocalSizeObj = InWidgetData->GetObjectField(TEXT("LocalSize"));
		FVector2D Point = FVector2D::ZeroVector;
		if (LocalSizeObj->HasField(TEXT("x")))
		{
			Point.X = LocalSizeObj->GetNumberField(TEXT("x"));
		}

		if (LocalSizeObj->HasField(TEXT("y")))
		{
			Point.Y = LocalSizeObj->GetNumberField(TEXT("y"));
		}
		return Point;
	}

	return FVector2D::ZeroVector;
}

// 从 JSON 解析一个二维坐标点, 并将坐标系从左下角原点转换为左上角原点
FVector2D FWidget2JsonFactory::DeserializePoint(const TSharedPtr<FJsonObject> InPosData, const FVector2D& InWindowSize)
{
	FVector2D Point = FVector2D::ZeroVector;
	if (InPosData->HasField(TEXT("x")))
	{
		Point.X = InPosData->GetNumberField(TEXT("x"));
	}

	if (InPosData->HasField(TEXT("y")))
	{
		Point.Y = InPosData->GetNumberField(TEXT("y"));
	}

	// 非零点才需要转换坐标系
	if (!Point.IsZero())
	{
		// 原始坐标以窗口左下角为原点, 这里转换回以左上角为原点 (Y 轴翻转)
		Point.Y = InWindowSize.Y - Point.Y;
	}

	return Point;
}