"""
Database Models for APEX-BTC
TimescaleDB/PostgreSQL schema for time-series trading data
"""
from sqlalchemy import (
    Column, Integer, BigInteger, Float, String, DateTime, 
    Boolean, JSON, Index, ForeignKey, Numeric, create_engine
)
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional

Base = declarative_base()


class Candle(Base):
    """OHLCV candles for all timeframes"""
    __tablename__ = 'candles'
    
    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    open = Column(Numeric(20, 8), nullable=False)
    high = Column(Numeric(20, 8), nullable=False)
    low = Column(Numeric(20, 8), nullable=False)
    close = Column(Numeric(20, 8), nullable=False)
    volume = Column(Numeric(20, 8), nullable=False)
    quote_volume = Column(Numeric(20, 8))
    trades_count = Column(Integer)
    taker_buy_volume = Column(Numeric(20, 8))
    taker_buy_quote = Column(Numeric(20, 8))
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        Index('idx_candles_symbol_tf_time', 'symbol', 'timeframe', 'timestamp'),
    )


class Tick(Base):
    """Individual trades for microstructure analysis"""
    __tablename__ = 'ticks'
    
    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    price = Column(Numeric(20, 8), nullable=False)
    quantity = Column(Numeric(20, 8), nullable=False)
    direction = Column(Integer)  # +1 buyer-initiated, -1 seller-initiated, 0 unknown
    is_buyer_market_maker = Column(Boolean)
    trade_id = Column(BigInteger, unique=True)
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        Index('idx_ticks_symbol_time', 'symbol', 'timestamp'),
    )


