import os
import json
import pandas as pd
import numpy as np
from typing import List, Dict, Tuple, Optional, Any
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import Dataset, DataLoader
from sklearn.model_selection import train_test_split
from stable_baselines3 import PPO
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from stable_baselines3.common.utils import set_random_seed
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.callbacks import EvalCallback, CheckpointCallback
import gymnasium as gym
from gymnasium import spaces
from dataclasses import dataclass
import logging
import random
from tqdm import tqdm
import time
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime
import argparse
import psutil
import gc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("sales_training.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

# GPU Setup
if torch.cuda.is_available():
    device = torch.device("cuda")
    logger.info(f"Using GPU: {torch.cuda.get_device_name(0)}")
else:
    device = torch.device("cpu")
    logger.info("GPU not available, using CPU")

@dataclass
class ConversationState:
    """Represents the state of a sales conversation for the RL environment."""
    conversation_history: List[Dict[str, str]]
    embedding: np.ndarray
    conversation_metrics: Dict[str, float]
    turn_number: int
    conversion_probabilities: List[float]
    
    @property
    def state_vector(self) -> np.ndarray:
        """Create a flat vector representation of the conversation state."""
        # Combine embedding with conversation metrics and history stats
        metric_values = np.array(list(self.conversation_metrics.values()), dtype=np.float32)
        turn_info = np.array([self.turn_number], dtype=np.float32)
        prob_history = np.array(self.conversion_probabilities, dtype=np.float32)
        
        # Pad probability history to a fixed size if needed
        padded_probs = np.zeros(10, dtype=np.float32)
        padded_probs[:len(prob_history)] = prob_history[-10:] if len(prob_history) > 10 else prob_history
        
        return np.concatenate([
            self.embedding,
            metric_values,
            turn_info,
            padded_probs
        ])

# Custom neural network for feature extraction - optimized for GPU
class CustomLN(BaseFeaturesExtractor):
    """Custom feature extractor for the embedding vector using linear layers."""
    
    def __init__(self, observation_space: gym.spaces.Box, features_dim: int = 128):
        super().__init__(observation_space, features_dim)
        
        # Get the input dimension from the observation space
        n_input_channels = observation_space.shape[0]
        
        # Create a network with linear layers
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

class SalesConversionEnv(gym.Env):
    """Reinforcement learning environment for sales conversation prediction."""
    
    def __init__(self, conversations_df: pd.DataFrame, use_miniembeddings=True):
        """
        Initialize the environment.
        
        Args:
            conversations_df: DataFrame containing sales conversations
            use_miniembeddings: If True, reduce embedding dimension to save memory
        """
        super().__init__()
        
        self.conversations_df = conversations_df
        self.current_conversation_idx = 0
        self.max_turns = 20
        self.use_miniembeddings = use_miniembeddings
        
        # Get embedding dimension
        embedding_cols = [col for col in conversations_df.columns if col.startswith('embedding_')]
        self.full_embedding_dim = len(embedding_cols)
        
        # Option to use reduced embedding dimension to save memory
        if use_miniembeddings:
            self.embedding_dim = min(1024, self.full_embedding_dim)  # Use 1024 instead of 256
            logger.info(f"Using reduced embeddings: {self.full_embedding_dim} -> {self.embedding_dim}")
        else:
            self.embedding_dim = self.full_embedding_dim
        
        # Action space: Probability of conversion (0-1)
        self.action_space = spaces.Box(
            low=np.array([0.0]),
            high=np.array([1.0]),
            dtype=np.float32
        )
        
        # Observation space: Embeddings + metrics + turn info + probability history
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=(self.embedding_dim + 5 + 1 + 10,),  # Embeddings + 5 metrics + turn number + prob history
            dtype=np.float32
        )
        
        self.current_turn = 0
        self.conversation_state = None
        self.true_probabilities = None
        
        logger.info(f"Initialized SalesConversionEnv with {len(conversations_df)} conversations")
    
    def _parse_conversation(self, conversation_idx: int) -> Tuple[List[Dict[str, str]], Dict[str, float], Dict[int, float]]:
        """Parse conversation data from the dataset."""
        row = self.conversations_df.iloc[conversation_idx]
        
        # Parse messages
        try:
            messages = json.loads(row['conversation'])
        except (json.JSONDecodeError, TypeError) as e:
            # Create a fallback simple conversation
            messages = [
                {"speaker": "customer", "message": "I'm interested in your product."},
                {"speaker": "sales_rep", "message": "Thank you for your interest. How can I help?"}
            ]
        
        # Parse metrics
        metrics = {
            'customer_engagement': float(row.get('customer_engagement', 0.5)),
            'sales_effectiveness': float(row.get('sales_effectiveness', 0.5)),
            'conversation_length': int(row.get('conversation_length', len(messages))),
            'outcome': float(row.get('outcome', 0.5)),
            'progress': 0.0  # Will be updated during stepping
        }
        
        # Parse probability trajectory
        try:
            probability_trajectory = json.loads(row['probability_trajectory'])
            # Convert string keys to integers
            probability_trajectory = {int(k): float(v) for k, v in probability_trajectory.items()}
        except (json.JSONDecodeError, TypeError, KeyError) as e:
            # If no trajectory or error, create a simple one
            if row.get('outcome', 0) == 1:
                probability_trajectory = {i: min(0.5 + i * 0.05, 0.95) for i in range(len(messages))}
            else:
                probability_trajectory = {i: max(0.5 - i * 0.05, 0.05) for i in range(len(messages))}
        
        return messages, metrics, probability_trajectory
    
    def _get_embedding_for_turn(self, conversation_idx: int, turn: int) -> np.ndarray:
        """Get the embedding for a specific conversation at a specific turn."""
        row = self.conversations_df.iloc[conversation_idx]
        
        # Get all embedding values
        embedding_cols = [col for col in row.index if col.startswith('embedding_')]
        try:
            embedding = row[embedding_cols].values.astype(np.float32)
            
            # Check for NaN or Inf values
            if np.isnan(embedding).any() or np.isinf(embedding).any():
                embedding = np.zeros(len(embedding_cols), dtype=np.float32)
        except Exception as e:
            embedding = np.zeros(len(embedding_cols), dtype=np.float32)
        
        # Use dimensionality reduction for very large embeddings to save memory
        if self.use_miniembeddings and len(embedding) > self.embedding_dim:
            # Simple dimensionality reduction - average pooling
            embedding = np.array([
                np.mean(embedding[i:i+self.full_embedding_dim//self.embedding_dim])
                for i in range(0, self.full_embedding_dim, self.full_embedding_dim//self.embedding_dim)
            ][:self.embedding_dim])
        
        # Simple scaling based on turn progress to simulate evolving embeddings
        progress = min(1.0, turn / self.max_turns)
        scaled_embedding = embedding * (0.6 + 0.4 * progress)
        
        return scaled_embedding
    
    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, Dict]:
        """Reset the environment to start a new episode."""
        super().reset(seed=seed)
        
        # Select a random conversation
        self.current_conversation_idx = np.random.randint(0, len(self.conversations_df))
        self.current_turn = 0
        
        # Parse conversation data
        messages, metrics, probability_trajectory = self._parse_conversation(self.current_conversation_idx)
        self.true_probabilities = probability_trajectory
        self.max_turns = min(20, len(messages))
        
        # Initialize state
        embedding = self._get_embedding_for_turn(self.current_conversation_idx, 0)
        metrics = metrics.copy()
        metrics['progress'] = 0.0
        
        self.conversation_state = ConversationState(
            conversation_history=messages[:1] if messages else [],
            embedding=embedding,
            conversation_metrics=metrics,
            turn_number=0,
            conversion_probabilities=[self.true_probabilities.get(0, 0.5)]
        )
        
        return self.conversation_state.state_vector, {}
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """Step the environment forward by one turn."""
        # Extract predicted probability
        predicted_prob = float(action[0])
        
        # Get true probability for current turn
        true_prob = self.true_probabilities.get(self.current_turn, 0.5)
        
        # Calculate reward based on prediction accuracy
        reward = 1.0 - abs(predicted_prob - true_prob)
        
        # Apply higher reward/penalty at final step based on outcome
        if self.current_turn == self.max_turns - 1:
            outcome = self.conversation_state.conversation_metrics['outcome']
            # Stronger penalty for confident wrong predictions
            if outcome == 1 and predicted_prob < 0.5:
                reward -= 1.0 * (0.5 - predicted_prob)
            elif outcome == 0 and predicted_prob > 0.5:
                reward -= 1.0 * (predicted_prob - 0.5)
        
        # Update turn
        self.current_turn += 1
        done = self.current_turn >= self.max_turns
        
        if not done:
            # Update state
            embedding = self._get_embedding_for_turn(self.current_conversation_idx, self.current_turn)
            metrics = self.conversation_state.conversation_metrics.copy()
            metrics['progress'] = self.current_turn / self.max_turns
            
            messages = self._parse_conversation(self.current_conversation_idx)[0]
            history = messages[:self.current_turn+1] if self.current_turn+1 < len(messages) else messages
            
            # Add current prediction to history
            conv_probs = self.conversation_state.conversion_probabilities.copy()
            conv_probs.append(predicted_prob)
            
            self.conversation_state = ConversationState(
                conversation_history=history,
                embedding=embedding,
                conversation_metrics=metrics,
                turn_number=self.current_turn,
                conversion_probabilities=conv_probs
            )
        
        return self.conversation_state.state_vector, reward, done, False, {'true_prob': true_prob}

class SalesRLTrainer:
    """Trainer for the sales conversion prediction RL model."""
    
    def __init__(self, dataset_path: str, model_save_path: str = "sales_conversion_model", 
                 use_miniembeddings: bool = True, batch_size: int = 64):
        """
        Initialize the trainer.
        
        Args:
            dataset_path: Path to the sales conversation dataset
            model_save_path: Path to save trained model
            use_miniembeddings: Whether to use reduced embeddings to save memory
            batch_size: Batch size for training
        """
        self.dataset_path = dataset_path
        self.model_save_path = model_save_path
        self.use_miniembeddings = use_miniembeddings
        self.batch_size = batch_size
        self.df = None
        self.model = None
        self.train_df = None
        self.val_df = None
        
        # Create directory for models and logs
        os.makedirs(os.path.dirname(model_save_path) if os.path.dirname(model_save_path) else ".", exist_ok=True)
        os.makedirs("logs", exist_ok=True)
        
        logger.info(f"Initialized SalesRLTrainer with dataset: {dataset_path}")
        
        # Monitor memory usage
        self._log_memory_usage("Initial")
    
    def _log_memory_usage(self, step=""):
        """Log current memory usage."""
        process = psutil.Process(os.getpid())
        cpu_mem = process.memory_info().rss / 1024 / 1024  # MB
        
        gpu_mem = 0
        if torch.cuda.is_available():
            gpu_mem = torch.cuda.memory_allocated() / 1024 / 1024  # MB
        
        logger.info(f"Memory usage [{step}] - CPU: {cpu_mem:.2f} MB, GPU: {gpu_mem:.2f} MB")
    
    def load_dataset(self, validation_split=0.1, sample_size=None):
        """
        Load and preprocess the sales conversation dataset.
        
        Args:
            validation_split: Proportion of data for validation
            sample_size: Optional limit on dataset size to save memory
        """
        logger.info(f"Loading dataset from {self.dataset_path}")
        try:
            # Read dataset in chunks to reduce memory usage
            chunks = []
            for chunk in pd.read_csv(self.dataset_path, chunksize=10000):
                chunks.append(chunk)
                
                # If sample size specified, break after enough chunks
                if sample_size and sum(len(c) for c in chunks) >= sample_size:
                    break
            
            self.df = pd.concat(chunks)
            
            # If sample size specified, limit the dataset
            if sample_size and len(self.df) > sample_size:
                self.df = self.df.sample(sample_size, random_state=42)
            
            logger.info(f"Loaded dataset with shape: {self.df.shape}")
            
            # Validate embedding columns
            embedding_cols = [col for col in self.df.columns if col.startswith('embedding_')]
            if not embedding_cols:
                raise ValueError("No embedding columns found in the dataset")
            
            logger.info(f"Found {len(embedding_cols)} embedding dimensions")
            
            # Clean the dataframe to reduce memory usage
            for col in self.df.columns:
                if col.startswith('embedding_'):
                    # Convert embedding columns to float32
                    self.df[col] = self.df[col].astype(np.float32)
                elif col in ['outcome', 'customer_engagement', 'sales_effectiveness']:
                    # Convert numeric columns to float32
                    self.df[col] = self.df[col].astype(np.float32)
                elif col == 'conversation_length':
                    # Convert to int32
                    self.df[col] = self.df[col].astype(np.int32)
            
            # Split into train and validation sets
            train_idx, val_idx = train_test_split(
                np.arange(len(self.df)),
                test_size=validation_split,
                random_state=42
            )
            
            self.train_df = self.df.iloc[train_idx].reset_index(drop=True)
            self.val_df = self.df.iloc[val_idx].reset_index(drop=True)
            
            logger.info(f"Split dataset: {len(self.train_df)} training samples, {len(self.val_df)} validation samples")
            
            # Monitor memory
            self._log_memory_usage("After dataset load")
            
            # Free up memory
            gc.collect()
            
        except Exception as e:
            logger.error(f"Error loading dataset: {str(e)}")
            raise
    
    def train(self, total_timesteps: int = 100000, learning_rate: float = 0.0003, n_envs: int = 1):
        """
        Train the RL model with GPU acceleration.
        
        Args:
            total_timesteps: Total timesteps for training
            learning_rate: Learning rate for the optimizer
            n_envs: Number of parallel environments
        """
        if self.train_df is None:
            self.load_dataset()
        
        # Use only 1 environment with GPU for better memory efficiency
        n_envs = 1 if torch.cuda.is_available() else n_envs
        
        # Create training environment
        def make_env(df_subset):
            """Create environment with a subset of data."""
            def _init():
                return SalesConversionEnv(df_subset, use_miniembeddings=self.use_miniembeddings)
            return _init
        
        # Create subsets of data for each environment
        if n_envs > 1:
            subset_size = len(self.train_df) // n_envs
            env_makers = [
                make_env(self.train_df.iloc[i*subset_size:(i+1)*subset_size if i < n_envs-1 else len(self.train_df)])
                for i in range(n_envs)
            ]
            env = SubprocVecEnv(env_makers)
        else:
            env = DummyVecEnv([make_env(self.train_df)])
        
        # Create validation environment
        val_env = DummyVecEnv([make_env(self.val_df)])
        
        # Configure policy network
        policy_kwargs = dict(
            activation_fn=nn.ReLU,
            net_arch=[dict(pi=[128, 64], vf=[128, 64])],  # Smaller network to save memory
            features_extractor_class=CustomLN,
            features_extractor_kwargs=dict(features_dim=64)
        )
        
        # Initialize model with GPU support
        self.model = PPO(
            "MlpPolicy",
            env,
            policy_kwargs=policy_kwargs,
            learning_rate=learning_rate,
            n_steps=512,  # Smaller n_steps to save memory
            batch_size=self.batch_size,
            n_epochs=5,  # Fewer epochs to speed up training
            gamma=0.99,
            gae_lambda=0.95,
            clip_range=0.2,
            clip_range_vf=0.2,
            ent_coef=0.01,
            vf_coef=0.5,
            max_grad_norm=0.5,
            tensorboard_log="./logs/",
            verbose=1,
            device=device  # Use GPU if available
        )
        
        # Set up callbacks
        eval_callback = EvalCallback(
            val_env,
            best_model_save_path=f"{os.path.dirname(self.model_save_path)}/best_model",
            log_path="./logs/",
            eval_freq=max(2000, total_timesteps // 20),  # Evaluate less frequently to save time
            deterministic=True,
            render=False
        )
        
        checkpoint_callback = CheckpointCallback(
            save_freq=max(5000, total_timesteps // 10),  # Save less frequently to reduce I/O
            save_path="./logs/checkpoints/",
            name_prefix="sales_model",
            save_replay_buffer=False,
            save_vecnormalize=False
        )
        
        # Monitor memory before training
        self._log_memory_usage("Before training")
        
        logger.info(f"Starting training for {total_timesteps} timesteps with {n_envs} environments on {device}")
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=[eval_callback, checkpoint_callback],
            progress_bar=True
        )
        
        # Save final model
        self.model.save(self.model_save_path)
        logger.info(f"Model saved to {self.model_save_path}")
        
        # Monitor memory after training
        self._log_memory_usage("After training")
        
        # Clean up to free memory
        env.close()
        val_env.close()
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
    
    def evaluate(self, num_episodes: int = 100):
        """Evaluate the trained model."""
        if self.model is None:
            logger.info(f"Loading model from {self.model_save_path}")
            self.model = PPO.load(self.model_save_path, device=device)
        
        if self.val_df is None:
            self.load_dataset()
        
        # Create environment
        env = SalesConversionEnv(self.val_df, use_miniembeddings=self.use_miniembeddings)
        
        logger.info(f"Evaluating model on {num_episodes} episodes")
        
        rewards = []
        accuracies = []
        predictions = []
        true_outcomes = []
        
        for i in tqdm(range(num_episodes), desc="Evaluating"):
            obs, _ = env.reset()
            done = False
            episode_reward = 0
            episode_predictions = []
            true_values = []
            
            while not done:
                action, _ = self.model.predict(obs, deterministic=True)
                obs, reward, done, _, info = env.step(action)
                
                episode_reward += reward
                episode_predictions.append(float(action[0]))
                true_values.append(info['true_prob'])
            
            rewards.append(episode_reward)
            
            # Calculate accuracy based on final prediction
            final_pred = episode_predictions[-1]
            outcome = env.conversation_state.conversation_metrics['outcome']
            correct = (final_pred >= 0.5 and outcome == 1) or (final_pred < 0.5 and outcome == 0)
            accuracies.append(int(correct))
            
            predictions.append(final_pred)
            true_outcomes.append(1 if outcome >= 0.5 else 0)
        
        mean_reward = np.mean(rewards)
        mean_accuracy = np.mean(accuracies)
        
        # Calculate additional metrics
        true_positives = sum(1 for p, t in zip(predictions, true_outcomes) if p >= 0.5 and t == 1)
        false_positives = sum(1 for p, t in zip(predictions, true_outcomes) if p >= 0.5 and t == 0)
        true_negatives = sum(1 for p, t in zip(predictions, true_outcomes) if p < 0.5 and t == 0)
        false_negatives = sum(1 for p, t in zip(predictions, true_outcomes) if p < 0.5 and t == 1)
        
        precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) > 0 else 0
        recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) > 0 else 0
        f1_score = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
        
        logger.info(f"Evaluation results:")
        logger.info(f"- Mean reward: {mean_reward:.4f}")
        logger.info(f"- Prediction accuracy: {mean_accuracy:.4f}")
        logger.info(f"- Precision: {precision:.4f}")
        logger.info(f"- Recall: {recall:.4f}")
        logger.info(f"- F1 Score: {f1_score:.4f}")
        
        return {
            'mean_reward': float(mean_reward),
            'accuracy': float(mean_accuracy),
            'precision': float(precision),
            'recall': float(recall),
            'f1_score': float(f1_score)
        }

def main():
    """Main function to run the training pipeline."""
    parser = argparse.ArgumentParser(description="Train a sales conversion prediction model")
    parser.add_argument("--dataset", type=str, required=True,
                      help="Path to the dataset CSV file")
    parser.add_argument("--model_path", type=str, default="models/sales_conversion_model",
                      help="Path to save the trained model")
    parser.add_argument("--timesteps", type=int, default=50000,
                      help="Number of timesteps to train for")
    parser.add_argument("--learning_rate", type=float, default=0.0003,
                      help="Learning rate for training")
    parser.add_argument("--batch_size", type=int, default=64,
                      help="Batch size for training")
    parser.add_argument("--sample_size", type=int, default=None,
                      help="Limit dataset size to save memory (e.g., 10000)")
    parser.add_argument("--evaluate_only", action="store_true",
                      help="Only evaluate an existing model without training")
    parser.add_argument("--num_eval_episodes", type=int, default=50,
                      help="Number of episodes for evaluation")
    parser.add_argument("--use_small_embedding", action="store_true",
                      help="Use reduced embedding dimension to save memory")
    
    args = parser.parse_args()
    
    # Initialize trainer
    trainer = SalesRLTrainer(
        dataset_path=args.dataset,
        model_save_path=args.model_path,
        use_miniembeddings=args.use_small_embedding,
        batch_size=args.batch_size
    )
    
    # Load dataset with optional sample limit
    trainer.load_dataset(sample_size=args.sample_size)
    
    # Train or evaluate
    if not args.evaluate_only:
        trainer.train(
            total_timesteps=args.timesteps,
            learning_rate=args.learning_rate
        )
    
    # Evaluate
    eval_results = trainer.evaluate(num_episodes=args.num_eval_episodes)
    
    # Print evaluation results
    print("\nEvaluation Results:")
    for metric, value in eval_results.items():
        print(f"- {metric}: {value:.4f}")

if __name__ == "__main__":
    main()