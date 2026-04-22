"""
Layer 9: Jump-Diffusion Risk Engine
Merton jump-diffusion parameter estimation and risk management (Han et al. 2026)
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque
import numpy as np
from scipy import stats
from scipy.optimize import minimize
from loguru import logger


@dataclass
class JumpDiffusionParams:
    """Jump-diffusion parameters θ = {µ, σ, ν, δ, λ}"""
    mu: float      # Drift
    sigma: float   # Diffusion volatility
    nu: float      # Mean jump size
    delta: float   # Jump volatility
    lambda_: float # Jump intensity
    
    def to_dict(self) -> Dict:
        return {
            'mu': self.mu,
            'sigma': self.sigma,
            'nu': self.nu,
            'delta': self.delta,
            'lambda': self.lambda_,
        }


@dataclass
class JumpEvent:
    """Detected jump event"""
    timestamp: datetime
    return_5min: float
    sigma_threshold: float
    price_before: float
    price_after: float
    direction: str  # "positive" or "adverse"
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'return_5min': self.return_5min,
            'sigma_threshold': self.sigma_threshold,
            'price_before': self.price_before,
            'price_after': self.price_after,
            'direction': self.direction,
        }


@dataclass
class MonteCarloResult:
    """Monte Carlo simulation result"""
    paths: np.ndarray
    final_equity_distribution: np.ndarray
    var_95: float
    var_99: float
    expected_final_equity: float
    prob_ruin: float
    
    def to_dict(self) -> Dict:
        return {
            'var_95': self.var_95,
            'var_99': self.var_99,
            'expected_final_equity': self.expected_final_equity,
            'prob_ruin': self.prob_ruin,
        }


class JumpDiffusionLayer:
    """
    Layer 9: Jump-Diffusion Risk Engine
    Daily parameter estimation and intra-day jump monitoring per PRD Section 12
    """
    
    # Reference BTC parameters from Han et al. 2026
    REFERENCE_PARAMS = {
        'mu': -0.003,
        'sigma': 0.016,
        'nu': -0.014,
        'delta': 0.394,
        'lambda_': 0.016,  # Using lambda_ to avoid Python keyword
    }
    
    def __init__(self, config, risk_layer):
        self.config = config
        self.risk_layer = risk_layer
        
        # Parameter estimates
        self.current_params: JumpDiffusionParams = JumpDiffusionParams(
            **self.REFERENCE_PARAMS
        )
        
        # Daily return history for estimation
        self._daily_returns: deque = deque(maxlen=365*3)  # 3 years
        
        # Intra-day 5-min returns for jump detection
        self._5min_returns: deque = deque(maxlen=288)  # 1 day
        self._5min_prices: deque = deque(maxlen=289)
        self._5min_timestamps: deque = deque(maxlen=289)
        
        # Jump detection
        self._rolling_vol_4h: deque = deque(maxlen=48)  # 4 hours of 5-min bars
        self.detected_jumps: deque = deque(maxlen=100)
        
        # Last estimation
        self._last_estimation: Optional[datetime] = None
        
        logger.info("Layer 9 initialized")
        
    def add_daily_return(self, return_val: float, timestamp: datetime):
        """Add daily return for parameter estimation"""
        self._daily_returns.append((timestamp, return_val))
        
        # Daily estimation at 00:00 UTC
        if timestamp.hour == 0 and timestamp.minute < 5:
            if self._last_estimation is None or (timestamp - self._last_estimation).days >= 1:
                self._estimate_parameters()
                self._last_estimation = timestamp
                
    def add_5min_return(self, return_val: float, price: float, timestamp: datetime):
        """Add 5-minute return for intra-day jump detection"""
        self._5min_returns.append(return_val)
        self._5min_prices.append(price)
        self._5min_timestamps.append(timestamp)
        
        # Update rolling volatility
        self._rolling_vol_4h.append(return_val)
        
        # Check for jump
        self._check_jump(timestamp)
        
    def _estimate_parameters(self):
        """Estimate jump-diffusion parameters via method of moments (Han et al. 2026)"""
        if len(self._daily_returns) < 60:
            logger.debug("Insufficient data for jump-diffusion estimation")
            return
            
        returns = np.array([r for _, r in self._daily_returns])
        log_rets = np.log(1 + returns)
        
        # Sample moments
        m1 = np.mean(log_rets)
        m2 = np.var(log_rets)
        m3 = stats.skew(log_rets)
        m4 = stats.kurtosis(log_rets, fisher=True)
        
        # Method of moments estimation (simplified)
        # Reference: Han et al. 2026 implementation
        
        # Initial estimates
        sigma_sq = max(m2 * 0.7, 1e-6)  # Diffusion variance
        lambda_ = max(0.001, min(m4 / 50, 0.1))  # Jump intensity from excess kurtosis
        
        # Jump size parameters
        if abs(m3) > 0.01 and lambda_ > 0.001:
            nu = m3 * np.sqrt(sigma_sq) / (lambda_ * 3)  # Mean jump
        else:
            nu = 0.0
            
        delta_sq = max(m2 * 0.3 / lambda_ - nu**2, 0.001) if lambda_ > 0 else 0.001
        delta = np.sqrt(delta_sq)
        
        # Drift
        mu = m1 + sigma_sq / 2 + lambda_ * (np.exp(nu + delta_sq / 2) - 1 - nu)
        
        self.current_params = JumpDiffusionParams(
            mu=float(mu),
            sigma=float(np.sqrt(sigma_sq)),
            nu=float(nu),
            delta=float(delta),
            lambda_=float(lambda_),
        )
        
        logger.info(f"Jump-diffusion parameters updated: λ={lambda_:.4f}, "
                   f"σ={np.sqrt(sigma_sq):.4f}, ν={nu:.4f}")
        
    def _check_jump(self, timestamp: datetime):
        """Check for jump in recent 5-minute returns"""
        if len(self._rolling_vol_4h) < 48:
            return
            
        recent_returns = np.array(list(self._rolling_vol_4h))
        vol_4h = np.std(recent_returns)
        
        if vol_4h == 0:
            return
            
        # Current return
        current_ret = self._5min_returns[-1]
        
        # Jump if exceeds 3-sigma
        if abs(current_ret) > 3 * vol_4h:
            price_before = self._5min_prices[-2] if len(self._5min_prices) >= 2 else self._5min_prices[-1]
            price_after = self._5min_prices[-1]
            
            direction = "positive" if current_ret > 0 else "adverse"
            
            jump = JumpEvent(
                timestamp=timestamp,
                return_5min=current_ret,
                sigma_threshold=3 * vol_4h,
                price_before=price_before,
                price_after=price_after,
                direction=direction,
            )
            
            self.detected_jumps.append(jump)
            
            logger.warning(f"JUMP DETECTED: {current_ret:.2%} in 5min | "
                          f"Direction: {direction} | Price: {price_before:.2f} -> {price_after:.2f}")
            
            # Return jump event for position review
            return jump
            
        return None
        
    def compute_expected_log_return(self, horizon_days: int = 1) -> float:
        """
        Compute expected log return under jump-diffusion
        E[log_return] = µ - σ²/2 - λk + λν
        where k = exp(ν + δ²/2) - 1
        """
        p = self.current_params
        
        k = np.exp(p.nu + p.delta**2 / 2) - 1
        
        daily_log_ret = p.mu - p.sigma**2 / 2 - p.lambda_ * k + p.lambda_ * p.nu
        
        return daily_log_ret * horizon_days
        
    def compute_variance(self, horizon_days: int = 1) -> float:
        """
        Compute variance under jump-diffusion
        Var[log_return] = σ² + λδ² + λν²
        """
        p = self.current_params
        
        daily_var = p.sigma**2 + p.lambda_ * p.delta**2 + p.lambda_ * p.nu**2
        
        return daily_var * horizon_days
        
    def run_monte_carlo(self, initial_equity: float, position_size: float,
                        days: int = 30, n_paths: int = 10000) -> MonteCarloResult:
        """
        Monte Carlo simulation of equity path (Han et al. 2026)
        dP_t/P_t = (µ - λk)dt + σdW_t + dJ_t
        """
        p = self.current_params
        dt = 1 / 365  # Daily steps
        n_steps = days
        
        k = np.exp(p.nu + p.delta**2 / 2) - 1
        drift = p.mu - p.lambda_ * k
        
        # Simulate paths
        paths = np.zeros((n_paths, n_steps + 1))
        paths[:, 0] = initial_equity
        
        for i in range(n_paths):
            equity = initial_equity
            for t in range(n_steps):
                # Diffusion component
                diffusion = p.sigma * np.random.normal() * np.sqrt(dt)
                
                # Jump component (Poisson)
                n_jumps = np.random.poisson(p.lambda_ * dt)
                if n_jumps > 0:
                    jump_sum = np.sum(np.random.normal(p.nu, p.delta, n_jumps))
                else:
                    jump_sum = 0
                    
                # Return
                ret = drift * dt + diffusion + jump_sum
                
                # Position exposure effect (simplified)
                position_ret = ret * (position_size / initial_equity)
                
                equity *= (1 + position_ret)
                paths[i, t + 1] = equity
                
        # Analyze distribution
        final_equities = paths[:, -1]
        
        var_95 = np.percentile(final_equities, 5)
        var_99 = np.percentile(final_equities, 1)
        expected = np.mean(final_equities)
        prob_ruin = np.mean(final_equities < initial_equity * 0.5)  # 50% loss
        
        return MonteCarloResult(
            paths=paths,
            final_equity_distribution=final_equities,
            var_95=var_95,
            var_99=var_99,
            expected_final_equity=expected,
            prob_ruin=prob_ruin,
        )
        
    def get_liquidation_risk_estimate(self, leverage: float, 
                                        stop_distance_pct: float) -> float:
        """
        Estimate liquidation risk from leverage and stop distance
        Under jump-diffusion, probability of hitting stop
        """
        p = self.current_params
        
        # Simplified: Probability of adverse jump exceeding stop
        # P(jump > stop) ≈ λ * P(N(ν, δ²) < log(1 - stop_distance))
        
        if stop_distance_pct <= 0 or leverage <= 0:
            return 0.0
            
        # Effective distance considering leverage
        effective_stop = stop_distance_pct / leverage
        
        # Probability from normal jump distribution
        prob_jump_exceeds = stats.norm.cdf(
            np.log(1 - effective_stop),
            loc=p.nu,
            scale=p.delta
        )
        
        # Daily probability
        daily_prob = p.lambda_ * prob_jump_exceeds
        
        return min(daily_prob, 1.0)
        
    def should_reduce_position(self, position_pnl_pct: float, 
                                distance_to_stop_pct: float) -> bool:
        """
        Determine if position should be reduced due to jump risk
        (Han et al. 2026 - intra-bar liquidation risk)
        """
        # If adverse jump detected and near stop
        if len(self.detected_jumps) > 0:
            last_jump = self.detected_jumps[-1]
            if (last_jump.direction == "adverse" and 
                position_pnl_pct < 0 and 
                distance_to_stop_pct < 0.005):  # Within 0.5% of stop
                return True
                
        # If jump intensity high and position underwater
        if (self.current_params.lambda_ > self.config.JUMP_THRESHOLD and 
            position_pnl_pct < 0):
            return True
            
        return False
        
    def get_params(self) -> JumpDiffusionParams:
        """Get current parameter estimates"""
        return self.current_params
        
    def get_detected_jumps(self, n: int = 10) -> List[JumpEvent]:
        """Get recent jump events"""
        return list(self.detected_jumps)[-n:]
        
    def estimate_tail_risk(self, confidence: float = 0.95) -> float:
        """Estimate tail risk using jump-diffusion"""
        mc_result = self.run_monte_carlo(
            initial_equity=self.risk_layer.current_equity,
            position_size=self.risk_layer.current_equity * 0.5,  # Half size
            days=30,
            n_paths=5000,
        )
        
        if confidence == 0.95:
            return mc_result.var_95
        elif confidence == 0.99:
            return mc_result.var_99
        else:
            return np.percentile(mc_result.final_equity_distribution, (1 - confidence) * 100)
