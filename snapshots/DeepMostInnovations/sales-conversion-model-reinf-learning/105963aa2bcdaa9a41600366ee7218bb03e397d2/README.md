---
license: mit
library_name: stable-baselines3
tags:
  - reinforcement-learning
  - sales
  - conversation-analysis
  - conversion-prediction
  - ppo
  - turn-by-turn-analysis
language:
  - en
pipeline_tag: reinforcement-learning
inference: true
datasets:
  - synthetic
metrics:
  - name: Conversion Prediction Accuracy
    type: accuracy
    value: 0.967
  - name: Inference Time
    type: speed
    value: 85
widget:
  - text: "user: I'm interested in your product\nassistant: Thank you for your interest. How can I help you today?"
    example_title: Early Stage Prospect
  - text: "user: What's your pricing?\nassistant: Our plans start at $10/user/month"
    example_title: Price Discussion
---

<p align="center">
  <a href="https://www.buymeacoffee.com/nandakishorm" target="_blank">
    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me a Coffee" style="height: 60px !important;width: 217px !important;">
  </a>
</p>


# Sales Conversation Analysis Model - Turn-by-Turn Prediction

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

A reinforcement learning model trained to analyze sales conversations and predict conversion probability evolution turn-by-turn. **Specializes in tracking how each message impacts sales success** using advanced PPO and LLM-powered metrics.

