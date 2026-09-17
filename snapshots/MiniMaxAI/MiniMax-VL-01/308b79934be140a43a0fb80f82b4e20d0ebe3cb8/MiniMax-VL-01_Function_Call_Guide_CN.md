# MiniMax-Text-01 函数调用（Function Call）功能指南

## 📖 简介

MiniMax-Text-01 模型支持函数调用功能，使模型能够识别何时需要调用外部函数，并以结构化格式输出函数调用参数。本文档详细介绍了如何使用 MiniMax-Text-01 的函数调用功能。

## 🛠️ 函数调用的定义

### 函数结构体

函数调用需要在请求体中定义 `tools` 字段，每个函数由以下部分组成：

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "function_name",           // 函数名称，必填
        "description": "function_description", // 函数描述，应简明扼要说明函数功能
        "parameters": {                    // 函数参数定义，符合 JSON Schema 格式
          "type": "object",                // 参数整体类型，固定为object
          "properties": {                  // 参数属性对象
            "param_name": {                // 参数名称
              "description": "参数描述",    // 参数说明
              "type": "string|number|boolean|array|object" // 参数类型
            }
          },
          "required": ["param1", "param2"]  // 必填参数列表
        }
      }
    }
  ]
}
```

### 示例

以下是一个简单的天气查询函数定义示例：

```json
"tools": [
  {
    "type": "function",
    "function": {
      "name": "get_current_weather",
      "description": "Get the latest weather for a location",
      "parameters": {
        "type": "object", 
        "properties": {
          "location": {
            "type": "string", 
            "description": "A certain city, such as Beijing, Shanghai"
          }
        }, 
        "required": ["location"]
      }
    }
  }
]
```

### 完整请求示例

下面是一个包含函数定义的完整Python代码示例：

```python
payload = json.dumps({
    "model": "MiniMax-VL-01",
    "messages": [
        {
            "role": "system",
            "content": "MM Intelligent Assistant is a large-scale language model developed by MiniMax and has no interfaces to call other products. MiniMax is a China technology company that has been committed to conducting research related to large models."
        },
        {
            "role": "user",
            "content": "上海今天天气怎么样？"
        }
    ],
    "tools": [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Get the latest weather for a location",
                "parameters": {
                  "type": "object", 
                  "properties": {
                    "location": {
                      "type": "string", 
                      "description": "A certain city, such as Beijing, Shanghai"
                    }
                  }, 
                  "required": ["location"]
                }
            }
        }
    ],
    "tool_choice": "auto",
    "stream": True,
    "max_tokens": 10000,
    "temperature": 0.9,
    "top_p": 1
})
```

## 🔄 函数调用的输入格式

在模型内部处理时，函数定义会被转换为特殊格式并拼接到输入文本中：

```
<beginning_of_sentence>system function_setting=functions
{"name": "get_current_weather", "description": "Get the latest weather for a location", "parameters": {"type": "object", "properties": {"location": {"type": "string", "description": "A certain city, such as Beijing, Shanghai"}}, "required": ["location"]}}<end_of_sentence>
```

注意事项：
1. 函数定义位于系统设置之后、对话数据之前
2. 使用 `function_setting=functions` 标记函数定义区域
3. 每个函数定义使用JSON字符串表示
4. 区域以 `<end_of_sentence>` 结束

## 📤 模型的函数调用输出

当模型决定调用函数时，它会在响应中使用特殊格式输出函数调用信息：

````
<function_call>```typescript
functions.get_current_weather({"location": "上海"})
```
````

"<function_call>" 是 special token, 后面的 "functions.函数名(参数 json 结构体)", 需要字符串匹配出参数, 交外部执行.

## 📥 函数执行结果的处理

当函数调用成功执行后，模型将返回以下格式的输出：

````typescript
```typescript
functions.get_current_weather({"location": "Shanghai"})
```
````

您可以使用以下正则表达式方法提取函数名称和参数，便于后续处理：

````python
def parse_function_calls(content: str):
    """
    解析模型返回的函数调用内容，提取函数名和参数
    
    参数:
        content: 模型返回的原始内容字符串
        
    返回:
        解析后的函数调用信息字典，包含函数名和参数
    """
    # 匹配 typescript 代码块
    pattern = r"```typescript\n(.+?)?\n```"
    matches = re.finditer(pattern, content, re.DOTALL)
    
    for match in matches:
        function_code = match.group(1)
        # 提取函数名和参数
        function_match = re.search(r'functions\.(\w+)\((.+)\)', function_code)
        
        if not function_match:
            continue
            
        function_name = function_match.group(1)
        arguments_str = function_match.group(2)
        
        try:
            # 解析参数JSON
            arguments = json.loads(arguments_str)
            print(f"调用函数: {function_name}, 参数: {arguments}")
            
            # 示例: 处理天气查询函数
            if function_name == "get_current_weather":
                location = arguments.get("location", "未知位置")
                # 构建函数执行结果
                return {
                    "role": "function", 
                    "name": function_name, 
                    "text": json.dumps({
                        "location": location, 
                        "temperature": "25", 
                        "unit": "celsius", 
                        "weather": "晴朗"
                    }, ensure_ascii=False)
                }
        except json.JSONDecodeError as e:
            print(f"参数解析失败: {arguments_str}, 错误: {e}")
    
    return {}
````

成功解析函数调用后，您应将函数执行结果添加到对话历史中，以便模型在后续交互中能够访问和利用这些信息。

## 💻 使用 Transformers 库的函数调用示例

MiniMax-VL-01 官方仓库提供了使用 Transformers 库进行函数调用的完整示例。您可以在 [MiniMaxAI/MiniMax-VL-01 huggingface 仓库](https://huggingface.co/MiniMaxAI/MiniMax-VL-01/blob/main/main.py) 中查看源代码。

以下是使用 Transformers 库实现函数调用的关键部分：

```python
def get_default_tools():
    return [
        {
            "type": "function",
            "function": {
                "name": "get_current_weather",
                "description": "Get the latest weather for a location",
                "parameters": {
                    "type": "object", 
                    "properties": {
                        "location": {
                            "type": "string", 
                            "description": "A certain city, such as Beijing, Shanghai"
                        }
                    }, 
                    "required": ["location"]
                }
            }
        }
    ]

