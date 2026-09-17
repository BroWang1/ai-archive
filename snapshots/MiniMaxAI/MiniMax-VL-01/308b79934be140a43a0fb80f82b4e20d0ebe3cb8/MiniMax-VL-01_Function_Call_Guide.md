# MiniMax-VL-01 Function Call Guide

## 📖 Introduction

MiniMax-VL-01 model supports function calling capability, allowing the model to identify when an external function needs to be called and output function call parameters in a structured format. This document provides detailed instructions on how to use the function calling feature of MiniMax-VL-01.

## 🛠️ Defining Function Calls

### Function Structure

Function calls need to be defined in the `tools` field of the request body. Each function consists of:

```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "function_name",           // Function name, required
        "description": "function_description", // Brief description of the function's purpose
        "parameters": {                    // Parameter definition in JSON Schema format
          "type": "object",                // Overall type, fixed as "object"
          "properties": {                  // Parameter property object
            "param_name": {                // Parameter name
              "description": "Parameter description",    // Description
              "type": "string|number|boolean|array|object" // Type
            }
          },
          "required": ["param1", "param2"]  // List of required parameters
        }
      }
    }
  ]
}
```

### Example

Below is a simple example of a weather query function definition:

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

### Complete Request Example

Below is a complete Python code example that includes function definitions:

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
            "content": "What's the weather like in Shanghai today?"
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

## 🔄 Function Call Input Format

When processed internally by the model, function definitions are converted to a special format and concatenated to the input text:

```
<beginning_of_sentence>system function_setting=functions
{"name": "get_current_weather", "description": "Get the latest weather for a location", "parameters": {"type": "object", "properties": {"location": {"type": "string", "description": "A certain city, such as Beijing, Shanghai"}}, "required": ["location"]}}<end_of_sentence>
```

Important notes:
1. Function definitions are placed after the system settings and before the conversation data
2. Function definitions are marked with `function_setting=functions`
3. Each function is defined as a JSON string
4. The area ends with `<end_of_sentence>`

## 📤 Model Function Call Output

When the model decides to call a function, it outputs the function call information in a special format:

````
<function_call>```typescript
functions.get_current_weather({"location": "Shanghai"})
```
````

"<function_call>" is a special token, followed by "functions.function_name(parameter json structure)". The parameters need to be string-matched and executed externally.

## 📥 Handling Function Results

After a function is successfully executed, the model will return output in the following format:

````typescript
```typescript
functions.get_current_weather({"location": "Shanghai"})
```
````

You can use the following regular expression method to extract the function name and parameters for subsequent processing:

````python
def parse_function_calls(content: str):
    """
    Parse the function call content returned by the model, extract function name and parameters
    
    Parameters:
        content: The original content string returned by the model
        
    Returns:
        A dictionary of parsed function call information, including function name and parameters
    """
    # Match typescript code block
    pattern = r"```typescript\n(.+?)?\n```"
    matches = re.finditer(pattern, content, re.DOTALL)
    
    for match in matches:
        function_code = match.group(1)
        # Extract function name and parameters
        function_match = re.search(r'functions\.(\w+)\((.+)\)', function_code)
        
        if not function_match:
            continue
            
        function_name = function_match.group(1)
        arguments_str = function_match.group(2)
        
        try:
            # Parse parameter JSON
            arguments = json.loads(arguments_str)
            print(f"Function call: {function_name}, Parameters: {arguments}")
            
            # Example: Handle weather query function
            if function_name == "get_current_weather":
                location = arguments.get("location", "Unknown location")
                # Build function execution result
                return {
                    "role": "function", 
                    "name": function_name, 
                    "text": json.dumps({
                        "location": location, 
                        "temperature": "25", 
                        "unit": "celsius", 
                        "weather": "Sunny"
                    }, ensure_ascii=False)
                }
        except json.JSONDecodeError as e:
            print(f"Parameter parsing failed: {arguments_str}, Error: {e}")
    
    return {}
````

After successfully parsing the function call, you should add the function execution result to the conversation history so that the model can access and utilize this information in subsequent interactions.

