"""
APEX-BTC Configuration Settings
Institutional-grade trading system configuration
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import List, Dict
import os


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "APEX-BTC"
    APP_VERSION: str = "6.0.0"
    ENVIRONMENT: str = Field(default="development", env="ENVIRONMENT")
    DEBUG: bool = Field(default=False, env="DEBUG")
    
    # Trading Parameters
    INITIAL_CAPITAL: float = Field(default=10.0, env="INITIAL_CAPITAL")
    SYMBOL: str = Field(default="BTCUSDT", env="TRADING_SYMBOL")
    TIMEFRAMES: List[str] = ["1m", "5m", "15m", "1h", "4h", "1d"]
    
    # Kelly Criterion (Principle 6)
    KELLY_FRACTION: float = 0.5  # Half-Kelly
    TARGET_VOLATILITY: float = 0.15  # 15% annualized
    
    # TSMOM Parameters (Han et al. 2026)
    TSMOM_LOOKBACK: int = 28  # 28-day lookback
    TSMOM_HOLDING: int = 5    # 5-day holding
    TSMOM_PERCENTILE_ENTRY: float = 0.667  # 66.7th percentile
    
    # HARRVJ Parameters (Pichl & Kaizoji 2017)
    HARRVJ_BETA: Dict[str, float] = {
        "beta0": 0.0103,
        "beta1": 0.3448,
        "beta2": 0.5179,
        "beta3": -0.2268,
        "beta5": -0.8609,
        "beta6": 0.8563,
    }
    
    # MRR Model Parameters (Dimpfl 2017)
    MRR_WINDOW: int = 500  # Rolling window for estimation
    MRR_ADVERSE_SELECTION_PCT: float = 0.463  # 46.3% of spread
    SPREAD_CONSTANT: bool = True  # Dimpfl finding: spread is constant 24h
    
    # Jump-Diffusion (Han et al. 2026)
    JUMP_MU: float = 0.005
    JUMP_SIGMA: float = 0.032
    JUMP_NU: float = 0.051
    JUMP_DELTA: float = 0.394
    JUMP_LAMBDA: float = 0.016
    JUMP_THRESHOLD: float = 0.015  # Trigger regime change
    
    # Avellaneda & Lee (2010)
    S_SCORE_ENTRY: float = 1.25
    S_SCORE_EXIT_LONG: float = 0.50
    S_SCORE_EXIT_SHORT: float = 0.75
    MEAN_REVERSION_SPEED_MIN: float = 8.4  # kappa > 252/30
    
    # Bootstrap Mode - Skip PSR/DSR validation for first trades
    BOOTSTRAP_MODE: bool = True  # Set to False after initial trades
    BOOTSTRAP_TRADES: int = 5    # Number of trades to bootstrap
    
    # Additional settings from .env
    TRADING_SYMBOL: str = "BTCUSDT"
    SECRET_KEY: str = "change_this_to_a_random_string"
    
    # Prospect Theory (Kahneman & Tversky 1979)
    PT_ALPHA: float = 0.88
    PT_BETA: float = 0.88
    PT_LAMBDA: float = 2.25  # Loss aversion
    PT_GAMMA: float = 0.67   # Probability weighting
    
    # DQN Parameters (Zhang et al. 2020)
    DQN_LEARNING_RATE: float = 0.0001
    DQN_GAMMA: float = 0.3
    DQN_BATCH_SIZE: int = 64
    DQN_MEMORY_SIZE: int = 5000
    DQN_TAU: int = 1000
    DQN_COST_RATE: float = 0.0020
    
    # Fees and Costs
    MAKER_FEE: float = 0.0004  # 0.04%
    TAKER_FEE: float = 0.0004  # 0.04%
    SLIPPAGE_ESTIMATE: float = 0.0003  # 0.03%
    
    # Risk Management
    MAX_DRAWDOWN_PCT: float = 0.15  # 15% circuit breaker
    YELLOW_DRAWDOWN: float = 0.05   # 5% warning
    ORANGE_DRAWDOWN: float = 0.08  # 8% suspension
    MAX_LEVERAGE: float = 3.0
    MAX_DAILY_TRADES: int = 5
    COOLDOWN_HOURS: int = 4
    
    # Signal Thresholds
    SIGNAL_THRESHOLD_REGIME_1: int = 70  # Bullish
    SIGNAL_THRESHOLD_REGIME_2: int = 75  # Bull volatile
    SIGNAL_THRESHOLD_REGIME_3: int = 80  # Range-bound
    SIGNAL_THRESHOLD_REGIME_4: int = 85  # High vol
    SIGNAL_THRESHOLD_REGIME_5: int = 90  # Crisis
    
    # Signal Component Thresholds
    MIN_OFI_CLEAN: float = 0.01  # Minimum OFI clean value
    MIN_MRR_RHO: float = 0.10  # Minimum MRR autocorrelation
    MIN_CO_VALUE: float = 0.0  # Minimum carry-over value
    MIN_ASYMMETRIC_SHARPE: float = 0.5  # Minimum asymmetric Sharpe ratio
    MIN_PROB_WEIGHTED_SCORE: float = 35.0  # Minimum probability-weighted score for signal validation
    
    # Dynamic Override (set via API to override regime-specific thresholds)
    DYNAMIC_SIGNAL_THRESHOLD: int = Field(default=0, env="DYNAMIC_SIGNAL_THRESHOLD")  # 0 = use regime-specific
    
    # Trade Decision Controls
    REQUIRE_SIGNAL_VALID: bool = True  # Require signal_valid flag to be True
    REQUIRE_DIRECTION: bool = True  # Require non-NEUTRAL direction
    MIN_SIGNAL_PROBABILITY: float = 0.5  # Minimum probability for trade
    MIN_PROSPECT_VALUE: float = 0.0  # Minimum prospect value for trade
    
    # Additional tunable settings for API
    SIGNAL_COOLDOWN_SECONDS: int = 300  # Cooldown between signals (seconds)
    POSITION_SIZE_PCT: float = 0.1  # Position size as % of equity
    STOP_LOSS_PCT: float = 0.01  # Stop loss percentage
    TAKE_PROFIT_MULT: float = 2.0  # Take profit multiplier (R:R)
    MAX_POSITIONS: int = 1  # Max concurrent positions
    VALIDITY_BOOTSTRAP_ENABLED: bool = True  # Bootstrap mode
    
    # Liquidity Windows (Dimpfl 2017)
    LIQUIDITY_THRESHOLD: float = 0.7
    PREMIUM_WINDOWS: List[int] = [7, 8, 9, 10, 11, 13, 14, 15, 16, 17]  # UTC
    AVOID_WINDOWS: List[int] = [2, 3, 4, 5, 6]  # UTC
    
    # Statistical Validation
    PSR_TARGET: float = 0.95
    DSR_TARGET: float = 0.95
    MIN_TRADES_FOR_STATS: int = 30
    LOG_RETURN_TSTAT_MIN: float = 2.0
    
    # Binance API
    BINANCE_API_KEY: str = Field(default="", env="BINANCE_API_KEY")
    BINANCE_SECRET_KEY: str = Field(default="", env="BINANCE_SECRET_KEY")
    BINANCE_TESTNET: bool = Field(default=False, env="BINANCE_TESTNET")
    
    # Database
    DATABASE_URL: str = Field(
        default="postgresql://apex:apex@localhost:5432/apex_btc",
        env="DATABASE_URL"
    )
    REDIS_URL: str = Field(default="redis://localhost:6379/0", env="REDIS_URL")
    INFLUXDB_URL: str = Field(default="http://localhost:8086", env="INFLUXDB_URL")
    INFLUXDB_TOKEN: str = Field(default="", env="INFLUXDB_TOKEN")
    INFLUXDB_ORG: str = Field(default="apex", env="INFLUXDB_ORG")
    INFLUXDB_BUCKET: str = Field(default="market_data", env="INFLUXDB_BUCKET")
    
    # PCA Multi-Asset
    PCA_ASSETS: List[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    PCA_LOOKBACK: int = 252
    
    # Data Buffers
    TICK_BUFFER_SIZE: int = 5000
    CANDLE_HISTORY_MIN: int = 500
    
    # API Server
    API_HOST: str = Field(default="0.0.0.0", env="API_HOST")
    API_PORT: int = Field(default=8000, env="API_PORT")
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Override with saved settings from settings.json if exists
try:
    import json
    import os
    _settings_path = os.path.join(os.path.dirname(__file__), 'settings.json')
    print(f"[SETTINGS] Looking for saved settings at: {_settings_path}")
    print(f"[SETTINGS] File exists: {os.path.exists(_settings_path)}")
    if os.path.exists(_settings_path):
        with open(_settings_path, 'r') as f:
            _saved_settings = json.load(f)
        print(f"[SETTINGS] Loaded {len(_saved_settings)} settings from file")
        print(f"[SETTINGS] Raw saved settings: {_saved_settings}")
        # Map of frontend keys to Settings attributes
        _key_mapping = {
            'signal_threshold': 'DYNAMIC_SIGNAL_THRESHOLD',
            'min_probability': 'MIN_SIGNAL_PROBABILITY',
            'min_prospect_value': 'MIN_PROSPECT_VALUE',
            'require_signal_valid': 'REQUIRE_SIGNAL_VALID',
            'require_direction': 'REQUIRE_DIRECTION',
            'cooldown_period': 'SIGNAL_COOLDOWN_SECONDS',
            'position_size_pct': 'POSITION_SIZE_PCT',
            'stop_loss_pct': 'STOP_LOSS_PCT',
            'take_profit_mult': 'TAKE_PROFIT_MULT',
            'enable_bootstrap': 'VALIDITY_BOOTSTRAP_ENABLED',
            'bootstrap_trades': 'BOOTSTRAP_TRADES',
            'max_positions': 'MAX_POSITIONS',
            'tsmom_percentile': 'TSMOM_PERCENTILE_ENTRY',
            'cooldown_hours': 'COOLDOWN_HOURS',
            'regime_1_threshold': 'SIGNAL_THRESHOLD_REGIME_1',
            'regime_2_threshold': 'SIGNAL_THRESHOLD_REGIME_2',
            'regime_3_threshold': 'SIGNAL_THRESHOLD_REGIME_3',
            'regime_4_threshold': 'SIGNAL_THRESHOLD_REGIME_4',
            'regime_5_threshold': 'SIGNAL_THRESHOLD_REGIME_5',
            'min_ofi_clean': 'MIN_OFI_CLEAN',
            'min_mrr_rho': 'MIN_MRR_RHO',
            'min_co_value': 'MIN_CO_VALUE',
            'min_asymmetric_sharpe': 'MIN_ASYMMETRIC_SHARPE',
            'min_prob_weighted_score': 'MIN_PROB_WEIGHTED_SCORE',
            'max_daily_trades': 'MAX_DAILY_TRADES',
        }
        # Update settings object with saved values
        for key, value in _saved_settings.items():
            attr_name = _key_mapping.get(key, key)
            if hasattr(settings, attr_name):
                old_value = getattr(settings, attr_name)
                setattr(settings, attr_name, value)
                new_value = getattr(settings, attr_name)
                print(f"[SETTINGS] Applied: {attr_name} = {new_value} (was {old_value})")
            else:
                print(f"[SETTINGS] Skipped: {key} (no attribute {attr_name})")
        print(f"[SETTINGS] TSMOM_PERCENTILE_ENTRY final value: {settings.TSMOM_PERCENTILE_ENTRY}")
    else:
        print(f"[SETTINGS] No saved settings file found, using defaults")
except Exception as e:
    print(f"[SETTINGS] Error loading saved settings: {e}")
    import traceback
    traceback.print_exc()
