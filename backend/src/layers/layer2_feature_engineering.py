"""
Layer 2: Feature Engineering
Transform OHLCV into alpha signals across 8 families
"""
import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass
from collections import deque
from loguru import logger
from scipy import stats
from sklearn.decomposition import PCA
try:
    import statsmodels.api as sm
    STATSMODELS_AVAILABLE = True
except (ImportError, TypeError):
    STATSMODELS_AVAILABLE = False


@dataclass
class FeatureSnapshot:
    """Complete feature snapshot at a point in time"""
    symbol: str = ""
    timestamp: datetime = None
    
    # TSMOM (Han et al. 2026)
    tsmom_rank: float = 0.0
    co_value: float = 0.0  # Continuing Overreaction
    
    # Volatility (Pichl & Kaizoji 2017)
    rv_daily: float = 0.0
    bv_daily: float = 0.0
    jump_component: float = 0.0
    harrvj_forecast: float = 0.0
    atr_harrvj: float = 0.0
    
    # Microstructure (Dimpfl 2017)
    mrr_theta: float = 0.0
    mrr_rho: float = 0.0
    mrr_spread: float = 0.0
    adverse_selection_pct: float = 0.463
    
    # Technical
    ema_21: float = 0.0
    ema_200: float = 0.0
    ema_slope_200: float = 0.0
    adx: float = 0.0
    rsi_30: float = 50.0
    bb_width: float = 0.0
    obv: float = 0.0
    macd_line: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0
    stoch_rsi: float = 50.0
    
    # Mean Reversion (Avellaneda & Lee 2010)
    s_score: float = 0.0
    mean_reversion_speed: float = 0.0
    cointegration_residual: float = 0.0
    
    # PCA Factors
    pca_factor_1: float = 0.0
    pca_factor_2: float = 0.0
    pca_factor_3: float = 0.0
    
    # Order Flow
    ofi_clean: float = 0.0
    ofi_raw: float = 0.0
    order_flow_autocorr: float = 0.0
    volume_profile_poc: float = 0.0
    algo_slicing_detected: bool = False
    
    # Liquidity (Dimpfl 2017)
    liquidity_score: float = 1.0
    spread_invariance_zscore: float = 0.0
    
    # Jump-Diffusion (Han et al. 2026)
    jump_mu: float = 0.005
    jump_sigma: float = 0.032
    jump_nu: float = 0.051
    jump_delta: float = 0.394
    jump_lambda: float = 0.016
    
    def to_dict(self) -> Dict:
        return {
            'symbol': self.symbol,
            'timestamp': self.timestamp.isoformat(),
            'tsmom_rank': self.tsmom_rank,
            'co_value': self.co_value,
            'rv_daily': self.rv_daily,
            'bv_daily': self.bv_daily,
            'jump_component': self.jump_component,
            'harrvj_forecast': self.harrvj_forecast,
            'atr_harrvj': self.atr_harrvj,
            'mrr_theta': self.mrr_theta,
            'mrr_rho': self.mrr_rho,
            'mrr_spread': self.mrr_spread,
            'adverse_selection_pct': self.adverse_selection_pct,
            'ema_21': self.ema_21,
            'ema_200': self.ema_200,
            'ema_slope_200': self.ema_slope_200,
            'adx': self.adx,
            'rsi_30': self.rsi_30,
            'bb_width': self.bb_width,
            'obv': self.obv,
            'macd_line': self.macd_line,
            'macd_signal': self.macd_signal,
            'macd_hist': self.macd_hist,
            'stoch_rsi': self.stoch_rsi,
            's_score': self.s_score,
            'mean_reversion_speed': self.mean_reversion_speed,
            'pca_factor_1': self.pca_factor_1,
            'pca_factor_2': self.pca_factor_2,
            'pca_factor_3': self.pca_factor_3,
            'ofi_clean': self.ofi_clean,
            'ofi_raw': self.ofi_raw,
            'order_flow_autocorr': self.order_flow_autocorr,
            'volume_profile_poc': self.volume_profile_poc,
            'algo_slicing_detected': self.algo_slicing_detected,
            'liquidity_score': self.liquidity_score,
            'spread_invariance_zscore': self.spread_invariance_zscore,
            'jump_mu': self.jump_mu,
            'jump_sigma': self.jump_sigma,
            'jump_nu': self.jump_nu,
            'jump_delta': self.jump_delta,
            'jump_lambda': self.jump_lambda,
        }


