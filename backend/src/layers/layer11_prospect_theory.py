"""
Layer 11: Prospect Theory Engine
Kahneman & Tversky (1979) - S-shaped valuation, π(p) weighting, reference point adaptation
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Tuple, Optional
from enum import Enum
import numpy as np
from loguru import logger


class Domain(Enum):
    """Gain/loss domain"""
    GAIN = "gain"
    LOSS = "loss"
    NEUTRAL = "neutral"


@dataclass
class ProspectState:
    """Current prospect theory state"""
    reference_point: float
    current_equity: float
    high_water_mark: float
    drawdown_pct: float
    domain: Domain
    
    # Value function parameters
    alpha: float  # 0.88 for gains
    beta: float   # 0.88 for losses
    lambda_: float # 2.25 loss aversion
    
    # Probability weighting
    gamma: float  # 0.67
    
    def to_dict(self) -> Dict:
        return {
            'reference_point': self.reference_point,
            'current_equity': self.current_equity,
            'domain': self.domain.value,
            'drawdown_pct': self.drawdown_pct,
            'parameters': {
                'alpha': self.alpha,
                'beta': self.beta,
                'lambda': self.lambda_,
                'gamma': self.gamma,
            }
        }


class ProspectTheoryLayer:
    """
    Layer 11: Prospect Theory Engine
    Implementation of Kahneman & Tversky (1979) per PRD Section 14
    """
    
    # Calibrated parameters from Kahneman & Tversky (1979)
    DEFAULT_ALPHA = 0.88
    DEFAULT_BETA = 0.88
    DEFAULT_LAMBDA = 2.25
    DEFAULT_GAMMA = 0.67
    
    def __init__(self, config):
        self.config = config
        
        # Parameters
        self.alpha = config.PT_ALPHA if hasattr(config, 'PT_ALPHA') else self.DEFAULT_ALPHA
        self.beta = config.PT_BETA if hasattr(config, 'PT_BETA') else self.DEFAULT_BETA
        self.lambda_ = config.PT_LAMBDA if hasattr(config, 'PT_LAMBDA') else self.DEFAULT_LAMBDA
        self.gamma = config.PT_GAMMA if hasattr(config, 'PT_GAMMA') else self.DEFAULT_GAMMA
        
        logger.info(f"Layer 11 initialized: α={self.alpha}, β={self.beta}, λ={self.lambda_}, γ={self.gamma}")
        
    def value_function(self, x: float) -> float:
        """
        S-shaped value function v(x) per PRD Section 14.1
        
        v(x) = { x^α for x ≥ 0
               { -λ × (-x)^β for x < 0
               
        Losses loom ~2.25× larger than equivalent gains (λ = 2.25)
        """
        if x >= 0:
            # Gains - concave, risk averse
            return x ** self.alpha
        else:
            # Losses - convex, risk seeking
            return -self.lambda_ * ((-x) ** self.beta)
            
    def probability_weighting(self, p: float) -> float:
        """
        Probability weighting function π(p) per PRD Section 14.1
        
        π(p) = p^γ / (p^γ + (1-p)^γ)^(1/γ)
        
        Properties:
        - π(0) = 0, π(1) = 1
        - π(p) + π(1-p) < 1 (subcertainty)
        - π(p) > p for small p (overweighting rare events)
        """
        if p <= 0:
            return 0.0
        if p >= 1:
            return 1.0
            
        numerator = p ** self.gamma
        denominator = (numerator + (1 - p) ** self.gamma) ** (1 / self.gamma)
        
        return numerator / denominator
        
    def prospect_value(self, p_win: float, gain: float, p_loss: float, loss: float) -> float:
        """
        Prospect value of a gamble
        V = π(p_win) × v(gain) + π(p_loss) × v(loss)
        """
        pi_win = self.probability_weighting(p_win)
        pi_loss = self.probability_weighting(p_loss)
        
        v_gain = self.value_function(gain)
        v_loss = self.value_function(loss)  # Already negative
        
        return pi_win * v_gain + pi_loss * v_loss
        
    def update_reference_point(self, current_equity: float, initial_capital: float,
                               high_water_mark: float, drawdown_pct: float) -> float:
        """
        Reference point adaptation per PRD Section 14.1
        
        Reference_Point_t = Initial_Capital (default)
        
        After 10%+ gain: Reference = HWM × 0.5 + Initial × 0.5
        After 5%+ drawdown: Reference = Initial × (1 - 0.25 × |DD|)
        At new HWM: Reference = HWM
        """
        gain_pct = (current_equity - initial_capital) / initial_capital
        
        if gain_pct > 0.10:
            # House money effect - reference shifts up
            reference = high_water_mark * 0.5 + initial_capital * 0.5
        elif drawdown_pct > 0.05:
            # Break-even effect - reference shifts down
            reference = initial_capital * (1 - 0.25 * drawdown_pct)
        elif current_equity >= high_water_mark:
            # At new high - use HWM as reference
            reference = high_water_mark
        else:
            # Default
            reference = initial_capital
            
        return reference
        
    def determine_domain(self, current_equity: float, reference_point: float) -> Domain:
        """Determine if in gain or loss domain"""
        if current_equity > reference_point:
            return Domain.GAIN
        elif current_equity < reference_point:
            return Domain.LOSS
        else:
            return Domain.NEUTRAL
            
    def get_certainty_bonus(self, composite_score: int) -> float:
        """
        Certainty bonus for high-confidence signals
        per PRD Section 14.2
        """
        if composite_score > 95:
            return 1.10  # 10% bonus
        elif composite_score > 90:
            return 1.05  # 5% bonus
        else:
            return 1.0
            
    def compute_position_adjustment(self, domain: Domain, 
                                     recent_performance: str) -> float:
        """
        Compute prospect theory position size adjustment
        per PRD Section 8.1 Step 7
        
        After gain (>10%): × 1.2 (house money - more risk seeking)
        After loss (>5%): × 1.15 (break-even - risk seeking to recover)
        In drawdown (>10%): × 0.5 (capital preservation)
        """
        if recent_performance == "strong_gain":
            return 1.2  # House money effect
        elif recent_performance == "significant_loss":
            return 1.15  # Break-even effect
        elif recent_performance == "deep_drawdown":
            return 0.5  # Capital preservation
        else:
            return 1.0
            
    def compute_asymmetric_stops(self, current_pnl_pct: float, base_stop_distance: float) -> float:
        """
        Compute asymmetric stop distances based on domain
        per PRD Section 8.2
        
        Gain domain (profit > 0): Tighter stop (risk averse)
        Loss domain (profit < 0): Wider stop (risk seeking)
        """
        if current_pnl_pct > 0:
            # Gain domain - risk averse, tighter stop
            return base_stop_distance * 0.75
        elif current_pnl_pct < 0:
            # Loss domain - risk seeking, wider stop
            return base_stop_distance * 1.5
        else:
            return base_stop_distance
            
    def evaluate_trade(self, p_win: float, gain_amount: float, 
                       loss_amount: float, current_domain: Domain) -> Dict:
        """
        Complete trade evaluation under prospect theory
        Returns evaluation metrics
        """
        p_loss = 1 - p_win
        
        # Standard expected value
        ev_standard = p_win * gain_amount + p_loss * (-loss_amount)
        
        # Prospect theory value
        v_trade = self.prospect_value(p_win, gain_amount, p_loss, -loss_amount)
        
        # Weighted probabilities
        pi_win = self.probability_weighting(p_win)
        pi_loss = self.probability_weighting(p_loss)
        
        # Certainty effect check
        certainty_effect = p_win > 0.95 or p_loss > 0.95
        
        # Recommendation
        acceptable = v_trade > 0
        
        return {
            'standard_ev': ev_standard,
            'prospect_value': v_trade,
            'pi_win': pi_win,
            'pi_loss': pi_loss,
            'v_gain': self.value_function(gain_amount),
            'v_loss': self.value_function(-loss_amount),
            'certainty_effect': certainty_effect,
            'acceptable': acceptable,
            'domain': current_domain.value,
        }
        
    def compute_cumulative_prospect_value(self, trades: list) -> float:
        """
        Compute cumulative prospect value (CPV) for trade history
        per PRD Section 10.9
        
        CPV = Σ[π(p_win_t)×v(gain_t) + π(p_loss_t)×v(loss_t)]
        """
        cpv = 0.0
        
        for trade in trades:
            p_win = trade.get('win_probability', 0.5)
            gain = trade.get('gain_amount', 0)
            loss = trade.get('loss_amount', 0)
            
            cpv += self.prospect_value(p_win, gain, 1 - p_win, -loss)
            
        return cpv
        
    def compute_loss_aversion_ratio(self, realized_gains: list, realized_losses: list) -> float:
        """
        Compute realized loss aversion ratio
        per PRD Section 10.9
        
        LAR = Σ|v(losses)| / Σv(gains)
        Target: LAR < λ = 2.25
        """
        if not realized_gains:
            return self.lambda_
            
        sum_v_gains = sum(self.value_function(g) for g in realized_gains)
        sum_v_losses = sum(abs(self.value_function(l)) for l in realized_losses)
        
        if sum_v_gains == 0:
            return self.lambda_
            
        return sum_v_losses / sum_v_gains
        
    def get_state(self, current_equity: float, initial_capital: float,
                  high_water_mark: float) -> ProspectState:
        """Get current prospect theory state"""
        drawdown = (high_water_mark - current_equity) / high_water_mark
        reference = self.update_reference_point(current_equity, initial_capital, 
                                                high_water_mark, drawdown)
        domain = self.determine_domain(current_equity, reference)
        
        return ProspectState(
            reference_point=reference,
            current_equity=current_equity,
            high_water_mark=high_water_mark,
            drawdown_pct=drawdown,
            domain=domain,
            alpha=self.alpha,
            beta=self.beta,
            lambda_=self.lambda_,
            gamma=self.gamma,
        )
