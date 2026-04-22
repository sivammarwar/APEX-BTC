"""
Layer 3: Regime Detection
Classify market into 5 regimes based on TSMOM, volatility, and microstructure
"""
from enum import IntEnum
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict
from collections import deque
import numpy as np
from loguru import logger


class MarketRegime(IntEnum):
    """Five market regimes per PRD Section 6.2"""
    TRENDING_BULLISH = 1  # GREEN - Full momentum
    TRENDING_BEARISH = 2  # RED - No new entries
    RANGE_BOUND = 3       # YELLOW - Mean reversion
    HIGH_VOL_UNDEFINED = 4  # ORANGE - 25% size
    MICROSTRUCTURE_DETERIORATION = 5  # PURPLE - No entries


@dataclass
class RegimeState:
    """Current regime state with all determining factors"""
    regime: MarketRegime = MarketRegime.RANGE_BOUND
    regime_name: str = "RANGE-BOUND"
    timestamp: datetime = None
    
    # Primary filters
    tsmom_percentile: float = 50.0
    tsmom_trigger: bool = False
    
    # Technical confirmations
    adx: float = 25.0
    adx_trending: bool = False
    bb_width_percentile: float = 50.0
    price_above_emas: bool = False
    macd_positive: bool = False
    obv_trending: bool = False
    
    # Momentum confirmation
    mrr_rho: float = 0.1
    mrr_confirms: bool = False
    co_positive: bool = False
    
    # Volatility/Jump
    jump_lambda: float = 0.0
    atr_expanding: bool = False
    
    # Microstructure
    mrr_theta_zscore: float = 0.0
    spread_deviation: float = 0.0
    liquidity_score: float = 50.0
    algo_slicing_fraction: float = 0.0
    
    # Decision flags
    entries_allowed: bool = True
    position_size_scale: float = 1.0
    signal_threshold: int = 70
    
    def to_dict(self) -> Dict:
        return {
            'regime': int(self.regime),
            'regime_name': self.regime_name,
            'timestamp': self.timestamp.isoformat(),
            'tsmom_percentile': self.tsmom_percentile,
            'entries_allowed': self.entries_allowed,
            'position_size_scale': self.position_size_scale,
            'signal_threshold': self.signal_threshold,
            'liquidity_score': self.liquidity_score,
            'liquidity_blocks_entries': self.liquidity_score < 0.7,
        }


