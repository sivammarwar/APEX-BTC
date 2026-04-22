"""
APEX-BTC Trading Engine
Orchestrates all 12 layers into a unified trading system
"""
import asyncio
from datetime import datetime
from typing import Optional, Dict, List
from dataclasses import dataclass
from loguru import logger

from ..layers.layer1_data_ingestion import DataIngestionLayer
from ..layers.layer2_feature_engineering import FeatureEngineeringLayer
from ..layers.layer3_regime_detection import RegimeDetectionLayer
from ..layers.layer4_signal_generation import SignalGenerationLayer
from ..layers.layer5_risk_management import RiskManagementLayer
from ..layers.layer6_execution import ExecutionLayer, PositionState
from ..layers.layer7_performance_analytics import PerformanceAnalyticsLayer
from ..layers.layer8_strategy_validity import StrategyValidityLayer
from ..layers.layer9_jump_diffusion import JumpDiffusionLayer
from ..layers.layer10_microstructure import MicrostructureLayer
from ..layers.layer11_prospect_theory import ProspectTheoryLayer
try:
    from ..layers.layer12_dqn_position_sizing import DQNPositionSizingLayer
    DQN_AVAILABLE = True
except ImportError:
    DQN_AVAILABLE = False
    logger.warning("PyTorch not available - DQN Layer 12 disabled")


@dataclass
class EngineState:
    """Complete state of the trading engine"""
    timestamp: datetime = None
    is_running: bool = False
    is_trading_allowed: bool = False
    
    # Market state
    current_price: float = 0.0
    current_spread: float = 0.0
    
    # Regime
    regime: Optional[Dict] = None
    
    # Signal
    latest_signal: Optional[Dict] = None
    
    # Risk
    equity: float = 0.0
    high_water_mark: float = 0.0
    drawdown_pct: float = 0.0
    open_positions: int = 0
    positions: Optional[List[Dict]] = None
    
    # Performance
    metrics: Optional[Dict] = None
    daily_pnl: float = 0.0
    pnl_30d: float = 0.0
    starting_equity: float = 10000.0
    
    # Alerts
    active_alerts: Optional[List[Dict]] = None
    manual_review_required: bool = False
    
    # Bootstrap mode
    validity_bootstrap: bool = False
    validity_bootstrap_count: int = 0


