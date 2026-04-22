"""
Layer 7: Performance Analytics
PSR, DSR, MinTRL, TuW, CPV - López de Prado / Bailey / Kahneman & Tversky metrics
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import deque
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import beta as beta_dist
from loguru import logger


@dataclass
class PerformanceSnapshot:
    """Complete performance metrics snapshot"""
    timestamp: datetime
    
    # Standard metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    
    # Returns
    total_return: float
    annualized_return: float
    volatility: float
    
    # Ratios
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    profit_factor: float
    
    # López de Prado metrics
    psr_sr0: float  # PSR(SR*=0)
    psr_sr25: float  # PSR(SR*=2.5)
    psr_sr30: float  # PSR(SR*=3.0)
    dsr: float  # Deflated Sharpe Ratio
    min_trl: float  # Minimum Track Record Length
    prob_strategy_failure: float  # P(Strategy Failure)
    
    # Time Under Water
    tuw_median: float
    tuw_75th: float
    tuw_95th: float
    current_tuw: float
    
    # Han et al. metrics
    mean_log_return: float
    log_return_tstat: float
    expected_log_return: float  # Jump-diffusion
    
    # Prospect Theory
    cumulative_prospect_value: float
    loss_aversion_ratio: float
    
    # Microstructure
    mean_adverse_selection_cost: float
    harrvj_mae: float
    
    # Drawdown
    max_drawdown: float
    current_drawdown: float
    
    # Time-based P&L
    daily_pnl: float
    pnl_30d: float
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'trades': {
                'total': self.total_trades,
                'winning': self.winning_trades,
                'losing': self.losing_trades,
                'win_rate': self.win_rate,
            },
            'returns': {
                'total': self.total_return,
                'annualized': self.annualized_return,
                'volatility': self.volatility,
            },
            'ratios': {
                'sharpe': self.sharpe_ratio,
                'sortino': self.sortino_ratio,
                'calmar': self.calmar_ratio,
                'profit_factor': self.profit_factor,
            },
            'statistical_validation': {
                'psr_sr0': self.psr_sr0,
                'psr_sr25': self.psr_sr25,
                'dsr': self.dsr,
                'min_trl': self.min_trl,
                'prob_failure': self.prob_strategy_failure,
            },
            'time_under_water': {
                'median': self.tuw_median,
                '75th': self.tuw_75th,
                '95th': self.tuw_95th,
                'current': self.current_tuw,
            },
            'log_return_analysis': {
                'mean': self.mean_log_return,
                'tstat': self.log_return_tstat,
                'expected': self.expected_log_return,
            },
            'prospect_theory': {
                'cumulative_value': self.cumulative_prospect_value,
                'loss_aversion_ratio': self.loss_aversion_ratio,
            },
            'microstructure': {
                'mean_as_cost': self.mean_adverse_selection_cost,
                'harrvj_mae': self.harrvj_mae,
            },
            'drawdown': {
                'max': self.max_drawdown,
                'current': self.current_drawdown,
            },
            'time_based_pnl': {
                'daily': self.daily_pnl,
                'pnl_30d': self.pnl_30d,
            },
        }


class PerformanceAnalyticsLayer:
    """
    Layer 7: Performance Analytics
    All statistical validation metrics per PRD Section 10
    """
    
    def __init__(self, config, risk_layer, prospect_layer):
        self.config = config
        self.risk_layer = risk_layer
        self.prospect_layer = prospect_layer
        
        # Trade history
        self.trade_returns: deque = deque(maxlen=1000)
        self.trade_pnls: deque = deque(maxlen=1000)
        self.trade_durations: deque = deque(maxlen=1000)
        self.trade_pnls_with_timestamps: deque = deque(maxlen=1000)  # (timestamp, pnl)
        
        # Equity history
        self.equity_history: deque = deque(maxlen=10000)
        self.high_water_marks: deque = deque(maxlen=10000)
        
        # Time Under Water tracking
        self.tuw_start: Optional[datetime] = None
        self.tuw_history: List[float] = []
        
        # Prospect theory tracking
        self.prospect_values: deque = deque(maxlen=1000)
        self.v_gains: deque = deque(maxlen=1000)
        self.v_losses: deque = deque(maxlen=1000)
        
        # HARRVJ accuracy tracking
        self.harrvj_errors: deque = deque(maxlen=100)
        
        # Adverse selection tracking
        self.as_costs: deque = deque(maxlen=100)
        
        logger.info("Layer 7 initialized")
        
    @property
    def metrics(self) -> Dict:
        """Return current metrics summary"""
        try:
            snapshot = self.compute_metrics()
            result = snapshot.to_dict()
            # Debug logging
            time_pnl = result.get('time_based_pnl', {})
            logger.info(f"[METRICS] daily_pnl={time_pnl.get('daily', 0)}, pnl_30d={time_pnl.get('pnl_30d', 0)}, trades_with_ts={len(self.trade_pnls_with_timestamps)}")
            return result
        except Exception as e:
            logger.error(f"Error computing metrics: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return {
                'total_trades': len(self.trade_returns),
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0.0,
                'total_return': 0.0,
                'sharpe_ratio': 0.0,
                'max_drawdown': 0.0,
                'psr_sr0': 0.5,
                'dsr': 0.5,
                'prob_failure': 0.5
            }
        
    def record_pnl(self, pnl: float, timestamp: datetime = None):
        """Record PnL directly (for partial exits)"""
        ts = timestamp or datetime.now()
        self.trade_pnls.append(pnl)
        self.trade_pnls_with_timestamps.append((ts, pnl))
        logger.info(f"[RECORD_PNL] Recorded PnL at {ts.strftime('%H:%M:%S')}, pnl=${pnl:.2f}, total={len(self.trade_pnls_with_timestamps)}")
        
    def record_trade(self, trade_record: Dict):
        """Record trade for analytics"""
        # Returns
        pnl = trade_record.get('net_pnl', 0)
        if trade_record.get('position_size_usd', 0) > 0:
            ret = pnl / trade_record['position_size_usd']
            self.trade_returns.append(ret)
            
        self.trade_pnls.append(pnl)
        
        # Store with timestamp for daily/30d P&L calculations
        # Use current time - the trade just completed
        ts = datetime.now()
        self.trade_pnls_with_timestamps.append((ts, pnl))
        logger.info(f"[RECORD_TRADE] Recorded trade at {ts.strftime('%H:%M:%S')}, pnl=${pnl:.2f}, total={len(self.trade_pnls_with_timestamps)}")
        
        # Duration
        entry = datetime.fromisoformat(trade_record['entry_timestamp']) if trade_record.get('entry_timestamp') else None
        exit_ts = datetime.fromisoformat(trade_record['exit_timestamp']) if trade_record.get('exit_timestamp') else None
        if entry and exit_ts:
            duration = (exit_ts - entry).total_seconds() / 3600  # hours
            self.trade_durations.append(duration)
            
        # Prospect theory
        self.prospect_values.append(trade_record.get('v_gain', 0) + trade_record.get('v_loss', 0))
        if trade_record.get('net_pnl', 0) > 0:
            self.v_gains.append(trade_record.get('v_gain', 0))
        else:
            self.v_losses.append(abs(trade_record.get('v_loss', 0)))
            
        # AS costs
        as_cost = trade_record.get('adverse_selection_cost', 0)
        if as_cost > 0:
            self.as_costs.append(as_cost)
            
    def record_harrvj_error(self, actual: float, forecast: float):
        """Record HARRVJ forecast error"""
        if forecast > 0:
            error = abs(actual - forecast) / forecast
            self.harrvj_errors.append(error)
            
    def record_equity(self, equity: float, timestamp: datetime):
        """Record equity for drawdown/TUW tracking"""
        self.equity_history.append((timestamp, equity))
        
        # Update high water mark
        if len(self.high_water_marks) == 0:
            self.high_water_marks.append((timestamp, equity))
        else:
            last_hwm = self.high_water_marks[-1][1]
            if equity >= last_hwm:
                if self.tuw_start is not None:
                    # Record completed T UW
                    tuw = (timestamp - self.tuw_start).total_seconds() / 3600  # hours
                    self.tuw_history.append(tuw)
                    self.tuw_start = None
                self.high_water_marks.append((timestamp, equity))
            else:
                # In drawdown
                if self.tuw_start is None:
                    self.tuw_start = timestamp
                    
    def compute_metrics(self) -> PerformanceSnapshot:
        """Compute all performance metrics"""
        timestamp = datetime.now()
        
        trades = list(self.trade_returns)
        pnls = list(self.trade_pnls)
        
        if len(trades) < 2:
            return self._empty_snapshot(timestamp)
            
        returns = np.array(trades)
        
        # Basic metrics
        total_trades = len(trades)
        winning_trades = sum(1 for p in pnls if p > 0)
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        # Returns
        total_return = np.prod(1 + returns) - 1
        
        # Annualized (assume trades per year based on recent frequency)
        if len(self.trade_durations) > 0:
            avg_duration = np.mean(list(self.trade_durations))
            trades_per_year = 365 * 24 / avg_duration if avg_duration > 0 else 252
        else:
            trades_per_year = 252
            
        annualized_return = (1 + total_return) ** (trades_per_year / total_trades) - 1 if total_trades > 0 else 0
        
        # Volatility (annualized)
        volatility = np.std(returns) * np.sqrt(trades_per_year) if len(returns) > 1 else 0
        
        # Sharpe
        sharpe = annualized_return / volatility if volatility > 0 else 0
        
        # Sortino (downside deviation)
        downside_returns = returns[returns < 0]
        downside_vol = np.std(downside_returns) * np.sqrt(trades_per_year) if len(downside_returns) > 1 else 0
        sortino = annualized_return / downside_vol if downside_vol > 0 else 0
        
        # Calmar
        max_dd = self._compute_max_drawdown()
        calmar = annualized_return / max_dd if max_dd > 0 else 0
        
        # Profit factor
        gross_profit = sum(p for p in pnls if p > 0)
        gross_loss = abs(sum(p for p in pnls if p < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0
        
        # Statistical validation (López de Prado)
        skewness = stats.skew(returns) if len(returns) > 2 else 0
        kurtosis = stats.kurtosis(returns, fisher=True) if len(returns) > 3 else 0
        
        psr_sr0 = self._compute_psr(sharpe, skewness, kurtosis, total_trades, 0)
        psr_sr25 = self._compute_psr(sharpe, skewness, kurtosis, total_trades, 2.5)
        psr_sr30 = self._compute_psr(sharpe, skewness, kurtosis, total_trades, 3.0)
        
        # DSR (simplified, assuming K=100 strategies tested)
        dsr = self._compute_dsr(sharpe, skewness, kurtosis, total_trades, K=100)
        
        # MinTRL
        min_trl = self._compute_min_trl(sharpe, skewness, kurtosis, 0.95, 0)
        
        # P(Strategy Failure)
        prob_failure = self._compute_prob_strategy_failure(winning_trades, losing_trades, 1/3)
        
        # Time Under Water
        tuw_stats = self._compute_tuw_stats()
        
        # Current T UW
        current_tuw = 0
        if self.tuw_start is not None:
            current_tuw = (timestamp - self.tuw_start).total_seconds() / 3600
            
        # Log return analysis (Han et al. 2026)
        log_rets = np.log(1 + returns)
        mean_log_ret = np.mean(log_rets)
        log_ret_std = np.std(log_rets)
        log_ret_tstat = mean_log_ret / (log_ret_std / np.sqrt(total_trades)) if log_ret_std > 0 else 0
        
        # Expected log return with jump-diffusion
        exp_log_ret = self._compute_expected_log_return(returns)
        
        # Prospect theory
        cpv = sum(self.prospect_values)
        lar = sum(self.v_losses) / sum(self.v_gains) if sum(self.v_gains) > 0 else 2.25
        
        # Microstructure
        mean_as = np.mean(list(self.as_costs)) if self.as_costs else 0
        harrvj_mae = np.mean(list(self.harrvj_errors)) if self.harrvj_errors else 0
        
        # Calculate daily and 30-day P&L
        daily_pnl = 0.0
        pnl_30d = 0.0
        now = datetime.now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        thirty_days_ago = now - timedelta(days=30)
        
        for ts, pnl in self.trade_pnls_with_timestamps:
            # Today's P&L
            if ts >= today_start:
                daily_pnl += pnl
            # 30-day P&L
            if ts >= thirty_days_ago:
                pnl_30d += pnl
        
        logger.info(f"[COMPUTE_METRICS] daily_pnl=${daily_pnl:.2f}, pnl_30d=${pnl_30d:.2f}, trades_today={sum(1 for ts,_ in self.trade_pnls_with_timestamps if ts >= today_start)}, total_trades={len(self.trade_pnls_with_timestamps)}")
        
        return PerformanceSnapshot(
            timestamp=timestamp,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_return=total_return,
            annualized_return=annualized_return,
            volatility=volatility,
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            calmar_ratio=calmar,
            profit_factor=profit_factor,
            psr_sr0=psr_sr0,
            psr_sr25=psr_sr25,
            psr_sr30=psr_sr30,
            dsr=dsr,
            min_trl=min_trl,
            prob_strategy_failure=prob_failure,
            tuw_median=tuw_stats[0],
            tuw_75th=tuw_stats[1],
            tuw_95th=tuw_stats[2],
            current_tuw=current_tuw,
            mean_log_return=mean_log_ret,
            log_return_tstat=log_ret_tstat,
            expected_log_return=exp_log_ret,
            cumulative_prospect_value=cpv,
            loss_aversion_ratio=lar,
            mean_adverse_selection_cost=mean_as,
            harrvj_mae=harrvj_mae,
            max_drawdown=max_dd,
            current_drawdown=self.risk_layer.current_equity / self.risk_layer.high_water_mark - 1,
            daily_pnl=daily_pnl,
            pnl_30d=pnl_30d,
        )
        
    def _compute_psr(self, sharpe: float, skew: float, kurt: float, 
                     T: int, SR_star: float) -> float:
        """
        Probabilistic Sharpe Ratio (López de Prado / Bailey 2012)
        PSR(SR*) = Φ[(SR_hat - SR*) × √(T-1) / √(1 - γ3×SR_hat + ((γ4-1)/4)×SR_hat²)]
        """
        if T < 2:
            return 0.5
            
        numerator = (sharpe - SR_star) * np.sqrt(T - 1)
        denominator = np.sqrt(1 - skew * sharpe + ((kurt - 1) / 4) * sharpe**2)
        
        if denominator == 0:
            return 0.5
            
        z_score = numerator / denominator
        psr = stats.norm.cdf(z_score)
        
        return psr
        
    def _compute_dsr(self, sharpe: float, skew: float, kurt: float,
                     T: int, K: int = 100) -> float:
        """
        Deflated Sharpe Ratio (López de Prado 2014)
        DSR = PSR(SR_0) where SR_0 corrects for multiple testing
        """
        # Simplified SR_0 estimation
        var_sr = 1 / (T - 1) if T > 1 else 1
        gamma = 0.5772  # Euler-Mascheroni constant
        
        # Approximate SR_0 for multiple testing
        sr_0 = np.sqrt(var_sr) * ((1 - gamma) * stats.norm.ppf(1 - 1/K) + 
                                   gamma * stats.norm.ppf(1 - 1/(K * np.e)))
        
        dsr = self._compute_psr(sharpe, skew, kurt, T, sr_0)
        return dsr
        
    def _compute_min_trl(self, sharpe: float, skew: float, kurt: float,
                         confidence: float, SR_star: float) -> float:
        """
        Minimum Track Record Length (López de Prado / Bailey 2012)
        MinTRL = 1 + [1 - γ3×SR_hat + ((γ4-1)/4)×SR_hat²] × (Z_α/(SR_hat - SR*))²
        """
        if abs(sharpe - SR_star) < 0.001:
            return float('inf')
            
        z_alpha = stats.norm.ppf(confidence)
        
        factor = 1 - skew * sharpe + ((kurt - 1) / 4) * sharpe**2
        denominator = (sharpe - SR_star)**2
        
        min_trl = 1 + factor * (z_alpha**2 / denominator)
        
        return max(min_trl, 0)
        
    def _compute_prob_strategy_failure(self, W: int, L: int, p0: float) -> float:
        """
        Probability of Strategy Failure (López de Prado 2018)
        P(Failure) = CDF_Beta(p_0 | W+1, L+1)
        """
        if W + L == 0:
            return 0.5
            
        # Beta distribution posterior
        alpha_post = W + 1
        beta_post = L + 1
        
        prob_failure = beta_dist.cdf(p0, alpha_post, beta_post)
        
        return prob_failure
        
    def _compute_tuw_stats(self) -> Tuple[float, float, float]:
        """Compute Time Under Water statistics"""
        if len(self.tuw_history) == 0:
            return (0, 0, 0)
            
        tuw_array = np.array(self.tuw_history)
        
        return (
            np.median(tuw_array),
            np.percentile(tuw_array, 75),
            np.percentile(tuw_array, 95),
        )
        
    def _compute_max_drawdown(self) -> float:
        """Compute maximum drawdown from equity history"""
        if len(self.equity_history) < 2:
            return 0
            
        equities = [e for _, e in self.equity_history]
        running_max = np.maximum.accumulate(equities)
        drawdowns = (running_max - equities) / running_max
        
        return np.max(drawdowns)
        
    def _compute_expected_log_return(self, returns: np.ndarray) -> float:
        """Compute expected log return with jump-diffusion (Han et al. 2026)"""
        log_rets = np.log(1 + returns)
        
        mu_hat = np.mean(log_rets)
        sigma_hat = np.std(log_rets)
        
        # Estimate jump parameters (simplified)
        excess_kurt = stats.kurtosis(log_rets, fisher=True)
        lam_hat = max(0.001, min(excess_kurt / 100, 0.1))
        nu_hat = np.mean(log_rets[log_rets < np.percentile(log_rets, 5)])
        delta_hat = sigma_hat * 0.5
        
        k = np.exp(nu_hat + delta_hat**2 / 2) - 1
        
        exp_log_ret = mu_hat - sigma_hat**2 / 2 - lam_hat * k + lam_hat * nu_hat
        
        return exp_log_ret
        
    def _empty_snapshot(self, timestamp: datetime) -> PerformanceSnapshot:
        """Create empty snapshot when insufficient data"""
        return PerformanceSnapshot(
            timestamp=timestamp,
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0,
            total_return=0,
            annualized_return=0,
            volatility=0,
            sharpe_ratio=0,
            sortino_ratio=0,
            calmar_ratio=0,
            profit_factor=0,
            psr_sr0=0.5,
            psr_sr25=0.5,
            psr_sr30=0.5,
            dsr=0.5,
            min_trl=float('inf'),
            prob_strategy_failure=0.5,
            tuw_median=0,
            tuw_75th=0,
            tuw_95th=0,
            current_tuw=0,
            mean_log_return=0,
            log_return_tstat=0,
            expected_log_return=0,
            cumulative_prospect_value=0,
            loss_aversion_ratio=2.25,
            mean_adverse_selection_cost=0,
            harrvj_mae=0,
            max_drawdown=0,
            current_drawdown=0,
            daily_pnl=0,
            pnl_30d=0,
        )
        
    def check_acceptance_criteria(self) -> Dict[str, bool]:
        """Check PRD acceptance criteria (Section 16.3)"""
        metrics = self.compute_metrics()
        
        return {
            'sharpe_gt_2_5': metrics.sharpe_ratio > 2.5,
            'log_return_tstat_gt_2': metrics.log_return_tstat > 2.0,
            'dsr_ge_0_95': metrics.dsr >= 0.95,
            'psr_sr0_ge_0_95': metrics.psr_sr0 >= 0.95,
            'psr_sr25_ge_0_90': metrics.psr_sr25 >= 0.90,
            'max_dd_lt_20': metrics.max_drawdown < 0.20,
            'profit_factor_gt_1_5': metrics.profit_factor > 1.5,
            'win_rate_40_70': 0.40 <= metrics.win_rate <= 0.70,
            'prob_failure_lt_5': metrics.prob_strategy_failure < 0.05,
            'harrvj_mae_lt_0_30': metrics.harrvj_mae < 0.30,
            'min_trades_60': metrics.total_trades >= 60,
        }
