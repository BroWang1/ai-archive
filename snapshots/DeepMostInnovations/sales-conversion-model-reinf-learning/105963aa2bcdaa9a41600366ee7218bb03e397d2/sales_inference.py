
import os
import json
import numpy as np
import torch
import torch.nn as nn
from openai import AzureOpenAI # Use the new AzureOpenAI client
from stable_baselines3 import PPO
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import gymnasium as gym
from gymnasium import spaces
from dataclasses import dataclass
from typing import List, Dict, Any
import argparse
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# GPU Setup
if torch.cuda.is_available():
    device = torch.device("cuda")
    logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
else:
    device = torch.device("cpu")
    logger.info("GPU not available, using CPU for inference")

# --- Replicated/Necessary Classes from train.py ---

@dataclass
class ConversationState:
    conversation_history: List[Dict[str, str]]
    embedding: np.ndarray
    conversation_metrics: Dict[str, float]
    turn_number: int
    conversion_probabilities: List[float]

    @property
    def state_vector(self) -> np.ndarray:
        metric_values = np.array(list(self.conversation_metrics.values()), dtype=np.float32)
        turn_info = np.array([self.turn_number], dtype=np.float32)
        padded_probs = np.zeros(10, dtype=np.float32)
        probs_to_pad = self.conversion_probabilities[-10:]
        padded_probs[:len(probs_to_pad)] = probs_to_pad
        
        return np.concatenate([
            self.embedding,
            metric_values,
            turn_info,
            padded_probs
        ]).astype(np.float32)

class CustomLN(BaseFeaturesExtractor):
    def __init__(self, observation_space: gym.spaces.Box, features_dim: int = 128):
        super().__init__(observation_space, features_dim)
        n_input_channels = observation_space.shape[0]
        self.linear_network = nn.Sequential(
            nn.Linear(n_input_channels, 512),
            nn.ReLU(),
            nn.Linear(512, 256),
            nn.ReLU(),
            nn.Linear(256, features_dim),
            nn.ReLU(),
        ).to(device)
        
    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        return self.linear_network(observations)

# --- Azure OpenAI Embedding Function ---

def get_azure_openai_embedding(
    text: str,
    client: AzureOpenAI,
    deployment_name: str
) -> np.ndarray:
    """Gets embedding from Azure OpenAI for the given text."""
    try:
        response = client.embeddings.create(
            input=text,
            model=deployment_name # For Azure, this is the deployment name
        )
        embedding_vector = np.array(response.data[0].embedding, dtype=np.float32)
        logger.debug(f"Received embedding from Azure. Shape: {embedding_vector.shape}")
        return embedding_vector
    except Exception as e:
        logger.error(f"Error getting embedding from Azure OpenAI: {e}")
        # Fallback to a zero vector of a common dimension, or raise error
        # For text-embedding-3-large, dimension is 3072. For ada-002 it's 1536.
        logger.warning("Falling back to zero embedding. This will impact prediction quality.")
        # It's better if the calling function determines the expected fallback dimension
        # based on the actual deployment model, but for simplicity here, we'll assume 3072 if error.
        return np.zeros(3072, dtype=np.float32) # Default to text-embedding-3-large dim

