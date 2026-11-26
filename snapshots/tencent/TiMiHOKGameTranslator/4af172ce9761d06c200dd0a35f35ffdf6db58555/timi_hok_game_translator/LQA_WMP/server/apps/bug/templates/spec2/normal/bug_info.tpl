<p><strong style="font-size: 18px;">【缺陷情况】</strong></p>
<div style="margin-left: 2em">
    <p style="margin: 0">缺陷描述（必填）： {{ bug_info.bug_type_names|join:"/" }}</p>
    <br>

    <p style="margin: 0">修复建议： </p>
    <br>

    <p style="margin: 0">中文文本内容(SourceString)（必填，文本缺失填”空“）</p>
    {% for source_string in bug_info.source_strings %}
    <p style="word-break: break-all;margin: 5px 0 5px 2em">{{forloop.counter}}、{{source_string}}</p>
    {% endfor %}
    <br>

    <p style="margin: 0">文本内容(textStr)（必填，文本缺失填”空“）：</p>
    {% for text_str in bug_info.text_strs %}
    <p style="word-break: break-all;margin: 5px 0 5px 2em">{{forloop.counter}}、{{text_str}}</p>
    {% endfor %}
    <br>

    <p style="margin: 0">文本key(TextKey)（必填）：</p>
    {% for text_key in bug_info.text_keys %}
    <p style="word-break: break-all;margin: 5px 0 5px 2em">{{forloop.counter}}、{{text_key}}</p>
    {% endfor %}
    <br>

    <p style="margin: 0">文本控件名(WidgetName)（必填）：</p>
    {% for widget_name in bug_info.widget_names %}
    <p style="word-break: break-all;margin: 5px 0 5px 2em">{{forloop.counter}}、{{widget_name}}</p>
    {% endfor %}
    <br>

    <p style="margin: 0">【文本所处蓝图 ParentWidget】</p>
    {% for parent_widget in bug_info.parent_widgets %}
    <p style="word-break: break-all;margin: 5px 0 5px 2em">{{forloop.counter}}、{{parent_widget}}</p>
    {% endfor %}
    <br>

    <p style="margin: 0">复现步骤（选填）：</p>
    <br>

    <p style="margin: 0">缺陷详情（必填）:
        <br>
        <span>游戏界面截图</span>
    </p>
</div>