class RegimeDetectionLayer:
    """
    Layer 3: Regime Detection
    Primary gate: TSMOM_rank from Han et al. 2026
    """
    
    def __init__(self, config, feature_layer):
        self.config = config
        self.feature_layer = feature_layer
        
        self.current_regime: Optional[RegimeState] = None
        self.regime_history: deque = deque(maxlen=1000)
        
        # Rolling statistics
        self._atr_history: deque = deque(maxlen=20)
        self._mrr_theta_history: deque = deque(maxlen=30*24)  # 30 days hourly
        self._spread_history: deque = deque(maxlen=24)
        
        logger.info("Layer 3 initialized")
        
    def detect_regime(self, features, current_price: float) -> RegimeState:
        """Classify current market regime"""
        timestamp = features.timestamp
        
        # Update rolling stats
        self._atr_history.append(features.atr_harrvj)
        self._mrr_theta_history.append(features.mrr_theta)
        
        # Determine primary gate values
        tsmom_percentile = features.tsmom_rank
        tsmom_trigger = tsmom_percentile > self.config.TSMOM_PERCENTILE_ENTRY
        
        # Technical confirmations
        adx_trending = features.adx > 25
        price_above_emas = current_price > features.ema_21 and current_price > features.ema_200
        macd_positive = features.macd_hist > 0
        obv_trending_up = True  # Simplified
        
        # MRR confirmations
        mrr_confirms = features.order_flow_autocorr > 0.10
        co_positive = features.co_value > 0
        
        # Volatility checks
        atr_expanding = False
        if len(self._atr_history) >= 20:
            recent_atr = np.mean(list(self._atr_history)[-5:])
            baseline_atr = np.mean(list(self._atr_history)[:15])
            atr_expanding = recent_atr > 2.0 * baseline_atr if baseline_atr > 0 else False
            
        jump_high = features.jump_lambda > self.config.JUMP_THRESHOLD
        
        # Microstructure checks
        mrr_theta_zscore = 0.0
        if len(self._mrr_theta_history) > 30:
            recent_theta = list(self._mrr_theta_history)
            mrr_theta_zscore = (features.mrr_theta - np.mean(recent_theta)) / (np.std(recent_theta) + 1e-10)
            
        spread_deviation = features.spread_invariance_zscore
        
        # Algo slicing fraction
        # Count recent algo detections
        recent_features = list(self.feature_layer.feature_history)[-20:]
        algo_count = sum(1 for f in recent_features if f.algo_slicing_detected)
        algo_fraction = algo_count / len(recent_features) if recent_features else 0.0
        
        # Regime classification
        regime = self._classify_regime(
            tsmom_percentile=tsmom_percentile,
            tsmom_trigger=tsmom_trigger,
            adx=features.adx,
            adx_trending=adx_trending,
            bb_width=features.bb_width,
            price_above_emas=price_above_emas,
            macd_positive=macd_positive,
            mrr_confirms=mrr_confirms,
            co_positive=co_positive,
            atr_expanding=atr_expanding,
            jump_high=jump_high,
            mrr_theta_zscore=mrr_theta_zscore,
            spread_deviation=spread_deviation,
            liquidity_score=features.liquidity_score,
            algo_fraction=algo_fraction,
        )
        
        # Regime-specific settings
        entries_allowed = regime not in [MarketRegime.TRENDING_BEARISH, MarketRegime.MICROSTRUCTURE_DETERIORATION]
        
        position_size_scale = {
            MarketRegime.TRENDING_BULLISH: 1.0,
            MarketRegime.TRENDING_BEARISH: 0.0,
            MarketRegime.RANGE_BOUND: 0.75,
            MarketRegime.HIGH_VOL_UNDEFINED: 0.25,
            MarketRegime.MICROSTRUCTURE_DETERIORATION: 0.0,
        }[regime]
        
        # Check for dynamic threshold override first
        if hasattr(self.config, 'DYNAMIC_SIGNAL_THRESHOLD') and self.config.DYNAMIC_SIGNAL_THRESHOLD > 0:
            signal_threshold = self.config.DYNAMIC_SIGNAL_THRESHOLD
        else:
            signal_threshold = {
                MarketRegime.TRENDING_BULLISH: self.config.SIGNAL_THRESHOLD_REGIME_1,
                MarketRegime.TRENDING_BEARISH: 999,  # No entries
                MarketRegime.RANGE_BOUND: self.config.SIGNAL_THRESHOLD_REGIME_3,
                MarketRegime.HIGH_VOL_UNDEFINED: self.config.SIGNAL_THRESHOLD_REGIME_4,
                MarketRegime.MICROSTRUCTURE_DETERIORATION: 999,
            }[regime]
        
        # Liquidity override
        if features.liquidity_score < self.config.LIQUIDITY_THRESHOLD:
            entries_allowed = False
            
        # Build regime state
        state = RegimeState(
            regime=regime,
            regime_name=regime.name.replace('_', ' ').title(),
            timestamp=timestamp,
            tsmom_percentile=tsmom_percentile,
            tsmom_trigger=tsmom_trigger,
            adx=features.adx,
            adx_trending=adx_trending,
            bb_width_percentile=features.bb_width,
            price_above_emas=price_above_emas,
            macd_positive=macd_positive,
            obv_trending=obv_trending_up,
            mrr_rho=features.order_flow_autocorr,
            mrr_confirms=mrr_confirms,
            co_positive=co_positive,
            jump_lambda=features.jump_lambda,
            atr_expanding=atr_expanding,
            mrr_theta_zscore=mrr_theta_zscore,
            spread_deviation=spread_deviation,
            liquidity_score=features.liquidity_score,
            algo_slicing_fraction=algo_fraction,
            entries_allowed=entries_allowed,
            position_size_scale=position_size_scale,
            signal_threshold=signal_threshold,
        )
        
        self.current_regime = state
        self.regime_history.append(state)
        
        return state
        
    def _classify_regime(self, **kwargs) -> MarketRegime:
        """Classify market into one of 5 regimes"""
        
        # Priority 1: Microstructure deterioration (PURPLE)
        if (kwargs['mrr_theta_zscore'] > 3.0 or 
            abs(kwargs['spread_deviation']) > 3.0 or
            kwargs['liquidity_score'] < 0.3 or
            kwargs['algo_fraction'] > 0.6):
            return MarketRegime.MICROSTRUCTURE_DETERIORATION
            
        # Priority 2: High volatility undefined (ORANGE)
        if kwargs['atr_expanding'] or kwargs['jump_high']:
            return MarketRegime.HIGH_VOL_UNDEFINED
            
        # Priority 3: TSMOM-based classification
        if kwargs['tsmom_trigger'] and kwargs['co_positive']:
            # Check for bullish confirmation
            if (kwargs['adx_trending'] and 
                kwargs['price_above_emas'] and 
                kwargs['macd_positive'] and
                kwargs['mrr_confirms']):
                return MarketRegime.TRENDING_BULLISH
            
        if kwargs['tsmom_percentile'] < 0.333:
            return MarketRegime.TRENDING_BEARISH
            
        # Priority 4: Range-bound (YELLOW)
        if (0.333 < kwargs['tsmom_percentile'] < 0.667 and 
            not kwargs['adx_trending'] and
            kwargs['bb_width'] < 30):
            return MarketRegime.RANGE_BOUND
            
        # Default: Trending Bullish if TSMOM positive
        if kwargs['tsmom_trigger']:
            return MarketRegime.TRENDING_BULLISH
            
        # Default to range-bound
        return MarketRegime.RANGE_BOUND
        
    def get_current_regime(self) -> Optional[RegimeState]:
        """Get current regime state"""
        return self.current_regime
        
    def is_entry_allowed(self) -> bool:
        """Quick check if entries allowed"""
        if self.current_regime is None:
            return False
        return self.current_regime.entries_allowed
        
    def get_position_size_scale(self) -> float:
        """Get position size scaling factor"""
        if self.current_regime is None:
            return 0.0
        return self.current_regime.position_size_scale
