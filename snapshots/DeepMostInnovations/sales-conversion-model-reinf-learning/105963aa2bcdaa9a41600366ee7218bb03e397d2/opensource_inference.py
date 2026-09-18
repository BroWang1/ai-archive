import argparse
import os
import json
import numpy as np
import torch
from typing import List, Dict
from transformers import (
    AutoTokenizer,
    AutoModel
)
from stable_baselines3 import PPO
from llama_cpp import Llama
import logging


# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)



class SalesConversionPredictor:
    """Sales conversion prediction class using Hugging Face models and llama.cpp"""

    def __init__(self,
                 model_path: str,
                 embedding_model_name: str = "BAAI/bge-large-en-v1.5",
                 llm_gguf_path: str = "path/to/your/llama-3.2-1b-instruct.gguf",
                 use_gpu: bool = True,
                 n_gpu_layers: int = -1,  # -1 for all layers on GPU
                 n_ctx: int = 2048,
                 use_mini_embeddings: bool = True):      # Context window size
        """Initialize with Hugging Face embeddings and llama.cpp LLM"""

        # Set device for embeddings
        self.device = torch.device("cuda" if torch.cuda.is_available() and use_gpu else "cpu")
        logger.info(f"Using device: {self.device}")

        # Initialize embedding model (BAAI/bge-large-en-v1.5)
        logger.info(f"Loading embedding model: {embedding_model_name}")
        self.embedding_tokenizer = AutoTokenizer.from_pretrained(embedding_model_name)
        self.embedding_model = AutoModel.from_pretrained(embedding_model_name).to(self.device)

        # Check if model was trained with mini embeddings
        self.use_mini_embeddings = use_mini_embeddings
        self.embedding_dim = 1024  # BGE-large outputs 1024 dimensions

        # Initialize LLM model using llama-cpp
        logger.info(f"Loading LLM model from GGUF: {llm_gguf_path}")
        self.llm = Llama.from_pretrained(
            repo_id=llm_gguf_path,
            filename="*Q4_K_M.gguf",
            n_gpu_layers=n_gpu_layers if use_gpu else 0,
            n_ctx=n_ctx,
            verbose=False,
            use_mlock=True,  # Keep model in RAM
            n_threads=None   # Use all available threads
        )

        # Load the trained PPO model (force CPU for PPO as recommended)
        ppo_device = "cpu"
        logger.info(f"Loading PPO model on {ppo_device}")
        self.ppo_model = PPO.load(model_path, device=ppo_device)

        # Store conversation states
        self.conversation_states = {}

    def _normalize_history_format(self, history: List[Dict[str, str]]) -> List[Dict[str, str]]:
        """Normalize history format to ensure consistency"""
        normalized_history = []

        for msg in history:
            # Extract role/speaker
            role = msg.get('role', msg.get('speaker', ''))

            # Extract content/message
            content = msg.get('content', msg.get('message', ''))

            # Map role to expected format for the model
            if role in ['user', 'customer']:
                speaker = 'user'
            elif role in ['assistant', 'sales_rep']:
                speaker = 'sales_rep'
            else:
                speaker = role  # Keep as is

            normalized_history.append({
                'speaker': speaker,
                'message': content
            })

        return normalized_history

    def get_embedding(self, text: str) -> np.ndarray:
        """Get embedding for text using BAAI/bge-large-en-v1.5"""
        try:
            # Tokenize input
            inputs = self.embedding_tokenizer(
                text,
                padding=True,
                truncation=True,
                return_tensors='pt',
                max_length=8192
            ).to(self.device)

            # Get model outputs
            with torch.no_grad():
                model_output = self.embedding_model(**inputs)
                # Get sentence embeddings from the model (mean pooling)
                embeddings = model_output.last_hidden_state
                attention_mask = inputs['attention_mask']

                # Apply mean pooling
                input_mask_expanded = attention_mask.unsqueeze(-1).expand(embeddings.size()).float()
                sum_embeddings = torch.sum(embeddings * input_mask_expanded, 1)
                sum_mask = input_mask_expanded.sum(1)

                # Avoid division by zero
                sum_mask = torch.clamp(sum_mask, min=1e-9)
                mean_embeddings = sum_embeddings / sum_mask

                # Normalize embeddings
                embeddings = torch.nn.functional.normalize(mean_embeddings, p=2, dim=1)

                # Move to CPU and convert to numpy
                bge_embedding = embeddings.cpu().numpy()[0].astype(np.float32)

                # BGE-large outputs 1024 dimensions by default
                logger.info(f"BGE embedding shape: {bge_embedding.shape}")

                # Ensure we have exactly 1024 dimensions
                if len(bge_embedding) != 1024:
                    logger.warning(f"Expected 1024 dimensions, got {len(bge_embedding)}")
                    # Pad or truncate to 1024
                    if len(bge_embedding) < 1024:
                        padded = np.zeros(1024, dtype=np.float32)
                        padded[:len(bge_embedding)] = bge_embedding
                        bge_embedding = padded
                    else:
                        bge_embedding = bge_embedding[:1024]

                return bge_embedding

        except Exception as e:
            logger.error(f"Error getting embedding: {str(e)}")
            # Return zeros as fallback with expected dimensions
            return np.zeros(1024, dtype=np.float32)

    def analyze_conversation_metrics(self, history: List[Dict[str, str]]) -> Dict[str, float]:
        """Analyze conversation to extract key metrics using LLM"""
        try:
            # Normalize history format first
            normalized_history = self._normalize_history_format(history)

            # Format conversation for analysis
            conversation_text = ""
            for msg in normalized_history:
                speaker = msg.get('speaker', '')
                message = msg.get('message', '')
                conversation_text += f"{speaker}: {message}\n\n"

            # Create prompt for metrics analysis
            prompt = f"""Analyze this sales conversation and rate each metric from 0.0 to 1.0:

customer_engagement:
sales_effectiveness:

Respond only with numbers in the format shown above.

Conversation:
{conversation_text}"""

            # Get analysis from LLM
            response = self.generate_llm_response(prompt, max_new_tokens=50)
            print("response", response)

            # Parse metrics
            lines = response.strip().split('\n')
            print("lines", lines)

            engagement = 0.5
            effectiveness = 0.5

            for line in lines:
                if 'customer_engagement' in line.lower():
                    try:
                        engagement = float(line.split(':')[-1].strip())
                        # Ensure it's between 0 and 1
                        engagement = max(0.0, min(1.0, engagement))
                    except:
                        pass
                elif 'sales_effectiveness' in line.lower():
                    try:
                        effectiveness = float(line.split(':')[-1].strip())
                        # Ensure it's between 0 and 1
                        effectiveness = max(0.0, min(1.0, effectiveness))
                    except:
                        pass

            return {
                'customer_engagement': engagement,
                'sales_effectiveness': effectiveness,
                'conversation_length': len(normalized_history),
                'outcome': 0.5,  # Unknown at inference time
                'progress': min(1.0, len(normalized_history) / 20)
            }

        except Exception as e:
            logger.error(f"Error analyzing conversation: {str(e)}")
            # Return default values
            return {
                'customer_engagement': 0.5,
                'sales_effectiveness': 0.5,
                'conversation_length': len(history),
                'outcome': 0.5,
                'progress': min(1.0, len(history) / 20)
            }

    def generate_llm_response(self, prompt: str, max_new_tokens: int = 2048) -> str:
        """Generate response using llama-cpp"""
        try:
            # Generate response
            response = self.llm(
                prompt,
                max_tokens=max_new_tokens,
                temperature=0.001,
                top_p=0.95,
                repeat_penalty=1.1,
                stop=["User:", "Assistant:", "\n\n"]
            )

            # Extract generated text
            generated_text = response['choices'][0]['text']

            # Clean up the response
            generated_text = generated_text.strip()

            return generated_text

        except Exception as e:
            logger.error(f"Error generating LLM response: {str(e)}")
            return "I apologize, but I encountered an error generating a response."

    def create_state_vector(self,
                           embedding: np.ndarray,
                           metrics: Dict[str, float],
                           turn_number: int,
                           previous_probs: List[float]) -> np.ndarray:
        """Create state vector for model input"""

        # Create metric array (ensure all 5 metrics are included)
        metric_values = np.array([
            metrics['customer_engagement'],
            metrics['sales_effectiveness'],
            metrics['conversation_length'],
            metrics['outcome'],
            metrics['progress']
        ], dtype=np.float32)

        # Create turn info
        turn_info = np.array([turn_number], dtype=np.float32)

        # Pad probability history
        padded_probs = np.zeros(10, dtype=np.float32)
        if previous_probs:
            # Handle the case where previous_probs might have more than 10 elements
            recent_probs = previous_probs[-10:] if len(previous_probs) > 10 else previous_probs
            padded_probs[:len(recent_probs)] = recent_probs

        # Keep original 1024-dimensional embedding without expanding
        if len(embedding) != 1024:
            logger.warning(f"Unexpected embedding size: {len(embedding)}. Expected 1024. Creating zero embedding.")
            embedding = np.zeros(1024, dtype=np.float32)

        # Total expected: 1024 + 5 + 1 + 10 = 1040
        combined = np.concatenate([
            embedding,          # 1024 dimensions
            metric_values,      # 5 dimensions
            turn_info,          # 1 dimension
            padded_probs        # 10 dimensions
        ])

        logger.info(f"State vector shape: {combined.shape} (expected: 1040)")
        return combined
        
    def predict_conversion(self, conversation_id: str, history: List[Dict[str, str]],
                          new_response: str) -> float:
        """Predict conversion probability for a conversation"""
        logger.info(f"Predicting conversion for conversation {conversation_id}")

        # Normalize history format
        normalized_history = self._normalize_history_format(history)

        # Update history with new response
        updated_history = normalized_history.copy()
        updated_history.append({'speaker': 'sales_rep', 'message': new_response})

        # Get full conversation text for embedding
        full_text = " ".join([msg.get('message', '') for msg in updated_history])

        # Get embedding (1024 dimensions)
        embedding = self.get_embedding(full_text)
        logger.info(f"Embedding shape: {embedding.shape}")

        # Analyze conversation with updated history
        metrics = self.analyze_conversation_metrics(updated_history)
        logger.info(f"Metrics: engagement={metrics['customer_engagement']:.2f}, effectiveness={metrics['sales_effectiveness']:.2f}")

        # Get turn number (each conversation turn includes user + assistant)
        turn = len(updated_history) // 2

        # Get previous probabilities
        if conversation_id in self.conversation_states:
            previous_probs = self.conversation_states[conversation_id]['probabilities']
        else:
            previous_probs = [0.5]  # Initial probability

        # Create state vector
        state_vector = self.create_state_vector(embedding, metrics, turn, previous_probs)

        # Convert to numpy array if it's not already
        if isinstance(state_vector, torch.Tensor):
            state_vector = state_vector.cpu().numpy()

        # Ensure it's a numpy array
        state_vector = np.array(state_vector, dtype=np.float32)

        # Log the final shape
        logger.info(f"Final state vector shape: {state_vector.shape}")

        # Predict using PPO model
        try:
            # Fix deprecation warning by extracting scalar properly
            action, _ = self.ppo_model.predict(state_vector, deterministic=True)

            # Extract the scalar value
            if hasattr(action, 'item'):
                predicted_prob = float(action.item())
            elif isinstance(action, np.ndarray):
                predicted_prob = float(action[0])
            else:
                predicted_prob = float(action)

            # Ensure probability is between 0 and 1
            predicted_prob = max(0.0, min(1.0, predicted_prob))

        except Exception as e:
            logger.error(f"Error during prediction: {str(e)}")
            # Fallback prediction
            predicted_prob = 0.5

        # Update state
        self.conversation_states[conversation_id] = {
            'history': updated_history,
            'probabilities': previous_probs + [predicted_prob]
        }

        logger.info(f"Predicted conversion probability: {predicted_prob:.4f}")
        return predicted_prob

    def generate_response(self, conversation_id: str, history: List[Dict[str, str]],
                         user_input: str, system_prompt: str = None) -> str:
        """Generate a response using llama-cpp and add conversion probability"""

        # Normalize history format
        normalized_history = self._normalize_history_format(history)

        # Format conversation for the LLM
        messages = []

        # Add system prompt if provided
        if system_prompt:
            messages.append(f"System: {system_prompt}\n")
        else:
            messages.append("System: You are a helpful sales assistant.\n")

        # Add conversation history
        for msg in normalized_history:
            speaker = msg.get('speaker', '')
            message = msg.get('message', '')

            if speaker == 'user':
                messages.append(f"User: {message}\n")
            elif speaker == 'sales_rep':
                messages.append(f"Assistant: {message}\n")

        # Add the latest user input
        messages.append(f"User: {user_input}\n")
        messages.append("Assistant: ")

        # Create prompt
        prompt = "".join(messages)

        # Generate LLM response
        llm_response = self.generate_llm_response(prompt, max_new_tokens=2048)
        print(llm_response)

        # Add user message to history for prediction
        history_with_user = history.copy()
        history_with_user.append({'role': 'user', 'content': user_input})

        # Predict conversion probability
        probability = self.predict_conversion(conversation_id, history_with_user, llm_response)

        # Format response with probability
        formatted_response = self.format_response_with_probability(llm_response, probability)

        return formatted_response

    def format_response_with_probability(self, response: str, probability: float) -> str:
        """Format response with conversion probability"""
        probability_pct = probability * 100

        if probability >= 0.38:
            indicator = "🟢 Conversion Highly Likely"
        elif probability >= 0.37:
            indicator = "🟡 Good Conversion Potential"
        elif probability >= 0.35:
            indicator = "🟠 Moderate Conversion Potential"
        else:
            indicator = "🔴 Conversion Unlikely"

        formatted_response = (
            f"{response}\n\n"
            f"---\n"
            f"{indicator} ({probability_pct:.1f}%)\n"
        )

        return formatted_response

    def format_prediction_result(self, probability: float) -> Dict[str, str]:
        """Format prediction result with status and suggestion"""
        probability_pct = probability * 100

        if probability >= 0.38:
            status = "🟢 Conversion Highly Likely"
            suggestion = "Follow up with specific next steps or a call to action."
        elif probability >= 0.37:
            status = "🟡 Good Conversion Potential"
            suggestion = "Address any remaining concerns and guide toward a decision."
        elif probability >= 0.35:
            status = "🟠 Moderate Conversion Potential"
            suggestion = "Focus on building value and addressing objections."
        else:
            status = "🔴 Conversion Unlikely"
            suggestion = "Reframe the conversation or qualify needs better."

        return {
            "probability": probability,
            "formatted_probability": f"{probability_pct:.1f}%",
            "status": status,
            "suggestion": suggestion
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sales Conversion Predictor")
    parser.add_argument(
        "--model_path",
        type=str,
        default="/content/sales-conversion-model-reinf-learning/sales_conversion_model",
        help="Path to the trained PPO model zip file."
    )
    parser.add_argument(
        "--embedding_model_name",
        type=str,
        default="BAAI/bge-m3", # Defaulting to bge-m3 as per example
        help="Name of the Hugging Face embedding model (e.g., 'BAAI/bge-m3', 'BAAI/bge-large-en-v1.5')."
    )
    parser.add_argument(
        "--llm_gguf_path",
        type=str,
        default="unsloth/gemma-3-4b-it-GGUF", # Defaulting to a repo ID as per example
        help="Path to the GGUF LLM model file, a local directory containing GGUF files, or a HuggingFace repo_id."
    )
    parser.add_argument(
        "--no_gpu",
        action="store_true",
        help="Disable GPU usage (use CPU only)."
    )
    parser.add_argument(
        "--n_gpu_layers",
        type=int,
        default=-1, # Default to all layers on GPU for llama.cpp
        help="Number of LLM layers to offload to GPU. -1 for all, 0 for none."
    )
    parser.add_argument(
        "--n_ctx",
        type=int,
        default=2048,
        help="Context window size for the LLM."
    )

    args = parser.parse_args()

    # Initialize predictor with GGUF model
    predictor = SalesConversionPredictor(
        model_path=args.model_path,
        embedding_model_name=args.embedding_model_name,
        llm_gguf_path=args.llm_gguf_path,
        use_gpu=not args.no_gpu,
        n_gpu_layers=args.n_gpu_layers,
        n_ctx=args.n_ctx,
        use_mini_embeddings=True # Kept from original, PPO model should match this if it affects state vector.
                                 # Currently, embedding dim is fixed at 1024 in code.
    )
    # Test with different conversation scenarios
    scenarios = [
        {
            "id": "negative_outcome",
            "history": [
                {"role": "user", "content": "I'm looking for a CRM solution for my startup."},
                {"role": "assistant", "content": "I'd be happy to help you find the right CRM solution. What's the size of your team and what are your main requirements?"},
                {"role": "user", "content": "We're a team of 10 and need lead management and email automation."},
                {"role": "assistant", "content": "Our CRM offers excellent lead management and built-in email automation that would be perfect for a team of 10. Let me show you how it works."},
                {"role": "user", "content": "not interested, bye"}
            ],
            "response": "ok, thank you for the interest"
        },
        {
            "id": "positive_outcome",
            "history": [
                {"role": "user", "content": "I need a project management tool urgently."},
                {"role": "assistant", "content": "I can definitely help you with that! Our tool is designed for quick implementation. What's your main priority?"},
                {"role": "user", "content": "We need to track tasks and deadlines for 20 people."},
                {"role": "assistant", "content": "Perfect! Our solution handles that easily with real-time collaboration features. We can get you set up today with a free trial."},
                {"role": "user", "content": "That sounds great! What's the pricing?"}
            ],
            "response": "For a team of 20, it's $299/month with all features included. You get 14 days free to test everything. Shall I send you the signup link?"
        },
        {
            "id": "neutral_outcome",
            "history": [
                {"role": "user", "content": "Tell me about your software."},
                {"role": "assistant", "content": "Our software helps businesses manage their operations more efficiently. What specific area are you looking to improve?"},
                {"role": "user", "content": "Just browsing for now."}
            ],
            "response": "No problem! Feel free to explore our website for more information, and I'm here if you have any questions."
        }
    ]

    # Test each scenario
    for scenario in scenarios:
        print(f"\n=== Testing Scenario: {scenario['id']} ===")

        # Predict conversion probability
        probability = predictor.predict_conversion(
            conversation_id=scenario['id'],
            history=scenario['history'],
            new_response=scenario['response']
        )

        # Get formatted result
        result = predictor.format_prediction_result(probability)

        # Print results
        print(f"Response: {scenario['response']}")
        print(f"Probability: {result['formatted_probability']}")
        print(f"Status: {result['status']}")
        print(f"Suggestion: {result['suggestion']}")
        print("-" * 50)