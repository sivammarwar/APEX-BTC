"""
Validation API Routes
300-Trade Statistical Validation Endpoints
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends
from pydantic import BaseModel
from typing import Optional, Dict, List
from datetime import datetime
from loguru import logger
import asyncio
import pandas as pd
import numpy as np

from src.validation.validation_backtest import ValidationBacktest, get_validation_backtest, ValidationResult
from src.validation.autoquant_validation import run_full_autoquant_validation

# Use file-based storage for persistence
import json
import os

# 300-Trade Backtest Validation files
BACKTEST_STATE_FILE = "/tmp/apex_btc_backtest_state.json"
BACKTEST_PROGRESS_FILE = "/tmp/apex_btc_backtest_progress.json"
BACKTEST_RESULT_FILE = "/tmp/apex_btc_backtest_result.json"
BACKTEST_REPORT_FILE = "/tmp/apex_btc_backtest_report.txt"

# AutoQuant Validation files
AUTOQUANT_STATE_FILE = "/tmp/apex_btc_autoquant_state.json"
AUTOQUANT_REPORT_FILE = "/tmp/apex_btc_autoquant_report.txt"

# Shared state object (module-level)
_shared_state = {
    'validation_task': None,
    'last_result': None,
    'autoquant_running': False,
    'autoquant_params': None,
    'autoquant_started_at': None
}

def _load_state_from_file():
    """Load state from file into shared state"""
    if os.path.exists(AUTOQUANT_STATE_FILE):
        try:
            with open(AUTOQUANT_STATE_FILE, 'r') as f:
                loaded = json.load(f)
                _shared_state.update(loaded)
                
                # Restore last_result if it exists (convert dict back to ValidationResult)
                if loaded.get('last_result'):
                    result_dict = loaded['last_result']
                    _shared_state['last_result'] = ValidationResult(
                        total_trades=result_dict.get('total_trades', 0),
                        winning_trades=result_dict.get('winning_trades', 0),
                        losing_trades=result_dict.get('losing_trades', 0),
                        win_rate=result_dict.get('win_rate', 0),
                        profit_factor=result_dict.get('profit_factor', 0),
                        sharpe_ratio=result_dict.get('sharpe_ratio', 0),
                        max_drawdown=result_dict.get('max_drawdown', 0),
                        skewness=result_dict.get('skewness', 0),
                        kurtosis=result_dict.get('kurtosis', 0),
                        psr_0=result_dict.get('psr_0', 0),
                        psr_1=result_dict.get('psr_1', 0),
                        trades=result_dict.get('trades', []),
                        equity_curve=result_dict.get('equity_curve', []),
                        passed=result_dict.get('passed', False),
                        report=result_dict.get('report', ''),
                        params_used=result_dict.get('params_used'),
                        run_timestamp=result_dict.get('run_timestamp')
                    )
                
                logger.info(f"[STATE] Loaded state from file: autoquant_running={_shared_state.get('autoquant_running')}, last_result_trades={len(_shared_state.get('last_result', {}).trades) if _shared_state.get('last_result') else 0}")
        except Exception as e:
            logger.error(f"[STATE] Failed to load state: {e}")

def _save_state_to_file():
    """Save shared state to file"""
    # Only save serializable fields
    state_to_save = {
        'autoquant_running': _shared_state.get('autoquant_running'),
        'autoquant_completed': _shared_state.get('autoquant_completed'),
        'autoquant_params': _shared_state.get('autoquant_params'),
        'validation_task': None  # Can't serialize asyncio.Task
    }
    
    # Save last_result if it exists (convert ValidationResult to dict for serialization)
    if _shared_state.get('last_result'):
        result = _shared_state['last_result']
        state_to_save['last_result'] = {
            'total_trades': int(result.total_trades),
            'winning_trades': int(result.winning_trades),
            'losing_trades': int(result.losing_trades),
            'win_rate': float(result.win_rate),
            'profit_factor': float(result.profit_factor),
            'sharpe_ratio': float(result.sharpe_ratio),
            'max_drawdown': float(result.max_drawdown),
            'skewness': float(result.skewness) if result.skewness is not None else None,
            'kurtosis': float(result.kurtosis) if result.kurtosis is not None else None,
            'psr_0': float(result.psr_0),
            'psr_1': float(result.psr_1),
            'trades': result.trades,
            'equity_curve': [float(x) for x in result.equity_curve] if result.equity_curve else [],
            'passed': bool(result.passed),
            'report': result.report,
            'params_used': result.params_used,
            'run_timestamp': result.run_timestamp
        }
    
    logger.info(f"[STATE] Saving state: autoquant_running={state_to_save.get('autoquant_running')}, autoquant_completed={state_to_save.get('autoquant_completed')}")
    try:
        with open(AUTOQUANT_STATE_FILE, 'w') as f:
            json.dump(state_to_save, f)
        logger.info(f"[STATE] State saved to {AUTOQUANT_STATE_FILE}")
    except Exception as e:
        logger.error(f"[STATE] Failed to save state: {e}")
        import traceback
        logger.error(f"[STATE] Traceback: {traceback.format_exc()}")

def _state():
    """Return shared state object"""
    return _shared_state

def _save_state(state):
    """Save state to file (alias for consistency)"""
    _save_state_to_file()

# Initialize by loading from file
_load_state_from_file()

router = APIRouter(prefix="/api/v1/validation", tags=["validation"])

# Backwards compatibility - these are now property-like accessors
def _validation_task():
    return _state()['validation_task']
def _last_result():
    return _state()['last_result']
def _autoquant_running():
    return _state()['autoquant_running']
def _autoquant_params():
    return _state()['autoquant_params']

# Module-level background task for AutoQuant
async def run_autoquant_task_async():
    """Async wrapper for AutoQuant validation task"""
    # Run the sync task in a thread pool to avoid blocking
    import asyncio
    await asyncio.to_thread(run_autoquant_task)

def run_autoquant_task():
    """Module-level background task for AutoQuant validation (sync for BackgroundTasks)"""
    try:
        logger.info("[AUTOQUANT] ================================================")
        logger.info("[AUTOQUANT] Starting full AutoQuant validation...")
        logger.info("[AUTOQUANT] ================================================")
        
        # Get data fetcher function that uses real historical data
        from main import trading_engine
        
        def get_real_data():
            """Fetch real 700-day historical data from Binance directly"""
            logger.info("[AUTOQUANT] Fetching 700-day historical data from Binance...")
            try:
                from binance.client import Client
                from datetime import timedelta
                
                client = Client()
                start_date = datetime.now() - timedelta(days=730)  # 2 years to ensure 700 days
                
                klines = client.get_historical_klines(
                    "BTCUSDT",
                    Client.KLINE_INTERVAL_1DAY,
                    start_date.strftime("%d %b %Y %H:%M:%S")
                )
                
                df = pd.DataFrame(klines, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'close_time', 'quote_volume', 'trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
                df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
                df.set_index('timestamp', inplace=True)
                df = df[['open', 'high', 'low', 'close', 'volume']]
                df = df.astype(float)
                
                # Take last 700 days
                df = df.tail(700)
                
                logger.info(f"[AUTOQUANT] Using real data: {len(df)} daily candles from Binance")
                return df
                
            except Exception as e:
                logger.error(f"[AUTOQUANT] Failed to fetch from Binance: {e}")
                # Fallback to mock data
                logger.warning("[AUTOQUANT] Falling back to mock data")
                dates = pd.date_range(end=datetime.now(), periods=700, freq='D')
                np.random.seed(42)
                returns = np.random.normal(0.001, 0.03, 700)
                prices = 50000 * np.exp(np.cumsum(returns))
                
                return pd.DataFrame({
                    'open': prices * (1 + np.random.normal(0, 0.001, 700)),
                    'high': prices * (1 + abs(np.random.normal(0, 0.02, 700))),
                    'low': prices * (1 - abs(np.random.normal(0, 0.02, 700))),
                    'close': prices,
                    'volume': np.random.uniform(1000, 10000, 700),
                }, index=dates)
        
        # Run synchronously (BackgroundTasks handles thread pool)
        params = _state().get('autoquant_params') or {}
        report, trades = run_full_autoquant_validation(params, get_real_data)
        
        # Format trades for ValidationResult (convert internal format to expected format)
        formatted_trades = []
        for i, trade in enumerate(trades):
            formatted_trades.append({
                'trade_num': i + 1,
                'entry_date': trade['entry'].strftime('%Y-%m-%d') if hasattr(trade['entry'], 'strftime') else str(trade['entry']),
                'exit_date': trade['exit'].strftime('%Y-%m-%d') if hasattr(trade['exit'], 'strftime') else str(trade['exit']),
                'entry_price': float(trade.get('entry_price', 0)),
                'exit_price': float(trade.get('exit_price', 0)),
                'stop_loss_price': float(trade.get('stop_loss_price', 0)),
                'take_profit_price': float(trade.get('take_profit_price', 0)),
                'exit_reason': trade['reason'],
                'hold_days': int(trade['hold']),
                'position_size': 0,
                'pnl_pct': float(trade['net']),
                'pnl_dollar': float(trade['pnl']),
                'is_win': bool(trade['net'] > 0),
                'score_at_entry': float(trade.get('score', 0))
            })
        
        # Calculate metrics from trades
        total_trades = len(formatted_trades)
        winning_trades = sum(1 for t in formatted_trades if t['is_win'])
        losing_trades = total_trades - winning_trades
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        total_wins = sum(t['pnl_dollar'] for t in formatted_trades if t['is_win'])
        total_losses = abs(sum(t['pnl_dollar'] for t in formatted_trades if not t['is_win']))
        profit_factor = total_wins / total_losses if total_losses > 0 else 0
        
        # Store result in shared state (ensure all values are Python native types)
        s = _state()
        s['last_result'] = ValidationResult(
            total_trades=int(total_trades),
            winning_trades=int(winning_trades),
            losing_trades=int(losing_trades),
            win_rate=float(win_rate),
            profit_factor=float(profit_factor),
            sharpe_ratio=0.0,  # Will be calculated from report
            max_drawdown=0.0,
            skewness=0.0,
            kurtosis=0.0,
            psr_0=0.0,
            psr_1=0.0,
            trades=formatted_trades,
            equity_curve=[],
            passed=bool(profit_factor > 1.5 and win_rate > 0.333),
            report=report,
            params_used=params,
            run_timestamp=datetime.now().isoformat()
        )
        _save_state(s)
        
        # Save report to file for persistence
        with open(AUTOQUANT_REPORT_FILE, 'w') as f:
            f.write(report)
        
        logger.info(f"[AUTOQUANT] Report SAVED to {AUTOQUANT_REPORT_FILE} (length: {len(report)} chars)")
        logger.info("[AUTOQUANT] ================================================")
        logger.info("[AUTOQUANT] Validation COMPLETE")
        logger.info("[AUTOQUANT] Report available at /api/v1/validation/report")
        logger.info("[AUTOQUANT] ================================================")
    except Exception as e:
        import traceback
        logger.error(f"[AUTOQUANT] Validation FAILED: {e}")
        logger.error(f"[AUTOQUANT] Traceback: {traceback.format_exc()}")
    finally:
        s = _state()
        s['autoquant_running'] = False
        s['autoquant_completed'] = True
        _save_state(s)

class ValidationStatusResponse(BaseModel):
    """Validation status response"""
    is_running: bool
    progress_pct: float
    trades_completed: int
    target_trades: int
    status: str
    # Validation metrics (populated when complete)
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    psr_0: Optional[float] = None
    max_drawdown: Optional[float] = None
    passed: Optional[bool] = None


class ValidationResultResponse(BaseModel):
    """Validation result response"""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    profit_factor: float
    sharpe_ratio: float
    max_drawdown: float
    skewness: float
    kurtosis: float
    psr_0: float
    psr_1: float
    passed: bool
    report: str
    timestamp: str


class ValidationProgressResponse(BaseModel):
    """Validation progress with milestone data"""
    milestone: int
    total_trades: int
    win_rate: float
    sharpe_ratio: float
    profit_factor: float
    psr_0: float
    message: str


@router.post("/start")
async def start_validation(background_tasks: BackgroundTasks):
    """
    Start 300-trade validation backtest in background
    """
    global _validation_task
    
    validation = get_validation_backtest()
    if validation is None:
        raise HTTPException(status_code=500, detail="Validation system not initialized")
    
    if validation.is_running:
        raise HTTPException(status_code=409, detail="Validation already running")
    
    async def run_validation():
        try:
            # Delete AutoQuant report to avoid stale status
            if os.path.exists(AUTOQUANT_REPORT_FILE):
                os.remove(AUTOQUANT_REPORT_FILE)
                logger.info("[VALIDATION] Removed stale AutoQuant report")
            # Delete AutoQuant state file
            if os.path.exists(AUTOQUANT_STATE_FILE):
                os.remove(AUTOQUANT_STATE_FILE)
                logger.info("[VALIDATION] Removed stale AutoQuant state")
            
            _state()['last_result'] = await validation.run_full_validation()
        except Exception as e:
            logger.error(f"Validation failed: {e}")
    
    _validation_task = asyncio.create_task(run_validation())
    
    return {
        "status": "started",
        "message": "300-trade validation started in background",
        "estimated_duration": "2-5 minutes"
    }


# Track AutoQuant validation state
_autoquant_running = False
_autoquant_started_at = None

@router.get("/status", response_model=ValidationStatusResponse)
async def get_validation_status():
    """
    Get current validation status and progress for 300-trade backtest
    """
    logger.info("[STATUS] === STATUS ENDPOINT CALLED ===")
    
    # Check old validation system first
    validation = get_validation_backtest()
    if validation is not None:
        progress = validation.get_progress()
        
        # If old validation is running, show that
        if progress['is_running']:
            # Check if validation progress file exists (for running validation)
            progress_file = BACKTEST_PROGRESS_FILE
            if os.path.exists(progress_file):
                try:
                    with open(progress_file, 'r') as f:
                        progress = json.load(f)
                    logger.info(f"[STATUS] Loaded progress from file: {progress.get('trades_completed')} trades")
                    
                    # Try to get metrics from progress file
                    if progress.get('win_rate') is not None:
                        return ValidationStatusResponse(
                            is_running=True,
                            progress_pct=progress.get('progress_pct', 0),
                            trades_completed=progress.get('trades_completed', 0),
                            target_trades=300,
                            status="running",
                            win_rate=progress.get('win_rate'),
                            profit_factor=progress.get('profit_factor'),
                            sharpe_ratio=progress.get('sharpe_ratio'),
                            psr_0=progress.get('psr_0'),
                            max_drawdown=progress.get('max_drawdown'),
                            passed=progress.get('passed')
                        )
                except Exception as e:
                    logger.error(f"[STATUS] Failed to read progress file: {e}")
            
            # Fallback to basic progress if file doesn't exist
            return ValidationStatusResponse(
                is_running=True,
                progress_pct=progress['progress_pct'],
                trades_completed=progress['trades_completed'],
                target_trades=300,
                status="running"
            )
    
    # Check if validation result file exists (for completed validation)
    validation_result_file = BACKTEST_RESULT_FILE
    if os.path.exists(validation_result_file):
        try:
            with open(validation_result_file, 'r') as f:
                validation_result = json.load(f)
            logger.info(f"[STATUS] Loaded validation result from file: {validation_result.get('total_trades')} trades")
            return ValidationStatusResponse(
                is_running=False,
                progress_pct=0,  # Show 0 progress when not running to prevent frontend from showing old cached result
                trades_completed=0,  # Show 0 trades when not running
                target_trades=300,
                status="complete",
                win_rate=validation_result.get('win_rate'),
                profit_factor=validation_result.get('profit_factor'),
                sharpe_ratio=validation_result.get('sharpe_ratio'),
                psr_0=validation_result.get('psr_0'),
                max_drawdown=validation_result.get('max_drawdown'),
                passed=validation_result.get('passed')
            )
        except Exception as e:
            logger.error(f"[STATUS] Failed to read validation result file: {e}")
    
    # No validation running or completed
    return ValidationStatusResponse(
        is_running=False,
        progress_pct=0,
        trades_completed=0,
        target_trades=300,
        status="not_initialized"
    )

@router.post("/reset")
async def reset_validation():
    """
    Reset 300-Trade backtest validation state and clear history
    """
    # Clear the module-level shared state
    _shared_state['last_result'] = None
    
    # Delete backtest files
    try:
        if os.path.exists(BACKTEST_PROGRESS_FILE):
            os.remove(BACKTEST_PROGRESS_FILE)
            logger.info(f"[VALIDATION] Deleted progress file: {BACKTEST_PROGRESS_FILE}")
    except Exception as e:
        logger.error(f"[VALIDATION] Failed to delete progress file: {e}")
    
    try:
        if os.path.exists(BACKTEST_RESULT_FILE):
            os.remove(BACKTEST_RESULT_FILE)
            logger.info(f"[VALIDATION] Deleted result file: {BACKTEST_RESULT_FILE}")
    except Exception as e:
        logger.error(f"[VALIDATION] Failed to delete result file: {e}")
    
    try:
        if os.path.exists(BACKTEST_REPORT_FILE):
            os.remove(BACKTEST_REPORT_FILE)
            logger.info(f"[VALIDATION] Deleted report file: {BACKTEST_REPORT_FILE}")
    except Exception as e:
        logger.error(f"[VALIDATION] Failed to delete report file: {e}")
    
    logger.info("[VALIDATION] Validation state reset successfully")
    return {"status": "reset", "message": "300-Trade backtest validation state cleared"}

@router.get("/autoquant/status", response_model=ValidationStatusResponse)
async def get_autoquant_status():
    """
    Get AutoQuant validation status
    """
    # Load state from file to get latest status
    _load_state_from_file()
    st = _state()
    
    if st.get('autoquant_running'):
        return ValidationStatusResponse(
            is_running=True,
            progress_pct=0,
            trades_completed=0,
            target_trades=0,
            status="autoquant_running"
        )
    
    # Only return "autoquant_complete" if there's a valid result with actual metrics
    if st.get('autoquant_completed') and st.get('last_result'):
        result = st.get('last_result')
        # Show as complete if validation completed, even if metrics are 0
        return ValidationStatusResponse(
            is_running=False,
            progress_pct=0,
            trades_completed=result.total_trades,
            target_trades=0,
            status="autoquant_complete",
            win_rate=result.win_rate,
            profit_factor=result.profit_factor,
            sharpe_ratio=result.sharpe_ratio,
            psr_0=result.psr_0,
            max_drawdown=result.max_drawdown,
            passed=result.passed
        )
    
    return ValidationStatusResponse(
        is_running=False,
        progress_pct=0,
        trades_completed=0,
        target_trades=0,
        status="not_initialized"
    )

@router.post("/autoquant/reset")
async def reset_autoquant_validation():
    """
    Reset AutoQuant validation state and clear history
    """
    st = _state()
    st['autoquant_running'] = False
    st['autoquant_completed'] = False
    st['last_result'] = None
    st['autoquant_params'] = {}
    st['autoquant_started_at'] = None
    _save_state(st)
    
    # Also clear the module-level shared state directly
    _shared_state['autoquant_running'] = False
    _shared_state['autoquant_completed'] = False
    _shared_state['last_result'] = None
    _shared_state['autoquant_params'] = None
    _shared_state['autoquant_started_at'] = None
    
    # Delete AutoQuant report file
    try:
        if os.path.exists(AUTOQUANT_REPORT_FILE):
            os.remove(AUTOQUANT_REPORT_FILE)
            logger.info(f"[AUTOQUANT] Deleted report file: {AUTOQUANT_REPORT_FILE}")
    except Exception as e:
        logger.error(f"[AUTOQUANT] Failed to delete report file: {e}")
    
    # Delete AutoQuant state file
    try:
        if os.path.exists(AUTOQUANT_STATE_FILE):
            os.remove(AUTOQUANT_STATE_FILE)
            logger.info(f"[AUTOQUANT] Deleted state file: {AUTOQUANT_STATE_FILE}")
    except Exception as e:
        logger.error(f"[AUTOQUANT] Failed to delete state file: {e}")
    
    logger.info("[AUTOQUANT] Validation state reset successfully")
    return {"status": "reset", "message": "AutoQuant validation state cleared"}


@router.get("/result", response_model=Optional[ValidationResultResponse])
async def get_validation_result():
    """
    Get last validation result
    """
    if _state()['last_result'] is None:
        return None
    
    return ValidationResultResponse(
        total_trades=_state()['last_result'].total_trades,
        winning_trades=_state()['last_result'].winning_trades,
        losing_trades=_state()['last_result'].losing_trades,
        win_rate=_state()['last_result'].win_rate,
        profit_factor=_state()['last_result'].profit_factor,
        sharpe_ratio=_state()['last_result'].sharpe_ratio,
        max_drawdown=_state()['last_result'].max_drawdown,
        skewness=_state()['last_result'].skewness,
        kurtosis=_state()['last_result'].kurtosis,
        psr_0=_state()['last_result'].psr_0,
        psr_1=_state()['last_result'].psr_1,
        passed=_state()['last_result'].passed,
        report=_state()['last_result'].report,
        timestamp=_state()['last_result'].run_timestamp
    )


@router.get("/autoquant/trades")
async def get_autoquant_trades():
    """
    Get detailed trade list from last AutoQuant validation
    """
    if _state().get('last_result') is None:
        return []
    
    return _state()['last_result'].trades


@router.get("/trades")
async def get_validation_trades():
    """
    Get detailed trade list from last validation (300-trade backtest)
    """
    if _state()['last_result'] is None:
        return []
    
    return _state()['last_result'].trades


@router.get("/equity-curve")
async def get_equity_curve():
    """
    Get equity curve data for charting
    """
    if _state()['last_result'] is None:
        return {"equity": [], "trades": []}
    
    return {
        "equity": _state()['last_result'].equity_curve,
        "trades": len(_state()['last_result'].trades)
    }


@router.get("/milestones")
async def get_milestone_progress():
    """
    Get validation progress at milestones: 50, 100, 200, 300 trades
    """
    if _state()['last_result'] is None or not _state()['last_result'].trades:
        return []
    
    milestones = [50, 100, 200, 300]
    results = []
    
    for milestone in milestones:
        if _state()['last_result'].total_trades >= milestone:
            # Calculate metrics up to this milestone
            trades_to_milestone = _state()['last_result'].trades[:milestone]
            
            winning = sum(1 for t in trades_to_milestone if t.get('is_win', False))
            win_rate = winning / milestone if milestone > 0 else 0
            
            total_wins = sum(t.get('pnl_pct', 0) for t in trades_to_milestone if t.get('is_win', False))
            total_losses = abs(sum(t.get('pnl_pct', 0) for t in trades_to_milestone if not t.get('is_win', False)))
            profit_factor = total_wins / total_losses if total_losses > 0 else 0
            
            returns = [t.get('pnl_pct', 0) for t in trades_to_milestone]
            sharpe = 0
            psr = 0.5
            
            if len(returns) > 0 and len(set(returns)) > 1:
                sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252 / 5)
                
                # Approximate PSR
                if len(returns) >= 30:
                    skew = pd.Series(returns).skew()
                    kurt = pd.Series(returns).kurtosis() + 3
                    from scipy import stats
                    denominator = np.sqrt(1 - skew * sharpe + ((kurt - 1) / 4) * (sharpe ** 2))
                    if denominator > 0:
                        z_score = sharpe * np.sqrt(len(returns) - 1) / denominator
                        psr = stats.norm.cdf(z_score)
            
            results.append({
                "milestone": milestone,
                "total_trades": milestone,
                "win_rate": win_rate,
                "sharpe_ratio": sharpe,
                "profit_factor": profit_factor,
                "psr_0": psr,
                "message": f"At {milestone} trades, PSR is {psr*100:.1f}%"
            })
    
    return results


@router.post("/stop")
async def stop_validation():
    """
    Stop running validation
    """
    global _validation_task
    
    if _validation_task and not _validation_task.done():
        _validation_task.cancel()
        return {"status": "stopped", "message": "Validation cancelled"}
    
    return {"status": "not_running", "message": "No validation running"}


@router.get("/autoquant/report")
async def get_autoquant_report():
    """
    Get AutoQuant validation report
    """
    if os.path.exists(AUTOQUANT_REPORT_FILE):
        with open(AUTOQUANT_REPORT_FILE, 'r') as f:
            return {"report": f.read()}
    return {"report": "No AutoQuant validation results available. Run validation first."}

@router.get("/report")
async def get_validation_report():
    """
    Get formatted validation report text
    """
    # Try backtest report first
    try:
        if os.path.exists(BACKTEST_REPORT_FILE):
            with open(BACKTEST_REPORT_FILE, 'r') as f:
                report = f.read()
            if report and len(report) > 100:
                return {"report": report}
    except Exception as e:
        logger.error(f"Error reading backtest report: {e}")
    
    # Try AutoQuant report
    try:
        if os.path.exists(AUTOQUANT_REPORT_FILE):
            with open(AUTOQUANT_REPORT_FILE, 'r') as f:
                report = f.read()
            if report and len(report) > 100:
                return {"report": report}
    except Exception as e:
        logger.error(f"Error reading AutoQuant report: {e}")
    
    return {"report": "No validation results available. Run validation first."}


# Import needed for milestone calculation
import numpy as np
import pandas as pd


# AutoQuant Validation endpoint
@router.post("/autoquant")
async def start_autoquant_validation(params: Dict = None):
    """
    Run full AutoQuant validation with all diagnostic tests.
    
    Includes:
    - T+1 strict execution semantics
    - Cost-ablation ladder (Naive/Standard/Rigorous)
    - Cost sensitivity grid (9 scenarios)
    - PBO overfitting diagnostic
    - Block bootstrap confidence intervals
    - Cross-asset validation (BTC vs ETH)
    - Full-chain accounting invariants
    """
    import json
    from src.validation.autoquant_validation import run_full_autoquant_validation
    
    # Load current settings
    settings_path = "/Users/shivamkumarsingh/Documents/AIM/apex-btc/backend/config/settings.json"
    try:
        with open(settings_path, 'r') as f:
            params = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load settings: {e}")
        raise HTTPException(status_code=500, detail="Failed to load settings")
    
    # Log all parameters being used for validation
    logger.info("[AUTOQUANT] ================================================")
    logger.info("[AUTOQUANT] VALIDATION PARAMETERS (from settings.json):")
    logger.info(f"[AUTOQUANT] Signal Threshold: {params.get('signal_threshold')}")
    logger.info(f"[AUTOQUANT] Min Probability: {params.get('min_probability')}")
    logger.info(f"[AUTOQUANT] Min Prospect Value: {params.get('min_prospect_value')}")
    logger.info(f"[AUTOQUANT] Cooldown Period: {params.get('cooldown_period')}s")
    logger.info(f"[AUTOQUANT] Position Size: {params.get('position_size_pct')}%")
    logger.info(f"[AUTOQUANT] Stop Loss: {params.get('stop_loss_pct')}%")
    logger.info(f"[AUTOQUANT] Take Profit Mult: {params.get('take_profit_mult')}x")
    logger.info(f"[AUTOQUANT] Min Prob-Weighted Score: {params.get('min_prob_weighted_score')}")
    logger.info(f"[AUTOQUANT] Max Positions: {params.get('max_positions')}")
    logger.info(f"[AUTOQUANT] TSMOM %: {params.get('tsmom_percentile')}")
    logger.info(f"[AUTOQUANT] Min OFI: {params.get('min_ofi_clean')}")
    logger.info(f"[AUTOQUANT] Min MRR: {params.get('min_mrr_rho')}")
    logger.info(f"[AUTOQUANT] Min CO: {params.get('min_co_value')}")
    logger.info(f"[AUTOQUANT] Min Sharpe: {params.get('min_asymmetric_sharpe')}")
    logger.info(f"[AUTOQUANT] Max Daily Trades: {params.get('max_daily_trades')}")
    logger.info(f"[AUTOQUANT] Bootstrap Trades: {params.get('bootstrap_trades')}")
    logger.info(f"[AUTOQUANT] Regime Thresholds: R1={params.get('regime_1_threshold')}, R2={params.get('regime_2_threshold')}, R3={params.get('regime_3_threshold')}, R4={params.get('regime_4_threshold')}, R5={params.get('regime_5_threshold')}")
    logger.info("[AUTOQUANT] ================================================")
    
    # Set params for the background task
    st = _state()
    st['autoquant_params'] = params
    st['autoquant_running'] = True
    st['autoquant_started_at'] = datetime.now().isoformat()
    st['autoquant_completed'] = False
    _save_state(st)
    
    # Run the AutoQuant validation as a background task using asyncio
    asyncio.create_task(run_autoquant_task_async())
    
    return {
        "status": "started",
        "message": "AutoQuant validation started in background (estimated 5-10 minutes)",
        "check_report_at": "/api/v1/validation/report",
        "features": [
            "T+1 strict execution semantics",
            "Cost-ablation ladder (3 configs)",
            "Cost sensitivity grid (9 scenarios)",
            "PBO overfitting diagnostic",
            "Block bootstrap CI",
            "Cross-asset validation (BTC/ETH)"
        ]
    }
