"""
Layer 10: Microstructure Intelligence Engine
MRR model, HARRVJ, algo-slicing detection, liquidity windows (Dimpfl 2017 + Pichl & Kaizoji 2017)
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque
import numpy as np
from loguru import logger


@dataclass
class MRREstimate:
    """MRR model estimate per Dimpfl (2017)"""
    timestamp: datetime
    theta: float  # Adverse selection parameter
    rho: float    # Order flow autocorrelation
    spread_estimate: float
    adverse_selection_pct: float
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'theta': self.theta,
            'rho': self.rho,
            'spread_estimate': self.spread_estimate,
            'adverse_selection_pct': self.adverse_selection_pct,
        }


@dataclass
class HARRVJForecast:
    """HARRVJ volatility forecast per Pichl & Kaizoji (2017)"""
    timestamp: datetime
    rv_forecast: float
    sigma_annualized: float
    jump_component: float
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'rv_forecast': self.rv_forecast,
            'sigma_annualized': self.sigma_annualized,
            'jump_component': self.jump_component,
        }


@dataclass
class LiquidityWindow:
    """Liquidity window assessment per Dimpfl (2017)"""
    hour_utc: int
    volume_1h: float
    mean_volume_30d: float
    liquidity_score: float
    is_premium: bool
    is_avoid: bool
    
    def to_dict(self) -> Dict:
        return {
            'hour_utc': self.hour_utc,
            'volume_1h': self.volume_1h,
            'mean_volume_30d': self.mean_volume_30d,
            'liquidity_score': self.liquidity_score,
            'is_premium': self.is_premium,
            'is_avoid': self.is_avoid,
        }


class MicrostructureLayer:
    """
    Layer 10: Microstructure Intelligence Engine
    Real-time MRR estimation, HARRVJ volatility, algo-slicing detection
    """
    
    # HARRVJ calibrated BTC parameters from Pichl & Kaizoji 2017
    HARRVJ_BETA = {
        'beta0': 0.0103,
        'beta1': 0.3448,
        'beta2': 0.5179,
        'beta3': -0.2268,
        'beta5': -0.8609,
        'beta6': 0.8563,
    }
    
    # Algo slicing detection thresholds per Pichl & Kaizoji
    INTEGER_VOLUMES = [1.0, 2.0, 3.0, 5.0, 10.0]
    ALGO_TOLERANCE = 0.001
    ALGO_THRESHOLD = 0.40  # 40% integer volumes = algo slicing
    
    def __init__(self, config):
        self.config = config
        
        # MRR estimation state
        self._price_changes: deque = deque(maxlen=500)
        self._trade_directions: deque = deque(maxlen=500)
        self._trade_prices: deque = deque(maxlen=500)
        self._last_mrr_estimate: Optional[MRREstimate] = None
        
        # HARRVJ state
        self._rv_history: deque = deque(maxlen=30)
        self._jump_history: deque = deque(maxlen=30)
        self._last_harrvj_forecast: Optional[HARRVJForecast] = None
        
        # Algo slicing detection state
        self._recent_volumes: deque = deque(maxlen=60)  # 60 seconds
        self._recent_timestamps: deque = deque(maxlen=60)
        self._algo_slicing_flag: bool = False
        self._algo_slicing_fraction_20windows: deque = deque(maxlen=20)
        
        # Liquidity window tracking
        self._hourly_volumes: Dict[int, deque] = {h: deque(maxlen=30) for h in range(24)}
        self._last_hour: Optional[int] = None
        self._current_hour_volume: float = 0.0
        
        logger.info("Layer 10 initialized")
        
    def on_trade(self, price: float, quantity: float, direction: int, timestamp: datetime):
        """Process tick-level trade for MRR and algo detection"""
        # Store for MRR
        if len(self._trade_prices) > 0:
            price_change = price - self._trade_prices[-1]
            self._price_changes.append(price_change)
            
        self._trade_directions.append(direction)
        self._trade_prices.append(price)
        
        # Algo slicing detection
        self._recent_volumes.append(quantity)
        self._recent_timestamps.append(timestamp)
        
        # Hourly volume tracking
        hour = timestamp.hour
        if self._last_hour is not None and hour != self._last_hour:
            # Hour complete, store volume
            self._hourly_volumes[self._last_hour].append(self._current_hour_volume)
            self._current_hour_volume = 0.0
            
        self._current_hour_volume += quantity
        self._last_hour = hour
        
    def on_5min_bar(self, returns: List[float], timestamp: datetime):
        """Process 5-minute bar for HARRVJ"""
        # Realized volatility for this 5-min period
        if len(returns) > 0:
            rv_5min = sum(r**2 for r in returns)
            
            # Only update daily at 00:00 UTC
            if timestamp.hour == 0 and timestamp.minute < 5:
                self._update_harrvj_daily()
                
    def _update_harrvj_daily(self):
        """Update HARRVJ forecast at 00:00 UTC"""
        # Compute daily RV from 5-min returns
        if len(self._rv_history) == 0:
            return
            
        # Current values
        sqrt_rv_t = np.sqrt(self._rv_history[-1]) if self._rv_history else 0
        sqrt_rv_t5 = np.sqrt(list(self._rv_history)[-6]) if len(self._rv_history) >= 6 else sqrt_rv_t
        sqrt_rv_t10 = np.sqrt(list(self._rv_history)[-11]) if len(self._rv_history) >= 11 else sqrt_rv_t5
        
        sqrt_j_t5 = np.sqrt(max(list(self._jump_history)[-6], 0)) if len(self._jump_history) >= 6 else 0
        sqrt_j_t10 = np.sqrt(max(list(self._jump_history)[-11], 0)) if len(self._jump_history) >= 11 else sqrt_j_t5
        
        # HARRVJ forecast
        b = self.HARRVJ_BETA
        sqrt_rv_forecast = (
            b['beta0'] +
            b['beta1'] * sqrt_rv_t +
            b['beta2'] * sqrt_rv_t5 +
            b['beta3'] * sqrt_rv_t10 +
            b['beta5'] * sqrt_j_t5 +
            b['beta6'] * sqrt_j_t10
        )
        
        rv_forecast = max(sqrt_rv_forecast**2, 0)
        sigma_annualized = np.sqrt(rv_forecast * 252)
        
        self._last_harrvj_forecast = HARRVJForecast(
            timestamp=datetime.utcnow(),
            rv_forecast=rv_forecast,
            sigma_annualized=sigma_annualized,
            jump_component=sqrt_j_t5,
        )
        
        logger.info(f"HARRVJ updated: σ_annual = {sigma_annualized:.2%}")
        
    def estimate_mrr(self, current_mid_price: float) -> MRREstimate:
        """
        Estimate MRR model from rolling window
        Model: Δp_t = θ × Q_t - ρθ × Q_{t-1} + e_t
        """
        if len(self._price_changes) < 100 or len(self._trade_directions) < 100:
            # Return default estimate
            return MRREstimate(
                timestamp=datetime.utcnow(),
                theta=0.5,
                rho=0.3,
                spread_estimate=1.0,
                adverse_selection_pct=0.463,  # Dimpfl 2017 default
            )
            
        # Get aligned data
        n = min(len(self._price_changes), len(self._trade_directions) - 1)
        
        delta_p = np.array(list(self._price_changes)[-n:])
        Q = np.array(list(self._trade_directions)[-n-1:-1])  # Q_{t-1}
        Q_lag = np.array(list(self._trade_directions)[-n-2:-2]) if n + 2 <= len(self._trade_directions) else Q
        
        # Simple OLS estimation
        # Δp_t = θ × Q_t - ρθ × Q_{t-1}
        # We'll estimate θ and ρ separately
        
        # Estimate θ from correlation
        if np.std(Q) > 0 and np.std(delta_p) > 0:
            theta = np.mean(delta_p * Q) / np.std(Q) if np.mean(Q**2) > 0 else 0.5
            theta = abs(theta)  # Should be positive
            theta = np.clip(theta, 0.1, 5.0)
        else:
            theta = 0.5
            
        # Estimate ρ from autocorrelation
        if len(Q) > 1 and np.std(Q) > 0:
            rho = np.corrcoef(Q[1:], Q[:-1])[0, 1] if len(Q) > 1 else 0.3
            rho = np.clip(rho, -1.0, 1.0)
        else:
            rho = 0.3
            
        # Spread estimate: S_MRR = 2θ
        spread = 2 * theta
        
        # Adverse selection %: AS% = θ / mid_price × 100
        if current_mid_price > 0:
            as_pct = theta / current_mid_price
        else:
            as_pct = 0.00463  # Default 46.3% of spread per Dimpfl
            
        estimate = MRREstimate(
            timestamp=datetime.utcnow(),
            theta=theta,
            rho=rho,
            spread_estimate=spread,
            adverse_selection_pct=as_pct,
        )
        
        self._last_mrr_estimate = estimate
        return estimate
        
    def detect_algo_slicing(self, window_seconds: int = 60) -> Tuple[bool, float]:
        """
        Detect algorithmic order slicing (Pichl & Kaizoji 2017)
        Returns: (detected, fraction)
        """
        if len(self._recent_volumes) < 10:
            return False, 0.0
            
        volumes = list(self._recent_volumes)
        
        # Count integer volumes
        n_integer = 0
        for v in volumes:
            is_integer = any(abs(v - iv) < self.ALGO_TOLERANCE for iv in self.INTEGER_VOLUMES)
            if is_integer:
                n_integer += 1
                
        fraction = n_integer / len(volumes)
        detected = fraction > self.ALGO_THRESHOLD
        
        # Store for 20-window tracking
        self._algo_slicing_fraction_20windows.append(fraction)
        self._algo_slicing_flag = detected
        
        return detected, fraction
        
    def get_algo_slicing_fraction_20windows(self) -> float:
        """Get fraction of windows showing algo slicing (for Regime 5 detection)"""
        if len(self._algo_slicing_fraction_20windows) == 0:
            return 0.0
        return sum(1 for f in self._algo_slicing_fraction_20windows if f > self.ALGO_THRESHOLD) / len(self._algo_slicing_fraction_20windows)
        
    def compute_liquidity_window(self, hour_utc: int, current_volume_1h: float) -> LiquidityWindow:
        """
        Compute liquidity window score (Dimpfl 2017)
        Peak: 13:00-17:00 UTC (NYSE): 1.8-2.2x
        Good: 07:00-12:00 UTC (Europe): 1.4-1.8x
        Avoid: 02:00-06:00 UTC (Asia night): 0.4-0.7x
        """
        # 30-day mean for this hour
        if len(self._hourly_volumes[hour_utc]) > 0:
            mean_volume = np.mean(list(self._hourly_volumes[hour_utc]))
        else:
            mean_volume = current_volume_1h if current_volume_1h > 0 else 1.0
            
        # Liquidity score
        if mean_volume > 0:
            score = current_volume_1h / mean_volume
        else:
            score = 1.0
            
        # Smooth with 3-hour rolling (Dimpfl finding: BTC spread is constant 24h)
        neighbors = [(hour_utc - 1) % 24, hour_utc, (hour_utc + 1) % 24]
        neighbor_scores = []
        for h in neighbors:
            if len(self._hourly_volumes[h]) > 0:
                h_mean = np.mean(list(self._hourly_volumes[h]))
                h_score = current_volume_1h / h_mean if h_mean > 0 else 1.0
                neighbor_scores.append(h_score)
                
        if neighbor_scores:
            score = np.mean(neighbor_scores)
            
        # Classify
        is_premium = 13 <= hour_utc <= 17 or 7 <= hour_utc <= 12
        is_avoid = 2 <= hour_utc <= 6
        
        return LiquidityWindow(
            hour_utc=hour_utc,
            volume_1h=current_volume_1h,
            mean_volume_30d=mean_volume,
            liquidity_score=score,
            is_premium=is_premium,
            is_avoid=is_avoid,
        )
        
    def compute_trading_time_weight(self, volume_1h: float, avg_volume: float) -> float:
        """
        Trading time weighting (Avellaneda & Lee 2010)
        R̅_t = R_t × [⟨δV⟩ / (V(t+Δt) - V(t))]
        """
        if volume_1h > 0 and avg_volume > 0:
            return avg_volume / volume_1h
        return 1.0
        
    def get_mrr_estimate(self) -> Optional[MRREstimate]:
        """Get last MRR estimate"""
        return self._last_mrr_estimate
        
    def get_harrvj_forecast(self) -> Optional[HARRVJForecast]:
        """Get last HARRVJ forecast"""
        return self._last_harrvj_forecast
        
    def is_spread_anomalous(self, current_spread: float, spread_history: List[float]) -> bool:
        """
        Check if current spread deviates from 24-hour mean (Dimpfl 2017)
        BTC spread is constant - any deviation > 3σ is anomaly
        """
        if len(spread_history) < 24:
            return False
            
        mean_spread = np.mean(spread_history[-24:])
        std_spread = np.std(spread_history[-24:])
        
        if std_spread == 0:
            return False
            
        z_score = (current_spread - mean_spread) / std_spread
        
        return abs(z_score) > 3.0