**Paper**: [SalesRLAgent: A Reinforcement Learning Approach for Real-Time Sales Conversion Prediction and Optimization](https://arxiv.org/abs/2503.23303)  
**Author**: Nandakishor M  
**Published**: arXiv:2503.23303

## 🚀 Quick Start with This Model

### Installation
```bash
# Requires Python 3.11 for optimal compatibility
pip install deepmost[gpu]  # Recommended for LLM features
```

### Method 1: Direct URL Download (Easiest)
```python
from deepmost import sales

# Automatically download and use this specific model from Hugging Face
agent = sales.Agent(
    model_path="https://huggingface.co/DeepMostInnovations/sales-conversion-model-reinf-learning/resolve/main/sales_conversion_model.zip",
    llm_model="unsloth/Qwen3-4B-GGUF",  # For dynamic metrics
    auto_download=True  # Downloads and caches the model automatically
)

conversation = [
    "Hello, I'm looking for information on your new AI-powered CRM",
    "You've come to the right place! Our AI CRM helps increase sales efficiency. What challenges are you facing?",
    "We struggle with lead prioritization and follow-up timing",
    "Excellent! Our AI automatically analyzes leads and suggests optimal follow-up times. Would you like to see a demo?",
    "That sounds interesting. What's the pricing like?"
]

# Get turn-by-turn analysis
results = agent.analyze_conversation_progression(conversation, print_results=True)
```

**Output:**
```
Turn 1 (customer): "Hello, I'm looking for information on your new AI-pow..." -> Probability: 0.1744
Turn 2 (sales_rep): "You've come to the right place! Our AI CRM helps increa..." -> Probability: 0.3292
Turn 3 (customer): "We struggle with lead prioritization and follow-up timing" -> Probability: 0.4156
Turn 4 (sales_rep): "Excellent! Our AI automatically analyzes leads and sugge..." -> Probability: 0.3908
Turn 5 (customer): "That sounds interesting. What's the pricing like?" -> Probability: 0.5234

Final Conversion Probability: 52.34%
Final Status: 🟡 Medium
```

> **Note**: When using Method 1 (URL), the model is automatically downloaded and cached locally in `~/.deepmost/models/` for faster subsequent usage.

### Method 2: Clone Repository (For Offline Use)
```bash
git lfs install
git clone https://huggingface.co/DeepMostInnovations/sales-conversion-model-reinf-learning
cd sales-conversion-model-reinf-learning
```

```python
from deepmost import sales

# Use the local model file
agent = sales.Agent(
    model_path="./sales_conversion_model.zip",  # Local file path
    llm_model="unsloth/Qwen3-4B-GGUF"
)

# Same analysis as above
results = agent.analyze_conversation_progression(conversation, print_results=True)
```

## 🎯 Model Architecture & Features

### Technical Details
- **Framework**: Stable Baselines3 (PPO)
- **State Representation**: Multi-modal (embeddings + LLM-derived metrics)
- **Action Space**: Continuous (conversion probability 0-1)
- **Feature Extractor**: Custom Linear layers optimized for conversation analysis
- **Embeddings**: BAAI/bge-m3 (1024-dim) with optional Azure OpenAI support
- **Dynamic Metrics**: LLM-powered customer engagement and sales effectiveness analysis

### Key Capabilities
- **Turn-by-Turn Analysis**: Track probability evolution throughout conversations
- **Real-time Insights**: 85ms inference speed vs 3450ms for GPT-4
- **Dynamic Metrics**: LLM analyzes engagement and effectiveness in real-time
- **Sales Training**: Identify which conversation elements increase conversion
- **A/B Testing**: Compare different sales approaches quantitatively

## 📊 Model Performance

According to the research paper, this model achieves:
- **96.7% accuracy** in conversion prediction
- **34.7% improvement** over LLM-only approaches  
- **85ms inference time** vs 3450ms for GPT-4
- **43.2% increase** in conversion rates when used by sales representatives

### Training Data
- 100,000+ synthetic sales conversations generated using large language models
- Multiple customer types and conversation scenarios
- Semantic embeddings capturing conversation meaning and context
- Dynamic metrics for engagement and sales effectiveness

## 💡 Use Cases

### 1. Sales Training & Coaching
```python
# Analyze what makes conversations successful
training_conversation = [
    {"speaker": "customer", "message": "I'm comparing different CRM vendors"},
    {"speaker": "sales_rep", "message": "Smart approach! What's most important to you?"},
    {"speaker": "customer", "message": "Integration with existing tools"},
    {"speaker": "sales_rep", "message": "We integrate with 200+ tools. Which do you use?"}
]

results = agent.analyze_conversation_progression(training_conversation)

# Identify turns that increased/decreased probability
for i, result in enumerate(results[1:], 1):
    change = result['probability'] - results[i-1]['probability']
    trend = "📈" if change > 0 else "📉" if change < 0 else "➡️"
    print(f"Turn {i+1}: {trend} {change:+.3f} change")
```

### 2. A/B Testing Sales Scripts
```python
# Compare different response strategies
script_a = ["I need pricing", "Our Pro plan is $99/month per user"]
script_b = ["I need pricing", "What's your team size? I'll get you accurate pricing"]

results_a = agent.analyze_conversation_progression(script_a, print_results=False)
results_b = agent.analyze_conversation_progression(script_b, print_results=False)

print(f"Script A: {results_a[-1]['probability']:.2%}")
print(f"Script B: {results_b[-1]['probability']:.2%}")
```

### 3. Real-time Sales Assistance
```python
# Get guidance during live conversations
current_conversation = [
    {"speaker": "customer", "message": "Your solution looks expensive"},
    {"speaker": "sales_rep", "message": "I understand the investment concern..."}
]

results = agent.analyze_conversation_progression(current_conversation, print_results=False)
current_metrics = results[-1]['metrics']

if current_metrics['customer_engagement'] < 0.5:
    print("💡 Suggestion: Customer engagement low. Ask open-ended questions.")
elif current_metrics['sales_effectiveness'] < 0.5:
    print("💡 Suggestion: Refine approach. Focus on value proposition.")
```

## 🔧 Configuration Options

### Backend Selection
```python
# Use open-source backend (recommended)
agent = sales.Agent(
    model_path="./sales_conversion_model.zip",  # This model
    embedding_model="BAAI/bge-m3",
    llm_model="unsloth/Qwen3-4B-GGUF",
    use_gpu=True
)

# Use Azure OpenAI backend (if you have Azure credentials)
agent = sales.Agent(
    model_path="./sales_model.zip",  # Azure-trained variant
    azure_api_key="your_key",
    azure_endpoint="your_endpoint", 
    azure_deployment="text-embedding-3-large",
    llm_model="unsloth/Qwen3-4B-GGUF"
)
```

### LLM Model Options
```python
# Recommended models for dynamic metrics
agent = sales.Agent(
    model_path="./sales_conversion_model.zip",
    llm_model="unsloth/Qwen3-4B-GGUF"          # Recommended
    # llm_model="unsloth/Llama-3.2-3B-Instruct-GGUF"  # Alternative
    # llm_model="unsloth/Llama-3.1-8B-Instruct-GGUF"  # Higher quality
)
```

## 📈 Advanced Analysis

### Conversation Trend Visualization
```python
import matplotlib.pyplot as plt

scenarios = {
    "Successful Sale": [
        "I need a CRM", "What's your team size?", "10 people", 
        "Perfect! Our Pro plan fits 5-20 users", "Sounds good!"
    ],
    "Price Objection": [
        "I need a CRM", "Our premium solution is $99/month", 
        "Too expensive", "Let me show ROI...", "Still too much"
    ]
}

plt.figure(figsize=(12, 6))
for scenario_name, conversation in scenarios.items():
    results = agent.analyze_conversation_progression(conversation, print_results=False)
    probabilities = [r['probability'] for r in results]
    turns = list(range(1, len(probabilities) + 1))
    
    plt.plot(turns, probabilities, marker='o', linewidth=2, label=scenario_name)

plt.xlabel('Conversation Turn')
plt.ylabel('Conversion Probability')
plt.title('Conversion Probability Evolution by Scenario')
plt.legend()
plt.grid(True, alpha=0.3)
plt.show()
```

## 🛠️ Installation & Setup

### Requirements
- **Python 3.11** (required for optimal compatibility)
- PyTorch with optional CUDA support
- Hugging Face Transformers
- llama-cpp-python for LLM features

### GPU Support Setup
```bash
# For NVIDIA CUDA
CMAKE_ARGS="-DGGML_CUDA=on" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir

# For Apple Metal (M1/M2/M3)
CMAKE_ARGS="-DGGML_METAL=on" pip install llama-cpp-python --upgrade --force-reinstall --no-cache-dir

# Install DeepMost
pip install deepmost[gpu]
```

### Verify Installation
```python
import torch
from deepmost import sales

print(f"CUDA Available: {torch.cuda.is_available()}")
info = sales.get_system_info()
print(f"Supported Backends: {info['supported_backends']}")
```

## 📊 Understanding Results

Each turn analysis provides detailed metrics:

```python
{
    'turn': 1,                           # Turn number (1-indexed)
    'speaker': 'customer',               # Who spoke
    'message': 'I need a CRM',          # Actual message
    'probability': 0.3456,              # Conversion probability
    'status': '🟠 Low',                 # Visual indicator
    'metrics': {
        'customer_engagement': 0.6,      # LLM-derived score (0-1)
        'sales_effectiveness': 0.4,      # LLM-derived score (0-1)
        'conversation_length': 3.0,      # Number of messages
        'progress': 0.15                 # Conversation progress
    }
}
```

### Status Indicators
- 🟢 **High** (≥70%): Strong conversion potential
- 🟡 **Medium** (≥50%): Good potential, build value
- 🟠 **Low** (≥30%): Needs improvement, re-engage
- 🔴 **Very Low** (<30%): Poor fit, consider re-qualifying

## 🎓 Research Context

This model implements the SalesRLAgent approach described in the research paper. Key innovations include:

1. **Reinforcement Learning Framework**: PPO-based training for conversation analysis
2. **Multi-modal State Representation**: Combines embeddings with dynamic metrics
3. **Real-time Performance**: Optimized for production sales environments
4. **Turn-by-Turn Analysis**: Novel approach to tracking conversation evolution

### Model Learned Patterns
The model identifies key conversation dynamics:
- Technical buyers respond to detailed feature discussions
- Price-conscious customers need ROI justification
- Early-stage prospects require thorough needs assessment
- Engagement patterns that predict successful outcomes

## 📝 Model Files

This repository contains:
- `sales_conversion_model.zip` - Open-source trained model (recommended)
- `sales_model.zip` - Azure OpenAI trained variant
- Training and inference scripts
- Sample conversation data

## 🤝 Contributing & Usage

### Using in Your Applications
```python
# Initialize with this specific model
agent = sales.Agent(
    model_path="https://huggingface.co/DeepMostInnovations/sales-conversion-model-reinf-learning/resolve/main/sales_conversion_model.zip",
    llm_model="unsloth/Qwen3-4B-GGUF"
)

# Integrate into your sales tools
def analyze_sales_call(conversation_messages):
    results = agent.analyze_conversation_progression(conversation_messages)
    return {
        'final_probability': results[-1]['probability'],
        'trend': 'improving' if results[-1]['probability'] > results[0]['probability'] else 'declining',
        'recommendations': generate_recommendations(results)
    }
```

### Custom Training
To train your own variant:
```bash
git clone https://huggingface.co/datasets/DeepMostInnovations/saas-sales-conversations
python train.py --dataset your_data.csv --model_path custom_model --timesteps 200000
```

## 📄 License & Citation

### License
MIT License - Feel free to use and modify for your needs.

### Citation
If you use this model in your research or applications, please cite:

```bibtex
@article{nandakishor2025salesrlagent,
  title={SalesRLAgent: A Reinforcement Learning Approach for Real-Time Sales Conversion Prediction and Optimization},
  author={Nandakishor, M},
  journal={arXiv preprint arXiv:2503.23303},
  year={2025},
  url={https://arxiv.org/abs/2503.23303}
}
```

## 🔗 Links & Resources

- **PyPI Package**: [https://pypi.org/project/deepmost/](https://pypi.org/project/deepmost/)
- **GitHub Repository**: [https://github.com/DeepMostInnovations/deepmost](https://github.com/DeepMostInnovations/deepmost)
- **Research Paper**: [https://arxiv.org/abs/2503.23303](https://arxiv.org/abs/2503.23303)
- **Training Dataset**: [https://huggingface.co/datasets/DeepMostInnovations/saas-sales-conversations](https://huggingface.co/datasets/DeepMostInnovations/saas-sales-conversations)
- **Documentation**: [GitHub README](https://github.com/DeepMostInnovations/deepmost/blob/main/README.md)
- **Support**: support@deepmost.ai

---

**Focus on what matters: understanding how each conversation turn impacts your sales success.** 🎯

Made with ❤️ by [DeepMost Innovations](https://www.deepmostai.com/)