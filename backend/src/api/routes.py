"""
APEX-BTC API Routes
FastAPI endpoints for frontend integration
"""
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime
import asyncio
import json
import math
import os
from loguru import logger
import numpy as np
import pandas as pd

# Custom JSON encoder to handle infinity and NaN values
class SafeJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, float):
            if math.isinf(obj) or math.isnan(obj):
                return None
        return super().default(obj)

def safe_jsonable(data):
    """Convert data to JSON-safe format, replacing inf/nan with None, datetime to string"""
    if isinstance(data, dict):
        return {k: safe_jsonable(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [safe_jsonable(item) for item in data]
    elif isinstance(data, float):
        if math.isinf(data) or math.isnan(data):
            return None
        return data
    elif isinstance(data, datetime):
        return data.isoformat()
    return data

app = FastAPI(
    title="APEX-BTC API",
    description="Autonomous Bitcoin Paper Trading Engine",
    version="6.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global engine reference
trading_engine = None

def set_engine(engine):
    global trading_engine
    trading_engine = engine


# Request/Response Models
class ManualOverrideRequest(BaseModel):
    action: str  # CLOSE_ALL, HALT, RESUME, CLEAR_REVIEW


class DQNTrainingRequest(BaseModel):
    enable: bool


class AlertAcknowledgeRequest(BaseModel):
    alert_key: str


class ThresholdUpdateRequest(BaseModel):
    threshold: int  # 0-100, 0 = use regime-specific thresholds


class SettingsUpdateRequest(BaseModel):
    signal_threshold: Optional[int] = None  # 0-100
    min_probability: Optional[float] = None  # 0.0-1.0
    min_prospect_value: Optional[float] = None  # -1.0 to 1.0
    require_signal_valid: Optional[bool] = None
    require_direction: Optional[bool] = None
    cooldown_period: Optional[int] = None  # seconds
    position_size_pct: Optional[float] = None  # 0.0-1.0
    stop_loss_pct: Optional[float] = None  # 0.0-0.1
    take_profit_mult: Optional[float] = None  # 1.0-5.0
    enable_bootstrap: Optional[bool] = None
    bootstrap_trades: Optional[int] = None  # 1-20
    max_positions: Optional[int] = None  # 1-10
    # New signal parameters
    tsmom_percentile: Optional[float] = None  # 0.0-0.95
    cooldown_hours: Optional[int] = None  # 0-24 hours
    regime_1_threshold: Optional[int] = None  # 0-100
    regime_2_threshold: Optional[int] = None  # 0-100
    regime_3_threshold: Optional[int] = None  # 0-100
    regime_4_threshold: Optional[int] = None  # 0-100
    regime_5_threshold: Optional[int] = None  # 0-100
    min_ofi_clean: Optional[float] = None  # -4.0 to 1.0
    min_mrr_rho: Optional[float] = None  # -1.0-1.0
    min_co_value: Optional[float] = None  # -1.0-1.0
    min_asymmetric_sharpe: Optional[float] = None  # -2.0-5.0
    min_prob_weighted_score: Optional[float] = None  # 0-100
    max_daily_trades: Optional[int] = None  # 1-50


# REST Endpoints

@app.get("/api/v1/state")
async def get_engine_state():
    """Get complete engine state"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    state = trading_engine.get_state()
    state_dict = state.to_dict() if hasattr(state, 'to_dict') else state.__dict__
    # Convert to JSON-safe format (handle inf/nan values)
    safe_state = safe_jsonable(state_dict)
    return JSONResponse(content=safe_state)


@app.get("/api/v1/price")
async def get_current_price():
    """Get current price and spread"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    return {
        "price": trading_engine.execution_layer.current_price,
        "spread": trading_engine.execution_layer.current_spread,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/v1/candles")
async def get_candles(timeframe: str = "1m", limit: int = 100):
    """Get historical candle data for chart"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    # Get candle history from data layer
    logger.info(f"Fetching candles for timeframe: {timeframe}")
    logger.info(f"Available timeframes: {list(trading_engine.data_layer.candle_history.keys())}")
    
    candles_df = trading_engine.data_layer.candle_history.get(timeframe)
    
    if candles_df is None:
        logger.warning(f"No candle data found for timeframe: {timeframe}")
        return {"candles": [], "timeframe": timeframe, "count": 0}
    
    if candles_df.empty:
        logger.warning(f"Candle dataframe is empty for timeframe: {timeframe}")
        return {"candles": [], "timeframe": timeframe, "count": 0}
    
    logger.info(f"Found {len(candles_df)} candles for {timeframe}")
    
    # Get last N candles
    candles_df = candles_df.tail(limit)
    
    # Convert to list of dicts
    candles = []
    for idx, row in candles_df.iterrows():
        try:
            # idx is a datetime object from the DataFrame index
            if isinstance(idx, datetime):
                timestamp = int(idx.timestamp() * 1000)
            elif hasattr(idx, 'timestamp'):
                timestamp = int(idx.timestamp() * 1000)
            else:
                timestamp = 0
                
            candles.append({
                "timestamp": timestamp,
                "open": float(row['open']),
                "high": float(row['high']),
                "low": float(row['low']),
                "close": float(row['close']),
                "volume": float(row.get('volume', 0)),
            })
        except Exception as e:
            logger.error(f"Error converting candle row: {e}, idx type: {type(idx)}")
            continue
    
    logger.info(f"Returning {len(candles)} formatted candles")
    return {
        "candles": candles,
        "timeframe": timeframe,
        "count": len(candles)
    }


@app.get("/api/v1/regime")
async def get_current_regime():
    """Get current market regime"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    regime = trading_engine.regime_layer.get_current_regime()
    return regime.to_dict() if regime else {"error": "No regime data"}


@app.get("/api/v1/signal/latest")
async def get_latest_signal():
    """Get latest trading signal"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    signals = trading_engine.signal_layer.get_signal_history(1)
    if signals:
        return signals[0].to_dict()
    return {"error": "No signals generated yet"}


@app.get("/api/v1/signal/history")
async def get_signal_history(limit: int = 100):
    """Get signal history"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    signals = trading_engine.signal_layer.get_signal_history(limit)
    return [s.to_dict() for s in signals]


@app.get("/api/v1/positions")
async def get_positions():
    """Get open positions"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    positions = trading_engine.execution_layer.get_open_positions()
    return [p.to_dict() for p in positions]


@app.get("/api/v1/trades/history")
async def get_trade_history(limit: int = 100):
    """Get trade history"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    trades = trading_engine.execution_layer.get_closed_trades(limit)
    return [t.to_dict() for t in trades]


@app.get("/api/v1/performance")
async def get_performance_metrics():
    """Get performance analytics"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    metrics = trading_engine.performance_layer.compute_metrics()
    return metrics.to_dict()


@app.get("/api/v1/performance/criteria")
async def get_acceptance_criteria():
    """Get acceptance criteria status"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    criteria = trading_engine.performance_layer.check_acceptance_criteria()
    return criteria


@app.get("/api/v1/risk/state")
async def get_risk_state():
    """Get risk management state"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    state = trading_engine.risk_layer.get_risk_state()
    return state.to_dict()


@app.get("/api/v1/alerts/active")
async def get_active_alerts():
    """Get active alerts"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    alerts = trading_engine.validity_layer.get_active_alerts()
    return [a.to_dict() for a in alerts]


@app.get("/api/v1/alerts/history")
async def get_alert_history(limit: int = 100):
    """Get alert history"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    alerts = trading_engine.validity_layer.get_alert_history(limit)
    return [a.to_dict() for a in alerts]


@app.post("/api/v1/alerts/acknowledge")
async def acknowledge_alert(request: AlertAcknowledgeRequest):
    """Acknowledge an alert"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    success = trading_engine.validity_layer.acknowledge_alert(request.alert_key)
    return {"acknowledged": success}


@app.get("/api/v1/features/latest")
async def get_latest_features():
    """Get latest feature snapshot"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    features = trading_engine.feature_layer.get_latest_features()
    return features.to_dict() if features else {"error": "No features available"}


@app.get("/api/v1/features/history")
async def get_feature_history(limit: int = 100):
    """Get feature history"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    features = trading_engine.feature_layer.get_feature_history(limit)
    return [f.to_dict() for f in features]


@app.get("/api/v1/jump/params")
async def get_jump_params():
    """Get jump-diffusion parameters"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    params = trading_engine.jump_layer.get_params()
    return params.to_dict()


@app.get("/api/v1/jump/events")
async def get_jump_events(limit: int = 10):
    """Get detected jump events"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    events = trading_engine.jump_layer.get_detected_jumps(limit)
    return [e.to_dict() for e in events]


@app.get("/api/v1/microstructure/mrr")
async def get_mrr_estimate():
    """Get MRR microstructure estimate"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    mrr = trading_engine.micro_layer.get_mrr_estimate()
    return mrr.to_dict() if mrr else {"error": "No MRR estimate available"}


@app.get("/api/v1/microstructure/harrvj")
async def get_harrvj_forecast():
    """Get HARRVJ volatility forecast"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    harrvj = trading_engine.micro_layer.get_harrvj_forecast()
    return harrvj.to_dict() if harrvj else {"error": "No HARRVJ forecast available"}


@app.get("/api/v1/prospect/state")
async def get_prospect_state():
    """Get prospect theory state"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    state = trading_engine.prospect_layer.get_state(
        trading_engine.risk_layer.current_equity,
        trading_engine.config.INITIAL_CAPITAL,
        trading_engine.risk_layer.high_water_mark,
    )
    return state.to_dict()


@app.get("/api/v1/dqn/state")
async def get_dqn_state():
    """Get DQN training state"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    return trading_engine.dqn_layer.get_stats()


@app.post("/api/v1/dqn/training")
async def set_dqn_training(request: DQNTrainingRequest):
    """Enable/disable DQN training"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    trading_engine.enable_dqn_training(request.enable)
    return {"training_mode": request.enable}


@app.post("/api/v1/manual-override")
async def manual_override(request: ManualOverrideRequest):
    """Manual override for emergency situations"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    trading_engine.manual_override(request.action)
    return {"action": request.action, "timestamp": datetime.now().isoformat()}


@app.get("/api/v1/trade-diagnostics")
async def get_trade_diagnostics():
    """Get detailed trade decision diagnostics - why trade was or wasn't taken"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    # Use global config to avoid any confusion
    from config.settings import settings as global_config
    
    latest_signal = trading_engine.latest_signal
    
    if not latest_signal:
        return {
            "status": "no_signal",
            "message": "No signal generated yet",
            "checks": [],
            "timestamp": datetime.now().isoformat(),
        }
    
    # Get current settings from global config
    threshold = getattr(global_config, 'DYNAMIC_SIGNAL_THRESHOLD', 0)
    if threshold == 0:
        # Use regime-specific threshold
        regime = getattr(latest_signal, 'regime', 1)
        threshold_map = {1: 70, 2: 999, 3: 80, 4: 85, 5: 999}
        threshold = threshold_map.get(regime, 70)
    
    min_probability = getattr(global_config, 'MIN_SIGNAL_PROBABILITY', 0.5)
    min_prospect = getattr(global_config, 'MIN_PROSPECT_VALUE', 0.0)
    max_positions = getattr(global_config, 'MAX_POSITIONS', 1)
    
    # Build diagnostics
    checks = []
    
    # Check 1: Signal Score
    score = getattr(latest_signal, 'composite_score', 0)
    checks.append({
        "name": "Signal Score",
        "required": f"≥ {threshold}",
        "actual": score,
        "status": "pass" if score >= threshold else "fail",
        "detail": f"Score {score}/105 {'meets' if score >= threshold else 'below'} threshold {threshold}"
    })
    
    # Check 2: Signal Valid Flag
    valid = getattr(latest_signal, 'signal_valid', False)
    require_signal_valid = getattr(global_config, 'REQUIRE_SIGNAL_VALID', True)
    checks.append({
        "name": "Signal Valid",
        "required": "True" if require_signal_valid else "Optional (skipped)",
        "actual": valid,
        "status": "pass" if (valid or not require_signal_valid) else "fail",
        "detail": "Signal internally validated" if valid else ("Signal failed internal validation" if require_signal_valid else "Optional - allowing invalid signals")
    })
    
    # Check 3: Direction (not NEUTRAL)
    direction = getattr(latest_signal, 'direction', 'NEUTRAL')
    has_direction = direction in ['LONG', 'SHORT']
    require_direction = getattr(global_config, 'REQUIRE_DIRECTION', True)
    checks.append({
        "name": "Direction Clear",
        "required": "LONG or SHORT" if require_direction else "Optional (skipped)",
        "actual": direction,
        "status": "pass" if (has_direction or not require_direction) else "fail",
        "detail": f"Signal direction is {direction}" + (" ✓" if has_direction else (" - too neutral" if require_direction else " (optional - allowing NEUTRAL)"))
    })
    
    # Check 4: Probability
    prob = getattr(latest_signal, 'probability_weighted', 0)
    checks.append({
        "name": "Probability",
        "required": f"≥ {min_probability:.0%}",
        "actual": f"{prob:.1%}",
        "status": "pass" if prob >= min_probability else "fail",
        "detail": f"Probability {prob:.1%} {'meets' if prob >= min_probability else 'below'} minimum {min_probability:.0%}"
    })
    
    # Check 5: Prospect Value
    prospect = getattr(latest_signal, 'prospect_value', 0)
    checks.append({
        "name": "Prospect Value",
        "required": f"≥ {min_prospect}",
        "actual": f"{prospect:.3f}",
        "status": "pass" if prospect >= min_prospect else "fail",
        "detail": f"Expected value {prospect:.3f} {'positive' if prospect >= min_prospect else 'negative'}"
    })
    
    # Check 6: Regime Allows Entry
    regime_allows = getattr(latest_signal, 'regime_allows_entry', False)
    checks.append({
        "name": "Regime Allows Entry",
        "required": "True",
        "actual": regime_allows,
        "status": "pass" if regime_allows else "fail",
        "detail": "Market regime permits trading" if regime_allows else "Market regime blocking entry"
    })
    
    # Check 7: Cooldown
    cooldown_active = getattr(latest_signal, 'cooldown_active', False)
    checks.append({
        "name": "Cooldown",
        "required": "Not Active",
        "actual": "Active" if cooldown_active else "Ready",
        "status": "pass" if not cooldown_active else "fail",
        "detail": f"Cooldown {'active - wait' if cooldown_active else 'ready for trade'}"
    })
    
    # Check 8: Max Positions
    open_pos = len(getattr(trading_engine, 'positions', []))
    can_open = open_pos < max_positions
    checks.append({
        "name": "Position Limit",
        "required": f"<{max_positions} open",
        "actual": f"{open_pos} open",
        "status": "pass" if can_open else "fail",
        "detail": f"{open_pos}/{max_positions} positions - {'can open' if can_open else 'limit reached'}"
    })
    
    # Check 9: PSR/DSR (if not in bootstrap)
    bootstrap = getattr(global_config, 'VALIDITY_BOOTSTRAP_ENABLED', True)
    if bootstrap:
        checks.append({
            "name": "PSR/DSR Check",
            "required": "N/A (Bootstrap)",
            "actual": "Skipped",
            "status": "pass",
            "detail": "Bootstrap mode - PSR/DSR validation skipped"
        })
    else:
        # PSR/DSR is calculated during validation runs, not available in real-time trade diagnostics
        checks.append({
            "name": "PSR/DSR Check",
            "required": "≥ 0.50",
            "actual": "N/A (Requires Validation Run)",
            "status": "pass",
            "detail": "PSR/DSR metrics available after 300-trade validation run"
        })
    
    # Overall trade decision
    all_pass = all(c['status'] == 'pass' for c in checks)
    
    return {
        "status": "can_trade" if all_pass else "blocked",
        "can_trade": all_pass,
        "signal_direction": direction,
        "signal_score": score,
        "threshold": threshold,
        "checks": checks,
        "blocking_reasons": [c['name'] for c in checks if c['status'] == 'fail'],
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/v1/settings/threshold")
async def get_threshold():
    """Get current signal threshold settings"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    config = trading_engine.config
    return {
        "dynamic_threshold": getattr(config, 'DYNAMIC_SIGNAL_THRESHOLD', 0),
        "regime_1_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_1', 70),
        "regime_3_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_3', 80),
        "regime_4_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_4', 85),
        "effective_threshold": getattr(config, 'DYNAMIC_SIGNAL_THRESHOLD', 0) if getattr(config, 'DYNAMIC_SIGNAL_THRESHOLD', 0) > 0 else "regime-specific",
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/v1/settings/threshold")
async def update_threshold(request: ThresholdUpdateRequest):
    """Update signal threshold dynamically (0 = use regime-specific)"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    # Validate threshold
    if request.threshold < 0 or request.threshold > 100:
        raise HTTPException(status_code=400, detail="Threshold must be between 0 and 100")
    
    # Update config
    config = trading_engine.config
    config.DYNAMIC_SIGNAL_THRESHOLD = request.threshold
    
    # Also update in the config file for persistence
    try:
        import json
        import os
        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'settings.json')
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                settings = json.load(f)
            settings['DYNAMIC_SIGNAL_THRESHOLD'] = request.threshold
            with open(config_path, 'w') as f:
                json.dump(settings, f, indent=2)
    except Exception as e:
        logger.warning(f"Could not persist threshold to file: {e}")
    
    logger.info(f"[THRESHOLD UPDATE] Dynamic threshold set to: {request.threshold}")
    
    return {
        "success": True,
        "new_threshold": request.threshold,
        "effective_threshold": request.threshold if request.threshold > 0 else "regime-specific",
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/v1/settings")
async def get_all_settings():
    """Get all tunable settings"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    config = trading_engine.config
    
    return {
        "signal_threshold": getattr(config, 'DYNAMIC_SIGNAL_THRESHOLD', 70),
        "min_probability": getattr(config, 'MIN_SIGNAL_PROBABILITY', 0.5),
        "min_prospect_value": getattr(config, 'MIN_PROSPECT_VALUE', 0.0),
        "require_signal_valid": getattr(config, 'REQUIRE_SIGNAL_VALID', True),
        "require_direction": getattr(config, 'REQUIRE_DIRECTION', True),
        "cooldown_period": getattr(config, 'SIGNAL_COOLDOWN_SECONDS', 300),
        "position_size_pct": getattr(config, 'POSITION_SIZE_PCT', 0.1),
        "stop_loss_pct": getattr(config, 'STOP_LOSS_PCT', 0.01),
        "take_profit_mult": getattr(config, 'TAKE_PROFIT_MULT', 2.0),
        "enable_bootstrap": getattr(config, 'VALIDITY_BOOTSTRAP_ENABLED', True),
        "bootstrap_trades": getattr(config, 'BOOTSTRAP_TRADES', 5),
        "max_positions": getattr(config, 'MAX_POSITIONS', 1),
        # New signal parameters
        "tsmom_percentile": getattr(config, 'TSMOM_PERCENTILE_ENTRY', 0.667),
        "cooldown_hours": getattr(config, 'COOLDOWN_HOURS', 4),
        "regime_1_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_1', 70),
        "regime_2_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_2', 75),
        "regime_3_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_3', 80),
        "regime_4_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_4', 85),
        "regime_5_threshold": getattr(config, 'SIGNAL_THRESHOLD_REGIME_5', 90),
        "min_ofi_clean": getattr(config, 'MIN_OFI_CLEAN', 0.01),
        "min_mrr_rho": getattr(config, 'MIN_MRR_RHO', 0.10),
        "min_co_value": getattr(config, 'MIN_CO_VALUE', 0.0),
        "min_asymmetric_sharpe": getattr(config, 'MIN_ASYMMETRIC_SHARPE', 0.5),
        "min_prob_weighted_score": getattr(config, 'MIN_PROB_WEIGHTED_SCORE', 35.0),
        "max_daily_trades": getattr(config, 'MAX_DAILY_TRADES', 5),
        "timestamp": datetime.now().isoformat(),
    }


@app.post("/api/v1/settings")
async def update_all_settings(request: SettingsUpdateRequest):
    """Update all settings dynamically"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    try:
        config = trading_engine.config
        updated = {}
        
        # Update each setting if provided
        if request.signal_threshold is not None:
            config.DYNAMIC_SIGNAL_THRESHOLD = max(0, min(100, request.signal_threshold))
            updated['signal_threshold'] = config.DYNAMIC_SIGNAL_THRESHOLD
        
        if request.min_probability is not None:
            config.MIN_SIGNAL_PROBABILITY = max(0.0, min(1.0, request.min_probability))
            updated['min_probability'] = config.MIN_SIGNAL_PROBABILITY
        
        if request.min_prospect_value is not None:
            config.MIN_PROSPECT_VALUE = max(-5.0, min(5.0, request.min_prospect_value))
            updated['min_prospect_value'] = config.MIN_PROSPECT_VALUE
        
        if request.require_signal_valid is not None:
            config.REQUIRE_SIGNAL_VALID = request.require_signal_valid
            updated['require_signal_valid'] = config.REQUIRE_SIGNAL_VALID
        
        if request.require_direction is not None:
            config.REQUIRE_DIRECTION = request.require_direction
            updated['require_direction'] = config.REQUIRE_DIRECTION
        
        if request.cooldown_period is not None:
            config.SIGNAL_COOLDOWN_SECONDS = max(0, request.cooldown_period)
            updated['cooldown_period'] = config.SIGNAL_COOLDOWN_SECONDS
        
        if request.position_size_pct is not None:
            config.POSITION_SIZE_PCT = max(0.01, min(1.0, request.position_size_pct))
            updated['position_size_pct'] = config.POSITION_SIZE_PCT
        
        if request.stop_loss_pct is not None:
            config.STOP_LOSS_PCT = max(0.001, min(0.1, request.stop_loss_pct))
            updated['stop_loss_pct'] = config.STOP_LOSS_PCT
        
        if request.take_profit_mult is not None:
            config.TAKE_PROFIT_MULT = max(1.0, min(5.0, request.take_profit_mult))
            updated['take_profit_mult'] = config.TAKE_PROFIT_MULT
        
        if request.enable_bootstrap is not None:
            config.VALIDITY_BOOTSTRAP_ENABLED = request.enable_bootstrap
            updated['enable_bootstrap'] = config.VALIDITY_BOOTSTRAP_ENABLED
        
        if request.bootstrap_trades is not None:
            config.BOOTSTRAP_TRADES = max(1, min(20, request.bootstrap_trades))
            updated['bootstrap_trades'] = config.BOOTSTRAP_TRADES
        
        if request.max_positions is not None:
            config.MAX_POSITIONS = max(1, min(10, request.max_positions))
            updated['max_positions'] = config.MAX_POSITIONS
        
        # New signal parameters
        if request.tsmom_percentile is not None:
            config.TSMOM_PERCENTILE_ENTRY = max(0.0, min(0.95, request.tsmom_percentile))
            updated['tsmom_percentile'] = config.TSMOM_PERCENTILE_ENTRY
        
        if request.cooldown_hours is not None:
            config.COOLDOWN_HOURS = max(0, min(24, request.cooldown_hours))
            updated['cooldown_hours'] = config.COOLDOWN_HOURS
        
        if request.regime_1_threshold is not None:
            config.SIGNAL_THRESHOLD_REGIME_1 = max(0, min(100, request.regime_1_threshold))
            updated['regime_1_threshold'] = config.SIGNAL_THRESHOLD_REGIME_1
        
        if request.regime_2_threshold is not None:
            config.SIGNAL_THRESHOLD_REGIME_2 = max(0, min(100, request.regime_2_threshold))
            updated['regime_2_threshold'] = config.SIGNAL_THRESHOLD_REGIME_2
        
        if request.regime_3_threshold is not None:
            config.SIGNAL_THRESHOLD_REGIME_3 = max(0, min(100, request.regime_3_threshold))
            updated['regime_3_threshold'] = config.SIGNAL_THRESHOLD_REGIME_3
        
        if request.regime_4_threshold is not None:
            config.SIGNAL_THRESHOLD_REGIME_4 = max(0, min(100, request.regime_4_threshold))
            updated['regime_4_threshold'] = config.SIGNAL_THRESHOLD_REGIME_4
        
        if request.regime_5_threshold is not None:
            config.SIGNAL_THRESHOLD_REGIME_5 = max(0, min(100, request.regime_5_threshold))
            updated['regime_5_threshold'] = config.SIGNAL_THRESHOLD_REGIME_5
        
        if request.min_ofi_clean is not None:
            config.MIN_OFI_CLEAN = max(-4.0, min(1.0, request.min_ofi_clean))
            updated['min_ofi_clean'] = config.MIN_OFI_CLEAN
        
        if request.min_mrr_rho is not None:
            config.MIN_MRR_RHO = max(-1.0, min(1.0, request.min_mrr_rho))
            updated['min_mrr_rho'] = config.MIN_MRR_RHO
        
        if request.min_co_value is not None:
            config.MIN_CO_VALUE = max(-1.0, min(1.0, request.min_co_value))
            updated['min_co_value'] = config.MIN_CO_VALUE
        
        if request.min_asymmetric_sharpe is not None:
            config.MIN_ASYMMETRIC_SHARPE = max(-2.0, min(5.0, request.min_asymmetric_sharpe))
            updated['min_asymmetric_sharpe'] = config.MIN_ASYMMETRIC_SHARPE
        
        if request.min_prob_weighted_score is not None:
            config.MIN_PROB_WEIGHTED_SCORE = max(0.0, min(100.0, request.min_prob_weighted_score))
            updated['min_prob_weighted_score'] = config.MIN_PROB_WEIGHTED_SCORE
        
        if request.max_daily_trades is not None:
            config.MAX_DAILY_TRADES = max(1, min(50, request.max_daily_trades))
            updated['max_daily_trades'] = config.MAX_DAILY_TRADES
        
        # Persist to file
        try:
            import json
            import os
            config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'config', 'settings.json')
            settings = {}
            if os.path.exists(config_path):
                with open(config_path, 'r') as f:
                    settings = json.load(f)
            settings.update(updated)
            with open(config_path, 'w') as f:
                json.dump(settings, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not persist settings to file: {e}")
        
        logger.info(f"[SETTINGS UPDATE] Updated: {updated}")
        
        return {
            "success": True,
            "updated": updated,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"[SETTINGS ERROR] {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Settings update failed: {str(e)}")


@app.get("/api/v1/candles/{timeframe}")
async def get_candles(timeframe: str, limit: int = 100):
    """Get historical candles"""
    if not trading_engine:
        raise HTTPException(status_code=503, detail="Engine not initialized")
    
    df = trading_engine.data_layer.get_candle_history(timeframe)
    if df.empty:
        return {"error": f"No candles for timeframe {timeframe}"}
    
    return {
        "timeframe": timeframe,
        "data": df.tail(limit).to_dict(orient='records'),
    }


# WebSocket for real-time updates
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        disconnected = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                disconnected.append(connection)
        
        for conn in disconnected:
            self.disconnect(conn)


manager = ConnectionManager()


# Import validation module
from src.validation.validation_backtest import ValidationBacktest, get_validation_backtest

# Validation endpoints
_validation_instance: Optional[ValidationBacktest] = None
_validation_task: Optional[asyncio.Task] = None
_last_validation_result: Optional[Dict] = None
VALIDATION_RESULT_FILE = "/tmp/apex_btc_validation_result.json"

def _load_validation_result_from_file():
    """Load validation result from file on startup"""
    global _last_validation_result
    if os.path.exists(VALIDATION_RESULT_FILE):
        try:
            with open(VALIDATION_RESULT_FILE, 'r') as f:
                _last_validation_result = json.load(f)
                logger.info(f"[VALIDATION] Loaded result from file: {_last_validation_result.get('total_trades')} trades")
        except Exception as e:
            logger.error(f"[VALIDATION] Failed to load result from file: {e}")

# Load result from file on startup
_load_validation_result_from_file()


def _get_validation_instance():
    """Get or create validation backtest instance with settings from file"""
    global _validation_instance
    if _validation_instance is None and trading_engine:
        from src.validation.validation_backtest import create_validation_with_params
        # Load settings from file
        _validation_instance = create_validation_with_params(
            settings_dict=None,
            data_layer=trading_engine.data_layer,
            config=trading_engine.config,
            use_settings_file=True
        )
    return _validation_instance


class ValidationStartRequest(BaseModel):
    """Request to start validation with custom parameters"""
    signal_threshold: Optional[int] = None
    min_probability: Optional[float] = None
    tsmom_percentile: Optional[float] = None
    min_ofi: Optional[float] = None
    min_mrr: Optional[float] = None
    min_co: Optional[float] = None
    cooldown_hours: Optional[int] = None
    use_current_settings: bool = True  # Use settings from dashboard


@app.post("/api/v1/validation/start")
async def start_validation(background_tasks: BackgroundTasks, request: Optional[ValidationStartRequest] = None):
    """
    Start 300-trade validation backtest in background.
    
    Args:
        request: Validation parameters (optional, defaults to dashboard settings)
        
    Returns:
        Status message with estimated duration
    """
    global _validation_task, _last_validation_result, _validation_instance
    
    logger.info("[VALIDATION] === START VALIDATION CALLED ===")
    
    # Delete old validation result files to ensure fresh results
    try:
        if os.path.exists(VALIDATION_RESULT_FILE):
            os.remove(VALIDATION_RESULT_FILE)
            logger.info("[VALIDATION] Deleted old validation result file")
    except Exception as e:
        logger.error(f"[VALIDATION] Failed to delete old result file: {e}")
    
    _last_validation_result = None  # Clear in-memory result
    logger.info("[VALIDATION] Cleared in-memory result")
    
    from src.validation.validation_backtest import ValidationParams, create_validation_with_params
    
    validation = _get_validation_instance()
    if validation is None:
        raise HTTPException(status_code=503, detail="Trading engine not initialized")
    
    if validation.is_running:
        raise HTTPException(status_code=409, detail="Validation already running")
    
    # Use default request if not provided
    if request is None:
        request = ValidationStartRequest(use_current_settings=True)
    
    # Build parameters from request or use current settings
    if request.use_current_settings:
        # ALWAYS reload from settings.json file to get latest changes
        from src.validation.validation_backtest import load_settings_from_file, create_validation_with_params
        
        logger.info("[VALIDATION] Reloading settings from settings.json...")
        file_settings = load_settings_from_file()
        
        # Override with any provided parameters from request
        if request.signal_threshold is not None:
            file_settings['signal_threshold'] = request.signal_threshold
        if request.min_probability is not None:
            file_settings['min_probability'] = request.min_probability
        if request.tsmom_percentile is not None:
            file_settings['tsmom_percentile'] = request.tsmom_percentile
        if request.min_ofi is not None:
            file_settings['min_ofi_clean'] = request.min_ofi
        if request.min_mrr is not None:
            file_settings['min_mrr_rho'] = request.min_mrr
        if request.min_co is not None:
            file_settings['min_co_value'] = request.min_co
        if request.cooldown_hours is not None:
            file_settings['cooldown_hours'] = request.cooldown_hours
        
        # Create new validation instance with updated settings
        _validation_instance = create_validation_with_params(
            settings_dict=file_settings,
            data_layer=trading_engine.data_layer if trading_engine else None,
            config=trading_engine.config if trading_engine else None,
            use_settings_file=False  # Already loaded above
        )
        validation = _validation_instance
        validation.reset_validation()
    else:
        # Use provided parameters directly
        params = ValidationParams()
        if request.signal_threshold is not None:
            params.signal_threshold = request.signal_threshold
        if request.min_probability is not None:
            params.min_probability = request.min_probability
        if request.tsmom_percentile is not None:
            params.tsmom_percentile = request.tsmom_percentile
        if request.min_ofi is not None:
            params.min_ofi = request.min_ofi
        if request.min_mrr is not None:
            params.min_mrr = request.min_mrr
        if request.min_co is not None:
            params.min_co = request.min_co
        if request.cooldown_hours is not None:
            params.cooldown_hours = request.cooldown_hours
        
        validation.params = params
        validation.reset_validation()
    
    def convert_to_python(obj):
        """Convert numpy/pandas types to native Python types"""
        if hasattr(obj, 'item'):  # numpy scalar
            return obj.item()
        elif isinstance(obj, (np.ndarray, pd.Series)):
            return obj.tolist()
        elif isinstance(obj, list):
            return [convert_to_python(x) for x in obj]
        elif isinstance(obj, dict):
            return {k: convert_to_python(v) for k, v in obj.items()}
        return obj
    
    async def run_validation():
        global _last_validation_result
        try:
            result = await validation.run_full_validation()
            _last_validation_result = {
                'total_trades': int(result.total_trades),
                'winning_trades': int(result.winning_trades),
                'losing_trades': int(result.losing_trades),
                'win_rate': float(result.win_rate),
                'profit_factor': float(result.profit_factor),
                'sharpe_ratio': float(result.sharpe_ratio),
                'max_drawdown': float(result.max_drawdown),
                'skewness': float(result.skewness) if result.skewness else 0.0,
                'kurtosis': float(result.kurtosis) if result.kurtosis else 3.0,
                'psr_0': float(result.psr_0),
                'psr_1': float(result.psr_1),
                'passed': bool(result.passed),
                'report': str(result.report),
                'trades': convert_to_python(result.trades),
                'equity_curve': convert_to_python(result.equity_curve),
                'params_used': result.params_used.to_dict() if result.params_used else {},
                'run_timestamp': result.run_timestamp
            }
            # Save to file for persistence
            with open(VALIDATION_RESULT_FILE, 'w') as f:
                json.dump(_last_validation_result, f, default=str)
                logger.info(f"[VALIDATION] Saved result to file: {_last_validation_result.get('total_trades')} trades")
        except Exception as e:
            logger.error(f"Validation failed: {e}")
    
    _validation_task = asyncio.create_task(run_validation())
    
    return {
        "status": "started",
        "message": "300-trade validation started in background",
        "estimated_duration": "2-5 minutes"
    }


@app.get("/api/v1/validation/result")
async def get_validation_result():
    """
    Get last validation result with parameters used.
    
    Returns:
        Complete validation result including metrics, trades, and parameters
    """
    global _last_validation_result
    
    if _last_validation_result is None:
        return {
            "error": "No validation results available. Run validation first.",
            "has_result": False
        }
    
    # Convert numpy types to native Python types for JSON serialization
    result = {}
    for key, value in _last_validation_result.items():
        if hasattr(value, 'item'):  # numpy type
            result[key] = value.item()
        elif isinstance(value, list):
            result[key] = [
                v.item() if hasattr(v, 'item') else v for v in value
            ]
        elif isinstance(value, dict):
            result[key] = {
                k: (v.item() if hasattr(v, 'item') else v) for k, v in value.items()
            }
        else:
            result[key] = value
    
    result['has_result'] = True
    return safe_jsonable(result)


@app.get("/api/v1/validation/trades")
async def get_validation_trades():
    """Get detailed trade list from last validation"""
    global _last_validation_result
    
    if _last_validation_result is None:
        return []
    
    return _last_validation_result.get('trades', [])


@app.get("/api/v1/validation/equity-curve")
async def get_validation_equity_curve():
    """Get equity curve data for charting"""
    global _last_validation_result
    
    if _last_validation_result is None:
        return {"equity": [], "trades": []}
    
    return {
        "equity": _last_validation_result.get('equity_curve', []),
        "trades": list(range(len(_last_validation_result.get('equity_curve', []))))
    }


@app.get("/api/v1/validation/report")
async def get_validation_report():
    """Get formatted validation report text - checks AutoQuant file first"""
    import os
    
    # Check for AutoQuant report file first
    AUTOQUANT_REPORT = "/tmp/apex_btc_validation_report.txt"
    try:
        if os.path.exists(AUTOQUANT_REPORT):
            with open(AUTOQUANT_REPORT, 'r') as f:
                report = f.read()
            if report and len(report) > 100:
                return {"report": report}
    except Exception:
        pass
    
    # Fallback to legacy validation result
    global _last_validation_result
    if _last_validation_result is None:
        return {"report": "No validation results available. Run validation first."}
    
    return {"report": _last_validation_result.get('report', '')}


@app.get("/api/v1/validation/history")
async def get_validation_history():
    """
    Get history of all validation runs.
    
    Returns:
        List of past validation results for comparison
    """
    validation = _get_validation_instance()
    if validation is None:
        return []
    
    history = validation.get_validation_history()
    return [
        {
            'run_timestamp': h.run_timestamp,
            'total_trades': h.total_trades,
            'win_rate': h.win_rate,
            'profit_factor': h.profit_factor,
            'sharpe_ratio': h.sharpe_ratio,
            'psr_0': h.psr_0,
            'max_drawdown': h.max_drawdown,
            'passed': h.passed,
            'params_used': h.params_used.to_dict() if h.params_used else {}
        }
        for h in history
    ]


@app.post("/api/v1/validation/reset")
async def reset_validation():
    """
    Reset validation state for fresh run.
    Clears history and current state.
    """
    validation = _get_validation_instance()
    if validation is None:
        raise HTTPException(status_code=503, detail="Trading engine not initialized")
    
    if validation.is_running:
        raise HTTPException(status_code=409, detail="Cannot reset while validation is running")
    
    validation.reset_validation()
    global _last_validation_result
    _last_validation_result = None
    
    # Delete all validation files
    BACKTEST_STATE_FILE = "/tmp/apex_btc_backtest_state.json"
    BACKTEST_PROGRESS_FILE = "/tmp/apex_btc_backtest_progress.json"
    BACKTEST_RESULT_FILE = "/tmp/apex_btc_backtest_result.json"
    BACKTEST_REPORT_FILE = "/tmp/apex_btc_backtest_report.txt"
    AUTOQUANT_STATE_FILE = "/tmp/apex_btc_autoquant_state.json"
    AUTOQUANT_REPORT_FILE = "/tmp/apex_btc_autoquant_report.txt"
    
    for file in [BACKTEST_STATE_FILE, BACKTEST_PROGRESS_FILE, BACKTEST_RESULT_FILE, BACKTEST_REPORT_FILE, AUTOQUANT_STATE_FILE, AUTOQUANT_REPORT_FILE]:
        try:
            os.remove(file)
            logger.info(f"[VALIDATION] Deleted file: {file}")
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.error(f"[VALIDATION] Failed to delete file {file}: {e}")
    
    return {"status": "reset", "message": "Validation state cleared. Ready for new run."}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket for real-time updates"""
    await manager.connect(websocket)
    
    try:
        while True:
            # Send state update every second
            if trading_engine:
                state = trading_engine.get_state()
                state_dict = state.to_dict() if hasattr(state, 'to_dict') else state.__dict__
                safe_state = safe_jsonable(state_dict)
                await websocket.send_json(safe_state)
            
            await asyncio.sleep(1)
            
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        manager.disconnect(websocket)


async def broadcast_update():
    """Broadcast update to all connected clients"""
    if trading_engine and manager.active_connections:
        state = trading_engine.get_state()
        state_dict = state.to_dict() if hasattr(state, 'to_dict') else state.__dict__
        safe_state = safe_jsonable(state_dict)
        await manager.broadcast(json.dumps(safe_state))
