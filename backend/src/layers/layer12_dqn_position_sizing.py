"""
Layer 12: DQN Position Sizing
Deep Q-Network for learned position sizing per Zhang, Zohren & Roberts (2020)
"""
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from collections import deque, namedtuple
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
from datetime import datetime
import random
from loguru import logger


Experience = namedtuple('Experience', ['state', 'action', 'reward', 'next_state', 'done'])


class DQNTradingNetwork(nn.Module):
    """
    DQN Network Architecture per Zhang et al. (2020)
    Dual LSTM layers with dropout
    """
    
    def __init__(self, input_dim: int = 60, hidden_dim: int = 64, output_dim: int = 3):
        super(DQNTradingNetwork, self).__init__()
        
        # First LSTM layer
        self.lstm1 = nn.LSTM(input_dim, hidden_dim, batch_first=True)
        
        # Second LSTM layer
        self.lstm2 = nn.LSTM(hidden_dim, 32, batch_first=True)
        
        # Fully connected output
        self.fc = nn.Linear(32, output_dim)
        
        # Dropout
        self.dropout = nn.Dropout(0.2)
        
    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass"""
        # First LSTM
        x, _ = self.lstm1(x)
        x = F.leaky_relu(x)
        
        # Second LSTM
        x, _ = self.lstm2(x)
        
        # Dropout on last timestep
        x = self.dropout(x[:, -1, :])
        
        # Output layer
        return self.fc(x)


class DQNPositionSizingLayer:
    """
    Layer 12: DQN Position Sizing
    Reinforcement learning position sizing per PRD Section 15
    
    Actions: A_t ∈ {-1 (short), 0 (neutral), 1 (long)}
    Sharpe 1.288 on 50 futures contracts (Zhang et al. 2020)
    """
    
    def __init__(self, config, feature_layer, risk_layer):
        self.config = config
        self.feature_layer = feature_layer
        self.risk_layer = risk_layer
        
        # Hyperparameters from Zhang et al. (2020)
        self.learning_rate = config.DQN_LEARNING_RATE if hasattr(config, 'DQN_LEARNING_RATE') else 0.0001
        self.gamma = config.DQN_GAMMA if hasattr(config, 'DQN_GAMMA') else 0.3
        self.batch_size = config.DQN_BATCH_SIZE if hasattr(config, 'DQN_BATCH_SIZE') else 64
        self.memory_size = config.DQN_MEMORY_SIZE if hasattr(config, 'DQN_MEMORY_SIZE') else 5000
        self.tau = config.DQN_TAU if hasattr(config, 'DQN_TAU') else 1000
        self.cost_rate = config.DQN_COST_RATE if hasattr(config, 'DQN_COST_RATE') else 0.0020
        
        # Target volatility for reward scaling
        self.vol_target = config.TARGET_VOLATILITY
        
        # Device
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Networks
        self.policy_net = DQNTradingNetwork(input_dim=60, output_dim=3).to(self.device)
        self.target_net = DQNTradingNetwork(input_dim=60, output_dim=3).to(self.device)
        self.target_net.load_state_dict(self.policy_net.state_dict())
        self.target_net.eval()
        
        # Optimizer
        self.optimizer = torch.optim.Adam(self.policy_net.parameters(), lr=self.learning_rate)
        
        # Replay memory
        self.memory: deque = deque(maxlen=self.memory_size)
        
        # Training state
        self.steps_done = 0
        self.episode_rewards: deque = deque(maxlen=100)
        self.training_mode = False
        
        # Action mapping
        self.actions = [-1, 0, 1]  # Short, Neutral, Long
        
        logger.info(f"Layer 12 initialized: lr={self.learning_rate}, γ={self.gamma}, device={self.device}")
        
    def build_state(self, features) -> np.ndarray:
        """
        Build state representation (60 observations) per PRD 15.3
        - Normalized close price series
        - Returns over 1, 2, 3, 12 months
        - MACD indicators
        - RSI
        """
        state = []
        
        # Price history (window of 20)
        hist = self.feature_layer.get_feature_history(20)
        if hist:
            closes = [f.ema_21 for f in hist]  # Use EMA21 as proxy
            if len(closes) > 0 and closes[-1] > 0:
                normalized = [c / closes[-1] - 1 for c in closes[-20:]]
                state.extend(normalized + [0] * (20 - len(normalized)))
            else:
                state.extend([0] * 20)
        else:
            state.extend([0] * 20)
            
        # Returns over different horizons (volatility-normalized)
        vol = features.harrvj_forecast if features.harrvj_forecast > 0 else 0.15
        for horizon in [21, 42, 63, 252]:  # ~1,2,3,12 months in trading days
            # Simplified - would need actual returns
            ret = features.tsmom_rank * 0.1  # Proxy
            state.append(ret / vol if vol > 0 else 0)
            
        # MACD indicators (3 lengths × 3 indicators)
        for short, long in [(8, 24), (16, 48), (32, 96)]:
            # Simplified MACD representation
            state.append(features.macd_hist / 100 if hasattr(features, 'macd_hist') else 0)
            state.append(features.macd_line / 100 if hasattr(features, 'macd_line') else 0)
            state.append(0)  # Signal placeholder
            
        # RSI
        state.append(features.rsi_30 / 100 if hasattr(features, 'rsi_30') else 0.5)
        
        # Pad to 60 if needed
        while len(state) < 60:
            state.append(0)
            
        return np.array(state[:60], dtype=np.float32)
        
    def select_action(self, state: np.ndarray, epsilon: float = 0.1) -> int:
        """Select action using ε-greedy policy"""
        if not self.training_mode or random.random() > epsilon:
            with torch.no_grad():
                state_tensor = torch.FloatTensor(state).unsqueeze(0).unsqueeze(0).to(self.device)
                q_values = self.policy_net(state_tensor)
                return q_values.argmax().item()
        else:
            return random.randrange(3)
            
    def get_position_action(self, features) -> Dict:
        """Get position sizing action from DQN"""
        state = self.build_state(features)
        action_idx = self.select_action(state)
        action = self.actions[action_idx]
        
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor)
            q_value = q_values[0][action_idx].item()
            
        return {
            'action': action,  # -1, 0, 1
            'action_idx': action_idx,
            'q_value': q_value,
            'raw_state': state.tolist(),
        }
        
    def compute_reward(self, action: int, prev_action: int, 
                       return_t: float, volatility_t: float, 
                       price_t: float) -> float:
        """
        Compute volatility-scaled reward per PRD Section 15.3
        
        R_t = μ[(σ_gt/σ_{t-1})r_t - bp×p_{t-1}|(σ_gt/σ_{t-1})A_t - (σ_gt/σ_{t-2})A_{t-1}|]
        """
        # Volatility scaling
        vol_scale = self.vol_target / volatility_t if volatility_t > 0 else 1.0
        
        # Scaled return component
        scaled_return = vol_scale * return_t * action
        
        # Transaction cost component
        position_change = abs(vol_scale * action - vol_scale * prev_action)
        cost_term = self.cost_rate * price_t * position_change
        
        reward = scaled_return - cost_term
        
        return reward
        
    def store_experience(self, state: np.ndarray, action: int, 
                         reward: float, next_state: np.ndarray, done: bool):
        """Store experience in replay memory"""
        self.memory.append(Experience(state, action, reward, next_state, done))
        
    def train_step(self) -> Optional[float]:
        """Single training step"""
        if len(self.memory) < self.batch_size:
            return None
            
        # Sample batch
        batch = random.sample(self.memory, self.batch_size)
        
        # Unpack
        states = torch.FloatTensor([e.state for e in batch]).unsqueeze(1).to(self.device)
        actions = torch.LongTensor([e.action for e in batch]).to(self.device)
        rewards = torch.FloatTensor([e.reward for e in batch]).to(self.device)
        next_states = torch.FloatTensor([e.next_state for e in batch]).unsqueeze(1).to(self.device)
        dones = torch.FloatTensor([e.done for e in batch]).to(self.device)
        
        # Current Q values
        current_q = self.policy_net(states).gather(1, actions.unsqueeze(1))
        
        # Target Q values
        with torch.no_grad():
            next_q = self.target_net(next_states).max(1)[0]
            target_q = rewards + (1 - dones) * self.gamma * next_q
            
        # Loss and update
        loss = F.mse_loss(current_q.squeeze(), target_q)
        
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()
        
        # Update target network
        self.steps_done += 1
        if self.steps_done % self.tau == 0:
            self.target_net.load_state_dict(self.policy_net.state_dict())
            
        return loss.item()
        
    def train_episode(self, episode_length: int = 100) -> float:
        """Train for one episode"""
        if not self.training_mode:
            self.training_mode = True
            
        total_reward = 0.0
        prev_action = 1  # Start long
        
        for _ in range(episode_length):
            # Get current state
            features = self.feature_layer.get_latest_features()
            if features is None:
                continue
                
            state = self.build_state(features)
            action_idx = self.select_action(state)
            action = self.actions[action_idx]
            
            # Simulate reward (would come from actual market in live)
            reward = self.compute_reward(
                action, prev_action,
                return_t=features.tsmom_rank * 0.01,
                volatility_t=features.harrvj_forecast,
                price_t=features.ema_21,
            )
            
            # Next state
            next_features = self.feature_layer.get_latest_features()
            next_state = self.build_state(next_features) if next_features else state
            
            # Store and train
            self.store_experience(state, action_idx, reward, next_state, False)
            loss = self.train_step()
            
            total_reward += reward
            prev_action = action
            
        self.episode_rewards.append(total_reward)
        
        return total_reward
        
    def get_q_values(self, features) -> List[float]:
        """Get Q-values for all actions"""
        state = self.build_state(features)
        
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).unsqueeze(0).to(self.device)
            q_values = self.policy_net(state_tensor).squeeze().cpu().numpy()
            
        return q_values.tolist()
        
    def save_model(self, path: str):
        """Save model weights"""
        torch.save({
            'policy_net': self.policy_net.state_dict(),
            'target_net': self.target_net.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'steps_done': self.steps_done,
        }, path)
        logger.info(f"DQN model saved to {path}")
        
    def load_model(self, path: str):
        """Load model weights"""
        checkpoint = torch.load(path, map_location=self.device)
        self.policy_net.load_state_dict(checkpoint['policy_net'])
        self.target_net.load_state_dict(checkpoint['target_net'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.steps_done = checkpoint['steps_done']
        logger.info(f"DQN model loaded from {path}")
        
    def get_stats(self) -> Dict:
        """Get DQN training statistics"""
        return {
            'steps_done': self.steps_done,
            'memory_size': len(self.memory),
            'recent_episode_rewards': list(self.episode_rewards)[-10:],
            'avg_reward': np.mean(self.episode_rewards) if self.episode_rewards else 0,
            'training_mode': self.training_mode,
        }