class TradingEngine:
    """
    APEX-BTC Trading Engine
    Complete integration of all 12 quantitative layers
    """
    
    def __init__(self, config, db_session=None):
        self.config = config
        self.db_session = db_session
        self.is_running = False
        
        # P&L tracking
        self.starting_equity = getattr(config, 'INITIAL_CAPITAL', 10000.0)
        self.daily_pnl = 0.0
        self.pnl_30d = 0.0
        self.daily_start_equity = self.starting_equity
        
        # Signal tracking for dashboard
        self.latest_signal = None
        
        # Initialize all 12 layers
        logger.info("Initializing APEX-BTC Trading Engine v6.0")
        
        # Layer 1: Data Ingestion
        self.data_layer = DataIngestionLayer(config, db_session)
        
        # Layer 2: Feature Engineering
        self.feature_layer = FeatureEngineeringLayer(config, self.data_layer)
        
        # Layer 3: Regime Detection
        self.regime_layer = RegimeDetectionLayer(config, self.feature_layer)
        
        # Layer 11: Prospect Theory (needed by other layers)
        self.prospect_layer = ProspectTheoryLayer(config)
        
        # Layer 5: Risk Management
        self.risk_layer = RiskManagementLayer(config, self.prospect_layer)
        
        # Layer 4: Signal Generation
        self.signal_layer = SignalGenerationLayer(
            config, self.feature_layer, self.regime_layer, 
            self.risk_layer, self.prospect_layer
        )
        
        # Layer 6: Execution
        self.execution_layer = ExecutionLayer(config, self.risk_layer, self.prospect_layer)
        
        # Layer 7: Performance Analytics
        self.performance_layer = PerformanceAnalyticsLayer(
            config, self.risk_layer, self.prospect_layer
        )
        
        # Layer 8: Strategy Validity
        self.validity_layer = StrategyValidityLayer(
            config, self.performance_layer, self.regime_layer
        )
        
        # Layer 9: Jump-Diffusion
        self.jump_layer = JumpDiffusionLayer(config, self.risk_layer)
        
        # Layer 10: Microstructure
        self.micro_layer = MicrostructureLayer(config)
        
        # Layer 12: DQN (optional)
        if DQN_AVAILABLE:
            self.dqn_layer = DQNPositionSizingLayer(config, self.feature_layer, self.risk_layer)
        else:
            self.dqn_layer = None
        
        # Register callbacks
        self._register_callbacks()
        
        logger.info("All 12 layers initialized successfully")
        
    def _register_callbacks(self):
        """Register inter-layer callbacks"""
        # Data -> Feature engineering
        self.data_layer.register_candle_callback(self._on_candle)
        self.data_layer.register_tick_callback(self._on_tick)
        
    async def start(self):
        """Start the trading engine"""
        logger.info("Starting APEX-BTC Trading Engine")
        
        # Initialize data layer
        await self.data_layer.initialize()
        
        # Start WebSocket connections
        await self.data_layer.start_websockets()
        
        self.is_running = True
        
        # Start main loop
        asyncio.create_task(self._main_loop())
        
        logger.info("Trading engine started")
        
    async def _main_loop(self):
        """Main trading loop"""
        signal_counter = 0
        while self.is_running:
            try:
                # Check strategy validity
                if not self.validity_layer.is_trading_allowed():
                    await asyncio.sleep(1)
                    continue
                    
                # Update jump-diffusion
                self._update_jump_diffusion()
                
                # Generate signals every 10 seconds (if we have price data)
                signal_counter += 1
                if signal_counter >= 10:
                    signal_counter = 0
                    current_price = self.data_layer.get_current_price()
                    if current_price:
                        try:
                            # Get latest features
                            features = self.feature_layer.get_latest_features()
                            if features:
                                # Detect regime
                                regime = self.regime_layer.detect_regime(features, current_price)
                                # Generate signal
                                signal = self.signal_layer.generate_signal(current_price)
                                # Store signal for dashboard
                                self.latest_signal = signal
                                logger.info(f"[SIGNAL] {signal.direction} | Score: {signal.composite_score}/{signal.max_possible_score} | Valid: {signal.signal_valid}")
                        except Exception as e:
                            logger.error(f"Signal generation error: {e}")
                            import traceback
                            logger.error(traceback.format_exc())
                
                # Check open positions
                self._manage_open_positions()
                
                # Update performance metrics
                self._update_performance()
                
                # Run DQN training if in training mode
                if self.dqn_layer and self.dqn_layer.training_mode:
                    self.dqn_layer.train_episode(episode_length=10)
                    
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                
            await asyncio.sleep(1)
            
    def _on_candle(self, candle):
        """Handle new candle - process all layers"""
        try:
            # Layer 2: Feature engineering
            features = self.feature_layer.on_candle(candle)
            
            # Layer 3: Regime detection
            regime = self.regime_layer.detect_regime(features, candle.close)
            
            # Layer 4: Signal generation
            signal = self.signal_layer.generate_signal(candle.close)
            
            logger.info(f"Signal generated: {signal.direction} (valid={signal.signal_valid}, score={signal.composite_score})")
            
            # Check if we should trade (respect config settings)
            config = self.config
            signal_valid_ok = signal.signal_valid or not getattr(config, 'REQUIRE_SIGNAL_VALID', True)
            direction_ok = signal.direction != "NEUTRAL" or not getattr(config, 'REQUIRE_DIRECTION', True)
            
            if signal_valid_ok and direction_ok:
                logger.info(f"Executing {signal.direction} signal (valid={signal.signal_valid}, require_valid={config.REQUIRE_SIGNAL_VALID}, dir={signal.direction}, require_dir={config.REQUIRE_DIRECTION})")
                self._execute_signal(signal, features, candle.close)
                
            # Update risk layer with latest price
            self.risk_layer.update_equity(
                self.risk_layer.current_equity + sum(
                    p.unrealized_pnl for p in self.execution_layer.get_open_positions()
                ),
                candle.timestamp
            )
            
            # Record equity for analytics
            self.performance_layer.record_equity(
                self.risk_layer.current_equity,
                candle.timestamp
            )
        except Exception as e:
            logger.error(f"Error in _on_candle: {e}")
        
    def _on_tick(self, tick):
        """Handle tick data"""
        # Update microstructure layer
        self.micro_layer.on_trade(tick.price, tick.quantity, tick.direction, tick.timestamp)
        
        # Update feature layer
        self.feature_layer.on_tick(tick)
        
        # Update execution with latest price
        self.execution_layer.on_price_update(tick.price)
        
    def _execute_signal(self, signal, features, current_price: float):
        """Execute trading signal"""
        # Layer 5: Calculate position size
        sizing = self.risk_layer.calculate_position_size(signal, features, current_price)
        
        if sizing.target_position_size_usd <= 0:
            return
            
        # Layer 12: DQN overlay (optional)
        if self.dqn_layer:
            dqn_action = self.dqn_layer.get_position_action(features)
            
            # Adjust size based on DQN if confident
            if dqn_action['q_value'] > 1.0:
                sizing.target_position_size_usd *= 1.1
            
        # Layer 6: Execute position
        position = self.execution_layer.create_position(
            signal, sizing, features, datetime.now()
        )
        
        if position:
            logger.info(f"Position executed: {position.position_id}")
            
    def _manage_open_positions(self):
        """Manage existing positions - check TP/SL and jump risk"""
        current_price = self.data_layer.get_current_price()
        if not current_price:
            return
            
        for position in self.execution_layer.get_open_positions():
            if position.state != PositionState.ACTIVE:
                continue
                
            # Check TP/SL for LONG positions
            if position.direction == "LONG":
                # Check Stop Loss
                if current_price <= position.stop_loss:
                    logger.warning(f"🛑 LONG Position {position.position_id} hit STOP LOSS at ${current_price:.2f} (SL: ${position.stop_loss:.2f})")
                    self.execution_layer.close_position(position, current_price, "STOP_LOSS")
                    # Record to performance layer
                    self._record_closed_trade(position)
                    continue
                    
                # Check Take Profit 1
                if current_price >= position.take_profit_1:
                    if not position.tp1_hit:
                        logger.info(f"✅ LONG Position {position.position_id} hit TP1 at ${current_price:.2f}")
                        self.execution_layer._partial_exit(position, current_price, "TAKE_PROFIT_1")
                        position.tp1_hit = True
                        
                # Check Take Profit 2
                if current_price >= position.take_profit_2:
                    if not position.tp2_hit:
                        logger.info(f"🎯 LONG Position {position.position_id} hit TP2 at ${current_price:.2f}")
                        self.execution_layer._partial_exit(position, current_price, "TAKE_PROFIT_2")
                        position.tp2_hit = True
                        
            # Check TP/SL for SHORT positions
            elif position.direction == "SHORT":
                # Check Stop Loss
                if current_price >= position.stop_loss:
                    logger.warning(f"🛑 SHORT Position {position.position_id} hit STOP LOSS at ${current_price:.2f} (SL: ${position.stop_loss:.2f})")
                    self.execution_layer.close_position(position, current_price, "STOP_LOSS")
                    # Record to performance layer
                    self._record_closed_trade(position)
                    continue
                    
                # Check Take Profit 1
                if current_price <= position.take_profit_1:
                    if not position.tp1_hit:
                        logger.info(f"✅ SHORT Position {position.position_id} hit TP1 at ${current_price:.2f}")
                        self.execution_layer._partial_exit(position, current_price, "TAKE_PROFIT_1")
                        position.tp1_hit = True
                        
                # Check Take Profit 2
                if current_price <= position.take_profit_2:
                    if not position.tp2_hit:
                        logger.info(f"🎯 SHORT Position {position.position_id} hit TP2 at ${current_price:.2f}")
                        self.execution_layer._partial_exit(position, current_price, "TAKE_PROFIT_2")
                        position.tp2_hit = True
            
            # Check jump-diffusion risk (only if position still active)
            if position.state == PositionState.ACTIVE:
                pnl_pct = position.unrealized_pnl / position.position_size_usd
                
                # Check if we should reduce due to jump risk
                if self.jump_layer.should_reduce_position(
                    pnl_pct, 
                    abs(position.entry_price - position.stop_loss) / position.entry_price
                ):
                    logger.warning(f"Reducing position {position.position_id} due to jump risk")
                    # Track PnL before partial exit
                    pnl_before = position.realized_pnl
                    # Partial close
                    self.execution_layer._partial_exit(position, current_price, "JUMP_RISK")
                    # Record the delta PnL from this partial exit
                    pnl_delta = position.realized_pnl - pnl_before
                    if pnl_delta != 0:
                        self.performance_layer.record_pnl(pnl_delta)
                        self.validity_layer.record_trade()
                    
    def _update_jump_diffusion(self):
        """Update jump-diffusion parameters"""
        # Add current return to estimation
        daily_returns = self.data_layer.get_daily_returns()
        if len(daily_returns) > 0:
            self.jump_layer.add_daily_return(
                daily_returns.iloc[-1] if len(daily_returns) > 0 else 0,
                datetime.now()
            )
            
    def _update_performance(self):
        """Update performance metrics"""
        metrics = self.performance_layer.compute_metrics()
        
        # Check acceptance criteria
        criteria = self.performance_layer.check_acceptance_criteria()
        
        # Check strategy validity
        self.validity_layer.check_validity(self.feature_layer.get_latest_features())
        
    def get_state(self) -> EngineState:
        """Get complete engine state"""
        regime = self.regime_layer.get_current_regime()
        # Get signal from latest_signal first, then fall back to signal_history
        signal = getattr(self, 'latest_signal', None)
        if not signal and self.signal_layer.signal_history:
            signal = self.signal_layer.signal_history[-1]
        metrics = self.performance_layer.compute_metrics()
        
        # Get current price - prefer data layer since WebSockets may not be working
        current_price = self.execution_layer.current_price
        if current_price == 0 or current_price is None:
            current_price = self.data_layer.get_current_price() or 0.0
        
        current_spread = self.execution_layer.current_spread
        if current_spread == 0 and current_price > 0:
            current_spread = self.data_layer.get_current_spread()
        
        # Get open positions with full details
        open_positions_list = self.execution_layer.get_open_positions()
        positions_data = [pos.to_dict() for pos in open_positions_list] if open_positions_list else []
        
        return EngineState(
            timestamp=datetime.now(),
            is_running=self.is_running,
            is_trading_allowed=self.validity_layer.is_trading_allowed(),
            current_price=current_price,
            current_spread=current_spread,
            regime=regime.to_dict() if regime else None,
            latest_signal=signal.to_dict() if signal else None,
            equity=self.risk_layer.current_equity,
            high_water_mark=self.risk_layer.high_water_mark,
            drawdown_pct=(self.risk_layer.high_water_mark - self.risk_layer.current_equity) / self.risk_layer.high_water_mark,
            open_positions=len(open_positions_list),
            positions=positions_data,
            metrics=self.performance_layer.metrics if self.performance_layer else None,
            daily_pnl=self.performance_layer.metrics.get('time_based_pnl', {}).get('daily', 0.0) if self.performance_layer else 0.0,
            pnl_30d=self.performance_layer.metrics.get('time_based_pnl', {}).get('pnl_30d', 0.0) if self.performance_layer else 0.0,
            starting_equity=getattr(self, 'starting_equity', 10000.0),
            active_alerts=[alert.to_dict() for alert in self.validity_layer.get_active_alerts()[-5:]],
            manual_review_required=self.validity_layer.manual_review_required,
            validity_bootstrap=self.validity_layer.bootstrap_mode_active,
            validity_bootstrap_count=self.validity_layer.bootstrap_trades_count
        )
        
    async def stop(self):
        """Stop the trading engine"""
        logger.info("Stopping APEX-BTC Trading Engine")
        
        self.is_running = False
        
        # Close all positions
        for position in list(self.execution_layer.get_open_positions()):
            self.execution_layer._close_position(
                position, 
                self.execution_layer.current_price,
                "SYSTEM_SHUTDOWN"
            )
            
        # Stop data layer
        await self.data_layer.stop()
        
        # Save DQN model
        if self.dqn_layer:
            self.dqn_layer.save_model("models/dqn_final.pt")
        
        logger.info("Trading engine stopped")
        
    def _record_closed_trade(self, position):
        """Record closed trade to performance layer"""
        try:
            # Get the trade record from the execution layer's ledger
            ledger = self.execution_layer.get_trade_ledger()
            if ledger:
                # Find the trade record matching this position
                trade_record = None
                for record in reversed(ledger):
                    if record.get('trade_id') == position.trade_id:
                        trade_record = record
                        break
                
                if trade_record:
                    # Record to performance layer
                    self.performance_layer.record_trade(trade_record)
                    # Record to validity layer
                    self.validity_layer.record_trade()
                    logger.info(f"[CLOSED_TRADE] Recorded closed trade: PnL=${trade_record.get('net_pnl', 0):.2f}, trade_id={position.trade_id}")
                else:
                    logger.warning(f"[CLOSED_TRADE] Could not find trade record for position {position.position_id}")
        except Exception as e:
            logger.error(f"Error recording closed trade: {e}")
        
    def manual_override(self, action: str):
        """Manual override for emergency situations"""
        if action == "CLOSE_ALL":
            for position in list(self.execution_layer.get_open_positions()):
                self.execution_layer._close_position(
                    position,
                    self.execution_layer.current_price,
                    "MANUAL_CLOSE"
                )
            logger.warning("MANUAL OVERRIDE: All positions closed")
            
        elif action == "HALT":
            self.validity_layer.trading_suspended = True
            logger.warning("MANUAL OVERRIDE: Trading halted")
            
        elif action == "RESUME":
            self.validity_layer.trading_suspended = False
            self.validity_layer.manual_review_required = False
            logger.info("MANUAL OVERRIDE: Trading resumed")
            
        elif action == "CLEAR_REVIEW":
            self.validity_layer.clear_manual_review()
            
    def enable_dqn_training(self, enable: bool = True):
        """Enable/disable DQN training mode"""
        if self.dqn_layer:
            self.dqn_layer.training_mode = enable
            logger.info(f"DQN training mode: {enable}")
        else:
            logger.warning("DQN not available")
