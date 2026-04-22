"""
Layer 1: Data Ingestion
Real-time market data from Binance via WebSocket and REST API
"""
import asyncio
import websockets
import json
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta
from collections import deque
import pandas as pd
import numpy as np
from loguru import logger
import aiohttp
from binance.client import Client as BinanceClient
from binance.enums import *
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


@dataclass
class OHLCV:
    """Candle data structure"""
    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float = 0.0
    trades: int = 0
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timeframe': self.timeframe,
            'timestamp': self.timestamp,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'close': self.close,
            'volume': self.volume,
            'quote_volume': self.quote_volume,
            'trades': self.trades,
        }


@dataclass
class TickData:
    """Individual trade/tick"""
    symbol: str
    timestamp: datetime
    price: float
    quantity: float
    direction: int  # +1 buyer, -1 seller, 0 unknown
    is_buyer_maker: bool
    trade_id: int
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp,
            'price': self.price,
            'quantity': self.quantity,
            'direction': self.direction,
            'is_buyer_maker': self.is_buyer_maker,
            'trade_id': self.trade_id,
        }


@dataclass
class OrderBookLevel:
    price: float
    quantity: float


@dataclass
class OrderBookSnapshot:
    """Order book top N levels"""
    symbol: str
    timestamp: datetime
    bids: List[OrderBookLevel]
    asks: List[OrderBookLevel]
    
    @property
    def best_bid(self) -> float:
        return self.bids[0].price if self.bids else 0.0
    
    @property
    def best_ask(self) -> float:
        return self.asks[0].price if self.asks else 0.0
    
    @property
    def spread(self) -> float:
        return self.best_ask - self.best_bid
    
    @property
    def mid_price(self) -> float:
        return (self.best_bid + self.best_ask) / 2