class FeatureEngineeringLayer:
    """
    Layer 2: Feature Engineering
    Computes all 8 families of features from raw data
    """
    
    def __init__(self, config, data_layer):
        self.config = config
        self.data_layer = data_layer
        
        # Feature storage
        self.feature_history: deque = deque(maxlen=1000)
        self.pca_model: Optional[PCA] = None
        self.pca_asset_returns: pd.DataFrame = pd.DataFrame()
        
        # Rolling windows for calculations
        self._hourly_volumes_30d: deque = deque(maxlen=30*24)
        self._daily_5min_returns: deque = deque(maxlen=288)  # One day
        
        # HARRVJ state
        self._rv_history: deque = deque(maxlen=30)
        self._jump_history: deque = deque(maxlen=30)
        
        # MRR state
        self._tick_directions: deque = deque(maxlen=500)
        self._tick_prices: deque = deque(maxlen=500)
        
        # Algo slicing detection
        self._recent_volumes: deque = deque(maxlen=60)
        
        logger.info("Layer 2 initialized")
        
    def on_candle(self, candle) -> FeatureSnapshot:
        """Process new candle and compute all features"""
        snapshot = FeatureSnapshot(
            symbol=candle.symbol,
            timestamp=candle.timestamp,
        )
        
        # Get data buffers
        tf_buffers = self.data_layer.get_candle_buffer('1h')
        
        if not tf_buffers or not tf_buffers.get('close'):
            return snapshot
            
        closes = np.array(list(tf_buffers['close']))
        highs = np.array(list(tf_buffers['high']))
        lows = np.array(list(tf_buffers['low']))
        volumes = np.array(list(tf_buffers['volume']))
        
        # Ensure volumes is a proper array, not a scalar
        if volumes.ndim == 0 or len(volumes) == 0:
            volumes = np.ones_like(closes)
        
        if len(closes) < 50:
            return snapshot
            
        # 1. Trend & Momentum Features (Han et al. 2026)
        try:
            self._compute_tsmom_features(snapshot, closes, volumes)
        except Exception as e:
            logger.warning(f"TSMOM features error: {e}")
        
        # 2. Technical Indicators
        try:
            self._compute_technical_features(snapshot, closes, highs, lows, volumes)
        except Exception as e:
            logger.warning(f"Technical features error: {e}")
        
        # 3. Volatility Features (Pichl & Kaizoji 2017)
        try:
            self._compute_volatility_features(snapshot, closes, highs, lows)
        except Exception as e:
            logger.warning(f"Volatility features error: {e}")
        
        # 4. Mean Reversion (Avellaneda & Lee 2010)
        try:
            self._compute_mean_reversion_features(snapshot)
        except Exception as e:
            logger.warning(f"Mean reversion features error: {e}")
        
        # 5. Order Flow (Dimpfl 2017 + Pichl & Kaizoji 2017)
        try:
            self._compute_order_flow_features(snapshot)
        except Exception as e:
            logger.warning(f"Order flow features error: {e}")
        
        # 6. Liquidity (Dimpfl 2017)
        try:
            self._compute_liquidity_features(snapshot, candle.timestamp)
        except Exception as e:
            logger.warning(f"Liquidity features error: {e}")
        
        # 7. Jump-Diffusion (Han et al. 2026)
        try:
            self._compute_jump_diffusion_params(snapshot)
        except Exception as e:
            logger.warning(f"Jump diffusion features error: {e}")
        
        # Store
        self.feature_history.append(snapshot)
        
        return snapshot
        
    def on_tick(self, tick):
        """Process tick for MRR model"""
        self._tick_directions.append(tick.direction)
        self._tick_prices.append(tick.price)
        self._recent_volumes.append(tick.quantity)
        
    def _compute_tsmom_features(self, snapshot: FeatureSnapshot, closes: np.ndarray, volumes: np.ndarray):
        """Compute TSMOM rank and CO factor (Han et al. 2026)"""
        # Get daily returns for TSMOM
        daily_returns = self.data_layer.get_daily_returns()
        
        logger.info(f"[TSMOM_DEBUG] daily_returns length: {len(daily_returns)}, required: {self.config.TSMOM_LOOKBACK + 1}")
        
        if len(daily_returns) < self.config.TSMOM_LOOKBACK + 1:
            logger.warning(f"[TSMOM_DEBUG] Not enough data! Have {len(daily_returns)}, need {self.config.TSMOM_LOOKBACK + 1}")
            return
            
        # Current 28-day return
        current_return = (closes[-1] / closes[-min(28, len(closes))]) - 1
        
        # Percentile rank vs historical
        historical_28d = []
        for i in range(len(daily_returns) - self.config.TSMOM_LOOKBACK):
            ret_28d = (daily_returns.iloc[i + self.config.TSMOM_LOOKBACK] / daily_returns.iloc[i]) - 1
            historical_28d.append(ret_28d)
            
        if historical_28d:
            snapshot.tsmom_rank = stats.percentileofscore(historical_28d, current_return) / 100.0
            logger.info(f"[TSMOM_DEBUG] Calculated tsmom_rank={snapshot.tsmom_rank:.4f}, current_return={current_return:.4f}, historical_count={len(historical_28d)}")
        else:
            logger.warning(f"[TSMOM_DEBUG] No historical 28d data! historical_28d is empty")
            
        # CO (Continuing Overreaction) - 21 days
        if len(daily_returns) >= 21:
            daily_rets = daily_returns.tail(21).values
            # Safely handle volumes - ensure it's an array with proper length
            if isinstance(volumes, np.ndarray) and len(volumes) >= 21:
                daily_vols = volumes[-21:]
            else:
                daily_vols = np.ones(21)
            
            co_sum = 0.0
            weight_sum = 0.0
            vol_sum = 0.0
            
            for j, (ret, vol) in enumerate(zip(daily_rets, daily_vols)):
                weight = 21 - j
                co_sum += weight * np.sign(ret) * vol
                vol_sum += vol
                
            if vol_sum > 0:
                snapshot.co_value = co_sum / (vol_sum / 21)
                
    def _compute_technical_features(self, snapshot: FeatureSnapshot, closes: np.ndarray, 
                                     highs: np.ndarray, lows: np.ndarray, volumes: np.ndarray):
        """Compute standard technical indicators"""
        n = len(closes)
        
        # EMAs
        ema_9_series = self._ema(closes, 9)
        ema_21_series = self._ema(closes, 21)
        ema_200_series = self._ema(closes, 200)
        
        # Check if EMA results are arrays
        if (isinstance(ema_9_series, np.ndarray) and isinstance(ema_21_series, np.ndarray) and
            len(ema_9_series) > 0 and len(ema_21_series) > 0):
            snapshot.price_to_ema9 = (closes[-1] / ema_9_series[-1]) - 1
            snapshot.price_to_ema21 = (closes[-1] / ema_21_series[-1]) - 1
            snapshot.ema9_above_21 = ema_9_series[-1] > ema_21_series[-1]
        
        if isinstance(ema_200_series, np.ndarray) and len(ema_200_series) > 10:
            snapshot.ema_slope_200 = (ema_200_series[-1] / ema_200_series[-10]) - 1
            
        # RSI (30-day)
        snapshot.rsi_30 = self._rsi(closes, 30)
        
        # ADX
        snapshot.adx = self._adx(highs, lows, closes, 14)
        
        # Bollinger Band Width
        bb_upper, bb_lower = self._bollinger_bands(closes, 20, 2.0)
        # Check if BB results are arrays/scalars
        if isinstance(bb_upper, np.ndarray) and isinstance(bb_lower, np.ndarray):
            if len(bb_upper) > 0 and len(bb_lower) > 0:
                bb_middle = (bb_upper[-1] + bb_lower[-1]) / 2
                if bb_middle > 0:
                    snapshot.bb_width = (bb_upper[-1] - bb_lower[-1]) / bb_middle * 100
        else:
            # Handle scalar case
            bb_middle = (bb_upper + bb_lower) / 2
            if bb_middle > 0:
                snapshot.bb_width = (bb_upper - bb_lower) / bb_middle * 100
            
        # OBV
        snapshot.obv = self._obv(closes, volumes)
        
        # MACD
        macd_line, macd_signal, macd_hist = self._macd(closes, 12, 26, 9)
        # Check if results are arrays before calling len()
        if (isinstance(macd_line, np.ndarray) and isinstance(macd_signal, np.ndarray) and 
            isinstance(macd_hist, np.ndarray) and
            len(macd_line) > 0 and len(macd_signal) > 0 and len(macd_hist) > 0):
            snapshot.macd_line = float(macd_line[-1])
            snapshot.macd_signal = float(macd_signal[-1])
            snapshot.macd_hist = float(macd_hist[-1]) if len(macd_hist) > 0 else 0
        
        # Stochastic RSI
        snapshot.stoch_rsi = self._stochastic_rsi(closes, 14, 14, 3, 3)
        
        # Volume Profile POC (Point of Control)
        if isinstance(volumes, np.ndarray) and len(volumes) >= 24:
            snapshot.volume_profile_poc = np.average(closes[-24:], weights=volumes[-24:])
            
    def _compute_volatility_features(self, snapshot: FeatureSnapshot, closes: np.ndarray,
                                       highs: np.ndarray, lows: np.ndarray):
        """Compute HARRVJ volatility features (Pichl & Kaizoji 2017)"""
        # 5-minute realized volatility
        if len(closes) >= 2:
            returns = np.diff(np.log(closes))
            
            # Daily RV from intraday returns (if 5-min bars)
            rv = np.sum(returns**2)
            snapshot.rv_daily = rv
            
            # Bipower variation
            bv = (np.pi / 2) * (len(returns) / (len(returns) - 1)) * np.sum(np.abs(returns[1:]) * np.abs(returns[:-1]))
            snapshot.bv_daily = bv
            
            # Jump component
            snapshot.jump_component = max(rv - bv, 0)
            
            # Store for HARRVJ
            self._rv_history.append(rv)
            self._jump_history.append(snapshot.jump_component)
            
            # HARRVJ forecast
            snapshot.harrvj_forecast = self._harrvj_forecast()
            
        # ATR using HARRVJ volatility
        if len(highs) >= 14:
            atr = self._atr(highs, lows, closes, 14)
            if snapshot.harrvj_forecast > 0:
                # Scale ATR by HARRVJ forecast
                vol_scalar = np.sqrt(snapshot.harrvj_forecast * 252) / (np.std(np.diff(np.log(closes[-20:]))) * np.sqrt(252) if len(closes) >= 21 else 0.5)
                snapshot.atr_harrvj = atr * max(0.5, min(vol_scalar, 2.0))
            else:
                snapshot.atr_harrvj = atr
                
    def _harrvj_forecast(self) -> float:
        """HARRVJ volatility forecast (Pichl & Kaizoji 2017)"""
        b = self.config.HARRVJ_BETA
        
        if len(self._rv_history) < 11 or len(self._jump_history) < 11:
            return 0.0
            
        rv_list = list(self._rv_history)
        j_list = list(self._jump_history)
        
        sqrt_rv_t = np.sqrt(rv_list[-1])
        sqrt_rv_t5 = np.sqrt(rv_list[-6]) if len(rv_list) >= 6 else sqrt_rv_t
        sqrt_rv_t10 = np.sqrt(rv_list[-11]) if len(rv_list) >= 11 else sqrt_rv_t5
        
        sqrt_j_t5 = np.sqrt(max(j_list[-6], 0)) if len(j_list) >= 6 else 0
        sqrt_j_t10 = np.sqrt(max(j_list[-11], 0)) if len(j_list) >= 11 else sqrt_j_t5
        
        sqrt_rv_forecast = (
            b['beta0'] + 
            b['beta1'] * sqrt_rv_t +
            b['beta2'] * sqrt_rv_t5 +
            b['beta3'] * sqrt_rv_t10 +
            b['beta5'] * sqrt_j_t5 +
            b['beta6'] * sqrt_j_t10
        )
        
        # Annualized volatility
        return np.sqrt(max(sqrt_rv_forecast**2 * 252, 0))
        
    def _compute_order_flow_features(self, snapshot: FeatureSnapshot):
        """Compute order flow features with algo slicing filter"""
        if len(self._tick_directions) < 100:
            return
            
        directions = np.array(list(self._tick_directions)[-200:])
        
        # Order flow autocorrelation (MRR confirmation)
        if len(directions) >= 2:
            corr = np.corrcoef(directions[1:], directions[:-1])[0, 1]
            snapshot.order_flow_autocorr = corr if not np.isnan(corr) else 0.0
            
        # OFI with algo slicing detection
        if len(self._recent_volumes) >= 60:
            volumes_60s = list(self._recent_volumes)[-60:]
            
            # Algo slicing detection (Pichl & Kaizoji 2017)
            integer_volumes = [1.0, 2.0, 3.0, 5.0, 10.0]
            tolerance = 0.001
            
            n_integer = sum(
                1 for v in volumes_60s 
                if any(abs(v - iv) < tolerance for iv in integer_volumes)
            )
            
            if len(volumes_60s) > 0:
                algo_fraction = n_integer / len(volumes_60s)
                snapshot.algo_slicing_detected = algo_fraction > 0.40
                
            # Clean OFI
            if not snapshot.algo_slicing_detected:
                ofi_sum = 0.0
                vol_sum = 0.0
                for d, v in zip(directions[-60:], volumes_60s):
                    ofi_sum += d * v
                    vol_sum += v
                if vol_sum > 0:
                    snapshot.ofi_clean = ofi_sum / vol_sum
                    
    def _compute_mean_reversion_features(self, snapshot: FeatureSnapshot):
        """Compute s-score and mean reversion parameters (Avellaneda & Lee 2010)"""
        # Update PCA if needed
        if self.pca_model is None or len(self.feature_history) % 24 == 0:
            self._update_pca()
            
        # Compute s-score from residual
        if len(self.feature_history) >= 30:
            residuals = [f.cointegration_residual for f in self.feature_history if f.cointegration_residual != 0]
            if len(residuals) >= 30:
                X = np.array(residuals[-30:-1])
                X_next = np.array(residuals[-29:])
                
                # AR(1) regression
                X_design = np.column_stack([np.ones(len(X)), X])
                beta = np.linalg.lstsq(X_design, X_next, rcond=None)[0]
                a, b = beta[0], beta[1]
                
                # Calculate half-life
                if b >= 1 or b <= 0:
                    return
                
                lambda_ou = -np.log(b)
                half_life = np.log(2) / lambda_ou
                
                if half_life < 0.5 or half_life > 30:
                    return
                
                # Compute residuals for sigma_eq
                y_pred = X_design @ beta
                resid = X_next - y_pred
                sigma_resid = np.std(resid, ddof=1)
                
                if sigma_resid == 0 or (1 - b**2) <= 0:
                    return
                
                sigma_eq = sigma_resid / np.sqrt(1 - b**2)
                
                m = a / (1 - b)
                s_score = -m / sigma_eq
                snapshot.s_score = s_score
                snapshot.cointegration_residual = residuals[-1]
                
    def _update_pca(self):
        """Update PCA factors from multi-asset data"""
        try:
            # Fetch multi-asset returns - schedule async task
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # We're in an async context, schedule the task
                    future = asyncio.ensure_future(
                        self.data_layer.fetch_multi_asset_data(
                            self.config.PCA_ASSETS,
                            timeframe='1h',
                            limit=self.config.PCA_LOOKBACK
                        )
                    )
                    # For now, skip PCA update if we're in running loop
                    # The proper fix would be to make _update_pca async
                    return
                else:
                    asset_data = loop.run_until_complete(
                        self.data_layer.fetch_multi_asset_data(
                            self.config.PCA_ASSETS,
                            timeframe='1h',
                            limit=self.config.PCA_LOOKBACK
                        )
                    )
            except RuntimeError:
                # No event loop running, create one
                asset_data = asyncio.run(
                    self.data_layer.fetch_multi_asset_data(
                        self.config.PCA_ASSETS,
                        timeframe='1h',
                        limit=self.config.PCA_LOOKBACK
                    )
                )
            
            if asset_data is None or (hasattr(asset_data, 'empty') and asset_data.empty) or len(asset_data) < 50:
                return
                
            # Compute returns
            returns = asset_data.pct_change().dropna()
            if returns.empty:
                return
                
            # Standardize
            standardized = (returns - returns.mean()) / returns.std()
            standardized = standardized.dropna()
            
            if len(standardized) < 50:
                return
                
            # PCA
            pca = PCA(n_components=min(5, len(returns.columns)))
            factors = pca.fit_transform(standardized)
            
            # Create factor DataFrame
            factor_df = pd.DataFrame(
                factors,
                index=standardized.index,
                columns=[f'PC{i+1}' for i in range(factors.shape[1])]
            )
            
            # Store recent factor values
            if len(factor_df) > 0:
                latest_factors = factor_df.iloc[-1]
                
                # Update last snapshot if exists
                if self.feature_history:
                    last = self.feature_history[-1]
                    last.pca_factor_1 = latest_factors[0]
                    last.pca_factor_2 = latest_factors[1] if len(latest_factors) > 1 else 0
                    last.pca_factor_3 = latest_factors[2] if len(latest_factors) > 2 else 0
                    
        except Exception as e:
            logger.warning(f"PCA update failed: {e}")
            
    def _compute_liquidity_features(self, snapshot: FeatureSnapshot, timestamp: datetime):
        """Compute liquidity window score (Dimpfl 2017)"""
        hour_utc = timestamp.hour
        
        # Dimpfl findings: BTC liquidity follows US/European equity hours
        # Peak: 13:00-17:00 UTC (NYSE open): 1.8-2.2x
        # Good: 07:00-12:00 UTC (European open): 1.4-1.8x
        # Avoid: 02:00-06:00 UTC (Asia night): 0.4-0.7x
        
        if 13 <= hour_utc <= 17:
            base_score = np.random.uniform(1.8, 2.2)
        elif 7 <= hour_utc <= 12:
            base_score = np.random.uniform(1.4, 1.8)
        elif 2 <= hour_utc <= 6:
            base_score = np.random.uniform(0.4, 0.7)
        else:
            base_score = 1.0
            
        snapshot.liquidity_score = base_score
        
    def _compute_jump_diffusion_params(self, snapshot: FeatureSnapshot):
        """Estimate jump-diffusion parameters (Han et al. 2026)"""
        daily_returns = self.data_layer.get_daily_returns()
        
        if len(daily_returns) < 60:
            # Use defaults
            snapshot.jump_mu = self.config.JUMP_MU
            snapshot.jump_sigma = self.config.JUMP_SIGMA
            snapshot.jump_nu = self.config.JUMP_NU
            snapshot.jump_delta = self.config.JUMP_DELTA
            snapshot.jump_lambda = self.config.JUMP_LAMBDA
            return
            
        # Simple method of moments estimation
        rets = daily_returns.tail(60).values
        log_rets = np.log(1 + rets)
        
        # Moments
        mean_lr = np.mean(log_rets)
        var_lr = np.var(log_rets)
        skew_lr = stats.skew(log_rets)
        kurt_lr = stats.kurtosis(log_rets, fisher=True)
        
        # Estimate parameters (simplified)
        snapshot.jump_mu = max(mean_lr, 0.001)
        snapshot.jump_sigma = np.sqrt(var_lr)
        snapshot.jump_lambda = max(0.001, min(kurt_lr / 100, 0.1))
        snapshot.jump_nu = skew_lr * 0.1 if not np.isnan(skew_lr) else 0.0
        snapshot.jump_delta = np.sqrt(var_lr * 0.5)
        
    # Technical indicator helpers
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Exponential moving average"""
        alpha = 2.0 / (period + 1)
        ema = np.zeros_like(data)
        ema[0] = data[0]
        for i in range(1, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i-1]
        return ema
        
    def _rsi(self, data: np.ndarray, period: int = 14) -> float:
        """Relative Strength Index"""
        if not isinstance(data, np.ndarray) or data.ndim == 0 or len(data) < period + 1:
            return 50.0
        deltas = np.diff(data)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))
        
    def _atr(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        """Average True Range"""
        if not isinstance(closes, np.ndarray) or closes.ndim == 0 or len(closes) < 2:
            return 0.0
        tr1 = highs[1:] - lows[1:]
        tr2 = np.abs(highs[1:] - closes[:-1])
        tr3 = np.abs(lows[1:] - closes[:-1])
        tr = np.maximum(np.maximum(tr1, tr2), tr3)
        return np.mean(tr[-period:])
        
    def _adx(self, highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        """Average Directional Index"""
        # Check if inputs are valid arrays
        if (not isinstance(closes, np.ndarray) or not isinstance(highs, np.ndarray) or 
            not isinstance(lows, np.ndarray) or closes.ndim == 0 or highs.ndim == 0 or lows.ndim == 0):
            return 20.0
        if len(closes) < period + 1:
            return 20.0
        
        plus_dm = np.where((highs[1:] - highs[:-1]) > (lows[:-1] - lows[1:]), 
                          np.maximum(highs[1:] - highs[:-1], 0), 0)
        minus_dm = np.where((lows[:-1] - lows[1:]) > (highs[1:] - highs[:-1]),
                           np.maximum(lows[:-1] - lows[1:], 0), 0)
        
        tr = np.maximum(highs[1:] - lows[1:], 
                       np.maximum(np.abs(highs[1:] - closes[:-1]),
                                 np.abs(lows[1:] - closes[:-1])))
        
        atr = np.mean(tr[-period:])
        if atr == 0:
            return 20.0
            
        plus_di = 100 * np.mean(plus_dm[-period:]) / atr
        minus_di = 100 * np.mean(minus_dm[-period:]) / atr
        
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di + 1e-10)
        return np.mean(dx) if len(dx) > 0 else 20.0
        
    def _bollinger_bands(self, data: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Tuple[float, float]:
        """Bollinger Bands"""
        if not isinstance(data, np.ndarray) or data.ndim == 0 or len(data) < period:
            if isinstance(data, np.ndarray) and len(data) > 0:
                return float(data[-1]) * 1.02, float(data[-1]) * 0.98
            return 0.0, 0.0
        sma = np.mean(data[-period:])
        std = np.std(data[-period:])
        return sma + std_dev * std, sma - std_dev * std
        
    def _obv(self, closes: np.ndarray, volumes) -> float:
        """On Balance Volume"""
        if len(closes) < 2 or not isinstance(volumes, np.ndarray) or len(volumes) < 2:
            return 0.0
        obv = 0
        for i in range(1, len(closes)):
            if closes[i] > closes[i-1]:
                obv += volumes[i]
            elif closes[i] < closes[i-1]:
                obv -= volumes[i]
        return obv
        
    def _macd(self, data: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
        """MACD indicator"""
        ema_fast = self._ema(data, fast)
        ema_slow = self._ema(data, slow)
        macd_line = ema_fast - ema_slow
        macd_signal = self._ema(macd_line, signal)
        macd_hist = macd_line - macd_signal
        return macd_line, macd_signal, macd_hist
        
    def _stochastic_rsi(self, data: np.ndarray, rsi_period: int = 14, 
                        stoch_period: int = 14, k_period: int = 3, d_period: int = 3) -> float:
        """Stochastic RSI"""
        # Check if data is valid
        if not isinstance(data, np.ndarray) or data.ndim == 0 or len(data) < rsi_period + 1:
            return 50.0
        if not isinstance(data, np.ndarray):
            data = np.array(data)
        # Compute RSI
        rsi_vals = []
        for i in range(rsi_period, len(data) + 1):
            rsi_vals.append(self._rsi(data[:i], rsi_period))
            
        if len(rsi_vals) < stoch_period:
            return 50.0
            
        # Stochastic of RSI
        recent_rsi = np.array(rsi_vals[-stoch_period:])
        rsi_min = np.min(recent_rsi)
        rsi_max = np.max(recent_rsi)
        
        if rsi_max == rsi_min:
            return 50.0
            
        stoch_rsi = 100 * (recent_rsi[-1] - rsi_min) / (rsi_max - rsi_min)
        return stoch_rsi
        
    def get_latest_features(self) -> Optional[FeatureSnapshot]:
        """Get most recent feature snapshot"""
        return self.feature_history[-1] if self.feature_history else None
        
    def get_feature_history(self, n: int = 100) -> List[FeatureSnapshot]:
        """Get recent feature history"""
        return list(self.feature_history)[-n:]
