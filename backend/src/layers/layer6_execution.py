"""
Layer 6: Execution
Paper trading order simulation with microstructure costs
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional
from enum import Enum
from collections import deque
import numpy as np
from loguru import logger


class OrderStatus(Enum):
    PENDING = "pending"
    FILLED = "filled"
    PARTIAL = "partial"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class PositionState(Enum):
    PENDING_ENTRY = "pending_entry"
    ACTIVE = "active"
    PARTIAL_EXIT = "partial_exit"
    CLOSED = "closed"


@dataclass
class PaperOrder:
    """Paper trading order"""
    order_id: str
    timestamp: datetime
    symbol: str
    side: str  # BUY, SELL
    order_type: str  # MARKET, LIMIT
    quantity: float
    price: float
    status: OrderStatus
    filled_qty: float = 0.0
    filled_price: float = 0.0
    fees_paid: float = 0.0
    slippage: float = 0.0
    adverse_selection_cost: float = 0.0


@dataclass
class PaperPosition:
    """Paper trading position"""
    position_id: str
    trade_id: str
    symbol: str
    
    # Entry
    entry_timestamp: datetime
    entry_price: float
    direction: str  # LONG, SHORT
    position_size_btc: float
    position_size_usd: float
    
    # Exit parameters
    stop_loss: float = 0.0
    take_profit_1: float = 0.0
    take_profit_2: float = 0.0
    tp1_hit: bool = False
    tp2_hit: bool = False
    
    # Risk levels
    composite_score: int = 0
    regime_at_entry: int = 0
    tsmom_rank_at_entry: float = 0.0
    co_value_at_entry: float = 0.0
    harrvj_forecast_at_entry: float = 0.0
    liquidity_score_at_entry: float = 0.0
    mrr_theta_at_entry: float = 0.0
    mrr_rho_at_entry: float = 0.0
    s_score_at_entry: float = 0.0
    reference_point_at_entry: float = 0.0
    
    # Execution
    entry_order: Optional[PaperOrder] = None
    exit_order: Optional[PaperOrder] = None
    
    # State
    state: PositionState = PositionState.PENDING_ENTRY
    
    # P&L tracking
    mfe: float = 0.0  # Maximum favorable excursion
    mae: float = 0.0  # Maximum adverse excursion
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    # Exit
    exit_timestamp: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None
    
    # Cost breakdown
    fixed_fees: float = 0.0
    execution_slippage: float = 0.0
    adverse_selection_cost: float = 0.0
    
    # Risk metrics
    kelly_fraction_used: float = 0.0
    jump_haircut_applied: float = 0.0
    
    # Prospect theory
    prospect_value: float = 0.0
    v_gain: float = 0.0
    v_loss: float = 0.0
    pi_p_win: float = 0.0
    pi_p_loss: float = 0.0
    
    def to_dict(self) -> Dict:
        # Calculate total P&L for flat field compatibility
        total_pnl = self.realized_pnl + self.unrealized_pnl
        return {
            'position_id': self.position_id,
            'trade_id': self.trade_id,
            'symbol': self.symbol,
            'direction': self.direction,
            'state': self.state.value,
            # Flat fields for frontend compatibility
            'timestamp': self.entry_timestamp.isoformat() if self.entry_timestamp else None,
            'entry_price': self.entry_price,
            'exit_price': self.exit_price,
            'pnl': total_pnl,
            'unrealized_pnl': self.unrealized_pnl,
            'size': self.position_size_btc,
            'stop_loss': self.stop_loss,
            'take_profit': self.take_profit_1,
            'status': 'CLOSED' if self.state.value == 'CLOSED' else 'OPEN',
            # Nested structures (keep for compatibility)
            'entry': {
                'timestamp': self.entry_timestamp.isoformat() if self.entry_timestamp else None,
                'price': self.entry_price,
                'size_btc': self.position_size_btc,
                'size_usd': self.position_size_usd,
            },
            'exit': {
                'timestamp': self.exit_timestamp.isoformat() if self.exit_timestamp else None,
                'price': self.exit_price,
                'reason': self.exit_reason,
            } if self.exit_timestamp else None,
            'risk_levels': {
                'stop_loss': self.stop_loss,
                'take_profit_1': self.take_profit_1,
                'take_profit_2': self.take_profit_2,
            },
            'pnl_detail': {
                'unrealized': self.unrealized_pnl,
                'realized': self.realized_pnl,
                'mfe': self.mfe,
                'mae': self.mae,
            },
            'costs': {
                'fixed_fees': self.fixed_fees,
                'slippage': self.execution_slippage,
                'adverse_selection': self.adverse_selection_cost,
            },
            'context': {
                'composite_score': self.composite_score,
                'regime': self.regime_at_entry,
                'tsmom_rank': self.tsmom_rank_at_entry,
            }
        }


class ExecutionLayer:
    """
    Layer 6: Execution
    Paper trading with realistic cost simulation (Dimpfl 2017 + Han et al. 2026)
    """
    
    def __init__(self, config, risk_layer, prospect_layer):
        self.config = config
        self.risk_layer = risk_layer
        self.prospect_layer = prospect_layer
        
        # Position tracking
        self.positions: Dict[str, PaperPosition] = {}
        self.position_history: deque = deque(maxlen=1000)
        self.closed_trades: deque = deque(maxlen=1000)
        
        # Order tracking
        self.orders: Dict[str, PaperOrder] = {}
        self.order_counter = 0
        
        # Trade ledger for analytics
        self.trade_ledger: List[Dict] = []
        
        # Current market state
        self.current_price: float = 0.0
        self.current_spread: float = 0.0
        
        logger.info("Layer 6 initialized")
        
    def on_price_update(self, price: float, spread: float = 0.0):
        """Update current market price"""
        self.current_price = price
        self.current_spread = spread
        
        # Update open positions
        for position in self.positions.values():
            if position.state == PositionState.ACTIVE:
                self._update_position_pnl(position, price)
                
    def _update_position_pnl(self, position: PaperPosition, current_price: float):
        """Update position P&L and track MFE/MAE"""
        if position.direction == "LONG":
            unrealized = (current_price - position.entry_price) * position.position_size_btc
            excursion = (current_price - position.entry_price) / position.entry_price
        else:
            unrealized = (position.entry_price - current_price) * position.position_size_btc
            excursion = (position.entry_price - current_price) / position.entry_price
            
        position.unrealized_pnl = unrealized
        
        # Update MFE/MAE
        if excursion > 0:
            position.mfe = max(position.mfe, excursion)
        else:
            position.mae = max(position.mae, abs(excursion))
            
        # Check stops
        self._check_stop_conditions(position, current_price)
        
    def _check_stop_conditions(self, position: PaperPosition, current_price: float):
        """Check if stop loss or take profit hit"""
        if position.direction == "LONG":
            if current_price <= position.stop_loss:
                self._close_position(position, position.stop_loss, "STOP_LOSS")
            elif current_price >= position.take_profit_1:
                # Partial exit at TP1
                if position.state != PositionState.PARTIAL_EXIT:
                    self._partial_exit(position, position.take_profit_1, "TP1")
            elif current_price >= position.take_profit_2:
                # Full exit at TP2
                self._close_position(position, position.take_profit_2, "TP2")
        else:
            if current_price >= position.stop_loss:
                self._close_position(position, position.stop_loss, "STOP_LOSS")
            elif current_price <= position.take_profit_1:
                if position.state != PositionState.PARTIAL_EXIT:
                    self._partial_exit(position, position.take_profit_1, "TP1")
            elif current_price <= position.take_profit_2:
                # Full exit at TP2
                self._close_position(position, position.take_profit_2, "TP2")

        # Check duration-based exit (max position duration in hours)
        max_duration_hours = getattr(self.config, 'MAX_POSITION_DURATION_HOURS', 24)
        if position.entry_timestamp:
            duration_hours = (datetime.now() - position.entry_timestamp).total_seconds() / 3600
            if duration_hours >= max_duration_hours:
                self._close_position(position, current_price, "TIME_EXPIRED")
                    
    def create_position(self, signal, sizing, features, timestamp: datetime) -> Optional[PaperPosition]:
        """Create new position from signal"""

        # Check constraints
        if sizing.circuit_breaker_active:
            logger.warning("Position creation blocked: circuit breaker active")
            return None

        if sizing.daily_trade_limit_capped:
            logger.warning("Position creation blocked: daily trade limit reached")
            return None

        if sizing.target_position_size_usd <= 0:
            return None

        # Check max positions limit
        max_positions = getattr(self.config, 'MAX_POSITIONS', 1)
        open_positions = self.get_open_positions()
        if len(open_positions) >= max_positions:
            logger.warning(f"Position creation blocked: max positions ({max_positions}) reached")
            return None
            
        # Generate IDs
        self.order_counter += 1
        position_id = f"POS_{timestamp.strftime('%Y%m%d_%H%M%S')}_{self.order_counter}"
        trade_id = f"TRADE_{self.order_counter}"
        
        # Simulate entry execution
        entry_order = self._simulate_market_order(
            symbol=self.config.SYMBOL,
            side="BUY" if signal.direction == "LONG" else "SELL",
            quantity=sizing.target_position_size_btc,
            timestamp=timestamp,
            mrr_theta=features.mrr_theta,
        )
        
        if entry_order.status == OrderStatus.REJECTED:
            logger.error("Entry order rejected")
            return None
            
        # Calculate prospect theory values
        win_prob = signal.historical_win_rate
        gain = signal.expected_rr * sizing.target_position_size_usd * 0.01
        loss = -sizing.target_position_size_usd * 0.01
        
        v_gain = self.prospect_layer.value_function(gain / self.config.INITIAL_CAPITAL)
        v_loss = self.prospect_layer.value_function(loss / self.config.INITIAL_CAPITAL)
        pi_win = self.prospect_layer.probability_weighting(win_prob)
        pi_loss = self.prospect_layer.probability_weighting(1 - win_prob)
        prospect_value = pi_win * v_gain + pi_loss * v_loss
        
        position = PaperPosition(
            position_id=position_id,
            trade_id=trade_id,
            symbol=self.config.SYMBOL,
            entry_timestamp=timestamp,
            entry_price=entry_order.filled_price,
            direction=signal.direction,
            position_size_btc=sizing.target_position_size_btc,
            position_size_usd=sizing.target_position_size_usd,
            stop_loss=signal.recommended_stop,
            take_profit_1=signal.recommended_tp1,
            take_profit_2=signal.recommended_tp2,
            composite_score=signal.composite_score,
            regime_at_entry=signal.regime,
            tsmom_rank_at_entry=features.tsmom_rank,
            co_value_at_entry=features.co_value,
            harrvj_forecast_at_entry=features.harrvj_forecast,
            liquidity_score_at_entry=features.liquidity_score,
            mrr_theta_at_entry=features.mrr_theta,
            mrr_rho_at_entry=features.order_flow_autocorr,
            s_score_at_entry=features.s_score,
            reference_point_at_entry=self.risk_layer.reference_point,
            entry_order=entry_order,
            state=PositionState.ACTIVE,
            fixed_fees=entry_order.fees_paid,
            execution_slippage=entry_order.slippage,
            adverse_selection_cost=entry_order.adverse_selection_cost,
            kelly_fraction_used=sizing.kelly_half_fraction,
            jump_haircut_applied=sizing.jump_haircut,
            prospect_value=prospect_value,
            v_gain=v_gain,
            v_loss=v_loss,
            pi_p_win=pi_win,
            pi_p_loss=pi_loss,
        )
        
        self.positions[position_id] = position
        self.risk_layer.record_trade_entry(position.to_dict(), timestamp)
        
        logger.info(f"Position created: {position_id} | {signal.direction} | "
                   f"{sizing.target_position_size_usd:.2f} USD | Score: {signal.composite_score}")
        
        return position
        
    def _simulate_market_order(self, symbol: str, side: str, quantity: float,
                                timestamp: datetime, mrr_theta: float) -> PaperOrder:
        """
        Simulate market order with realistic costs (Dimpfl 2017)
        Total cost: 0.15% expected, 0.23% 95th percentile
        """
        self.order_counter += 1
        order_id = f"ORD_{timestamp.strftime('%Y%m%d%H%M%S')}_{self.order_counter}"
        
        # Base price
        base_price = self.current_price
        
        # Slippage: LogNormal(μ=0.03%, σ=0.02%)
        slippage_pct = np.random.lognormal(np.log(0.0003), 0.0002)
        
        # Adverse selection cost (Dimpfl 2017)
        # AS% = θ / mid_price * 100
        as_cost_pct = mrr_theta / base_price if base_price > 0 else 0.0005
        
        # Fixed fees
        maker_fee = self.config.MAKER_FEE
        taker_fee = self.config.TAKER_FEE
        
        # Directional price impact
        if side == "BUY":
            filled_price = base_price * (1 + slippage_pct)
        else:
            filled_price = base_price * (1 - slippage_pct)
            
        # Total costs
        total_fees = quantity * filled_price * (maker_fee + taker_fee)
        slippage_cost = quantity * filled_price * slippage_pct
        as_cost = quantity * filled_price * as_cost_pct
        
        order = PaperOrder(
            order_id=order_id,
            timestamp=timestamp,
            symbol=symbol,
            side=side,
            order_type="MARKET",
            quantity=quantity,
            price=base_price,
            status=OrderStatus.FILLED,
            filled_qty=quantity,
            filled_price=filled_price,
            fees_paid=total_fees,
            slippage=slippage_cost,
            adverse_selection_cost=as_cost,
        )
        
        self.orders[order_id] = order
        
        return order
        
    def _partial_exit(self, position: PaperPosition, price: float, reason: str):
        """Execute partial position exit"""
        # Close 50% at TP1
        exit_qty = position.position_size_btc * 0.5
        
        exit_order = self._simulate_market_order(
            symbol=position.symbol,
            side="SELL" if position.direction == "LONG" else "BUY",
            quantity=exit_qty,
            timestamp=datetime.now(),
            mrr_theta=0.0,  # Use current
        )
        
        # Calculate realized P&L on exited portion
        if position.direction == "LONG":
            pnl = (price - position.entry_price) * exit_qty
        else:
            pnl = (position.entry_price - price) * exit_qty
            
        position.realized_pnl += pnl - exit_order.fees_paid
        position.state = PositionState.PARTIAL_EXIT
        
        logger.info(f"Partial exit: {position.position_id} | {reason} | PnL: {pnl:.2f}")
        
    def _close_position(self, position: PaperPosition, price: float, reason: str):
        """Close position fully"""
        if position.state == PositionState.CLOSED:
            return
            
        timestamp = datetime.now()
        
        # Calculate remaining quantity
        remaining_qty = position.position_size_btc
        if position.state == PositionState.PARTIAL_EXIT:
            remaining_qty *= 0.5
            
        exit_order = self._simulate_market_order(
            symbol=position.symbol,
            side="SELL" if position.direction == "LONG" else "BUY",
            quantity=remaining_qty,
            timestamp=timestamp,
            mrr_theta=0.0,
        )
        
        # Calculate P&L
        if position.direction == "LONG":
            gross_pnl = (price - position.entry_price) * position.position_size_btc
        else:
            gross_pnl = (position.entry_price - price) * position.position_size_btc
            
        # Total costs
        entry_costs = position.fixed_fees + position.execution_slippage + position.adverse_selection_cost
        exit_costs = exit_order.fees_paid + exit_order.slippage + exit_order.adverse_selection_cost
        
        net_pnl = gross_pnl - entry_costs - exit_costs
        
        # Update position
        position.exit_timestamp = timestamp
        position.exit_price = price
        position.exit_reason = reason
        position.exit_order = exit_order
        position.realized_pnl = net_pnl
        position.state = PositionState.CLOSED
        
        # Record to ledger
        trade_record = self._create_trade_ledger_record(position, gross_pnl, net_pnl)
        self.trade_ledger.append(trade_record)
        self.closed_trades.append(position)
        
        # Update risk layer
        self.risk_layer.record_trade_exit({
            'net_pnl': net_pnl,
            'cumulative_equity': self.risk_layer.current_equity + net_pnl,
            'exit_timestamp': timestamp,
        })
        
        # Remove from active positions
        if position.position_id in self.positions:
            del self.positions[position.position_id]
            
        logger.info(f"Position closed: {position.position_id} | {reason} | Net PnL: {net_pnl:.2f}")
        
    def close_position(self, position: PaperPosition, price: float, reason: str):
        """Public method to close position (wrapper for _close_position)"""
        self._close_position(position, price, reason)
        
    def _create_trade_ledger_record(self, position: PaperPosition, 
                                     gross_pnl: float, net_pnl: float) -> Dict:
        """Create complete trade ledger record per PRD Section 9.3"""
        return {
            'trade_id': position.trade_id,
            'entry_timestamp': position.entry_timestamp.isoformat(),
            'entry_price': position.entry_price,
            'direction': position.direction,
            'position_size_btc': position.position_size_btc,
            'position_size_usd': position.position_size_usd,
            'stop_loss': position.stop_loss,
            'tp1': position.take_profit_1,
            'tp2': position.take_profit_2,
            'composite_score': position.composite_score,
            'regime': position.regime_at_entry,
            'exit_timestamp': position.exit_timestamp.isoformat() if position.exit_timestamp else None,
            'exit_price': position.exit_price,
            'exit_reason': position.exit_reason,
            'gross_pnl': gross_pnl,
            'fixed_fees': position.fixed_fees + (position.exit_order.fees_paid if position.exit_order else 0),
            'execution_slippage': position.execution_slippage + (position.exit_order.slippage if position.exit_order else 0),
            'adverse_selection_cost': position.adverse_selection_cost + (position.exit_order.adverse_selection_cost if position.exit_order else 0),
            'net_pnl': net_pnl,
            'cumulative_equity': self.risk_layer.current_equity + net_pnl,
            'mfe': position.mfe,
            'mae': position.mae,
            'kelly_fraction': position.kelly_fraction_used,
            'jump_haircut': position.jump_haircut_applied,
            'harrvj_forecast': position.harrvj_forecast_at_entry,
            'liquidity_score': position.liquidity_score_at_entry,
            'mrr_theta': position.mrr_theta_at_entry,
            'mrr_rho': position.mrr_rho_at_entry,
            'tsmom_rank': position.tsmom_rank_at_entry,
            'co_value': position.co_value_at_entry,
            'reference_point': position.reference_point_at_entry,
            'v_gain': position.v_gain,
            'v_loss': position.v_loss,
            'pi_p_win': position.pi_p_win,
            'pi_p_loss': position.pi_p_loss,
        }
        
    def get_open_positions(self) -> List[PaperPosition]:
        """Get all open positions"""
        return [p for p in self.positions.values() if p.state != PositionState.CLOSED]
        
    def get_closed_trades(self, n: int = 100) -> List[PaperPosition]:
        """Get recent closed trades"""
        return list(self.closed_trades)[-n:]
        
    def get_trade_ledger(self) -> List[Dict]:
        """Get complete trade ledger"""
        return self.trade_ledger
