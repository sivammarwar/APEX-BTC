"""
Layer 4: Signal Generation
105-point composite scoring system with multi-timeframe confluence
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import deque
import numpy as np
from loguru import logger


@dataclass
class Signal:
    """Generated trading signal"""
    timestamp: datetime = None
    direction: str = "NEUTRAL"  # LONG, SHORT, NEUTRAL
    
    # Scoring
    composite_score: int = 0
    max_possible_score: int = 105
    component_scores: Dict[str, int] = None
    
    # Validation
    regime: int = 0
    regime_allows_entry: bool = False
    signal_threshold: int = 70
    signal_valid: bool = False
    
    # Probability weighting (Kahneman & Tversky)
    historical_win_rate: float = 0.0
    probability_weighted: float = 0.0  # π(p)
    prospect_value: float = 0.0
    
    # Risk metrics
    recommended_stop: float = 0.0
    recommended_tp1: float = 0.0
    recommended_tp2: float = 0.0
    expected_rr: float = 0.0
    
    # Pre-trade checks
    asymmetric_payout_sharpe: float = 0.0
    log_return_expectation: float = 0.0
    as_cost_adjusted_edge: float = 0.0
    
    # Cooldown state
    cooldown_active: bool = False
    cooldown_remaining: int = 0  # hours
    
    # Signal metrics for comparison display
    signal_metrics: Dict = None
    
    def __post_init__(self):
        if self.component_scores is None:
            self.component_scores = {}
            
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'direction': self.direction,
            'composite_score': self.composite_score,
            'max_score': self.max_possible_score,
            'regime': self.regime,
            'entries_allowed': self.regime_allows_entry,
            'signal_valid': self.signal_valid,
            'signal_metrics': self.signal_metrics or {},
            'signal_threshold': self.signal_threshold,
            'probability_weighted': self.probability_weighted,
            'prospect_value': self.prospect_value,
            'recommended_stop': self.recommended_stop,
            'recommended_tp1': self.recommended_tp1,
            'recommended_tp2': self.recommended_tp2,
            'expected_rr': self.expected_rr,
            'asymmetric_payout_sharpe': self.asymmetric_payout_sharpe,
            'log_return_expectation': self.log_return_expectation,
            'cooldown_active': self.cooldown_active,
            'component_breakdown': self.component_scores,
        }


class SignalGenerationLayer:
    """
    Layer 4: Signal Generation
    105-point composite scoring system per PRD Section 7
    """
    
    # Score weights per PRD 7.1
    SCORE_WEIGHTS = {
        'ema_200_slope': 15,      # 4H 200 EMA slopes upward
        'tsmom_rank': 20,         # TSMOM in top tercile
        'co_positive': 15,        # CO > 0
        'price_near_ema': 10,     # Within 1.5 ATR of 21 EMA
        'rsi_range': 5,           # RSI 40-60
        'stoch_rsi_cross': 5,     # Stoch RSI crossing up from <30
        'macd_bullish': 5,        # MACD bullish crossover
        'ofi_clean': 10,          # OFI_clean > 0.1
        'obv_trending': 5,        # OBV trending up
        'volume_poc': 5,          # POC below current price
        'mrr_rho': 5,             # MRR ρ > 0.10
        's_score': 5,             # s-score < -1.25
    }
    
    def __init__(self, config, feature_layer, regime_layer, risk_layer, prospect_layer):
        self.config = config
        self.feature_layer = feature_layer
        self.regime_layer = regime_layer
        self.risk_layer = risk_layer
        self.prospect_layer = prospect_layer
        
        # Signal history
        self.signal_history: deque = deque(maxlen=1000)
        self.trade_history: deque = deque(maxlen=100)
        
        # Cooldown tracking
        self._last_trade_time: Optional[datetime] = None
        self._cooldown_hours = config.COOLDOWN_HOURS
        
        # Historical win rate estimation
        self._wins = 0
        self._losses = 0
        
        logger.info("Layer 4 initialized")
        
    def generate_signal(self, current_price: float) -> Signal:
        """Generate composite trading signal"""
        timestamp = datetime.now()
        
        features = self.feature_layer.get_latest_features()
        regime = self.regime_layer.get_current_regime()
        
        if features is None or regime is None:
            return self._neutral_signal(timestamp, "Missing data")
            
        # Check cooldown
        cooldown_active, cooldown_remaining = self._check_cooldown(timestamp)
        
        # Compute component scores
        scores = self._compute_component_scores(features, current_price, regime)
        composite_score = sum(scores.values())
        
        # Direction determination
        direction = self._determine_direction(scores, regime)
        logger.info(f"[SIGNAL_DEBUG] scores={scores}, direction={direction}, tsmom_rank={features.tsmom_rank}, co_value={features.co_value}")
        
        # Probability weighting (Kahneman & Tversky 1979)
        historical_win_rate = self._estimate_win_rate()
        prob_weighted = self.prospect_layer.probability_weighting(historical_win_rate)
        
        # Prospect value calculation
        if direction == "LONG":
            gain = composite_score * 0.5  # Simplified
            loss = -composite_score * 0.3
            prospect_value = self.prospect_layer.prospect_value(historical_win_rate, gain, 
                                                                 1-historical_win_rate, loss)
        else:
            prospect_value = 0.0
            
        # Signal validation
        signal_valid = self._validate_signal(
            composite_score, 
            regime.signal_threshold,
            prob_weighted,
            prospect_value,
            regime.entries_allowed,
            cooldown_active
        )
        
        # Risk parameters
        stop, tp1, tp2, rr = self._compute_risk_levels(features, current_price, direction)
        
        # Pre-trade checks
        as_sharpe = self._compute_asymmetric_payout_sharpe(historical_win_rate, 60, 0.3, 0.6)
        log_ret_exp = self._compute_log_return_expectation(features)
        as_edge = self._compute_as_adjusted_edge(composite_score, features)
        
        # Build signal metrics for display
        signal_metrics = {
            'tsmom_percentile': getattr(features, 'tsmom_percentile', 0) if features else 0,
            'ofi_clean': getattr(features, 'ofi_clean', 0) if features else 0,
            'mrr_rho': getattr(features, 'order_flow_autocorr', 0) if features else 0,
            'co_value': getattr(features, 'carry_over_value', 0) if features else 0,
            's_score': getattr(features, 's_score', 0) if features else 0,
            'ema_200_slope': getattr(features, 'ema_200_slope', 0) if features else 0,
        }
        
        signal = Signal(
            timestamp=timestamp,
            direction=direction,  # Keep actual direction regardless of validation
            composite_score=composite_score,
            component_scores=scores,
            regime=int(regime.regime),
            regime_allows_entry=regime.entries_allowed,
            signal_threshold=regime.signal_threshold,
            signal_valid=signal_valid,
            historical_win_rate=historical_win_rate,
            probability_weighted=prob_weighted,
            prospect_value=prospect_value,
            recommended_stop=stop,
            recommended_tp1=tp1,
            recommended_tp2=tp2,
            expected_rr=rr,
            asymmetric_payout_sharpe=as_sharpe,
            log_return_expectation=log_ret_exp,
            as_cost_adjusted_edge=as_edge,
            cooldown_active=cooldown_active,
            cooldown_remaining=cooldown_remaining,
            signal_metrics=signal_metrics,
        )
        
        self.signal_history.append(signal)
        
        if signal_valid and direction != "NEUTRAL":
            logger.info(f"Signal generated: {direction} | Score: {composite_score} | Regime: {regime.regime_name}")
            
        return signal
        
    def _compute_component_scores(self, features, current_price: float, regime) -> Dict[str, int]:
        """Compute individual component scores"""
        scores = {}
        
        # 1. EMA 200 slope (15 pts)
        if features.ema_slope_200 > 0:
            scores['ema_200_slope'] = 15
            
        # 2. TSMOM rank (20 pts)
        if features.tsmom_rank >= self.config.TSMOM_PERCENTILE_ENTRY:
            # Scale by percentile (ensure non-negative)
            tsmom_score = max(0, int(20 * (features.tsmom_rank - 0.5) / 0.5))
            scores['tsmom_rank'] = min(tsmom_score, 20)
            
        # 3. CO positive (15 pts)
        if features.co_value >= 0:
            scores['co_positive'] = min(15, int(15 * features.co_value / 2))
            
        # 4. Price within 1.5 ATR of 21 EMA (10 pts)
        distance_from_ema = abs(current_price - features.ema_21)
        if distance_from_ema < 1.5 * features.atr_harrvj:
            scores['price_near_ema'] = 10
            
        # 5. RSI 40-60 (5 pts)
        if 40 <= features.rsi_30 <= 60:
            scores['rsi_range'] = 5
            
        # 6. Stochastic RSI crossing up (5 pts)
        # Check previous values for cross
        recent_features = list(self.feature_layer.feature_history)[-5:]
        if len(recent_features) >= 2:
            prev_stoch = recent_features[-2].stoch_rsi if len(recent_features) > 1 else 50
            if prev_stoch < 30 and features.stoch_rsi > prev_stoch:
                scores['stoch_rsi_cross'] = 5
                
        # 7. MACD bullish (5 pts)
        if features.macd_hist > 0:
            scores['macd_bullish'] = 5
            
        # 8. OFI clean > min threshold (10 pts)
        if features.ofi_clean > getattr(self.config, 'MIN_OFI_CLEAN', 0.01):
            scores['ofi_clean'] = min(10, int(10 * features.ofi_clean / 0.2))
            
        # 9. OBV trending (5 pts)
        if features.obv > 0:  # Simplified
            scores['obv_trending'] = 5
            
        # 10. Volume POC below price (5 pts)
        if features.volume_profile_poc < current_price:
            scores['volume_poc'] = 5
            
        # 11. MRR rho > min threshold (5 pts)
        if features.order_flow_autocorr > getattr(self.config, 'MIN_MRR_RHO', 0.10):
            scores['mrr_rho'] = 5
            
        # 12. s-score for mean reversion (5 pts) - only in Regime 3
        if regime.regime == 3 and features.s_score < -1.25:
            scores['s_score'] = 5
            
        return scores
        
    def _determine_direction(self, scores: Dict[str, int], regime) -> str:
        """Determine trade direction from scores"""
        # Long bias for TSMOM momentum (allow >= 0 to catch edge case)
        if 'tsmom_rank' in scores and scores['tsmom_rank'] >= 0:
            if 'co_positive' in scores:
                return "LONG"
                
        # Mean reversion in range-bound
        if regime.regime == 3 and 's_score' in scores:
            return "LONG"  # Long at s < -1.25
            
        return "NEUTRAL"
        
    def _validate_signal(self, composite_score: int, threshold: int,
                         prob_weighted: float, prospect_value: float,
                         entries_allowed: bool, cooldown_active: bool) -> bool:
        """Validate signal against all criteria"""

        # Regime check
        if not entries_allowed:
            return False

        # Cooldown check
        if cooldown_active:
            return False

        # Score threshold
        if composite_score < threshold:
            return False

        # Probability-weighted score check (read from global settings for dynamic updates)
        try:
            from config.settings import settings
            min_prob_weighted_score = getattr(settings, 'MIN_PROB_WEIGHTED_SCORE', 35.0)
        except:
            min_prob_weighted_score = getattr(self.config, 'MIN_PROB_WEIGHTED_SCORE', 35.0)
        if prob_weighted * composite_score < min_prob_weighted_score:
            return False

        # Prospect value check (read from global settings for dynamic updates)
        try:
            from config.settings import settings
            min_prospect_value = getattr(settings, 'MIN_PROSPECT_VALUE', 0.0)
        except:
            min_prospect_value = getattr(self.config, 'MIN_PROSPECT_VALUE', 0.0)
        if prospect_value < min_prospect_value:
            return False

        return True
        
    def _compute_risk_levels(self, features, current_price: float, direction: str) -> Tuple[float, float, float, float]:
        """Compute stop loss and take profit levels"""
        atr = features.atr_harrvj
        
        if direction == "LONG":
            # Stop at swing low approximation - 0.3 ATR
            stop = current_price - 2.0 * atr  # Simplified
            
            # TP at 2:1 R:R
            risk = current_price - stop
            tp1 = current_price + 1.0 * risk
            tp2 = current_price + 2.0 * risk
            rr = 2.0
        else:
            stop = current_price + 2.0 * atr
            risk = stop - current_price
            tp1 = current_price - 1.0 * risk
            tp2 = current_price - 2.0 * risk
            rr = 2.0
            
        return stop, tp1, tp2, rr
        
    def _estimate_win_rate(self) -> float:
        """Estimate historical win rate from trade history"""
        total = self._wins + self._losses
        if total == 0:
            return 0.55  # Default optimistic prior
        return self._wins / total
        
    def _compute_asymmetric_payout_sharpe(self, p: float, n: int, 
                                           pi_minus: float, pi_plus: float) -> float:
        """Asymmetric payout Sharpe ratio"""
        numerator = (pi_plus - pi_minus) * p + pi_minus
        denominator = (pi_plus - pi_minus) * np.sqrt(p * (1 - p))
        if denominator == 0:
            return 0.0
        return numerator / denominator * np.sqrt(n)
        
    def _compute_log_return_expectation(self, features) -> float:
        """Compute expected log return with jump-diffusion"""
        mu = features.jump_mu
        sigma = features.jump_sigma
        lam = features.jump_lambda
        nu = features.jump_nu
        delta = features.jump_delta
        
        k = np.exp(nu + delta**2 / 2) - 1
        exp_log_ret = mu - sigma**2/2 - lam * k + lam * nu
        return exp_log_ret
        
    def _compute_as_adjusted_edge(self, composite_score: int, features) -> float:
        """Compute adverse selection adjusted edge"""
        gross_edge = composite_score * 0.01  # Simplified conversion
        fixed_cost = 0.0013  # 0.13%
        # Avoid division by zero
        ema_21 = getattr(features, 'ema_21', 0)
        if ema_21 == 0:
            as_cost = 0.0
        else:
            as_cost = features.adverse_selection_pct * features.mrr_spread / ema_21
        return gross_edge - fixed_cost - as_cost
        
    def _check_cooldown(self, current_time: datetime) -> Tuple[bool, int]:
        """Check if in cooldown period"""
        if self._last_trade_time is None:
            return False, 0
            
        elapsed = current_time - self._last_trade_time
        elapsed_hours = elapsed.total_seconds() / 3600
        
        if elapsed_hours < self._cooldown_hours:
            return True, int(self._cooldown_hours - elapsed_hours)
            
        return False, 0
        
    def record_trade_outcome(self, win: bool):
        """Record trade outcome for win rate tracking"""
        if win:
            self._wins += 1
        else:
            self._losses += 1
        self._last_trade_time = datetime.now()
        
    def _neutral_signal(self, timestamp: datetime, reason: str) -> Signal:
        """Create neutral signal"""
        return Signal(
            timestamp=timestamp,
            direction="NEUTRAL",
            composite_score=0,
            regime=0,
            regime_allows_entry=False,
            signal_threshold=999,
            signal_valid=False,
            historical_win_rate=0.5,
            probability_weighted=0.5,
            prospect_value=0.0,
            recommended_stop=0.0,
            recommended_tp1=0.0,
            recommended_tp2=0.0,
            expected_rr=0.0,
            asymmetric_payout_sharpe=0.0,
            log_return_expectation=0.0,
            as_cost_adjusted_edge=0.0,
            cooldown_active=False,
            cooldown_remaining=0,
        )
        
    def get_signal_history(self, n: int = 100) -> List[Signal]:
        """Get recent signal history"""
        return list(self.signal_history)[-n:]