## 💻 Function Call Example with Transformers Library

The official MiniMax-VL-01 repository provides a complete example of function calling using the Transformers library. You can view the source code in the [MiniMaxAI/MiniMax-VL-01 huggingface repository](https://huggingface.co/MiniMaxAI/MiniMax-VL-01/blob/main/main.py).

The following is the key part of implementing function calls using the Transformers library:

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

# Load model and tokenizer
tokenizer = AutoTokenizer.from_pretrained(model_id)
prompt = "What's the weather like in Shanghai today?"
messages = [
    {"role": "system", "content": [{"type": "text", "text": "You are a helpful assistant created by Minimax based on MiniMax-VL-01 model."}]},
    {"role": "user", "content": [{"type": "text", "text": prompt}]},
]

# Enable function call tools
tools = get_default_tools()

# Apply chat template and add tool definitions
text = tokenizer.apply_chat_template(
    messages,
    tokenize=False,
    add_generation_prompt=True,
    tools=tools
)

# Generate response
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

# Execute generation
generated_ids = quantized_model.generate(**model_inputs, generation_config=generation_config)
response = tokenizer.batch_decode(generated_ids, skip_special_tokens=True)[0]
```

### Running the Example

You can run the example code using the following command:

```bash
export SAFETENSORS_FAST_GPU=1
python main.py --quant_type int8 --world_size 8 --model_id <model_path> --enable_tools
```

Parameter description:
- `--quant_type`: Quantization type, options are "default" or "int8"
- `--world_size`: Number of GPUs, int8 quantization requires at least 8 GPUs
- `--model_id`: Model path
- `--enable_tools`: Enable function call feature

### Result Processing
As expected, you will get the following output:

````base
```typescript
functions.get_current_weather({"location": "Shanghai"})
```
````

You can use regular expressions to extract the function to call and its corresponding parameters:

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

### Chat Template

MiniMax-VL-01 uses a specific chat template format to process function calls. The chat template is defined in `tokenizer_config.json`:

```json
"{% for message in messages %}{% if message['role'] == 'system' %}{{ '<beginning_of_sentence>system ai_setting=assistant\n' }}{% for item in message['content'] %}{% if item.type == 'image' %}<image>{% elif item.type == 'text' %}{{ item.text }}{% endif %}{% endfor %}{{ '<end_of_sentence>\n' }}{% endif %}{% if message['role'] == 'assistant' %}{{ '<beginning_of_sentence>ai name=assistant\n' }}{% for item in message['content'] %}{% if item.type == 'image' %}<image>{% elif item.type == 'text' %}{{ item.text }}{% endif %}{% endfor %}{{ '<end_of_sentence>\n' }}{% endif %}{% if message['role'] == 'user' %}{{ '<beginning_of_sentence>user name=user\n' }}{% for item in message['content'] %}{% if item.type == 'image' %}<image>{% elif item.type == 'text' %}{{ item.text }}{% endif %}{% endfor %}{{ '<end_of_sentence>\n' }}{% endif %}{% if message['role'] == 'function' %}{{ '<beginning_of_sentence>system function_response=functions\n' + '{\"name\": \"' + message['name'] + '\", \"response\": ' + message['content'][0]['text'] + '}' + '<end_of_sentence>\n'}}{% endif %}{% endfor %}{% if tools %}{% for function in tools %}{{ '<beginning_of_sentence>system function_setting=functions\n' + function | tojson + '<end_of_sentence>\n'}}{% endfor %}{% endif %}{% if add_generation_prompt %}{{ '<beginning_of_sentence>ai name=assistant\n' }}{% generation %}{% endgeneration %}{% endif %}"
```

## 📝 Important Notes

1. Function names should follow programming language naming conventions and avoid special characters
2. Parameter descriptions should be concise and help the model understand the parameter's purpose and constraints
3. The model does not guarantee that it will call a function; this depends on the user's input and the model's judgment
4. Function results should be returned in a structured format for easy processing by the model
5. The model might not call a function even if one is provided, depending on whether it determines a function call is appropriate for the given user query 