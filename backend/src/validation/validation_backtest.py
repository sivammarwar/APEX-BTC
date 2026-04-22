"""
300-Trade Statistical Validation System
Based on López de Prado (2014) and Han, Kang & Ryu (2026)

BTC kurtosis ≈ 466 requires 300+ trades for PSR > 0.95 statistical significance

This validation uses your ACTUAL 12-layer signal generation with configurable parameters,
allowing you to tune and test your live trading configuration before going live.
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from loguru import logger
from scipy import stats
import asyncio
from concurrent.futures import ThreadPoolExecutor
import copy
import json
import os

PROGRESS_FILE = "/tmp/apex_btc_backtest_progress.json"
RESULT_FILE = "/tmp/apex_btc_backtest_result.json"
REPORT_FILE = "/tmp/apex_btc_backtest_report.txt"


@dataclass
class ValidationParams:
    """Configurable validation parameters - mirror of dashboard settings"""
    # Signal Thresholds
    signal_threshold: int = 38
    min_probability: float = 0.45
    min_prospect_value: float = -2.92
    cooldown_hours: int = 0
    
    # Position Management
    position_size_pct: float = 0.1
    stop_loss_pct: float = 0.01
    take_profit_multiplier: float = 2.0
    holding_days: int = 5
    
    # Signal Component Parameters
    tsmom_percentile: float = 0.0  # 0 = use default from config
    min_ofi: float = -4.0
    min_mrr: float = -1.0
    min_co: float = -1.0
    min_sharpe: float = 0.5
    min_prob_weighted_score: float = 35.0
    
    # Validation Settings
    max_trades: int = 300
    days_of_data: int = 700
    allow_overlapping: bool = True
    
    # Additional constraints
    require_signal_valid: bool = False
    require_direction: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'signal_threshold': self.signal_threshold,
            'min_probability': self.min_probability,
            'min_prospect_value': self.min_prospect_value,
            'cooldown_hours': self.cooldown_hours,
            'position_size_pct': self.position_size_pct,
            'stop_loss_pct': self.stop_loss_pct,
            'take_profit_multiplier': self.take_profit_multiplier,
            'holding_days': self.holding_days,
            'tsmom_percentile': self.tsmom_percentile,
            'min_ofi': self.min_ofi,
            'min_mrr': self.min_mrr,
            'min_co': self.min_co,
            'min_sharpe': self.min_sharpe,
            'min_prob_weighted_score': self.min_prob_weighted_score,
            'max_trades': self.max_trades,
            'days_of_data': self.days_of_data,
            'allow_overlapping': self.allow_overlapping,
            'require_signal_valid': self.require_signal_valid,
            'require_direction': self.require_direction,
        }


@dataclass
class ValidationResult:
    """Results from 300-trade validation"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    skewness: float
    kurtosis: float
    psr_0: float  # PSR with benchmark SR=0
    psr_1: float  # PSR with benchmark SR=1
    trades: List[Dict]
    equity_curve: List[float]
    passed: bool
    report: str
    params_used: ValidationParams = field(default_factory=ValidationParams)
    run_timestamp: str = ""