class FeatureSnapshot(Base):
    """Computed features at each timestamp"""
    __tablename__ = 'feature_snapshots'
    
    id = Column(BigInteger, primary_key=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # TSMOM Features
    tsmom_rank = Column(Float)
    co_value = Column(Float)  # Continuing Overreaction
    
    # Volatility Features
    rv_daily = Column(Float)  # Realized volatility
    bv_daily = Column(Float)  # Bipower variation
    jump_component = Column(Float)
    harrvj_forecast = Column(Float)
    atr_harrvj = Column(Float)
    
    # MRR Microstructure
    mrr_theta = Column(Float)
    mrr_rho = Column(Float)
    mrr_spread_estimate = Column(Float)
    adverse_selection_pct = Column(Float)
    
    # Technical Indicators
    ema_21 = Column(Float)
    ema_200 = Column(Float)
    adx = Column(Float)
    rsi_30 = Column(Float)
    bb_width = Column(Float)
    obv = Column(Float)
    macd_line = Column(Float)
    macd_signal = Column(Float)
    macd_hist = Column(Float)
    stochastic_rsi = Column(Float)
    
    # PCA Factors
    pca_factor_1 = Column(Float)
    pca_factor_2 = Column(Float)
    pca_factor_3 = Column(Float)
    s_score = Column(Float)
    mean_reversion_speed = Column(Float)
    
    # Order Flow
    ofi_clean = Column(Float)
    ofi_raw = Column(Float)
    volume_profile_poc = Column(Float)
    algo_slicing_detected = Column(Boolean)
    
    # Regime Detection
    regime = Column(Integer)  # 1-5
    liquidity_score = Column(Float)
    
    # Jump-Diffusion Parameters
    jump_mu = Column(Float)
    jump_sigma = Column(Float)
    jump_nu = Column(Float)
    jump_delta = Column(Float)
    jump_lambda = Column(Float)
    
    created_at = Column(DateTime, default=func.now())
    
    __table_args__ = (
        Index('idx_features_symbol_time', 'symbol', 'timestamp'),
    )


class Trade(Base):
    """Paper trading ledger"""
    __tablename__ = 'trades'
    
    id = Column(BigInteger, primary_key=True)
    trade_id = Column(String(50), unique=True, nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    
    # Entry
    entry_timestamp = Column(DateTime, nullable=False, index=True)
    entry_price = Column(Numeric(20, 8), nullable=False)
    direction = Column(String(10), nullable=False)  # LONG/SHORT
    position_size_btc = Column(Numeric(20, 8), nullable=False)
    position_size_usd = Column(Numeric(20, 8), nullable=False)
    
    # Risk Parameters
    stop_loss = Column(Numeric(20, 8))
    take_profit_1 = Column(Numeric(20, 8))
    take_profit_2 = Column(Numeric(20, 8))
    
    # Signal Context
    composite_score = Column(Float)
    regime_at_entry = Column(Integer)
    tsmom_rank_at_entry = Column(Float)
    co_value_at_entry = Column(Float)
    harrvj_forecast_at_entry = Column(Float)
    liquidity_score_at_entry = Column(Float)
    mrr_theta_at_entry = Column(Float)
    mrr_rho_at_entry = Column(Float)
    s_score_at_entry = Column(Float)
    reference_point_at_entry = Column(Float)
    
    # Exit
    exit_timestamp = Column(DateTime)
    exit_price = Column(Numeric(20, 8))
    exit_reason = Column(String(50))  # TP1, TP2, SL, TRAILING, TIME, MANUAL
    
    # P&L Breakdown
    gross_pnl = Column(Numeric(20, 8))
    fixed_fees = Column(Numeric(20, 8))
    execution_slippage = Column(Numeric(20, 8))
    adverse_selection_cost = Column(Numeric(20, 8))
    net_pnl = Column(Numeric(20, 8))
    cumulative_equity = Column(Numeric(20, 8))
    
    # Performance Metrics
    mfe = Column(Float)  # Maximum favorable excursion
    mae = Column(Float)  # Maximum adverse excursion
    
    # Risk Metrics
    kelly_fraction_used = Column(Float)
    jump_haircut_applied = Column(Float)
    
    # DQN State
    dqn_action = Column(Integer)
    dqn_q_value = Column(Float)
    
    # Prospect Theory
    prospect_value = Column(Float)
    v_gain = Column(Float)
    v_loss = Column(Float)
    pi_p_win = Column(Float)
    pi_p_loss = Column(Float)
    
    created_at = Column(DateTime, default=func.now())
    closed_at = Column(DateTime)
    
    __table_args__ = (
        Index('idx_trades_symbol_entry', 'symbol', 'entry_timestamp'),
    )


class EquityCurve(Base):
    """Daily equity snapshots"""
    __tablename__ = 'equity_curve'
    
    id = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    equity = Column(Numeric(20, 8), nullable=False)
    high_water_mark = Column(Numeric(20, 8), nullable=False)
    drawdown_pct = Column(Float, nullable=False)
    reference_point = Column(Float)
    daily_return = Column(Float)
    
    # Position Summary
    open_positions = Column(Integer)
    exposure_btc = Column(Numeric(20, 8))
    exposure_usd = Column(Numeric(20, 8))
    
    # Daily Stats
    trades_count = Column(Integer)
    wins = Column(Integer)
    losses = Column(Integer)
    gross_pnl_day = Column(Numeric(20, 8))
    fees_paid = Column(Numeric(20, 8))
    
    created_at = Column(DateTime, default=func.now())


class PerformanceMetrics(Base):
    """Statistical performance metrics (PSR, DSR, etc.)"""
    __tablename__ = 'performance_metrics'
    
    id = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Standard Metrics
    total_trades = Column(Integer)
    win_rate = Column(Float)
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    calmar_ratio = Column(Float)
    profit_factor = Column(Float)
    
    # López de Prado Metrics
    psr_sr0 = Column(Float)  # PSR(SR*=0)
    psr_sr25 = Column(Float)  # PSR(SR*=2.5)
    dsr = Column(Float)  # Deflated Sharpe Ratio
    min_trl = Column(Float)  # Minimum Track Record Length
    prob_strategy_failure = Column(Float)
    
    # Time Under Water
    tuw_median = Column(Float)
    tuw_75th = Column(Float)
    tuw_95th = Column(Float)
    current_tuw = Column(Float)
    
    # Han et al. Metrics
    mean_log_return = Column(Float)
    log_return_tstat = Column(Float)
    expected_log_return = Column(Float)
    jump_intensity = Column(Float)
    
    # Prospect Theory
    cumulative_prospect_value = Column(Float)
    loss_aversion_ratio = Column(Float)
    
    # Microstructure
    mean_adverse_selection_cost = Column(Float)
    harrvj_mae = Column(Float)
    
    created_at = Column(DateTime, default=func.now())


class RegimeHistory(Base):
    """Historical regime classifications"""
    __tablename__ = 'regime_history'
    
    id = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False)
    regime = Column(Integer, nullable=False)  # 1-5
    regime_name = Column(String(50))
    
    # Regime Features
    tsmom_percentile = Column(Float)
    adx = Column(Float)
    bb_width_percentile = Column(Float)
    jump_lambda = Column(Float)
    mrr_theta_zscore = Column(Float)
    spread_deviation = Column(Float)
    liquidity_score = Column(Float)
    algo_slicing_fraction = Column(Float)
    
    created_at = Column(DateTime, default=func.now())


class Alert(Base):
    """System alerts and warnings"""
    __tablename__ = 'alerts'
    
    id = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime, default=func.now(), index=True)
    level = Column(String(20), nullable=False)  # INFO, WARNING, YELLOW, ORANGE, RED
    category = Column(String(50), nullable=False)  # PSR, DSR, JUMP, AS, etc.
    message = Column(String(500), nullable=False)
    metric_value = Column(Float)
    threshold = Column(Float)
    action_taken = Column(String(200))
    acknowledged = Column(Boolean, default=False)


class DQNExperience(Base):
    """DQN replay buffer storage"""
    __tablename__ = 'dqn_experiences'
    
    id = Column(BigInteger, primary_key=True)
    timestamp = Column(DateTime, default=func.now())
    
    state = Column(JSON, nullable=False)
    action = Column(Integer, nullable=False)
    reward = Column(Float, nullable=False)
    next_state = Column(JSON, nullable=False)
    done = Column(Boolean, default=False)
    
    # Trading context
    position_size = Column(Float)
    volatility = Column(Float)
    

# Database engine and session
def get_engine(database_url: str):
    return create_engine(database_url, pool_size=20, max_overflow=30)


def init_db(engine):
    Base.metadata.create_all(engine)


SessionLocal = sessionmaker(autocommit=False, autoflush=False)

def get_session(engine):
    SessionLocal.configure(bind=engine)
    return SessionLocal()
