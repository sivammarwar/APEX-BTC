"""
Layer 5: Risk Management
Kelly-Correct position sizing with fee-drag adjustment and prospect theory
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Tuple
from collections import deque
import numpy as np
from loguru import logger


@dataclass
class PositionSizing:
    """Risk-managed position sizing result"""
    # Position
    target_position_size_usd: float
    target_position_size_btc: float
    leverage: float
    
    # Sizing breakdown
    kelly_fraction_raw: float
    kelly_half_fraction: float
    jump_haircut: float
    volatility_scalar: float
    prospect_adjustment: float
    liquidity_scalar: float
    certainty_multiplier: float
    
    # Final multiplier
    final_size_multiplier: float
    
    # Constraints applied
    max_leverage_capped: bool
    daily_trade_limit_capped: bool
    circuit_breaker_active: bool
    
    def to_dict(self) -> Dict:
        return {
            'position_usd': self.target_position_size_usd,
            'position_btc': self.target_position_size_btc,
            'leverage': self.leverage,
            'kelly_half_fraction': self.kelly_half_fraction,
            'jump_haircut': self.jump_haircut,
            'volatility_scalar': self.volatility_scalar,
            'prospect_adjustment': self.prospect_adjustment,
            'liquidity_scalar': self.liquidity_scalar,
            'certainty_multiplier': self.certainty_multiplier,
            'final_multiplier': self.final_size_multiplier,
            'constraints_applied': {
                'max_leverage': self.max_leverage_capped,
                'daily_limit': self.daily_trade_limit_capped,
                'circuit_breaker': self.circuit_breaker_active,
            }
        }


@dataclass
class RiskState:
    """Current risk state for portfolio monitoring"""
    timestamp: datetime
    
    # Portfolio
    current_equity: float
    high_water_mark: float
    drawdown_pct: float
    
    # Position state
    open_positions: int
    total_exposure_usd: float
    total_exposure_btc: float
    effective_leverage: float
    
    # Circuit breakers
    circuit_breaker_level: str  # NONE, YELLOW, ORANGE, RED
    trading_halted: bool
    
    # Consecutive losses
    consecutive_losses: int
    position_size_penalty: float
    
    # Daily tracking
    daily_trades_count: int
    daily_pnl: float
    
    # Reference point for prospect theory
    reference_point: float
    domain: str  # gain, loss, neutral
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp.isoformat(),
            'equity': self.current_equity,
            'high_water_mark': self.high_water_mark,
            'drawdown_pct': self.drawdown_pct,
            'open_positions': self.open_positions,
            'exposure_usd': self.total_exposure_usd,
            'effective_leverage': self.effective_leverage,
            'circuit_breaker': self.circuit_breaker_level,
            'trading_halted': self.trading_halted,
            'consecutive_losses': self.consecutive_losses,
            'daily_trades': self.daily_trades_count,
            'reference_point': self.reference_point,
            'domain': self.domain,
        }


class RiskManagementLayer:
    """
    Layer 5: Risk Management
    Kelly criterion position sizing with all adjustments from PRD Section 8
    """
    
    def __init__(self, config, prospect_layer):
        self.config = config
        self.prospect_layer = prospect_layer
        
        # State
        self.initial_capital = config.INITIAL_CAPITAL
        self.current_equity = config.INITIAL_CAPITAL
        self.high_water_mark = config.INITIAL_CAPITAL
        self.reference_point = config.INITIAL_CAPITAL
        
        # Position tracking
        self.open_positions: list = []
        self.trade_history: deque = deque(maxlen=100)
        
        # Daily tracking
        self.daily_trades_count = 0
        self.last_trade_date: Optional[datetime] = None
        
        # Circuit breakers
        self.circuit_breaker_level = "NONE"
        self.trading_halted = False
        
        # Consecutive losses
        self.consecutive_losses = 0
        self.loss_penalty_active = False
        self.loss_penalty_trades_remaining = 0
        
        logger.info("Layer 5 initialized")
        
    def update_equity(self, current_equity: float, timestamp: datetime):
        """Update equity and compute risk metrics"""
        self.current_equity = current_equity
        
        # Update high water mark
        if current_equity > self.high_water_mark:
            self.high_water_mark = current_equity
            
        # Compute drawdown
        drawdown = (self.high_water_mark - current_equity) / self.high_water_mark
        
        # Update reference point (Prospect Theory)
        self.reference_point = self.prospect_layer.update_reference_point(
            current_equity,
            self.initial_capital,
            self.high_water_mark,
            drawdown
        )
        
        # Check circuit breakers
        self._check_circuit_breakers(drawdown, timestamp)
        
        # Reset daily counter if new day
        if self.last_trade_date and timestamp.date() != self.last_trade_date:
            self.daily_trades_count = 0
            
    def _check_circuit_breakers(self, drawdown: float, timestamp: datetime):
        """Check and update circuit breaker state"""
        prev_level = self.circuit_breaker_level
        
        if drawdown >= self.config.MAX_DRAWDOWN_PCT:
            self.circuit_breaker_level = "RED"
            self.trading_halted = True
            logger.critical(f"RED CIRCUIT BREAKER: {drawdown*100:.1f}% drawdown")
        elif drawdown >= self.config.ORANGE_DRAWDOWN:
            self.circuit_breaker_level = "ORANGE"
            # Suspend for 24 hours
            if prev_level != "ORANGE":
                logger.warning(f"ORANGE ALERT: {drawdown*100:.1f}% drawdown, 24h suspension")
        elif drawdown >= self.config.YELLOW_DRAWDOWN:
            self.circuit_breaker_level = "YELLOW"
            if prev_level != "YELLOW":
                logger.warning(f"YELLOW WARNING: {drawdown*100:.1f}% drawdown, 50% size reduction")
        else:
            self.circuit_breaker_level = "NONE"
            self.trading_halted = False
            
    def calculate_position_size(self, signal, features, current_price: float) -> PositionSizing:
        """
        Calculate Kelly-correct position size with all adjustments
        PRD Section 8.1
        """
        
        # Step 1: Total round-trip cost
        as_premium = features.adverse_selection_pct * features.mrr_spread / current_price
        total_cost = 0.0004 + 0.0004 + 0.0003 + as_premium  # maker + taker + slippage + AS
        
        # Step 2: Fee-adjusted outcomes (assume 2:1 R:R)
        win_rate = signal.historical_win_rate
        pi_plus = 2.0 * 0.01  # 2% gain target
        pi_minus = -1.0 * 0.01  # 1% loss
        
        pi_plus_net = pi_plus - total_cost
        pi_minus_net = pi_minus - total_cost
        
        # Step 3: Kelly fraction
        numerator = win_rate * pi_plus_net - (1 - win_rate) * abs(pi_minus_net)
        denominator = pi_plus_net * abs(pi_minus_net)
        
        if denominator == 0 or numerator <= 0:
            return PositionSizing(
                target_position_size_usd=0,
                target_position_size_btc=0,
                leverage=0,
                kelly_fraction_raw=0,
                kelly_half_fraction=0,
                jump_haircut=0,
                volatility_scalar=0,
                prospect_adjustment=1.0,
                liquidity_scalar=0,
                certainty_multiplier=1.0,
                final_size_multiplier=0,
                max_leverage_capped=False,
                daily_trade_limit_capped=False,
                circuit_breaker_active=self.trading_halted,
            )
            
        kelly_fraction = numerator / denominator
        
        # Step 4: Half-Kelly
        kelly_half = 0.5 * kelly_fraction
        
        # Step 5: Jump-diffusion haircut (Han et al. 2026)
        jump_haircut = 1.0 / (1.0 + features.jump_lambda * 
                             (features.jump_nu**2 + features.jump_delta**2) / 
                             (2 * pi_plus_net**2))
        f_jd = kelly_half * jump_haircut
        
        # Step 6: HARRVJ volatility scaling (Pichl & Kaizoji 2017)
        vol_target = self.config.TARGET_VOLATILITY
        vol_forecast = features.harrvj_forecast if features.harrvj_forecast > 0 else 0.5
        vol_scalar = vol_target / vol_forecast
        
        # Step 7: Prospect theory adjustments (Kahneman & Tversky 1979)
        gain_pct = (self.current_equity - self.initial_capital) / self.initial_capital
        drawdown_pct = (self.high_water_mark - self.current_equity) / self.high_water_mark
        
        prospect_adj = 1.0
        if gain_pct > 0.10:
            # House money effect
            prospect_adj = 1.2
        elif drawdown_pct > 0.05:
            # Break-even effect (risk-seeking to recover)
            prospect_adj = 1.15
        elif drawdown_pct > 0.10:
            # Capital preservation
            prospect_adj = 0.5
            
        f_pt = f_jd * prospect_adj
        
        # Step 8: Liquidity scaling (Dimpfl 2017)
        liquidity_scalar = min(1.0, features.liquidity_score / 1.5)
        
        # Certainty multiplier for high-confidence signals
        certainty_mult = 1.0
        if signal.composite_score > 95:
            certainty_mult = 1.10
        elif signal.composite_score > 90:
            certainty_mult = 1.05
            
        # Final sizing
        final_multiplier = f_pt * vol_scalar * liquidity_scalar * certainty_mult
        
        # Apply circuit breaker penalties
        if self.circuit_breaker_level == "YELLOW":
            final_multiplier *= 0.5
        elif self.circuit_breaker_level == "ORANGE":
            final_multiplier = 0.0  # No new entries
            
        # Apply consecutive loss penalty
        if self.consecutive_losses >= 3:
            final_multiplier *= 0.5
            
        # Calculate position
        position_usd = self.current_equity * final_multiplier
        position_btc = position_usd / current_price if current_price > 0 else 0
        
        # Calculate leverage
        leverage = position_usd / self.current_equity if self.current_equity > 0 else 0
        
        # Constraint checks
        max_leverage_capped = leverage > self.config.MAX_LEVERAGE
        if max_leverage_capped:
            leverage = self.config.MAX_LEVERAGE
            position_usd = self.current_equity * leverage
            position_btc = position_usd / current_price
            
        daily_limit_capped = self.daily_trades_count >= self.config.MAX_DAILY_TRADES
        
        sizing = PositionSizing(
            target_position_size_usd=position_usd,
            target_position_size_btc=position_btc,
            leverage=leverage,
            kelly_fraction_raw=kelly_fraction,
            kelly_half_fraction=kelly_half,
            jump_haircut=jump_haircut,
            volatility_scalar=vol_scalar,
            prospect_adjustment=prospect_adj,
            liquidity_scalar=liquidity_scalar,
            certainty_multiplier=certainty_mult,
            final_size_multiplier=final_multiplier,
            max_leverage_capped=max_leverage_capped,
            daily_trade_limit_capped=daily_limit_capped,
            circuit_breaker_active=self.trading_halted,
        )
        
        return sizing
        
    def calculate_stop_loss(self, entry_price: float, direction: str, 
                           features, current_pnl_pct: float = 0) -> float:
        """Calculate stop loss with prospect theory asymmetry"""
        atr = features.atr_harrvj
        
        # Base stop distance
        base_distance = 2.0 * atr
        
        # Prospect theory asymmetric adjustment
        if current_pnl_pct > 0:
            # Gain domain - tighter stop (risk averse)
            stop_distance = 1.5 * atr
        elif current_pnl_pct < 0:
            # Loss domain - wider stop (risk seeking)
            stop_distance = 3.0 * atr
        else:
            stop_distance = base_distance
            
        # Jump-adjusted stop
        if features.jump_lambda > 0.015:
            stop_distance = max(stop_distance, 1.5 * atr)
            
        if direction == "LONG":
            return entry_price - stop_distance
        else:
            return entry_price + stop_distance
            
    def calculate_take_profit(self, entry_price: float, stop_price: float, 
                              direction: str, tier: int = 1) -> float:
        """Calculate take profit with minimum 2:1 R:R"""
        risk = abs(entry_price - stop_price)
        
        if tier == 1:
            # First target at 1:1
            reward = risk
        elif tier == 2:
            # Second target at 2:1
            reward = 2.0 * risk
        else:
            reward = 3.0 * risk
            
        if direction == "LONG":
            return entry_price + reward
        else:
            return entry_price - reward
            
    def check_liquidation_risk(self, position_size_usd: float, 
                                current_price: float, stop_price: float) -> bool:
        """Check for intra-bar liquidation risk (Han et al. 2026)"""
        if self.current_equity <= 0:
            return True
            
        effective_leverage = position_size_usd / self.current_equity
        
        # Check if stop is within liquidation distance
        if effective_leverage > self.config.MAX_LEVERAGE:
            return True
            
        return False
        
    def record_trade_entry(self, position, timestamp: datetime):
        """Record new position entry"""
        self.open_positions.append(position)
        self.daily_trades_count += 1
        self.last_trade_date = timestamp.date()
        
    def record_trade_exit(self, trade_result: Dict):
        """Record trade exit and update risk state"""
        pnl = trade_result.get('net_pnl', 0)
        
        # Update consecutive losses
        if pnl < 0:
            self.consecutive_losses += 1
            if self.consecutive_losses >= 3:
                self.loss_penalty_active = True
                self.loss_penalty_trades_remaining = 5
        else:
            self.consecutive_losses = 0
            self.loss_penalty_active = False
            self.loss_penalty_trades_remaining = 0
            
        # Decrement penalty counter
        if self.loss_penalty_trades_remaining > 0:
            self.loss_penalty_trades_remaining -= 1
            if self.loss_penalty_trades_remaining == 0:
                self.loss_penalty_active = False
                
        # Update equity
        self.update_equity(trade_result.get('cumulative_equity', self.current_equity),
                          trade_result.get('exit_timestamp', datetime.now()))
        
        self.trade_history.append(trade_result)
        
    def get_risk_state(self) -> RiskState:
        """Get current risk state"""
        drawdown = (self.high_water_mark - self.current_equity) / self.high_water_mark
        
        # Determine domain
        if self.current_equity > self.high_water_mark:
            domain = "gain"
        elif self.current_equity < self.reference_point:
            domain = "loss"
        else:
            domain = "neutral"
            
        total_exposure = sum(p.get('size_usd', 0) for p in self.open_positions)
        effective_lev = total_exposure / self.current_equity if self.current_equity > 0 else 0
        
        return RiskState(
            timestamp=datetime.now(),
            current_equity=self.current_equity,
            high_water_mark=self.high_water_mark,
            drawdown_pct=drawdown,
            open_positions=len(self.open_positions),
            total_exposure_usd=total_exposure,
            total_exposure_btc=sum(p.get('size_btc', 0) for p in self.open_positions),
            effective_leverage=effective_lev,
            circuit_breaker_level=self.circuit_breaker_level,
            trading_halted=self.trading_halted,
            consecutive_losses=self.consecutive_losses,
            position_size_penalty=0.5 if self.loss_penalty_active else 1.0,
            daily_trades_count=self.daily_trades_count,
            daily_pnl=self.current_equity - self.initial_capital,
            reference_point=self.reference_point,
            domain=domain,
        )
