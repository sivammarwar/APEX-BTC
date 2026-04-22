"""
Layer 8: Strategy Validity Monitor
Sentinel system for statistical edge monitoring per PRD Section 11
"""
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from enum import Enum
from collections import deque
import numpy as np
from loguru import logger


class AlertLevel(Enum):
    INFO = "info"
    WARNING = "warning"
    YELLOW = "yellow"
    ORANGE = "orange"
    RED = "red"


@dataclass
class StrategyAlert:
    """Strategy validity alert"""
    timestamp: datetime
    level: AlertLevel
    category: str
    message: str
    metric_value: float
    threshold: float
    action_taken: str
    requires_manual_review: bool = False
    acknowledged: bool = False
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level.value,
            'category': self.category,
            'message': self.message,
            'metric_value': self.metric_value,
            'threshold': self.threshold,
            'action': self.action_taken,
            'requires_review': self.requires_manual_review,
            'acknowledged': self.acknowledged,
        }


class StrategyValidityLayer:
    """
    Layer 8: Strategy Validity Monitor
    Sentinel components per PRD Section 11.1
    """
    
    # Alert thresholds per PRD Section 11.1
    THRESHOLDS = {
        'PSR': {'warning': 0.90, 'yellow': 0.80, 'orange': 0.75, 'red': 0.70},
        'DSR': {'warning': 0.90, 'yellow': 0.85, 'orange': 0.80, 'red': 0.75},
        'LOG_RETURN_T': {'warning': 2.0, 'yellow': 1.5, 'orange': 1.0, 'red': 0.5},
        'CO_FACTOR': {'warning': 1.5, 'yellow': 1.3, 'orange': 1.0, 'red': 0.8},
        'JUMP_INTENSITY': {'warning': 0.020, 'yellow': 0.025, 'orange': 0.030, 'red': 0.040},
        'AS_COST': {'warning': 0.0006, 'yellow': 0.0008, 'orange': 0.0010, 'red': 0.0012},
        'MRR_RHO': {'warning': 0.05, 'yellow': 0.0, 'orange': -0.05, 'red': -0.10},
        'HARRVJ_MAE': {'warning': 0.30, 'yellow': 0.35, 'orange': 0.40, 'red': 0.50},
        'CPV': {'warning': 0, 'yellow': -5, 'orange': -10, 'red': -15},
        'PROB_FAILURE': {'warning': 0.05, 'yellow': 0.10, 'orange': 0.20, 'red': 0.35},
    }
    
    def __init__(self, config, performance_layer, regime_layer):
        self.config = config
        self.performance_layer = performance_layer
        self.regime_layer = regime_layer
        
        # Alert storage
        self.alerts: deque = deque(maxlen=1000)
        self.active_alerts: Dict[str, StrategyAlert] = {}
        
        # Manual review flag
        self.manual_review_required = False
        self.trading_suspended = False
        
        # Bootstrap mode tracking
        self.bootstrap_trades_count = 0
        self.bootstrap_mode_active = getattr(config, 'BOOTSTRAP_MODE', True)
        self.bootstrap_trades_target = getattr(config, 'BOOTSTRAP_TRADES', 5)
        self._bootstrap_logged = False  # Track if we've logged bootstrap status
        
        if self.bootstrap_mode_active:
            logger.warning(f"🚀 BOOTSTRAP MODE ACTIVE - Will allow {self.bootstrap_trades_target} trades without PSR/DSR validation")
            logger.warning(f"   Set BOOTSTRAP_MODE=False in config after initial trades to enable full validation")
        
        # Alert callbacks
        self.alert_callbacks: List[Callable[[StrategyAlert], None]] = []
        
        # Tracking windows
        self._log_return_history: deque = deque(maxlen=20)
        self._mrr_rho_history: deque = deque(maxlen=3)  # 3 consecutive windows
        self._as_cost_history: deque = deque(maxlen=30)  # 30 trades
        
        logger.info("Layer 8 initialized")
        
    def check_validity(self, features=None) -> bool:
        """Run all sentinel checks, return True if strategy valid"""
        timestamp = datetime.now()
        is_valid = True
        
        # Get current metrics
        metrics = self.performance_layer.compute_metrics()
        
        # Bootstrap mode: skip PSR/DSR/ProbFailure for first N trades
        in_bootstrap = self.bootstrap_mode_active and self.bootstrap_trades_count < self.bootstrap_trades_target
        
        if in_bootstrap:
            logger.debug(f"Bootstrap mode: skipping PSR/DSR checks ({self.bootstrap_trades_count}/{self.bootstrap_trades_target} trades)")
        else:
            # 1. PSR Check
            if not self._check_psr(metrics.psr_sr0, timestamp):
                is_valid = False
                
            # 2. DSR Check
            if not self._check_dsr(metrics.dsr, timestamp):
                is_valid = False
            
        # 3. Log Return T-stat Check - skip in bootstrap
        if not in_bootstrap:
            self._log_return_history.append(metrics.log_return_tstat)
            if len(self._log_return_history) >= 20:
                if not self._check_log_return_tstat(np.mean(self._log_return_history), timestamp):
                    is_valid = False
                
        # 4. MinTRL Check
        if metrics.total_trades < metrics.min_trl:
            logger.debug(f"MinTRL not met: {metrics.total_trades}/{metrics.min_trl:.0f}")
            
        # 5. P(Strategy Failure) Check - skip in bootstrap
        if not in_bootstrap and not self._check_prob_failure(metrics.prob_strategy_failure, timestamp):
            is_valid = False
            
        # 6. Jump Intensity Check
        if features and not self._check_jump_intensity(features.jump_lambda, timestamp):
            is_valid = False
            
        # 7. Adverse Selection Cost Check
        if not self._check_as_cost(metrics.mean_adverse_selection_cost, timestamp):
            is_valid = False
            
        # 8. MRR Rho Check
        if features:
            self._mrr_rho_history.append(features.order_flow_autocorr)
            if not self._check_mrr_rho(timestamp):
                is_valid = False
                
        # 9. HARRVJ MAE Check
        if not self._check_harrvj_mae(metrics.harrvj_mae, timestamp):
            is_valid = False
            
        # 10. CPV Check
        if not self._check_cpv(metrics.cumulative_prospect_value, timestamp):
            is_valid = False
            
        # 11. CO Factor Check
        if features and not self._check_co_factor(features.co_value, timestamp):
            is_valid = False
            
        # Check manual review triggers - skip in bootstrap
        if not in_bootstrap:
            self._check_manual_review_triggers(metrics, timestamp)
        
        return is_valid and not self.trading_suspended
        
    def _check_psr(self, psr: float, timestamp: datetime) -> bool:
        """Check PSR threshold"""
        thresholds = self.THRESHOLDS['PSR']
        
        if psr < thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'PSR', 
                             f"PSR({psr:.2%}) critically low", psr, thresholds['red'],
                             "Halt all trading, full system review", True)
            return False
        elif psr < thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'PSR',
                             f"PSR({psr:.2%}) below 75%", psr, thresholds['orange'],
                             "Suspend entries, diagnostic mode")
        elif psr < thresholds['yellow']:
            self._create_alert(timestamp, AlertLevel.YELLOW, 'PSR',
                             f"PSR({psr:.2%}) below 80%", psr, thresholds['yellow'],
                             "50% position size reduction")
        elif psr < thresholds['warning']:
            self._create_alert(timestamp, AlertLevel.WARNING, 'PSR',
                             f"PSR({psr:.2%}) below 90%", psr, thresholds['warning'],
                             "Monitor closely")
                             
        return True
        
    def _check_dsr(self, dsr: float, timestamp: datetime) -> bool:
        """Check DSR threshold"""
        thresholds = self.THRESHOLDS['DSR']
        
        if dsr < thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'DSR',
                             f"DSR({dsr:.2%}) critically low - possible overfitting", 
                             dsr, thresholds['red'],
                             "Halt trading, overfitting investigation", True)
            return False
        elif dsr < thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'DSR',
                             f"DSR({dsr:.2%}) suggests overfitting", dsr, thresholds['orange'],
                             "Review strategy complexity")
        elif dsr < thresholds['yellow']:
            self._create_alert(timestamp, AlertLevel.YELLOW, 'DSR',
                             f"DSR({dsr:.2%}) warning", dsr, thresholds['yellow'],
                             "Alert for overfitting")
                             
        return True
        
    def _check_log_return_tstat(self, tstat: float, timestamp: datetime) -> bool:
        """Check log return t-statistic"""
        thresholds = self.THRESHOLDS['LOG_RETURN_T']
        
        if tstat < thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'LOG_RETURN',
                             f"Log return t-stat {tstat:.2f} critically low", tstat, thresholds['red'],
                             "Full strategy review", True)
            return False
        elif tstat < thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'LOG_RETURN',
                             f"Log return t-stat {tstat:.2f} below 1.0", tstat, thresholds['orange'],
                             "50% size, investigate")
        elif tstat < thresholds['yellow']:
            self._create_alert(timestamp, AlertLevel.YELLOW, 'LOG_RETURN',
                             f"Log return t-stat {tstat:.2f} below 1.5", tstat, thresholds['yellow'],
                             "Enhanced monitoring")
                             
        return True
        
    def _check_prob_failure(self, prob: float, timestamp: datetime) -> bool:
        """Check P(Strategy Failure)"""
        thresholds = self.THRESHOLDS['PROB_FAILURE']
        
        if prob > thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'PROB_FAILURE',
                             f"P(Failure) = {prob:.1%} - CRITICAL", prob, thresholds['red'],
                             "HALT ALL TRADING", True)
            return False
        elif prob > thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'PROB_FAILURE',
                             f"P(Failure) = {prob:.1%} - suspend 24h", prob, thresholds['orange'],
                             "No new entries 24h")
        elif prob > thresholds['yellow']:
            self._create_alert(timestamp, AlertLevel.YELLOW, 'PROB_FAILURE',
                             f"P(Failure) = {prob:.1%} - yellow alert", prob, thresholds['yellow'],
                             "50% position size")
        elif prob > thresholds['warning']:
            self._create_alert(timestamp, AlertLevel.WARNING, 'PROB_FAILURE',
                             f"P(Failure) = {prob:.1%} - orange warning", prob, thresholds['warning'],
                             "Monitor closely")
                             
        return True
        
    def _check_jump_intensity(self, lam: float, timestamp: datetime) -> bool:
        """Check jump intensity"""
        thresholds = self.THRESHOLDS['JUMP_INTENSITY']
        
        if lam > thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'JUMP_INTENSITY',
                             f"Jump intensity λ={lam:.3f} extreme", lam, thresholds['red'],
                             "Regime 4, minimum sizing", True)
            return False
        elif lam > thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'JUMP_INTENSITY',
                             f"Jump intensity λ={lam:.3f} high", lam, thresholds['orange'],
                             "Regime 4, 25% size")
                             
        return True
        
    def _check_as_cost(self, cost: float, timestamp: datetime) -> bool:
        """Check adverse selection cost"""
        thresholds = self.THRESHOLDS['AS_COST']
        
        if cost > thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'AS_COST',
                             f"AS cost {cost:.3%} critically high", cost, thresholds['red'],
                             "Suspend 4h, review MRR", True)
            return False
        elif cost > thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'AS_COST',
                             f"AS cost {cost:.3%} high", cost, thresholds['orange'],
                             "75% size, check microstructure")
        elif cost > thresholds['yellow']:
            self._create_alert(timestamp, AlertLevel.YELLOW, 'AS_COST',
                             f"AS cost {cost:.3%} elevated", cost, thresholds['yellow'],
                             "Reduce trading frequency")
                             
        return True
        
    def _check_mrr_rho(self, timestamp: datetime) -> bool:
        """Check MRR rho consistency"""
        if len(self._mrr_rho_history) < 3:
            return True
            
        rhos = list(self._mrr_rho_history)
        avg_rho = np.mean(rhos)
        
        thresholds = self.THRESHOLDS['MRR_RHO']
        
        if avg_rho < thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'MRR_RHO',
                             f"MRR ρ avg = {avg_rho:.3f} negative", avg_rho, thresholds['red'],
                             "Block new longs")
            return False
        elif avg_rho < thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'MRR_RHO',
                             f"MRR ρ avg = {avg_rho:.3f} low", avg_rho, thresholds['orange'],
                             "Reduce TSMOM weight 25%")
                             
        return True
        
    def _check_harrvj_mae(self, mae: float, timestamp: datetime) -> bool:
        """Check HARRVJ forecast accuracy"""
        thresholds = self.THRESHOLDS['HARRVJ_MAE']
        
        if mae > thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'HARRVJ',
                             f"HARRVJ MAE = {mae:.2f} - model broken", mae, thresholds['red'],
                             "Fall back to ATR, recalibrate", True)
            return False
        elif mae > thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'HARRVJ',
                             f"HARRVJ MAE = {mae:.2f} poor", mae, thresholds['orange'],
                             "Fall back to ATR")
        elif mae > thresholds['warning']:
            self._create_alert(timestamp, AlertLevel.WARNING, 'HARRVJ',
                             f"HARRVJ MAE = {mae:.2f} elevated", mae, thresholds['warning'],
                             "Schedule recalibration")
                             
        return True
        
    def _check_cpv(self, cpv: float, timestamp: datetime) -> bool:
        """Check Cumulative Prospect Value"""
        thresholds = self.THRESHOLDS['CPV']
        
        if cpv < thresholds['red']:
            self._create_alert(timestamp, AlertLevel.RED, 'PROSPECT',
                             f"CPV = {cpv:.2f} - behavioral edge gone", cpv, thresholds['red'],
                             "Full behavioral review", True)
            return False
        elif cpv < thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'PROSPECT',
                             f"CPV = {cpv:.2f} declining", cpv, thresholds['orange'],
                             "Investigate value function fit")
                             
        return True
        
    def _check_co_factor(self, co: float, timestamp: datetime) -> bool:
        """Check CO factor t-statistic proxy"""
        thresholds = self.THRESHOLDS['CO_FACTOR']
        
        # Simplified check - assume CO value itself as proxy
        if co < thresholds['orange']:
            self._create_alert(timestamp, AlertLevel.ORANGE, 'CO_FACTOR',
                             f"CO = {co:.3f} fading", co, thresholds['orange'],
                             "Behavioral edge fading")
                             
        return True
        
    def _check_manual_review_triggers(self, metrics, timestamp: datetime):
        """Check PRD Section 11.2 manual review triggers"""
        requires_review = False
        reasons = []
        
        if metrics.dsr < 0.90:
            requires_review = True
            reasons.append(f"DSR = {metrics.dsr:.2%}")
            
        if metrics.prob_strategy_failure > 0.35:
            requires_review = True
            reasons.append(f"P(Failure) = {metrics.prob_strategy_failure:.1%}")
            
        if metrics.psr_sr0 < 0.75:
            requires_review = True
            reasons.append(f"PSR(SR*=0) = {metrics.psr_sr0:.1%}")
            
        # Current TuW vs 95th percentile
        if metrics.current_tuw > 3 * metrics.tuw_95th:
            requires_review = True
            reasons.append(f"TuW = {metrics.current_tuw:.1f}h vs 95th = {metrics.tuw_95th:.1f}h")
            
        # Win rate check
        if metrics.total_trades >= 20 and metrics.win_rate < 0.333:
            requires_review = True
            reasons.append(f"Win rate = {metrics.win_rate:.1%} over 20 trades")
            
        if requires_review:
            self.manual_review_required = True
            self.trading_suspended = True
            self._create_alert(timestamp, AlertLevel.RED, 'MANUAL_REVIEW',
                             f"Manual review required: {', '.join(reasons)}", 0, 0,
                             "HALT TRADING - AWAIT MANUAL REVIEW", True)
            
    def _create_alert(self, timestamp: datetime, level: AlertLevel, category: str,
                      message: str, value: float, threshold: float,
                      action: str, requires_review: bool = False):
        """Create and store alert"""
        alert = StrategyAlert(
            timestamp=timestamp,
            level=level,
            category=category,
            message=message,
            metric_value=value,
            threshold=threshold,
            action_taken=action,
            requires_manual_review=requires_review,
        )
        
        self.alerts.append(alert)
        self.active_alerts[f"{category}_{timestamp.isoformat()}"] = alert
        
        # Notify callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")
                
        logger.log(
            level.value.upper() if level.value in ['warning', 'info'] else 'CRITICAL',
            f"[{category}] {message} | Action: {action}"
        )
        
        # Auto-actions for critical alerts
        if level == AlertLevel.RED:
            if category == 'PSR' or category == 'PROB_FAILURE':
                self.trading_suspended = True
                
    def acknowledge_alert(self, alert_key: str) -> bool:
        """Acknowledge an alert"""
        if alert_key in self.active_alerts:
            self.active_alerts[alert_key].acknowledged = True
            return True
        return False
        
    def clear_manual_review(self):
        """Clear manual review flag (requires human verification)"""
        self.manual_review_required = False
        self.trading_suspended = False
        logger.info("Manual review cleared - trading resumed")
        
    def get_active_alerts(self) -> List[StrategyAlert]:
        """Get all non-acknowledged active alerts"""
        return [a for a in self.active_alerts.values() if not a.acknowledged]
        
    def get_alert_history(self, n: int = 100) -> List[StrategyAlert]:
        """Get recent alert history"""
        return list(self.alerts)[-n:]
        
    def register_alert_callback(self, callback: Callable[[StrategyAlert], None]):
        """Register alert callback"""
        self.alert_callbacks.append(callback)
        
    def is_trading_allowed(self) -> bool:
        """Check if trading is currently allowed - bypass PSR/DSR in bootstrap mode"""
        # Bootstrap mode: allow trading for first N trades regardless of PSR/DSR
        if self.bootstrap_mode_active and self.bootstrap_trades_count < self.bootstrap_trades_target:
            return True
        
        return not self.trading_suspended and not self.manual_review_required
    
    def record_trade(self):
        """Record a trade for bootstrap tracking"""
        if self.bootstrap_mode_active:
            self.bootstrap_trades_count += 1
            logger.info(f"Bootstrap trade {self.bootstrap_trades_count}/{self.bootstrap_trades_target}")
            
            if self.bootstrap_trades_count >= self.bootstrap_trades_target:
                logger.info("Bootstrap complete - switching to full PSR/DSR validation")
                self.bootstrap_mode_active = False