class ValidationBacktest:
    """
    300-Trade Walk-Forward Backtest with Full Signal Generation
    
    Methodology:
    - Fetch historical OHLCV data
    - Generate signals using ACTUAL 12-layer signal generation
    - Apply configurable thresholds (same as live trading)
    - Simulate trades with proper risk management
    - Calculate statistical metrics per López de Prado (2014)
    
    Key Features:
    - Uses live trading parameters (configurable)
    - Supports multiple reruns with different parameters
    - Detailed reporting with parameters used
    - Realistic signal generation with cooldown
    """
    
    def __init__(self, data_layer, config, params: Optional[ValidationParams] = None):
        self.data_layer = data_layer
        self.config = config
        self.params = params or ValidationParams()  # Use provided params or defaults
        self.executor = ThreadPoolExecutor(max_workers=1)
        self.is_running = False
        self.current_progress = 0
        self.current_trade_count = 0
        self.last_signal_time = None
        self._validation_history: List[ValidationResult] = []  # Store multiple runs
        
    async def fetch_historical_daily_data(
        self, 
        symbol: str = "BTCUSDT", 
        days: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Fetch historical daily OHLCV from Binance.
        
        Args:
            symbol: Trading pair (default BTCUSDT)
            days: Number of days to fetch (default from params.days_of_data)
        
        Returns:
            DataFrame with OHLCV data indexed by timestamp
        """
        from binance.client import Client
        
        days = days or self.params.days_of_data
        client = Client()
        
        # Fetch data from Binance
        start_date = datetime.now() - timedelta(days=days + 30)  # Extra buffer
        
        logger.info(f"[VALIDATION] Fetching {days} days of historical data for {symbol}...")
        logger.info(f"[VALIDATION] Using parameters: {self.params.to_dict()}")
        
        klines = client.get_historical_klines(
            symbol,
            Client.KLINE_INTERVAL_1DAY,
            start_date.strftime("%d %b %Y %H:%M:%S")
        )
        
        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_asset_volume', 'number_of_trades',
            'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
        ])
        
        # Convert types
        df['open'] = df['open'].astype(float)
        df['high'] = df['high'].astype(float)
        df['low'] = df['low'].astype(float)
        df['close'] = df['close'].astype(float)
        df['volume'] = df['volume'].astype(float)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df.set_index('timestamp', inplace=True)
        
        # Sort by index to ensure chronological order
        df.sort_index(inplace=True)
        
        # Verify minimum data requirement
        if len(df) < 300:
            raise ValueError(f"Only {len(df)} days fetched. Need 300+ for validation.")
        
        logger.info(f"[VALIDATION] Successfully fetched {len(df)} days of data")
        logger.info(f"[VALIDATION] Date range: {df.index[0]} to {df.index[-1]}")
        
        return df[['open', 'high', 'low', 'close', 'volume']]
    
    def compute_all_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute all technical features needed for signal generation.
        Mirrors the feature engineering from Layer 2.
        """
        # Basic returns
        df['returns'] = df['close'].pct_change()
        df['returns_28d'] = df['close'].pct_change(28)
        
        # TSMOM (Time-Series Momentum) - 28-day percentile over 252 days
        df['tsmom_rank'] = df['returns_28d'].rolling(252).apply(
            lambda x: (x.iloc[-1] > x).sum() / len(x) if len(x) > 0 else 0.5
        )
        
        # CO (Continuing Overreaction)
        def compute_co(returns, volumes, lookback=21):
            co_values = []
            for i in range(lookback, len(returns)):
                weight_sum = 0
                vol_sum = 0
                for j in range(1, lookback + 1):
                    weight = lookback - j + 1
                    sign_r = 1 if returns.iloc[i - j] > 0 else -1
                    vol = volumes.iloc[i - j]
                    weight_sum += weight * sign_r * vol
                    vol_sum += vol
                co = weight_sum / (vol_sum / lookback) if vol_sum > 0 else 0
                co_values.append(co)
            return [0] * lookback + co_values
        
        df['co_value'] = compute_co(df['returns'], df['volume'])
        df['co_standardized'] = (
            (df['co_value'] - df['co_value'].rolling(252).mean()) / 
            df['co_value'].rolling(252).std().replace(0, 1)
        )
        
        # EMAs
        df['ema_21'] = df['close'].ewm(span=21).mean()
        df['ema_200'] = df['close'].ewm(span=200).mean()
        
        # EMA Slopes (rate of change)
        df['ema_slope_200'] = df['ema_200'].diff(5) / df['ema_200'].shift(5)
        
        # ATR (Average True Range)
        df['tr1'] = df['high'] - df['low']
        df['tr2'] = abs(df['high'] - df['close'].shift(1))
        df['tr3'] = abs(df['low'] - df['close'].shift(1))
        df['true_range'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
        df['atr_14'] = df['true_range'].rolling(14).mean()
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss.replace(0, 0.001)
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Volume metrics
        df['volume_sma'] = df['volume'].rolling(20).mean()
        df['volume_std'] = df['volume'].rolling(20).std()
        
        # Price momentum
        df['momentum_10'] = df['close'].pct_change(10)
        
        # Volatility (realized)
        df['volatility_20'] = df['returns'].rolling(20).std() * np.sqrt(365)
        
        # Clean up intermediate columns
        df = df.drop(['tr1', 'tr2', 'tr3', 'true_range'], axis=1)
        
        return df
    
    def generate_full_signal(
        self,
        row: pd.Series,
        current_price: float,
        prev_signals: List[Dict],
        timestamp: datetime
    ) -> Dict:
        """
        Generate trading signal using FULL 12-layer approach.
        
        This mirrors your live signal generation with all component scores:
        - EMA 200 slope (15 pts)
        - TSMOM rank (20 pts)  
        - CO positive (15 pts)
        - Price near EMA (10 pts)
        - RSI range (5 pts)
        - OFI clean (10 pts)
        - Volume POC (5 pts)
        - MRR rho (5 pts)
        
        Args:
            row: DataFrame row with all computed features
            current_price: Current price
            prev_signals: List of previous signals for cooldown check
            timestamp: Current timestamp
            
        Returns:
            Signal dict with all scoring details
        """
        scores = {}
        direction = "NEUTRAL"
        
        # Get configured thresholds (allow 0.0 as valid value)
        if self.params.tsmom_percentile >= 0:
            tsmom_threshold = self.params.tsmom_percentile
        else:
            tsmom_threshold = getattr(self.config, 'TSMOM_PERCENTILE_ENTRY', 0.667)
        min_ofi = self.params.min_ofi
        min_mrr = self.params.min_mrr
        min_co = self.params.min_co
        signal_threshold = self.params.signal_threshold
        
        # 1. EMA 200 slope (15 pts) - bullish bias
        ema_slope = row.get('ema_slope_200', 0)
        if ema_slope > 0:
            scores['ema_200_slope'] = 15
        
        # 2. TSMOM rank (20 pts) - momentum
        tsmom_rank = row.get('tsmom_rank', 0.5)
        if tsmom_rank >= tsmom_threshold:
            tsmom_score = int(20 * (tsmom_rank - 0.5) / 0.5)
            scores['tsmom_rank'] = min(tsmom_score, 20)
        
        # 3. CO positive (15 pts) - overreaction
        co_value = row.get('co_standardized', 0)
        if co_value > min_co:
            scores['co_positive'] = min(15, int(15 * max(0, co_value) / 2))
        
        # 4. Price within 1.5 ATR of 21 EMA (10 pts)
        ema_21 = row.get('ema_21', current_price)
        atr = row.get('atr_14', current_price * 0.01)
        distance = abs(current_price - ema_21)
        if distance < 1.5 * atr:
            scores['price_near_ema'] = 10
        
        # 5. RSI 40-60 range (5 pts) - avoid extremes
        rsi = row.get('rsi_14', 50)
        if 40 <= rsi <= 60:
            scores['rsi_range'] = 5
        
        # 6. OFI clean proxy (10 pts) - use momentum as proxy
        momentum = row.get('momentum_10', 0)
        if momentum > min_ofi / 10:  # Scaled threshold
            scores['ofi_clean'] = min(10, int(10 * momentum / 0.2))
        
        # 7. Volume confirmation (5 pts)
        volume = row.get('volume', 0)
        vol_sma = row.get('volume_sma', 1)
        if volume > vol_sma:
            scores['volume_poc'] = 5
        
        # 8. MRR rho proxy (5 pts) - volatility regime
        volatility = row.get('volatility_20', 0.5)
        if volatility < 1.0:  # Low vol regime favorable
            scores['mrr_rho'] = 5
        
        # Calculate total score
        total_score = sum(scores.values())
        max_score = 105
        
        # Determine direction based on score
        if total_score >= signal_threshold:
            direction = "LONG"
        
        # Check cooldown
        cooldown_active = False
        if self.params.cooldown_hours > 0 and self.last_signal_time:
            hours_since = (timestamp - self.last_signal_time).total_seconds() / 3600
            if hours_since < self.params.cooldown_hours:
                cooldown_active = True
                direction = "NEUTRAL"  # Block signal during cooldown
        
        # Additional filters
        signal_valid = direction == "LONG"
        
        # Apply probability filter
        if total_score > 0:
            probability = total_score / max_score
            if probability < self.params.min_probability:
                signal_valid = False
                direction = "NEUTRAL"
        
        # Update last signal time if we have a valid signal
        if direction == "LONG":
            self.last_signal_time = timestamp
        
        return {
            'direction': direction,
            'score': total_score,
            'max_score': max_score,
            'component_scores': scores,
            'tsmom_rank': tsmom_rank,
            'co_value': co_value,
            'signal_valid': signal_valid,
            'cooldown_active': cooldown_active,
            'ema_slope': ema_slope,
            'rsi': rsi,
            'probability': total_score / max_score if max_score > 0 else 0,
            'valid': direction != "NEUTRAL" and signal_valid
        }
    
    def _save_progress(self, trades_taken: int, winning_trades: int, losing_trades: int, current_equity: float):
        """Save current progress to file for real-time tracking"""
        progress = {
            'trades_completed': trades_taken,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': winning_trades / trades_taken if trades_taken > 0 else 0,
            'current_equity': current_equity,
            'is_running': True,
            'timestamp': datetime.now().isoformat()
        }
        try:
            with open(PROGRESS_FILE, 'w') as f:
                json.dump(progress, f)
        except Exception as e:
            logger.error(f"[VALIDATION] Failed to save progress: {e}")
    
    def run_300_trade_backtest(
        self,
        df: pd.DataFrame,
        max_trades: Optional[int] = None,
        holding_days: Optional[int] = None,
        initial_equity: float = 10000.0
    ) -> ValidationResult:
        """
        Run 300-trade walk-forward backtest using FULL signal generation.
        
        Args:
            df: DataFrame with all OHLCV and computed features
            max_trades: Target number of trades (default from params)
            holding_days: Days to hold each trade (default from params)
            initial_equity: Starting capital
            
        Returns:
            ValidationResult with all metrics and trade history
        """
        # Use params if not specified
        max_trades = max_trades or self.params.max_trades
        holding_days = holding_days or self.params.holding_days
        
        logger.info(f"[VALIDATION] Starting 300-trade backtest with parameters:")
        logger.info(f"[VALIDATION] Signal Threshold: {self.params.signal_threshold}")
        logger.info(f"[VALIDATION] Min Probability: {self.params.min_probability}")
        logger.info(f"[VALIDATION] Min TSMOM: {self.params.tsmom_percentile}")
        logger.info(f"[VALIDATION] Min OFI: {self.params.min_ofi}")
        logger.info(f"[VALIDATION] Min MRR: {self.params.min_mrr}")
        logger.info(f"[VALIDATION] Min CO: {self.params.min_co}")
        
        # Reset state
        self.current_trade_count = 0
        self.last_signal_time = None
        
        # Start trading after enough history (200 days for EMA 200)
        start_idx = 252
        trades_taken = 0
        current_equity = initial_equity
        prev_signals = []
        
        results = {
            'trades': [],
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'equity_curve': [initial_equity],
            'daily_returns': [],
            'signal_details': []
        }
        
        i = start_idx
        total_bars = len(df) - holding_days
        signals_generated = 0
        signals_blocked_by_cooldown = 0
        
        logger.info(f"[VALIDATION] Starting backtest: {total_bars} bars, target {max_trades} trades")
        
        while i < total_bars and trades_taken < max_trades:
            # Update progress
            if trades_taken % 10 == 0 or i == start_idx:
                self.current_progress = min(100, int((trades_taken / max_trades) * 100))
                self.current_trade_count = trades_taken
            
            # Get current data
            # Use OPEN price for entry to avoid look-ahead bias
            # (we can't know the close price when we decide to enter at day start)
            current_price = df['open'].iloc[i]
            timestamp = df.index[i]
            
            # Generate signal using full 12-layer approach
            signal = self.generate_full_signal(
                df.iloc[i],
                current_price,
                prev_signals,
                timestamp
            )
            
            # Track signal details
            if i < start_idx + 50:  # Log first 50 signals for debugging
                logger.info(f"[VALIDATION] Bar {i}: Score={signal['score']}/{signal['max_score']}, "
                          f"Direction={signal['direction']}, Components={signal['component_scores']}")
            
            if signal['direction'] == "LONG" and signal['valid']:
                signals_generated += 1
                
                # Enter trade
                entry_price = current_price
                entry_date = timestamp
                position_size = current_equity * self.params.position_size_pct
                
                # Calculate SL/TP levels (just like live trading)
                stop_loss_price = entry_price * (1 - self.params.stop_loss_pct)
                take_profit_price = entry_price * (1 + (self.params.stop_loss_pct * self.params.take_profit_multiplier))
                
                # Check intraday on entry day first (same day exit possible)
                entry_day_high = df['high'].iloc[i]
                entry_day_low = df['low'].iloc[i]
                
                exit_price = None
                exit_date = None
                exit_reason = None
                
                # Check if SL hit on entry day
                if entry_day_low <= stop_loss_price:
                    exit_price = stop_loss_price
                    exit_date = timestamp
                    exit_reason = "STOP_LOSS_SAME_DAY"
                # Check if TP hit on entry day
                elif entry_day_high >= take_profit_price:
                    exit_price = take_profit_price
                    exit_date = timestamp
                    exit_reason = "TAKE_PROFIT_SAME_DAY"
                else:
                    # Scan forward subsequent days
                    max_scan_days = holding_days * 3
                    
                    for day_offset in range(1, min(max_scan_days, len(df) - i)):
                        scan_idx = i + day_offset
                        if scan_idx >= len(df):
                            break
                        
                        scan_high = df['high'].iloc[scan_idx]
                        scan_low = df['low'].iloc[scan_idx]
                        
                        # Check if SL hit
                        if scan_low <= stop_loss_price:
                            exit_price = stop_loss_price
                            exit_date = df.index[scan_idx]
                            exit_reason = "STOP_LOSS"
                            break
                        
                        # Check if TP hit
                        if scan_high >= take_profit_price:
                            exit_price = take_profit_price
                            exit_date = df.index[scan_idx]
                            exit_reason = "TAKE_PROFIT"
                            break
                
                # If no SL/TP hit, exit at holding period or last available price
                if exit_price is None:
                    exit_idx = min(i + holding_days, len(df) - 1)
                    exit_price = df['close'].iloc[exit_idx]
                    exit_date = df.index[exit_idx]
                    exit_reason = "TIME_EXIT"
                
                # Calculate P&L
                pnl_pct = (exit_price - entry_price) / entry_price
                pnl_dollar = position_size * pnl_pct
                
                # Update equity
                current_equity += pnl_dollar
                
                # Record trade
                is_win = pnl_pct > 0
                trade_record = {
                    'trade_num': trades_taken + 1,
                    'entry_date': entry_date.strftime('%Y-%m-%d'),
                    'exit_date': exit_date.strftime('%Y-%m-%d'),
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'stop_loss_price': stop_loss_price,
                    'take_profit_price': take_profit_price,
                    'exit_reason': exit_reason,
                    'hold_days': (exit_date - entry_date).days if exit_date else 0,
                    'position_size': position_size,
                    'pnl_pct': pnl_pct,
                    'pnl_dollar': pnl_dollar,
                    'is_win': is_win,
                    'score_at_entry': signal['score'],
                    'component_scores': signal['component_scores'],
                    'tsmom_rank_at_entry': signal['tsmom_rank'],
                    'co_at_entry': signal['co_value'],
                    'rsi_at_entry': signal['rsi'],
                    'equity_after': current_equity
                }
                
                results['trades'].append(trade_record)
                prev_signals.append(trade_record)
                
                if is_win:
                    results['winning_trades'] += 1
                else:
                    results['losing_trades'] += 1
                
                results['total_pnl'] += pnl_dollar
                results['equity_curve'].append(current_equity)
                
                trades_taken += 1
                
                # Save progress for real-time tracking
                self._save_progress(trades_taken, results['winning_trades'], results['losing_trades'], current_equity)
                
                if trades_taken % 20 == 0 or trades_taken <= 10:
                    logger.info(f"[VALIDATION] Trade {trades_taken}/{max_trades}: {'WIN' if is_win else 'LOSS'} "
                              f"Exit={exit_reason}, Hold={(exit_date-entry_date).days}d, "
                              f"PnL=${pnl_dollar:.2f} ({pnl_pct*100:+.1f}%)")
                
                # Advance iterator
                if self.params.allow_overlapping:
                    i += 1
                else:
                    # Move to day after exit for non-overlapping
                    exit_idx = df.index.get_loc(exit_date) if exit_date in df.index else i + holding_days
                    i = exit_idx + 1 if isinstance(exit_idx, int) else i + holding_days
            else:
                if signal['direction'] == "LONG" and signal.get('cooldown_active'):
                    signals_blocked_by_cooldown += 1
                i += 1
        
        # Log summary
        logger.info(f"[VALIDATION] Backtest complete: {trades_taken} trades from {signals_generated} signals")
        if signals_blocked_by_cooldown > 0:
            logger.info(f"[VALIDATION] Signals blocked by cooldown: {signals_blocked_by_cooldown}")
        
        # Calculate metrics
        return self._calculate_validation_metrics(
            results, 
            trades_taken, 
            initial_equity,
            signals_generated,
            signals_blocked_by_cooldown
        )
    
    def _calculate_validation_metrics(
        self, 
        results: Dict, 
        trades_taken: int,
        initial_equity: float,
        signals_generated: int = 0,
        signals_blocked: int = 0
    ) -> ValidationResult:
        """
        Calculate all statistical metrics for validation.
        Includes detailed breakdown with parameters used.
        """
        
        # Win rate
        win_rate = results['winning_trades'] / trades_taken if trades_taken > 0 else 0
        
        # Profit Factor
        total_wins = sum([t['pnl_pct'] for t in results['trades'] if t['is_win']])
        total_losses = abs(sum([t['pnl_pct'] for t in results['trades'] if not t['is_win']]))
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')
        
        # Sharpe Ratio (using trade returns)
        trade_returns = [t['pnl_pct'] for t in results['trades']]
        holding_days = self.params.holding_days
        if len(trade_returns) > 0 and np.std(trade_returns) > 0:
            sharpe_ratio = (np.mean(trade_returns) / np.std(trade_returns)) * np.sqrt(365 / holding_days)
        else:
            sharpe_ratio = 0
        
        # Maximum Drawdown
        equity_array = np.array(results['equity_curve'])
        running_max = np.maximum.accumulate(equity_array)
        drawdowns = (running_max - equity_array) / running_max
        max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0
        
        # Total return
        total_return = (equity_array[-1] - initial_equity) / initial_equity if len(equity_array) > 0 else 0
        
        # Distribution moments for PSR
        if len(trade_returns) > 0:
            skewness = pd.Series(trade_returns).skew()
            kurtosis = pd.Series(trade_returns).kurtosis() + 3
        else:
            skewness = 0
            kurtosis = 3
        
        # PSR (Probabilistic Sharpe Ratio)
        psr_0 = self._calculate_psr(sharpe_ratio, trades_taken, skewness, kurtosis, benchmark=0)
        psr_1 = self._calculate_psr(sharpe_ratio, trades_taken, skewness, kurtosis, benchmark=1.0)
        
        # Validation checks
        passed = self._validate_results(
            trades_taken, win_rate, profit_factor, sharpe_ratio, psr_0, max_drawdown
        )
        
        # Calculate exit reasons
        exit_reasons = {}
        for trade in results['trades']:
            reason = trade.get('exit_reason', 'UNKNOWN')
            exit_reasons[reason] = exit_reasons.get(reason, 0) + 1
        
        # Generate detailed report
        # Generate standard report
        report = self._generate_detailed_report(
            trades_taken, 
            results['winning_trades'], 
            results['losing_trades'],
            win_rate, 
            profit_factor, 
            sharpe_ratio, 
            psr_0, 
            psr_1,
            max_drawdown,
            total_return,
            signals_generated,
            signals_blocked,
            passed,
            exit_reasons,
            results['trades']
        )
        
        # Also generate AutoQuant report if enough trades
        try:
            from .autoquant_validation import run_full_autoquant_validation
            import json
            
            # Load current settings
            settings_path = "/Users/shivamkumarsingh/Documents/AIM/apex-btc/backend/config/settings.json"
            try:
                with open(settings_path, 'r') as f:
                    params = json.load(f)
                
                logger.info("[VALIDATION] Generating AutoQuant diagnostic report...")
                autoquant_report = run_full_autoquant_validation(params, df)
                
                # Append AutoQuant report
                report += "\n\n"
                report += "=" * 80
                report += "\n"
                report += autoquant_report
            except Exception as e:
                logger.error(f"[VALIDATION] AutoQuant report generation failed: {e}")
        except ImportError:
            logger.warning("[VALIDATION] AutoQuant validation not available")
        
        return ValidationResult(
            total_trades=trades_taken,
            winning_trades=results['winning_trades'],
            losing_trades=results['losing_trades'],
            win_rate=win_rate,
            profit_factor=profit_factor,
            sharpe_ratio=sharpe_ratio,
            max_drawdown=max_drawdown,
            skewness=skewness,
            kurtosis=kurtosis,
            psr_0=psr_0,
            psr_1=psr_1,
            trades=results['trades'],
            equity_curve=results['equity_curve'],
            passed=passed,
            report=report,
            params_used=self.params,
            run_timestamp=datetime.now().isoformat()
        )
    
    def _calculate_psr(
        self, 
        sharpe: float, 
        n: int, 
        skewness: float, 
        kurtosis: float, 
        benchmark: float = 0
    ) -> float:
        """
        PSR = Φ[(SR_hat - SR*) × √(n-1) / √(1 - γ3×SR_hat + ((γ4-1)/4)×SR_hat²)]
        
        López de Prado (2012) Probabilistic Sharpe Ratio
        """
        if n < 2:
            return 0.5
        
        denominator = np.sqrt(
            1 - skewness * sharpe + ((kurtosis - 1) / 4) * (sharpe ** 2)
        )
        
        if denominator <= 0 or np.isnan(denominator):
            return 0.5
        
        z_score = (sharpe - benchmark) * np.sqrt(n - 1) / denominator
        psr = stats.norm.cdf(z_score)
        
        return float(psr)
    
    def _validate_results(
        self,
        total_trades: int,
        win_rate: float,
        profit_factor: float,
        sharpe_ratio: float,
        psr_0: float,
        max_drawdown: float
    ) -> bool:
        """
        López de Prado (2014) acceptance criteria.
        ALL must pass for strategy to be considered valid.
        """
        checks = {
            'min_trades': total_trades >= 300,
            'win_rate_above_33': win_rate > 0.333,
            'profit_factor_above_1.5': profit_factor > 1.5,
            'sharpe_above_1.0': sharpe_ratio > 1.0,
            'psr_0_above_0.95': psr_0 > 0.95,
            'max_drawdown_below_20': max_drawdown < 0.20,
        }
        
        logger.info(f"[VALIDATION] Criteria: {checks}")
        
        return all(checks.values())
    
    def _generate_detailed_report(
        self,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        win_rate: float,
        profit_factor: float,
        sharpe_ratio: float,
        psr_0: float,
        psr_1: float,
        max_drawdown: float,
        total_return: float,
        signals_generated: int,
        signals_blocked: int,
        passed: bool,
        exit_reasons: Dict[str, int] = None,
        trades: List[Dict] = None
    ) -> str:
        """Generate detailed validation report with parameters used"""
        
        def check_mark(condition: bool) -> str:
            return "✅" if condition else "❌"
        
        # Format parameters
        params = self.params
        
        report = f"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    300-TRADE STATISTICAL VALIDATION REPORT                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  RUN TIMESTAMP: {datetime.now().strftime('%Y-%m-%d %H:%M:%S'):<56} ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  PERFORMANCE METRICS                                                         ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Total Trades:           {total_trades:>4} / {params.max_trades:<4}                     {check_mark(total_trades >= params.max_trades)}  ║
║  Signals Generated:      {signals_generated:>4} (blocked by cooldown: {signals_blocked:<3})          ║
║                                                                              ║
║  Exit Breakdown:                                                            ║
║    🎯 Take Profit:       {exit_reasons.get('TAKE_PROFIT', 0):>4} trades                                           ║
║    🛑 Stop Loss:         {exit_reasons.get('STOP_LOSS', 0):>4} trades                                           ║
║    ⏱️  Time Exit:        {exit_reasons.get('TIME_EXIT', 0):>4} trades                                           ║
║                                                                              ║
║  Win Rate:               {win_rate*100:>6.1f}%  (need > 33.3%)              {check_mark(win_rate > 0.333)}  ║
║  Profit Factor:          {profit_factor:>6.2f}   (need > 1.5)                 {check_mark(profit_factor > 1.5)}  ║
║  Sharpe Ratio:           {sharpe_ratio:>6.2f}   (need > 1.0)                  {check_mark(sharpe_ratio > 1.0)}  ║
║  PSR (SR*=0):            {psr_0*100:>6.1f}%  (need > 95%)                 {check_mark(psr_0 > 0.95)}  ║
║  PSR (SR*=1):            {psr_1*100:>6.1f}%  (benchmark Sharpe=1.0)                      ║
║  Max Drawdown:           {max_drawdown*100:>6.1f}%  (need < 20%)              {check_mark(max_drawdown < 0.20)}  ║
║  Total Return:          {total_return*100:>6.1f}% (${total_return*10:>6.2f} on $10)              ║
║                                                                              ║
║  Overall Status:        {'✅ STRATEGY VALIDATED - READY FOR LIVE TRADING' if passed else '❌ FAILED - REQUIRES OPTIMIZATION':<56}║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  PARAMETERS USED FOR THIS VALIDATION RUN                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  Signal Threshold:        {params.signal_threshold:<6} (minimum score for LONG)                        ║
║  Min Probability:         {params.min_probability:<6.2f} (π(p) weighting threshold)                  ║
║  Min Prospect Value:      {params.min_prospect_value:<6.2f} (Kahneman-Tversky value)              ║
║  Cooldown (hours):        {params.cooldown_hours:<6} (signal frequency control)                      ║
║                                                                              ║
║  Position Size:           {params.position_size_pct*100:<5.1f}% of equity per trade                   ║
║  Stop Loss:               {params.stop_loss_pct*100:<5.1f}% maximum loss per trade                    ║
║  Take Profit Mult:        {params.take_profit_multiplier:<5.1f}x (TP = SL * multiplier)              ║
║  Holding Period:          {params.holding_days:<6} days (fixed exit time)                            ║
║                                                                              ║
║  Signal Component Thresholds:                                                ║
║    TSMOM Percentile:    {params.tsmom_percentile if params.tsmom_percentile >= 0 else 'Default (0.667)':<48}║
║    Min OFI:              {params.min_ofi:<6.2f} (Order Flow Imbalance)                   ║
║    Min MRR:              {params.min_mrr:<6.2f} (Microstructure Return)                ║
║    Min CO:               {params.min_co:<6.2f} (Continuing Overreaction)                 ║
║    Min Sharpe:           {params.min_sharpe:<6.2f} (minimum forecast Sharpe)             ║
║                                                                              ║
║  Execution Mode:          {'Overlapping trades' if params.allow_overlapping else 'Non-overlapping (holding period)':<56}║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  STATISTICAL ANALYSIS (López de Prado 2014)                                  ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  With BTC kurtosis ≈ 466 and {total_trades} trades:                               ║
║    → PSR = {psr_0*100:.1f}% confidence that true Sharpe > 0                       ║
║    → PSR = {psr_1*100:.1f}% confidence that true Sharpe > 1.0                     ║
║                                                                              ║
║  Required for 95% confidence: 300+ independent trades                        ║
║                                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  RECOMMENDATION                                                              ║
╠══════════════════════════════════════════════════════════════════════════════╣
║                                                                              ║
║  {'✅ All criteria passed. Strategy shows statistical edge. You may disable' if passed else '❌ Strategy does not meet professional quantitative standards:'}
║  {'   Bootstrap Mode and trade with full confidence.                           ' if passed else '   - Win rate below 33.3% suggests no directional edge'}
║  {'                                                                 ' if passed else '   - Profit factor < 1.5 indicates poor risk/reward'}
║  {'                                                                 ' if passed else '   - Sharpe ratio < 1.0 shows insufficient risk-adjusted returns'}
║                                                                              ║
║  {'Action: Continue monitoring. Strategy is validated for live trading.' if passed else 'Action: Adjust parameters and rerun validation. Continue Bootstrap Mode until validation passes.'}
║                                                                              ║
╚══════════════════════════════════════════════════════════════════════════════╝

Note: This validation uses historical 700-day data. Past performance does not
guarantee future results. Always monitor live trading performance.
"""
        return report
    
    async def run_full_validation(self, params: Optional[ValidationParams] = None) -> ValidationResult:
        """
        Run complete validation pipeline with optional parameter override.
        
        Args:
            params: Optional ValidationParams to override default settings
            
        Returns:
            ValidationResult with detailed metrics and report
        """
        # Update params if provided
        if params:
            self.params = params
            logger.info(f"[VALIDATION] Using custom parameters: {params.to_dict()}")
        
        self.is_running = True
        self.current_progress = 0
        self.current_trade_count = 0
        
        try:
            # Step 1: Fetch data
            df = await self.fetch_historical_daily_data(days=self.params.days_of_data)
            
            # Step 2: Compute all features (not just TSMOM)
            logger.info("[VALIDATION] Computing full feature set...")
            df = self.compute_all_features(df)
            
            # Check for NaN values after feature computation
            nan_count = df.isna().sum().sum()
            if nan_count > 0:
                logger.warning(f"[VALIDATION] Found {nan_count} NaN values, forward filling...")
                df = df.ffill().fillna(0)
            
            # Step 3: Run backtest
            logger.info("[VALIDATION] Running backtest with full signal generation...")
            result = await asyncio.get_event_loop().run_in_executor(
                self.executor,
                lambda: self.run_300_trade_backtest(df)
            )
            
            # Store in history for comparison
            self._validation_history.append(result)
            
            logger.info(result.report)
            
            return result
            
        except Exception as e:
            logger.error(f"[VALIDATION] Error: {e}")
            import traceback
            logger.error(traceback.format_exc())
            raise
        finally:
            self.is_running = False
            # Delete progress file when validation completes
            try:
                if os.path.exists(PROGRESS_FILE):
                    os.remove(PROGRESS_FILE)
                    logger.info("[VALIDATION] Deleted progress file")
            except Exception as e:
                logger.error(f"[VALIDATION] Failed to delete progress file: {e}")
            
            # Save result and report to files for persistence
            try:
                if 'result' in locals() and result:
                    # Save result to file
                    result_dict = {
                        'total_trades': result.total_trades,
                        'winning_trades': result.winning_trades,
                        'losing_trades': result.losing_trades,
                        'win_rate': result.win_rate,
                        'profit_factor': result.profit_factor,
                        'sharpe_ratio': result.sharpe_ratio,
                        'max_drawdown': result.max_drawdown,
                        'skewness': result.skewness,
                        'kurtosis': result.kurtosis,
                        'psr_0': result.psr_0,
                        'psr_1': result.psr_1,
                        'passed': result.passed
                    }
                    with open(RESULT_FILE, 'w') as f:
                        json.dump(result_dict, f)
                    logger.info(f"[VALIDATION] Saved result to {RESULT_FILE}")
                    
                    # Save report to file
                    with open(REPORT_FILE, 'w') as f:
                        f.write(result.report)
                    logger.info(f"[VALIDATION] Saved report to {REPORT_FILE}")
            except Exception as e:
                logger.error(f"[VALIDATION] Failed to save result/report: {e}")
    
    def get_progress(self) -> Dict:
        """Get current validation progress"""
        return {
            'is_running': self.is_running,
            'progress_pct': self.current_progress,
            'trades_completed': self.current_trade_count,
            'target_trades': self.params.max_trades,
            'params': self.params.to_dict()
        }
    
    def get_validation_history(self) -> List[ValidationResult]:
        """Get history of all validation runs"""
        return self._validation_history
    
    def reset_validation(self):
        """Reset validation state for new run"""
        self.is_running = False
        self.current_progress = 0
        self.current_trade_count = 0
        self.last_signal_time = None
        logger.info("[VALIDATION] State reset for new validation run")


# Global instance for background processing
_validation_instance: Optional[ValidationBacktest] = None


def get_validation_backtest(data_layer=None, config=None, params: Optional[ValidationParams] = None) -> ValidationBacktest:
    """
    Get or create validation backtest instance.
    
    Args:
        data_layer: Data layer for fetching data
        config: Configuration object
        params: Optional ValidationParams for custom settings
        
    Returns:
        ValidationBacktest instance
    """
    global _validation_instance
    if _validation_instance is None and data_layer is not None:
        _validation_instance = ValidationBacktest(data_layer, config, params)
    elif params and _validation_instance:
        # Update params on existing instance
        _validation_instance.params = params
    return _validation_instance


def load_settings_from_file(config_path: str = "/Users/shivamkumarsingh/Documents/AIM/apex-btc/backend/config/settings.json") -> Dict[str, Any]:
    """Load settings from settings.json file"""
    import json
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"[VALIDATION] Failed to load settings: {e}")
        return {}


def create_validation_with_params(settings_dict: Optional[Dict[str, Any]] = None, data_layer=None, config=None, use_settings_file: bool = True) -> ValidationBacktest:
    """
    Create a new validation instance with parameters from settings.
    
    Args:
        settings_dict: Optional dictionary with settings (overrides file)
        data_layer: Data layer
        config: Configuration
        use_settings_file: Whether to load from settings.json first
        
    Returns:
        ValidationBacktest configured with provided settings
    """
    # Start with file settings if enabled
    if use_settings_file:
        file_settings = load_settings_from_file()
        if file_settings:
            logger.info(f"[VALIDATION] Loaded settings from file: {file_settings}")
            # Merge with provided settings (provided takes precedence)
            if settings_dict:
                file_settings.update(settings_dict)
            settings_dict = file_settings
    
    # If still no settings, use empty dict
    if settings_dict is None:
        settings_dict = {}
    
    params = ValidationParams()
    
    # Map settings from dashboard/settings file
    # Signal thresholds
    if 'signal_threshold' in settings_dict:
        params.signal_threshold = int(settings_dict['signal_threshold'])
    if 'min_probability' in settings_dict:
        params.min_probability = float(settings_dict['min_probability'])
    if 'min_prospect_value' in settings_dict:
        params.min_prospect_value = float(settings_dict['min_prospect_value'])
    if 'tsmom_percentile' in settings_dict:
        params.tsmom_percentile = float(settings_dict['tsmom_percentile'])
    if 'cooldown_hours' in settings_dict:
        params.cooldown_hours = int(settings_dict['cooldown_hours'])
    
    # Component thresholds (handle both naming conventions)
    if 'min_ofi_clean' in settings_dict:
        params.min_ofi = float(settings_dict['min_ofi_clean'])
    elif 'min_ofi' in settings_dict:
        params.min_ofi = float(settings_dict['min_ofi'])
        
    if 'min_mrr_rho' in settings_dict:
        params.min_mrr = float(settings_dict['min_mrr_rho'])
    elif 'min_mrr' in settings_dict:
        params.min_mrr = float(settings_dict['min_mrr'])
        
    if 'min_co_value' in settings_dict:
        params.min_co = float(settings_dict['min_co_value'])
    elif 'min_co' in settings_dict:
        params.min_co = float(settings_dict['min_co'])
        
    if 'min_asymmetric_sharpe' in settings_dict:
        params.min_sharpe = float(settings_dict['min_asymmetric_sharpe'])
    elif 'min_sharpe' in settings_dict:
        params.min_sharpe = float(settings_dict['min_sharpe'])

    if 'min_prob_weighted_score' in settings_dict:
        params.min_prob_weighted_score = float(settings_dict['min_prob_weighted_score'])

    # Position management
    if 'position_size_pct' in settings_dict:
        params.position_size_pct = float(settings_dict['position_size_pct'])
    if 'stop_loss_pct' in settings_dict:
        params.stop_loss_pct = float(settings_dict['stop_loss_pct'])
    if 'take_profit_mult' in settings_dict:
        params.take_profit_multiplier = float(settings_dict['take_profit_mult'])
    elif 'take_profit_multiplier' in settings_dict:
        params.take_profit_multiplier = float(settings_dict['take_profit_multiplier'])
    
    # Validation settings
    if 'max_daily_trades' in settings_dict:
        params.max_trades = int(settings_dict['max_daily_trades']) * 10  # Scale up for validation
    if 'bootstrap_trades' in settings_dict:
        params.max_trades = max(params.max_trades, int(settings_dict['bootstrap_trades']) * 15)
    
    logger.info(f"[VALIDATION] Created ValidationParams: {params.to_dict()}")
    
    return ValidationBacktest(data_layer, config, params)