# 加载模型和分词器
tokenizer = AutoTokenizer.from_pretrained(model_id)
prompt = "What's the weather like in Shanghai today?"
messages = [
    {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant created by Minimax based on MiniMax-Text-01 model."}]},
    {"role": "user", "content": [{"type": "text", "text": prompt}]},
]

# 启用函数调用工具
tools = get_default_tools()

# 应用聊天模板，并加入工具定义
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    tools=tools
)

# 生成回复
model_inputs = tokenizer(text, return_tensors="pt").to("cuda")
quantized_model = AutoModelForCausalLM.from_pretrained(
    model_id,
    torch_dtype="bfloat16",
    device_map=device_map,
    quantization_config=quantization_config,
    trust_remote_code=True,
    offload_buffers=True,
)
generation_config = GenerationConfig(
    max_new_tokens=20,
    eos_token_id=200020,
    use_cache=True,
)

# 执行生成
generated_ids = quantized_model.generate(**model_inputs, generation_config=generation_config)
response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
```

### 运行方式

您可以通过以下命令运行示例代码：

```bash
export SAFETENSORS_FAST_GPU=1
python main.py --quant_type int8 --world_size 8 --model_id <model_path> --enable_tools
```

参数说明：
- `--quant_type`: 量化类型，可选 "default" 或 "int8"
- `--world_size`: GPU 数量，int8 量化至少需要 8 个 GPU
- `--model_id`: 模型路径
- `--enable_tools`: 启用函数调用功能

### 结果处理
符合预期的情况下，你将得到以下输出

````base
```typescript
functions.get_current_weather({"location": "Shanghai"})
```
````

你可以使用正则表达式提取出需要调用的 function 和 对应的参数

````python
def try_parse_tool_calls(content: str):
    pattern = r"```typescript\n(.+?)?\n```"
    matches = re.finditer(pattern, content, re.DOTALL)
    
    for match in matches:
        function_code = match.group(1)
        function_match = re.search(r'functions\.(\w+)\((.+)\)', function_code)
        
        if not function_match:
            continue
            
        function_name = function_match.group(1)
        arguments_str = function_match.group(2)
        
        try:
            arguments = json.loads(arguments_str)
            print(f"tool_calls: [{{'type': 'function', 'function': {{'name': '{function_name}', 'arguments': {arguments}}}}}]")
            
            if function_name == "get_current_weather":
                location = arguments.get("location", "Unknown")
                return {"role": "function", "name": function_name, "text": f'{{"location": "{location}", "temperature": "25", "unit": "celsius", "weather": "Sun"}}'}
        except json.JSONDecodeError as e:
            print(f"Failed parse tools: {arguments_str}, Error: {e}")
    
    return {}
````

### 聊天模板

MiniMax-VL-01 使用特定的聊天模板格式处理函数调用。聊天模板定义在 `tokenizer_config.json` 中：

```json
"{% for message in messages %}{% if message['role'] == 'system' %}{{ '<beginning_of_sentence>system ai_setting=assistant\n' }}{% for item in message['content'] %}{% if item.type == 'image' %}<image>{% elif item.type == 'text' %}{{ item.text }}{% endif %}{% endfor %}{{ '<end_of_sentence>\n' }}{% endif %}{% if message['role'] == 'assistant' %}{{ '<beginning_of_sentence>ai name=assistant\n' }}{% for item in message['content'] %}{% if item.type == 'image' %}<image>{% elif item.type == 'text' %}{{ item.text }}{% endif %}{% endfor %}{{ '<end_of_sentence>\n' }}{% endif %}{% if message['role'] == 'user' %}{{ '<beginning_of_sentence>user name=user\n' }}{% for item in message['content'] %}{% if item.type == 'image' %}<image>{% elif item.type == 'text' %}{{ item.text }}{% endif %}{% endfor %}{{ '<end_of_sentence>\n' }}{% endif %}{% if message['role'] == 'function' %}{{ '<beginning_of_sentence>system function_response=functions\n' + '{\"name\": \"' + message['name'] + '\", \"response\": ' + message['content'][0]['text'] + '}' + '<end_of_sentence>\n'}}{% endif %}{% endfor %}{% if tools %}{% for function in tools %}{{ '<beginning_of_sentence>system function_setting=functions\n' + function | tojson + '<end_of_sentence>\n'}}{% endfor %}{% endif %}{% if add_generation_prompt %}{{ '<beginning_of_sentence>ai name=assistant\n' }}{% generation %}{% endgeneration %}{% endif %}"

```

## 📝 注意事项

1. 函数名称应当遵循编程语言的命名规范，避免使用特殊字符
2. 参数描述应当简洁明了，帮助模型理解参数的用途和约束
3. 模型并不保证每次都会调用函数，这取决于用户的输入和模型的判断
4. 函数调用结果应当以结构化方式返回，便于模型理解和处理