class DataIngestionLayer:
    """
    Layer 1: Data Ingestion
    - WebSocket streams for real-time data
    - REST API for historical data
    - Multi-asset support for PCA
    - Tick-level buffering for MRR model
    """
    
    def __init__(self, config: Any, db_session=None):
        self.config = config
        self.db_session = db_session
        
        # Binance clients
        self.binance_client = BinanceClient(
            api_key=config.BINANCE_API_KEY,
            api_secret=config.BINANCE_SECRET_KEY,
            testnet=config.BINANCE_TESTNET
        )
        
        # WebSocket connections
        self.ws_connections: Dict[str, websockets.WebSocketClientProtocol] = {}
        self.ws_tasks: Dict[str, asyncio.Task] = {}
        
        # Data buffers
        self.tick_buffer: deque = deque(maxlen=config.TICK_BUFFER_SIZE)
        self.candle_buffers: Dict[str, Dict[str, deque]] = {}
        self.order_book: Optional[OrderBookSnapshot] = None
        
        # Historical data cache
        self.candle_history: Dict[str, pd.DataFrame] = {}
        self.daily_returns: pd.Series = pd.Series(dtype=float)
        
        # Callbacks
        self.candle_callbacks: List[Callable[[OHLCV], None]] = []
        self.tick_callbacks: List[Callable[[TickData], None]] = []
        self.book_callbacks: List[Callable[[OrderBookSnapshot], None]] = []
        
        # State
        self.running = False
        self._last_prices: Dict[str, float] = {}
        
    async def initialize(self):
        """Initialize data buffers and load historical data"""
        logger.info("Initializing Layer 1: Data Ingestion")
        
        # Initialize candle buffers
        for tf in self.config.TIMEFRAMES:
            self.candle_buffers[tf] = {
                'open': deque(maxlen=self.config.CANDLE_HISTORY_MIN),
                'high': deque(maxlen=self.config.CANDLE_HISTORY_MIN),
                'low': deque(maxlen=self.config.CANDLE_HISTORY_MIN),
                'close': deque(maxlen=self.config.CANDLE_HISTORY_MIN),
                'volume': deque(maxlen=self.config.CANDLE_HISTORY_MIN),
            }
        
        # Load historical candles
        await self._load_historical_data()
        
        logger.info("Layer 1 initialization complete")
        
    async def _load_historical_data(self):
        """Load minimum required historical data"""
        symbol = self.config.SYMBOL
        
        for tf in self.config.TIMEFRAMES:
            try:
                # Fetch minimum required candles
                limit = max(self.config.CANDLE_HISTORY_MIN, 500)
                klines = self.binance_client.get_klines(
                    symbol=symbol,
                    interval=tf,
                    limit=limit
                )
                
                df = self._klines_to_dataframe(klines, tf)
                self.candle_history[tf] = df
                
                # Populate buffers
                for col in ['open', 'high', 'low', 'close', 'volume']:
                    self.candle_buffers[tf][col].extend(df[col].values)
                
                logger.info(f"Loaded {len(df)} candles for {tf}")
                
            except Exception as e:
                logger.error(f"Failed to load {tf} candles: {e}")
                
        # Load daily data for TSMOM and jump-diffusion
        try:
            daily_klines = self.binance_client.get_klines(
                symbol=symbol,
                interval='1d',
                limit=365 * 3  # 3 years minimum
            )
            daily_df = self._klines_to_dataframe(daily_klines, '1d')
            self.daily_returns = np.log(daily_df['close'] / daily_df['close'].shift(1)).dropna()
            logger.info(f"Loaded {len(daily_df)} daily candles")
        except Exception as e:
            logger.error(f"Failed to load daily candles: {e}")
            
    def _klines_to_dataframe(self, klines: List, timeframe: str) -> pd.DataFrame:
        """Convert Binance klines to DataFrame with validation"""
        data = []
        invalid_count = 0
        
        for k in klines:
            try:
                open_p = float(k[1])
                high_p = float(k[2])
                low_p = float(k[3])
                close_p = float(k[4])
                
                # Validate OHLC logic: low <= open, close <= high
                if low_p > high_p:
                    logger.warning(f"Invalid candle: low({low_p}) > high({high_p})")
                    invalid_count += 1
                    continue
                    
                if open_p < low_p or open_p > high_p:
                    logger.warning(f"Invalid candle: open({open_p}) outside range [{low_p}, {high_p}]")
                    invalid_count += 1
                    continue
                    
                if close_p < low_p or close_p > high_p:
                    logger.warning(f"Invalid candle: close({close_p}) outside range [{low_p}, {high_p}]")
                    invalid_count += 1
                    continue
                
                data.append({
                    'timestamp': datetime.fromtimestamp(k[0] / 1000),
                    'open': open_p,
                    'high': high_p,
                    'low': low_p,
                    'close': close_p,
                    'volume': float(k[5]),
                    'quote_volume': float(k[7]),
                    'trades': int(k[8]),
                    'taker_buy_volume': float(k[9]),
                })
            except (IndexError, ValueError) as e:
                logger.error(f"Error parsing kline: {e}, kline: {k}")
                invalid_count += 1
                continue
        
        if invalid_count > 0:
            logger.warning(f"Skipped {invalid_count} invalid candles out of {len(klines)}")
        
        if len(data) == 0:
            logger.error(f"No valid candles after parsing {len(klines)} klines")
            return pd.DataFrame()
        
        # Log sample candle for debugging
        if len(data) > 0:
            sample = data[0]
            logger.info(f"Sample {timeframe} candle: O={sample['open']:.2f} H={sample['high']:.2f} L={sample['low']:.2f} C={sample['close']:.2f}")
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        return df
        
    async def start_websockets(self):
        """Start all WebSocket connections"""
        self.running = True
        symbol_lower = self.config.SYMBOL.lower()
        
        streams = [
            (f"{symbol_lower}@kline_1m", self._handle_kline),
            (f"{symbol_lower}@kline_5m", self._handle_kline),
            (f"{symbol_lower}@kline_15m", self._handle_kline),
            (f"{symbol_lower}@kline_1h", self._handle_kline),
            (f"{symbol_lower}@aggTrade", self._handle_agg_trade),
            (f"{symbol_lower}@depth20@100ms", self._handle_order_book),
        ]
        
        for stream, handler in streams:
            task = asyncio.create_task(self._ws_listener(stream, handler))
            self.ws_tasks[stream] = task
            
        logger.info(f"Started {len(streams)} WebSocket streams")
        
    async def _ws_listener(self, stream: str, handler: Callable):
        """Generic WebSocket listener with reconnection"""
        base_url = "wss://stream.binance.com:9443/ws"
        if self.config.BINANCE_TESTNET:
            base_url = "wss://testnet.binance.vision/ws"
            
        while self.running:
            try:
                async with websockets.connect(f"{base_url}/{stream}") as ws:
                    logger.info(f"Connected to {stream}")
                    self.ws_connections[stream] = ws
                    
                    async for message in ws:
                        if not self.running:
                            break
                        data = json.loads(message)
                        await handler(data)
                        
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"WebSocket {stream} closed, reconnecting...")
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"WebSocket {stream} error: {e}")
                await asyncio.sleep(5)
                
    async def _handle_kline(self, data: Dict):
        """Handle kline/candlestick data"""
        k = data.get('k', {})
        if not k.get('x'):  # Only process closed candles
            return
            
        candle = OHLCV(
            symbol=data['s'],
            timeframe=k['i'],
            timestamp=datetime.fromtimestamp(k['t'] / 1000),
            open=float(k['o']),
            high=float(k['h']),
            low=float(k['l']),
            close=float(k['c']),
            volume=float(k['v']),
            quote_volume=float(k['q']),
            trades=int(k['n']),
        )
        
        # Update buffers
        tf = candle.timeframe
        if tf in self.candle_buffers:
            self.candle_buffers[tf]['open'].append(candle.open)
            self.candle_buffers[tf]['high'].append(candle.high)
            self.candle_buffers[tf]['low'].append(candle.low)
            self.candle_buffers[tf]['close'].append(candle.close)
            self.candle_buffers[tf]['volume'].append(candle.volume)
        
        # Notify subscribers
        for callback in self.candle_callbacks:
            try:
                callback(candle)
            except Exception as e:
                logger.error(f"Candle callback error: {e}")
                
    async def _handle_agg_trade(self, data: Dict):
        """Handle aggregate trade data for MRR model"""
        price = float(data['p'])
        prev_price = self._last_prices.get(data['s'], price)
        
        # Trade direction using tick test (Lee & Ready 1991)
        if data.get('m') is not None:
            # Binance provides maker flag
            direction = -1 if data['m'] else 1  # True = buyer is maker = sell market order
        else:
            # Tick test fallback
            if price > prev_price:
                direction = 1  # Buyer initiated
            elif price < prev_price:
                direction = -1  # Seller initiated
            else:
                direction = 0  # Unknown
                
        tick = TickData(
            symbol=data['s'],
            timestamp=datetime.fromtimestamp(data['T'] / 1000),
            price=price,
            quantity=float(data['q']),
            direction=direction,
            is_buyer_maker=data.get('m', False),
            trade_id=data['a'],
        )
        
        self._last_prices[data['s']] = price
        self.tick_buffer.append(tick)
        
        # Notify subscribers
        for callback in self.tick_callbacks:
            try:
                callback(tick)
            except Exception as e:
                logger.error(f"Tick callback error: {e}")
                
    async def _handle_order_book(self, data: Dict):
        """Handle order book updates"""
        bids = [OrderBookLevel(float(b[0]), float(b[1])) for b in data.get('b', [])[:20]]
        asks = [OrderBookLevel(float(a[0]), float(a[1])) for a in data.get('a', [])[:20]]
        
        self.order_book = OrderBookSnapshot(
            symbol=data.get('s', self.config.SYMBOL),
            timestamp=datetime.now(),
            bids=bids,
            asks=asks,
        )
        
        for callback in self.book_callbacks:
            try:
                callback(self.order_book)
            except Exception as e:
                logger.error(f"Order book callback error: {e}")
                
    def get_candle_buffer(self, timeframe: str) -> Dict[str, deque]:
        """Get candle buffer for a timeframe"""
        return self.candle_buffers.get(timeframe, {})
        
    def get_candle_history(self, timeframe: str) -> pd.DataFrame:
        """Get historical candles as DataFrame"""
        return self.candle_history.get(timeframe, pd.DataFrame())
        
    def get_tick_buffer(self, n: Optional[int] = None) -> List[TickData]:
        """Get recent ticks"""
        if n is None:
            return list(self.tick_buffer)
        return list(self.tick_buffer)[-n:]
        
    def get_order_book(self) -> Optional[OrderBookSnapshot]:
        """Get current order book"""
        return self.order_book
        
    def get_daily_returns(self) -> pd.Series:
        """Get daily returns series for TSMOM"""
        return self.daily_returns
    
    def get_current_price(self) -> Optional[float]:
        """Get current price from latest candle or WebSocket data"""
        # Try to get from _last_prices first (WebSocket updates)
        if self.config.SYMBOL in self._last_prices:
            return self._last_prices[self.config.SYMBOL]
        
        # Fallback to latest 1m candle close price
        if '1m' in self.candle_history and not self.candle_history['1m'].empty:
            return float(self.candle_history['1m']['close'].iloc[-1])
        
        # Try other timeframes
        for tf in ['5m', '15m', '1h']:
            if tf in self.candle_history and not self.candle_history[tf].empty:
                return float(self.candle_history[tf]['close'].iloc[-1])
        
        return None
    
    def get_current_spread(self) -> float:
        """Get current bid-ask spread"""
        if self.order_book:
            return self.order_book.best_ask - self.order_book.best_bid
        # Default spread estimate (0.01% of price)
        price = self.get_current_price()
        if price:
            return price * 0.0001
        return 0.0
        
    def register_candle_callback(self, callback: Callable[[OHLCV], None]):
        """Register candle update callback"""
        self.candle_callbacks.append(callback)
        
    def register_tick_callback(self, callback: Callable[[TickData], None]):
        """Register tick update callback"""
        self.tick_callbacks.append(callback)
        
    def register_book_callback(self, callback: Callable[[OrderBookSnapshot], None]):
        """Register order book update callback"""
        self.book_callbacks.append(callback)
        
    async def stop(self):
        """Stop all connections"""
        self.running = False
        
        # Cancel tasks
        for task in self.ws_tasks.values():
            task.cancel()
            
        # Close connections
        for ws in self.ws_connections.values():
            await ws.close()
            
        logger.info("Layer 1 stopped")
        
    async def fetch_multi_asset_data(self, symbols: List[str], timeframe: str = '1h', limit: int = 252) -> pd.DataFrame:
        """Fetch data for PCA multi-asset analysis"""
        data = {}
        
        for symbol in symbols:
            try:
                klines = self.binance_client.get_klines(
                    symbol=symbol,
                    interval=timeframe,
                    limit=limit
                )
                df = self._klines_to_dataframe(klines, timeframe)
                data[symbol] = df['close']
            except Exception as e:
                logger.error(f"Failed to fetch {symbol}: {e}")
                
        return pd.DataFrame(data)