def process_raw_embedding(
    raw_embedding: np.ndarray,
    turn: int,
    max_turns_for_scaling: int,
    target_model_embedding_dim: int, # The dimension model's observation space expects
    use_miniembeddings: bool
) -> np.ndarray:
    """
    Scales and potentially reduces/pads the raw embedding (from Azure)
    to match the model's expected input dimension and characteristics.
    """
    dim_of_raw_embedding = len(raw_embedding)
    logger.debug(f"Processing raw_embedding. Dim: {dim_of_raw_embedding}, Target model dim: {target_model_embedding_dim}, Use mini: {use_miniembeddings}")


    # 1. Apply turn-based dynamic scaling (mimicking training)
    progress = min(1.0, turn / max_turns_for_scaling)
    scaled_embedding = raw_embedding * (0.6 + 0.4 * progress)

    # 2. Adjust dimension to target_model_embedding_dim
    if use_miniembeddings and dim_of_raw_embedding > target_model_embedding_dim:
        logger.debug(f"Applying mini-embedding reduction from {dim_of_raw_embedding} to {target_model_embedding_dim}")
        if target_model_embedding_dim <= 0:
            logger.error("Target model embedding dimension is <=0. Cannot pool.")
            return np.zeros(1, dtype=np.float32) # Return a minimal valid array

        pool_factor = dim_of_raw_embedding // target_model_embedding_dim
        if pool_factor == 0: pool_factor = 1 

        num_elements_to_pool = pool_factor * target_model_embedding_dim
        
        # If not enough elements for perfect pooling (e.g. raw_dim=5, target_dim=3 -> pool_factor=1, num_elements_to_pool=3)
        # or too many (e.g. raw_dim=5, target_dim=2 -> pool_factor=2, num_elements_to_pool=4)
        # We'll pool from the available part of scaled_embedding
        elements_for_pooling = scaled_embedding[:num_elements_to_pool] if num_elements_to_pool <= dim_of_raw_embedding else scaled_embedding
        
        if len(elements_for_pooling) < target_model_embedding_dim : # Not enough elements even to form the target dim vector
            logger.warning(f"Not enough elements ({len(elements_for_pooling)}) to pool into target_dim ({target_model_embedding_dim}). Padding result.")
            reduced_embedding = np.zeros(target_model_embedding_dim, dtype=np.float32)
            fill_len = min(len(elements_for_pooling), target_model_embedding_dim)
            reduced_embedding[:fill_len] = elements_for_pooling[:fill_len] # Simplified: take first elements if pooling fails
        else:
            try:
                # Adjust elements_for_pooling to be perfectly divisible if necessary
                reshapable_length = (len(elements_for_pooling) // pool_factor) * pool_factor
                reshaped_for_pooling = elements_for_pooling[:reshapable_length].reshape(-1, pool_factor) # -1 infers target_model_embedding_dim or similar
                
                # Ensure the first dimension of reshaped matches target_model_embedding_dim
                if reshaped_for_pooling.shape[0] > target_model_embedding_dim:
                    reshaped_for_pooling = reshaped_for_pooling[:target_model_embedding_dim, :]
                elif reshaped_for_pooling.shape[0] < target_model_embedding_dim:
                     # This case should ideally be handled by padding the result
                    logger.warning(f"Pooling resulted in fewer dimensions ({reshaped_for_pooling.shape[0]}) than target ({target_model_embedding_dim}). Will pad.")
                    temp_reduced = np.mean(reshaped_for_pooling, axis=1)
                    reduced_embedding = np.zeros(target_model_embedding_dim, dtype=np.float32)
                    reduced_embedding[:len(temp_reduced)] = temp_reduced
                else:
                    reduced_embedding = np.mean(reshaped_for_pooling, axis=1)

            except ValueError as e: 
                logger.error(f"Reshape for pooling failed: {e}. Lengths: elements_for_pooling={len(elements_for_pooling)}, pool_factor={pool_factor}. Falling back to simple truncation/padding.")
                if dim_of_raw_embedding > target_model_embedding_dim:
                    reduced_embedding = scaled_embedding[:target_model_embedding_dim]
                else: 
                    reduced_embedding = np.zeros(target_model_embedding_dim, dtype=np.float32)
                    reduced_embedding[:dim_of_raw_embedding] = scaled_embedding
        
        processed_embedding = reduced_embedding

    elif dim_of_raw_embedding == target_model_embedding_dim:
        processed_embedding = scaled_embedding
    elif dim_of_raw_embedding > target_model_embedding_dim: 
        logger.debug(f"Truncating embedding from {dim_of_raw_embedding} to {target_model_embedding_dim}")
        processed_embedding = scaled_embedding[:target_model_embedding_dim]
    else: 
        logger.debug(f"Padding embedding from {dim_of_raw_embedding} to {target_model_embedding_dim}")
        processed_embedding = np.zeros(target_model_embedding_dim, dtype=np.float32)
        processed_embedding[:dim_of_raw_embedding] = scaled_embedding
    
    if len(processed_embedding) != target_model_embedding_dim:
        logger.warning(f"Dimension mismatch after processing. Expected {target_model_embedding_dim}, got {len(processed_embedding)}. Adjusting...")
        final_embedding = np.zeros(target_model_embedding_dim, dtype=np.float32)
        fill_len = min(len(processed_embedding), target_model_embedding_dim)
        final_embedding[:fill_len] = processed_embedding[:fill_len]
        return final_embedding.astype(np.float32)

    return processed_embedding.astype(np.float32)


# --- Main Prediction Logic ---

def predict_conversation_trajectory(
    model: PPO,
    azure_openai_client: AzureOpenAI,
    azure_deployment_name: str,
    conversation_messages: List[Dict[str, str]],
    initial_metrics: Dict[str, float],
    model_expected_embedding_dim: int,
    use_miniembeddings_on_azure_emb: bool,
    max_conversation_turns_scaling: int = 20
):
    logger.info(f"Starting prediction. Model expects embedding_dim: {model_expected_embedding_dim}. use_mini_on_azure: {use_miniembeddings_on_azure_emb}")

    current_conversation_history_text = []
    current_conversation_history_struct = []
    agent_predicted_probabilities = []
    output_predictions = []

    num_metrics = 5 
    expected_obs_dim = model_expected_embedding_dim + num_metrics + 1 + 10 
    if model.observation_space.shape[0] != expected_obs_dim:
        logger.error(f"CRITICAL: Model observation space dimension mismatch! Model expects total obs_dim {model.observation_space.shape[0]}, "
                     f"but calculations suggest {expected_obs_dim} based on model_expected_embedding_dim={model_expected_embedding_dim}. "
                     f"Ensure --embedding_dim matches the dimension used for the embedding component during training.")
        inferred_emb_dim = model.observation_space.shape[0] - num_metrics - 1 - 10
        logger.error(f"The model might have been trained with an embedding component of dimension: {inferred_emb_dim}")
        raise ValueError("Observation space dimension mismatch. Check --embedding_dim.")

    for turn_idx, message_info in enumerate(conversation_messages):
        speaker = message_info.get("speaker", "unknown")
        message = message_info.get("message", "")
        
        current_conversation_history_struct.append(message_info)
        current_conversation_history_text.append(f"{speaker}: {message}")
        
        text_for_embedding = "\n".join(current_conversation_history_text)
        if not text_for_embedding.strip(): 
            logger.warning("Empty text for embedding at turn_idx %s, using zero vector from Azure (or fallback).", turn_idx)
            # Attempt to get an embedding for a neutral character to get shape, or use a known default.
            # This path should be rare if conversations always start with text.
            raw_turn_embedding = get_azure_openai_embedding(" ", azure_openai_client, azure_deployment_name)
            if np.all(raw_turn_embedding == 0): # If fallback was hit
                logger.warning("Fallback zero embedding used for empty text. Assuming 3072 dim if Azure call failed internally.")
                raw_turn_embedding = np.zeros(3072, dtype=np.float32) # Default to text-embedding-3-large dim
        else:
            raw_turn_embedding = get_azure_openai_embedding(
                text_for_embedding,
                azure_openai_client,
                azure_deployment_name
            )
        
        final_turn_embedding = process_raw_embedding(
            raw_turn_embedding,
            turn_idx,
            max_conversation_turns_scaling,
            model_expected_embedding_dim,
            use_miniembeddings_on_azure_emb
        )
        
        if final_turn_embedding.shape[0] != model_expected_embedding_dim:
            logger.error(f"Embedding dimension mismatch after processing. Expected {model_expected_embedding_dim}, got {final_turn_embedding.shape[0]}. Critical error.")
            raise ValueError("Embedding dimension error after processing.")

        metrics = initial_metrics.copy()
        metrics['conversation_length'] = len(current_conversation_history_struct)
        metrics['progress'] = min(1.0, turn_idx / max_conversation_turns_scaling)
        if 'outcome' not in metrics: metrics['outcome'] = 0.5 

        state = ConversationState(
            conversation_history=current_conversation_history_struct,
            embedding=final_turn_embedding,
            conversation_metrics=metrics,
            turn_number=turn_idx,
            conversion_probabilities=agent_predicted_probabilities
        )
        
        observation_vector = state.state_vector
        
        if observation_vector.shape[0] != model.observation_space.shape[0]:
            logger.error(f"Observation vector dimension mismatch before prediction! Expected {model.observation_space.shape[0]}, Got {observation_vector.shape[0]}")
            raise ValueError("Observation vector dimension mismatch.")

        action_probs, _ = model.predict(observation_vector, deterministic=True)
        predicted_prob_this_turn = float(action_probs[0])
        
        output_predictions.append({
            "turn": turn_idx + 1,
            "speaker": speaker,
            "message": message,
            "predicted_conversion_probability": predicted_prob_this_turn
        })
        agent_predicted_probabilities.append(predicted_prob_this_turn)

    return output_predictions


def main():
    parser = argparse.ArgumentParser(description="Run inference with Azure OpenAI embeddings.")
    parser.add_argument("--model_path", type=str, required=True, help="Path to the trained PPO model (.zip file).")
    parser.add_argument("--conversation_json", type=str, required=True,
                        help="JSON string or path to JSON file for the conversation.")
    
    parser.add_argument("--azure_api_key", type=str, required=True, help="Azure OpenAI API Key.")
    parser.add_argument("--azure_endpoint", type=str, required=True, help="Azure OpenAI Endpoint URL.")
    parser.add_argument("--azure_deployment_name", type=str, required=True, help="Azure OpenAI embedding deployment name (e.g., for text-embedding-3-large).")
    parser.add_argument("--azure_api_version", type=str, default="2023-12-01-preview", help="Azure OpenAI API Version (e.g., 2023-05-15 or 2023-12-01-preview for newer models).")

    parser.add_argument("--embedding_dim", type=int, required=True,
                        help="The dimension of the embedding vector component EXPECTED BY THE PPO MODEL's observation space.")
    parser.add_argument("--use_miniembeddings", action="store_true",
                        help="Flag if the Azure OpenAI embedding should be reduced (if larger than --embedding_dim) using the mini-embedding logic.")
    parser.add_argument("--max_turns_scaling", type=int, default=20,
                        help="The 'max_turns' value used for progress scaling (default: 20).")
    args = parser.parse_args()

    try:
        azure_client = AzureOpenAI(
            api_key=args.azure_api_key,
            azure_endpoint=args.azure_endpoint,
            api_version=args.azure_api_version
        )
        logger.info("Testing Azure OpenAI connection by embedding a short string...")
        test_embedding = get_azure_openai_embedding("test connection", azure_client, args.azure_deployment_name)
        logger.info(f"Azure OpenAI connection successful. Received test embedding of shape: {test_embedding.shape}")
        # This also implicitly tells us the dimension of the deployed Azure model
        # We could store test_embedding.shape[0] and use it, but process_raw_embedding gets it anyway.

    except Exception as e:
        logger.error(f"Failed to initialize or test Azure OpenAI client: {e}")
        return

    try:
        if os.path.exists(args.conversation_json):
            with open(args.conversation_json, 'r') as f:
                sample_conversation = json.load(f)
        else:
            sample_conversation = json.loads(args.conversation_json)
        if not isinstance(sample_conversation, list):
            raise ValueError("Conversation JSON must be a list of message objects.")
    except Exception as e:
        logger.error(f"Error loading conversation JSON: {e}")
        return

    initial_metrics = {
        'customer_engagement': 0.5, 'sales_effectiveness': 0.5,
        'conversation_length': 0, 'outcome': 0.5, 'progress': 0.0
    }

    try:
        model = PPO.load(args.model_path, device=device)
        logger.info(f"Model loaded from {args.model_path}")
        logger.info(f"Model's observation space shape: {model.observation_space.shape}")
    except Exception as e:
        logger.error(f"Error loading PPO model: {e}")
        return

    predictions = predict_conversation_trajectory(
        model,
        azure_client,
        args.azure_deployment_name,
        sample_conversation,
        initial_metrics,
        model_expected_embedding_dim=args.embedding_dim,
        use_miniembeddings_on_azure_emb=args.use_miniembeddings,
        max_conversation_turns_scaling=args.max_turns_scaling
    )

    print("\n--- Conversation Predictions (with Azure OpenAI Embeddings) ---")
    for pred_info in predictions:
        print(f"Turn {pred_info['turn']} ({pred_info['speaker']}): \"{pred_info['message'][:60]}...\" -> Probability: {pred_info['predicted_conversion_probability']:.4f}")

if __name__ == "__main__":
    # python inference_azure_openai_v2.py \
    #   --model_path models/sales_conversion_model.zip \
    #   --conversation_json sample_conv.json \
    #   --azure_api_key "YOUR_AZURE_API_KEY" \
    #   --azure_endpoint "YOUR_AZURE_ENDPOINT" \
    #   --azure_deployment_name "your-text-embedding-3-large-deployment-name" \
    #   --azure_api_version "2023-12-01-preview" \
    #   --embedding_dim 1024 \
    #   --use_miniembeddings 
    #
    # (The above example assumes your PPO model was trained expecting 1024-dim embeddings,
    # and text-embedding-3-large (3072-dim) will be reduced to 1024)
    #
    # If your PPO model was trained directly with 3072-dim embeddings:
    # python inference_azure_openai_v2.py \
    #   --model_path models/sales_conversion_model.zip \
    #   --conversation_json sample_conv.json \
    #   --azure_api_key "YOUR_AZURE_API_KEY" \
    #   --azure_endpoint "YOUR_AZURE_ENDPOINT" \
    #   --azure_deployment_name "your-text-embedding-3-large-deployment-name" \
    #   --azure_api_version "2023-12-01-preview" \
    #   --embedding_dim 3072 
    #   (Do NOT specify --use_miniembeddings in this case, as 3072 (Azure) == 3072 (model))

    main()