import React, { useState, useEffect, useRef } from 'react';
import './App.css';

function App() {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeframe, setTimeframe] = useState('1m');
  const [candles, setCandles] = useState([]);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [threshold, setThreshold] = useState(70);
  const [thresholdLoading, setThresholdLoading] = useState(false);
  const [thresholdMessage, setThresholdMessage] = useState('');
  
  // Comprehensive Settings State
  const [settings, setSettings] = useState({
    signal_threshold: 70,
    min_probability: 0.5,
    min_prospect_value: 0.0,
    require_signal_valid: true,
    require_direction: true,
    cooldown_period: 300,
    position_size_pct: 0.1,
    stop_loss_pct: 0.01,
    take_profit_mult: 2.0,
    enable_bootstrap: true,
    bootstrap_trades: 5,
    max_positions: 1,
    // New signal parameters
    tsmomPercentile: 0.667,
    cooldownHours: 4,
    regime1Threshold: 70,
    regime2Threshold: 75,
    regime3Threshold: 80,
    regime4Threshold: 85,
    regime5Threshold: 90,
    minOfiClean: 0.01,
    minMrrRho: 0.10,
    minCoValue: 0.0,
    minAsymmetricSharpe: 0.5,
  });
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsMessage, setSettingsMessage] = useState('');
  const [activeTooltip, setActiveTooltip] = useState(null);
  
  // Trade Decision Diagnostics State
  const [tradeDiagnostics, setTradeDiagnostics] = useState(null);
  const [diagnosticsLoading, setDiagnosticsLoading] = useState(false);
  
  // Trade History State
  const [tradeHistory, setTradeHistory] = useState([]);
  
  // Open Positions State
  const [positions, setPositions] = useState([]);
  
  // AutoQuant Validation State
  const [autoquantStatus, setAutoquantStatus] = useState(null);
  const [autoquantResult, setAutoquantResult] = useState(null);
  const [autoquantReport, setAutoquantReport] = useState(null);
  const [autoquantTrades, setAutoquantTrades] = useState([]);
  const [autoquantLoading, setAutoquantLoading] = useState(false);
  const [activeAutoquantTab, setActiveAutoquantTab] = useState('status');
  
  // 300-Trade Backtest Validation State
  const [backtestStatus, setBacktestStatus] = useState(null);
  const [backtestResult, setBacktestResult] = useState(null);
  const [backtestReport, setBacktestReport] = useState(null);
  const [backtestTrades, setBacktestTrades] = useState([]);
  const [backtestLoading, setBacktestLoading] = useState(false);
  const [activeBacktestTab, setActiveBacktestTab] = useState('status');
  
  const chartContainerRef = useRef(null);
  const chartRef = useRef(null);
  const candleSeriesRef = useRef(null);
  const priceLinesRef = useRef({ entry: null, tp1: null, tp2: null, sl: null, current: null });
  const currentPriceRef = useRef(null);
  const lastCandleRef = useRef(null);
  const historicalCandlesRef = useRef([]);

  const timeframes = ['1m', '5m', '15m', '1h', '4h', '1d'];

  // Fetch engine state
  useEffect(() => {
    const fetchData = async () => {
      try {
        const response = await fetch('/api/v1/state');
        if (!response.ok) throw new Error('Failed to fetch');
        const data = await response.json();
        setState(data);
        setLoading(false);
      } catch (err) {
        setError(err.message);
        setLoading(false);
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 1000); // 1 second for live price updates
    return () => clearInterval(interval);
  }, []);

  // Fetch trade history
  useEffect(() => {
    const fetchTrades = async () => {
      try {
        const response = await fetch('/api/v1/trades/history');
        if (response.ok) {
          const data = await response.json();
          setTradeHistory(data);
        }
      } catch (err) {
        console.error('Failed to fetch trade history:', err);
      }
    };
    
    fetchTrades();
    const interval = setInterval(fetchTrades, 3000);
    return () => clearInterval(interval);
  }, []);

  // Fetch open positions
  useEffect(() => {
    const fetchPositions = async () => {
      try {
        const response = await fetch('/api/v1/positions');
        if (response.ok) {
          const data = await response.json();
          setPositions(data);
        }
      } catch (err) {
        console.error('Failed to fetch positions:', err);
      }
    };
    
    fetchPositions();
    const interval = setInterval(fetchPositions, 2000);
    return () => clearInterval(interval);
  }, []);

  // Fetch AutoQuant validation status
  useEffect(() => {
    const fetchAutoquant = async () => {
      try {
        const response = await fetch('/api/v1/validation/autoquant/status');
        if (response.ok) {
          const data = await response.json();
          setAutoquantStatus(data);
          
          // If AutoQuant completed and has metrics, use them directly
          if (!data.is_running && data.status === 'autoquant_complete' && data.win_rate !== null) {
            setAutoquantResult({
              win_rate: data.win_rate,
              profit_factor: data.profit_factor,
              sharpe_ratio: data.sharpe_ratio,
              psr_0: data.psr_0,
              max_drawdown: data.max_drawdown,
              passed: data.passed,
              total_trades: data.trades_completed
            });
            setAutoquantLoading(false);
            
            // Fetch the AutoQuant report
            try {
              const reportResponse = await fetch('/api/v1/validation/autoquant/report');
              if (reportResponse.ok) {
                const reportData = await reportResponse.json();
                setAutoquantReport(reportData.report);
              }
            } catch (err) {
              console.error('Failed to fetch AutoQuant report:', err);
            }

            // Fetch AutoQuant trades
            fetchAutoquantTrades();
          }
          
          // If AutoQuant is not running and not complete, clear loading state
          if (!data.is_running && data.status === 'not_initialized') {
            setAutoquantLoading(false);
            setAutoquantReport(null);
          }
        }
      } catch (err) {
        // AutoQuant endpoint might not exist yet
      }
    };
    
    fetchAutoquant();
    const interval = setInterval(fetchAutoquant, 5000);
    return () => clearInterval(interval);
  }, [autoquantLoading]);

  // Fetch 300-trade backtest validation status
  useEffect(() => {
    const fetchBacktest = async () => {
      try {
        const response = await fetch('/api/v1/validation/status');
        if (response.ok) {
          const data = await response.json();
          setBacktestStatus(data);
          
          // If backtest completed and has metrics, use them directly
          if (!data.is_running && data.status === 'complete' && data.win_rate !== null) {
            setBacktestResult({
              win_rate: data.win_rate,
              profit_factor: data.profit_factor,
              sharpe_ratio: data.sharpe_ratio,
              psr_0: data.psr_0,
              max_drawdown: data.max_drawdown,
              passed: data.passed,
              total_trades: data.trades_completed
            });
            setBacktestLoading(false);
            
            // Fetch the report
            try {
              const reportResponse = await fetch('/api/v1/validation/report');
              if (reportResponse.ok) {
                const reportData = await reportResponse.json();
                setBacktestReport(reportData.report);
              }
            } catch (err) {
              console.error('Failed to fetch backtest report:', err);
            }

            // Fetch backtest trades
            fetchBacktestTrades();
          }
          
          // If backtest is not running and not complete, clear loading state
          if (!data.is_running && data.status === 'not_initialized') {
            setBacktestLoading(false);
            setBacktestReport(null);
          }
        }
      } catch (err) {
        // Validation endpoint might not exist yet
      }
    };
    
    fetchBacktest();
    const interval = setInterval(fetchBacktest, 5000);
    return () => clearInterval(interval);
  }, [backtestLoading]);

  // Live streaming chart update with current price
  useEffect(() => {
    if (!candleSeriesRef.current || !state?.current_price) return;
    
    const price = Number(state.current_price);
    const now = Math.floor(Date.now() / 1000);
    const candleInterval = 60; // 1 minute candles
    const currentCandleTime = Math.floor(now / candleInterval) * candleInterval;
    
    // Remove old current price line
    if (priceLinesRef.current.current) {
      candleSeriesRef.current.removePriceLine(priceLinesRef.current.current);
    }
    
    // Add new current price line
    priceLinesRef.current.current = candleSeriesRef.current.createPriceLine({
      price: price,
      color: '#f59e0b',
      lineWidth: 1,
      lineStyle: 3,
      axisLabelVisible: true,
      title: `Price: $${price.toFixed(0)}`,
    });
    
    // Live streaming - update the forming candle
    if (lastCandleRef.current) {
      const lastCandleTime = lastCandleRef.current.time;
      
      if (currentCandleTime === lastCandleTime) {
        // Same candle interval - update the forming candle
        const updatedCandle = {
          time: lastCandleTime,
          open: lastCandleRef.current.open,
          high: Math.max(lastCandleRef.current.high, price),
          low: Math.min(lastCandleRef.current.low, price),
          close: price,
        };
        candleSeriesRef.current.update(updatedCandle);
        lastCandleRef.current = updatedCandle;
      } else if (currentCandleTime > lastCandleTime) {
        // New candle interval - finalize old candle and start new one
        const newCandle = {
          time: currentCandleTime,
          open: price,
          high: price,
          low: price,
          close: price,
        };
        candleSeriesRef.current.update(newCandle);
        lastCandleRef.current = newCandle;
      }
    }
  }, [state?.current_price, state?.last_update]);

  // Fetch current threshold
  useEffect(() => {
    const fetchThreshold = async () => {
      try {
        const response = await fetch('/api/v1/settings/threshold');
        if (response.ok) {
          const data = await response.json();
          if (data.dynamic_threshold > 0) {
            setThreshold(data.dynamic_threshold);
          } else if (data.effective_threshold !== 'regime-specific') {
            setThreshold(data.effective_threshold);
          }
        }
      } catch (err) {
        console.error('Failed to fetch threshold:', err);
      }
    };

    fetchThreshold();
  }, []);

  // Update threshold function
  const updateThreshold = async () => {
    setThresholdLoading(true);
    setThresholdMessage('');
    try {
      const response = await fetch('/api/v1/settings/threshold', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ threshold: parseInt(threshold) })
      });
      if (response.ok) {
        setThresholdMessage('Threshold updated successfully!');
        setTimeout(() => setThresholdMessage(''), 3000);
      } else {
        const error = await response.json();
        setThresholdMessage(`Error: ${error.detail}`);
      }
    } catch (err) {
      setThresholdMessage(`Error: ${err.message}`);
    }
    setThresholdLoading(false);
  };

  // Fetch comprehensive settings
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const response = await fetch('/api/v1/settings');
        if (response.ok) {
          const data = await response.json();
          // Get effective threshold - if 0, use state's current threshold or 70
          const effectiveThreshold = data.signal_threshold === 0 ? 
            (state?.latest_signal?.signal_threshold || 70) : data.signal_threshold;
          setSettings({
            signal_threshold: data.signal_threshold,  // Keep actual value (0 means auto)
            min_probability: data.min_probability,
            min_prospect_value: data.min_prospect_value,
            require_signal_valid: data.require_signal_valid !== undefined ? data.require_signal_valid : true,
            require_direction: data.require_direction !== undefined ? data.require_direction : true,
            cooldown_period: data.cooldown_period,
            position_size_pct: data.position_size_pct,
            stop_loss_pct: data.stop_loss_pct,
            take_profit_mult: data.take_profit_mult,
            enable_bootstrap: data.enable_bootstrap,
            bootstrap_trades: data.bootstrap_trades ?? 5,
            max_positions: data.max_positions,
            // New signal parameters
            tsmom_percentile: data.tsmom_percentile ?? 0.667,
            cooldown_hours: data.cooldown_hours ?? 4,
            regime_1_threshold: data.regime_1_threshold ?? 70,
            regime_2_threshold: data.regime_2_threshold ?? 75,
            regime_3_threshold: data.regime_3_threshold ?? 80,
            regime_4_threshold: data.regime_4_threshold ?? 85,
            regime_5_threshold: data.regime_5_threshold ?? 90,
            max_daily_trades: data.max_daily_trades ?? 5,
            min_ofi_clean: data.min_ofi_clean ?? 0.01,
            min_mrr_rho: data.min_mrr_rho ?? 0.10,
            min_co_value: data.min_co_value ?? 0.0,
            min_asymmetric_sharpe: data.min_asymmetric_sharpe ?? 0.5,
            min_prob_weighted_score: data.min_prob_weighted_score ?? 35.0,
          });
        }
      } catch (err) {
        console.error('Failed to fetch settings:', err);
      }
    };

    fetchSettings();
  }, []);

  // Update all settings function
  const updateSettings = async () => {
    setSettingsLoading(true);
    setSettingsMessage('');
    try {
      const response = await fetch('/api/v1/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(settings)
      });
      if (response.ok) {
        setSettingsMessage('All settings updated successfully!');
        setTimeout(() => setSettingsMessage(''), 3000);
      } else {
        const error = await response.json();
        setSettingsMessage(`Error: ${error.detail}`);
      }
    } catch (err) {
      setSettingsMessage(`Error: ${err.message}`);
    }
    setSettingsLoading(false);
  };

  // Reset settings to defaults
  const resetSettings = () => {
    setSettings({
      signal_threshold: 70,
      min_probability: 0.5,
      min_prospect_value: 0.0,
      require_signal_valid: true,
      require_direction: true,
      cooldown_period: 300,
      position_size_pct: 0.1,
      stop_loss_pct: 0.01,
      take_profit_mult: 2.0,
      enable_bootstrap: true,
      bootstrap_trades: 5,
      max_positions: 1,
      // New signal parameters - defaults
      tsmom_percentile: 0.667,
      cooldown_hours: 4,
      regime_1_threshold: 70,
      regime_2_threshold: 75,
      regime_3_threshold: 80,
      regime_4_threshold: 85,
      regime_5_threshold: 90,
      max_daily_trades: 5,
      min_ofi_clean: 0.01,
      min_mrr_rho: 0.10,
      min_co_value: 0.0,
      min_asymmetric_sharpe: 0.5,
      min_prob_weighted_score: 35.0,
    });
  };

  // Fetch Trade Decision Diagnostics
  const fetchTradeDiagnostics = async () => {
    setDiagnosticsLoading(true);
    try {
      const response = await fetch('/api/v1/trade-diagnostics');
      if (response.ok) {
        const data = await response.json();
        setTradeDiagnostics(data);
      }
    } catch (err) {
      console.error('Failed to fetch trade diagnostics:', err);
    }
    setDiagnosticsLoading(false);
  };

  // Start AutoQuant validation
  const startAutoquant = async () => {
    setAutoquantLoading(true);
    try {
      const response = await fetch('/api/v1/validation/autoquant', { method: 'POST' });
      if (response.ok) {
        // Status will be fetched by the polling useEffect
      } else {
        console.error('Failed to start AutoQuant validation');
        setAutoquantLoading(false);
      }
    } catch (err) {
      console.error('Failed to start AutoQuant validation:', err);
      setAutoquantLoading(false);
    }
  };

  const resetAutoquant = async () => {
    try {
      const response = await fetch('/api/v1/validation/autoquant/reset', { method: 'POST' });
      if (response.ok) {
        setAutoquantResult(null);
        setAutoquantReport(null);
        setAutoquantStatus(null);
        setAutoquantTrades([]);
        setAutoquantLoading(false);
      }
    } catch (err) {
      console.error('Failed to reset AutoQuant validation:', err);
    }
  };

  // Start 300-trade backtest validation
  const startBacktest = async () => {
    setBacktestLoading(true);
    setBacktestResult(null);  // Clear old result
    try {
      const response = await fetch('/api/v1/validation/start', {
        method: 'POST'
      });
      if (response.ok) {
        const data = await response.json();
      } else {
        console.error('Failed to start backtest validation');
        setBacktestLoading(false);
      }
    } catch (err) {
      console.error('Failed to start backtest validation:', err);
      setBacktestLoading(false);
    }
  };

  const resetBacktest = async () => {
    try {
      const response = await fetch('/api/v1/validation/reset', { method: 'POST' });
      if (response.ok) {
        setBacktestResult(null);
        setBacktestReport(null);
        setBacktestStatus(null);
        setBacktestTrades([]);
        setBacktestLoading(false);
      }
    } catch (err) {
      console.error('Failed to reset backtest validation:', err);
    }
  };

  // Fetch AutoQuant trades
  const fetchAutoquantTrades = async () => {
    try {
      const response = await fetch('/api/v1/validation/autoquant/trades');
      if (response.ok) {
        const data = await response.json();
        setAutoquantTrades(data || []);
      }
    } catch (err) {
      console.error('Failed to fetch AutoQuant trades:', err);
    }
  };

  // Fetch backtest trades
  const fetchBacktestTrades = async () => {
    try {
      const response = await fetch('/api/v1/validation/trades');
      if (response.ok) {
        const data = await response.json();
        setBacktestTrades(data || []);
      }
    } catch (err) {
      console.error('Failed to fetch backtest trades:', err);
    }
  };

  // Fetch candles for chart
  useEffect(() => {
    const fetchCandles = async () => {
      try {
        console.log(`Fetching candles for timeframe: ${timeframe}`);
        const response = await fetch(`/api/v1/candles?timeframe=${timeframe}&limit=100`);
        console.log(`Candles response status: ${response.status}`);
        if (response.ok) {
          const data = await response.json();
          console.log(`Received ${data.candles?.length || 0} candles`);
          setCandles(data.candles || []);
          setLastUpdate(new Date());
        } else {
          console.error('Failed to fetch candles:', await response.text());
        }
      } catch (err) {
        console.error('Failed to fetch candles:', err);
      }
    };

    fetchCandles();
    const interval = setInterval(fetchCandles, 1000); // Update every 1 second for live feel
    return () => clearInterval(interval);
  }, [timeframe]);

  // Fetch trade diagnostics periodically
  useEffect(() => {
    fetchTradeDiagnostics();
    const interval = setInterval(fetchTradeDiagnostics, 3000);
    return () => clearInterval(interval);
  }, []);

  // Initialize TradingView Chart (disabled - using TradingView iframe instead)
  // useEffect(() => {
  //   console.log('Chart effect triggered. Candles:', candles.length, 'Container:', !!chartContainerRef.current);
  //   if (!chartContainerRef.current || candles.length === 0) {
  //     console.log('Skipping chart render - no container or candles');
  //     return;
  //   }

  //   // Dynamically import lightweight-charts
  //   import('lightweight-charts').then(({ createChart, CrosshairMode }) => {
  //     console.log('lightweight-charts loaded');
      
  //     if (!chartRef.current) {
  //       console.log('Creating new chart');
  //       const chart = createChart(chartContainerRef.current, {
  //         width: chartContainerRef.current.clientWidth || 800,
  //         height: 400,
  //         layout: {
  //           background: { color: '#0a0e1a' },
  //           textColor: '#e0e0e0',
  //         },
  //         grid: {
  //           vertLines: { color: 'rgba(255,255,255,0.05)' },
  //           horzLines: { color: 'rgba(255,255,255,0.05)' },
  //         },
  //         crosshair: {
  //           mode: CrosshairMode.Normal,
  //         },
  //         rightPriceScale: {
  //           borderColor: 'rgba(255,255,255,0.1)',
  //           scaleMargins: {
  //             top: 0.1,
  //             bottom: 0.1,
  //           },
  //           autoScale: true,
  //         },
  //         timeScale: {
  //           borderColor: 'rgba(255,255,255,0.1)',
  //           timeVisible: true,
  //           secondsVisible: false,
  //         },
  //       });
        
  //       chartRef.current = chart;
  //       console.log('Chart created successfully');
  //     }

  //     const candleSeries = chartRef.current.addCandlestickSeries({
  //       upColor: '#22c55e',
  //       downColor: '#ef4444',
  //       borderDownColor: '#ef4444',
  //       borderUpColor: '#22c55e',
  //       wickDownColor: '#ef4444',
  //       wickUpColor: '#22c55e',
  //     });

  //     candleSeriesRef.current = candleSeries;

  //     // Format candles for lightweight-charts
  //     const formattedCandles = candles.map(c => ({
  //       time: Math.floor(new Date(c.timestamp).getTime() / 1000),
  //       open: c.open,
  //       high: c.high,
  //       low: c.low,
  //       close: c.close,
  //     }));

  //     console.log('First candle:', formattedCandles[0]);
  //     console.log('Last candle:', formattedCandles[formattedCandles.length - 1]);
  //     console.log('Sample OHLC:', { o: formattedCandles[0].open, h: formattedCandles[0].high, l: formattedCandles[0].low, c: formattedCandles[0].close });

  //     // Calculate average body and wick for sizing
  //     const avgBody = formattedCandles.reduce((sum, c) => sum + Math.abs(c.close - c.open), 0) / formattedCandles.length;
  //     const avgWick = formattedCandles.reduce((sum, c) => sum + (c.high - c.low), 0) / formattedCandles.length;
  //     console.log('Avg body:', avgBody.toFixed(2), 'Avg wick:', avgWick.toFixed(2));

  //     candleSeries.setData(formattedCandles);
      
  //     // Store historical candles and initialize last candle ref for streaming
  //     if (formattedCandles.length > 0) {
  //       historicalCandlesRef.current = formattedCandles.slice(0, -1); // All but last
  //       lastCandleRef.current = formattedCandles[formattedCandles.length - 1]; // Last for streaming
  //       console.log('Initialized streaming with last candle:', lastCandleRef.current);
  //     }
  //     chartRef.current.timeScale().fitContent();
  //   }).catch(err => {
  //     console.error('Failed to load lightweight-charts:', err);
  //   });

  //   return () => {
  //     if (chartRef.current) {
  //       chartRef.current.remove();
  //       chartRef.current = null;
  //       candleSeriesRef.current = null;
  //     }
  //   };
  // }, [candles, state]);

  // Update price lines for open positions (disabled - using TradingView iframe)
  // useEffect(() => {
  //   if (!candleSeriesRef.current) return;

  //   console.log('[Chart] Updating price lines, positions:', positions);

  //   // Remove old price lines
  //   if (priceLinesRef.current.tp1) {
  //     candleSeriesRef.current.removePriceLine(priceLinesRef.current.tp1);
  //     priceLinesRef.current.tp1 = null;
  //   }
  //   if (priceLinesRef.current.tp2) {
  //     candleSeriesRef.current.removePriceLine(priceLinesRef.current.tp2);
  //     priceLinesRef.current.tp2 = null;
  //   }
  //   if (priceLinesRef.current.sl) {
  //     candleSeriesRef.current.removePriceLine(priceLinesRef.current.sl);
  //     priceLinesRef.current.sl = null;
  //   }
  //   if (priceLinesRef.current.entry) {
  //     candleSeriesRef.current.removePriceLine(priceLinesRef.current.entry);
  //     priceLinesRef.current.entry = null;
  //   }

  //   // Add new price lines for open positions
  //   if (positions && positions.length > 0) {
  //     positions.forEach(pos => {
  //       console.log('[Chart] Processing position:', pos);
  //       if (pos.state === 'active' || pos.state === 'OPEN') {
  //         // Entry price line
  //         if (pos.entry_price) {
  //           priceLinesRef.current.entry = candleSeriesRef.current.createPriceLine({
  //             price: pos.entry_price,
  //             color: '#22c55e',
  //             lineWidth: 2,
  //             lineStyle: 2,
  //             axisLabelVisible: true,
  //             title: `Entry: $${Number(pos.entry_price).toFixed(0)}`,
  //           });
  //           console.log('[Chart] Added entry line at', pos.entry_price);
  //         }

  //         // TP1 line
  //         if (pos.risk_levels?.take_profit_1 || pos.take_profit_1) {
  //           const tp1 = pos.risk_levels?.take_profit_1 || pos.take_profit_1;
  //           priceLinesRef.current.tp1 = candleSeriesRef.current.createPriceLine({
  //             price: tp1,
  //             color: '#3b82f6',
  //             lineWidth: 2,
  //             lineStyle: 2,
  //             axisLabelVisible: true,
  //             title: `TP1: $${Number(tp1).toFixed(0)}`,
  //           });
  //           console.log('[Chart] Added TP1 line at', tp1);
  //         }

  //         // TP2 line
  //         if (pos.risk_levels?.take_profit_2 || pos.take_profit_2) {
  //           const tp2 = pos.risk_levels?.take_profit_2 || pos.take_profit_2;
  //           priceLinesRef.current.tp2 = candleSeriesRef.current.createPriceLine({
  //             price: tp2,
  //             color: '#8b5cf6',
  //             lineWidth: 2,
  //             lineStyle: 2,
  //             axisLabelVisible: true,
  //             title: `TP2: $${Number(tp2).toFixed(0)}`,
  //           });
  //           console.log('[Chart] Added TP2 line at', tp2);
  //         }

  //         // SL line
  //         if (pos.risk_levels?.stop_loss || pos.stop_loss) {
  //           const sl = pos.risk_levels?.stop_loss || pos.stop_loss;
  //           priceLinesRef.current.sl = candleSeriesRef.current.createPriceLine({
  //             price: sl,
  //             color: '#ef4444',
  //             lineWidth: 2,
  //             lineStyle: 2,
  //             axisLabelVisible: true,
  //             title: `SL: $${Number(sl).toFixed(0)}`,
  //           });
  //           console.log('[Chart] Added SL line at', sl);
  //         }
  //       } else {
  //         console.log('[Chart] Position state not active:', pos.state);
  //       }
  //     });
  //   }
  // }, [positions]);

  // Handle window resize
  useEffect(() => {
    const handleResize = () => {
      if (chartRef.current && chartContainerRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
        });
      }
    };

    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  if (loading) return <div style={{ background: '#0a0e1a', color: '#e0e0e0', minHeight: '100vh', padding: '20px' }}>Loading...</div>;
  if (error) return <div style={{ background: '#0a0e1a', color: '#e0e0e0', minHeight: '100vh', padding: '20px' }}>Error: {error}</div>;

  return (
    <div className="App" style={{ background: '#0a0e1a', color: '#e0e0e0', minHeight: '100vh', padding: '20px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '15px', marginBottom: '10px' }}>
        <h1 style={{ background: 'linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', margin: 0 }}>
          APEX-BTC v6.0
        </h1>
        <div style={{ 
          display: 'flex', 
          alignItems: 'center', 
          gap: '6px',
          background: 'rgba(34, 197, 94, 0.2)', 
          padding: '4px 12px', 
          borderRadius: '20px',
          border: '1px solid #22c55e'
        }}>
          <span style={{ 
            width: '8px', 
            height: '8px', 
            background: '#22c55e', 
            borderRadius: '50%',
            animation: 'pulse 2s infinite'
          }}></span>
          <span style={{ color: '#22c55e', fontSize: '12px', fontWeight: 'bold' }}>LIVE</span>
        </div>
        {lastUpdate && (
          <span style={{ color: '#6b7280', fontSize: '11px' }}>
            Last update: {lastUpdate.toLocaleTimeString()}
          </span>
        )}
      </div>
      <p style={{ marginTop: 0 }}>Autonomous Paper Trading Engine - Real Binance Data</p>
      
      {/* Timeframe Selector */}
      <div style={{ display: 'flex', gap: '10px', marginTop: '20px', marginBottom: '10px' }}>
        {timeframes.map(tf => (
          <button
            key={tf}
            onClick={() => setTimeframe(tf)}
            style={{
              padding: '8px 16px',
              border: 'none',
              borderRadius: '4px',
              background: timeframe === tf ? '#3b82f6' : 'rgba(255,255,255,0.1)',
              color: '#fff',
              cursor: 'pointer',
              fontWeight: timeframe === tf ? 'bold' : 'normal',
            }}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* Signal Calculation Monitor */}
      <div style={{ 
        marginTop: '15px',
        padding: '15px', 
        background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1), rgba(59, 130, 246, 0.1))', 
        borderRadius: '12px', 
        border: '1px solid rgba(139, 92, 246, 0.3)',
        fontSize: '13px'
      }}>
        <h3 style={{ color: '#8b5cf6', marginBottom: '10px', fontSize: '16px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          ⚡ Signal Calculation Monitor
          <span style={{ 
            width: '8px', 
            height: '8px', 
            background: '#22c55e', 
            borderRadius: '50%', 
            animation: 'pulse 2s infinite',
            display: 'inline-block'
          }}></span>
        </h3>
        
        {state.latest_signal ? (
          <div>
            {/* Signal Score Bar */}
            <div style={{ marginBottom: '15px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px' }}>
                <span style={{ color: '#9ca3af' }}>Composite Score</span>
                <span style={{ color: '#fff', fontWeight: 'bold' }}>
                  {state.latest_signal.composite_score || 0} / {state.latest_signal.max_possible_score || 105}
                </span>
              </div>
              <div style={{ 
                height: '8px', 
                background: 'rgba(255,255,255,0.1)', 
                borderRadius: '4px',
                overflow: 'hidden'
              }}>
                <div style={{ 
                  height: '100%', 
                  width: `${((state.latest_signal.composite_score || 0) / (state.latest_signal.max_possible_score || 105)) * 100}%`,
                  background: (state.latest_signal.composite_score || 0) >= threshold ? '#22c55e' : (state.latest_signal.composite_score || 0) >= 50 ? '#f59e0b' : '#ef4444',
                  borderRadius: '4px',
                  transition: 'width 0.5s ease'
                }}></div>
              </div>
              <p style={{ color: (state.latest_signal.composite_score || 0) >= threshold ? '#22c55e' : '#9ca3af', fontSize: '11px', marginTop: '5px' }}>
                Current Threshold: {threshold} | Signal: {state.latest_signal.direction || 'NEUTRAL'}
              </p>
            </div>

            {/* Comprehensive Settings Control Panel */}
            <div style={{ 
              padding: '15px', 
              background: 'rgba(255,255,255,0.05)', 
              borderRadius: '8px', 
              borderLeft: "3px solid #22c55e",
              marginTop: '10px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                <span style={{ color: '#22c55e', fontWeight: 'bold', fontSize: '14px' }}>⚙️ Advanced Settings Control</span>
                <span style={{ color: settingsMessage?.includes('Error') ? '#ef4444' : '#22c55e', fontSize: '12px' }}>
                  {settingsMessage && (settingsMessage.includes('Error') ? '❌' : '✅')}
                </span>
              </div>

              {/* Settings Grid */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '15px' }}>
                
                {/* Signal Threshold */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Signal Threshold</span>
                    <span 
                      onMouseEnter={() => setActiveTooltip('threshold')}
                      onMouseLeave={() => setActiveTooltip(null)}
                      style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}
                    >ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 70 (0=auto)</span>
                  </div>
                  {activeTooltip === 'threshold' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Minimum score (0-100) required to trigger a trade. Lower = more trades but lower quality.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="0" max="90" value={settings.signal_threshold} onChange={(e) => setSettings({...settings, signal_threshold: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                    <div style={{ 
                      width: '50px', 
                      padding: '4px', 
                      background: settings.signal_threshold === 0 ? 'rgba(34,197,94,0.2)' : 'rgba(255,255,255,0.1)', 
                      border: '1px solid rgba(255,255,255,0.2)', 
                      borderRadius: '4px', 
                      color: settings.signal_threshold === 0 ? '#22c55e' : '#fff', 
                      textAlign: 'center', 
                      fontSize: '11px',
                      fontWeight: settings.signal_threshold === 0 ? 'bold' : 'normal'
                    }}>
                      {settings.signal_threshold === 0 ? `Auto(${state?.latest_signal?.signal_threshold || 70})` : settings.signal_threshold}
                    </div>
                  </div>
                  {settings.signal_threshold === 0 && (
                    <span style={{ color: '#22c55e', fontSize: '9px' }}>Using regime-specific thresholds</span>
                  )}
                </div>

                {/* Min Probability */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Min Probability</span>
                    <span onMouseEnter={() => setActiveTooltip('probability')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 0.5</span>
                  </div>
                  {activeTooltip === 'probability' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Minimum probability (0.0-1.0) that signal will be profitable. Higher = more confident trades.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="0" max="100" value={settings.min_probability * 100} onChange={(e) => setSettings({...settings, min_probability: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                    <input type="number" min="0" max="1" step="0.1" value={settings.min_probability} onChange={(e) => setSettings({...settings, min_probability: parseFloat(e.target.value)})} style={{ width: '50px', padding: '4px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '11px' }} />
                  </div>
                </div>

                {/* Min Prospect Value */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Min Prospect Value</span>
                    <span onMouseEnter={() => setActiveTooltip('prospect')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 0.0</span>
                  </div>
                  {activeTooltip === 'prospect' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Risk-adjusted expected value (-5.0 to 5.0). Positive = profitable expectation. Lower values allow riskier trades.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="-500" max="500" value={settings.min_prospect_value * 100} onChange={(e) => setSettings({...settings, min_prospect_value: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                    <input type="number" min="-5" max="5" step="0.1" value={settings.min_prospect_value} onChange={(e) => setSettings({...settings, min_prospect_value: parseFloat(e.target.value)})} style={{ width: '50px', padding: '4px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '11px' }} />
                  </div>
                </div>

                {/* Cooldown Period */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Cooldown (sec)</span>
                    <span onMouseEnter={() => setActiveTooltip('cooldown')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 300</span>
                  </div>
                  {activeTooltip === 'cooldown' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Seconds to wait between trades. Prevents over-trading. 300 = 5 minutes.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="0" max="600" value={settings.cooldown_period} onChange={(e) => setSettings({...settings, cooldown_period: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                    <input type="number" min="0" max="600" value={settings.cooldown_period} onChange={(e) => setSettings({...settings, cooldown_period: parseInt(e.target.value)})} style={{ width: '50px', padding: '4px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '11px' }} />
                  </div>
                </div>

                {/* Position Size % */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Position Size %</span>
                    <span onMouseEnter={() => setActiveTooltip('position')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 0.1</span>
                  </div>
                  {activeTooltip === 'position' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      % of equity to risk per trade. 0.1 = 10%. Higher = bigger positions, more risk.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="1" max="100" value={settings.position_size_pct * 100} onChange={(e) => setSettings({...settings, position_size_pct: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                    <input type="number" min="0.01" max="1" step="0.01" value={settings.position_size_pct} onChange={(e) => setSettings({...settings, position_size_pct: parseFloat(e.target.value)})} style={{ width: '50px', padding: '4px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '11px' }} />
                  </div>
                </div>

                {/* Stop Loss % */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Stop Loss %</span>
                    <span onMouseEnter={() => setActiveTooltip('stoploss')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 0.01</span>
                  </div>
                  {activeTooltip === 'stoploss' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      % below entry price to exit losing trades. 0.01 = 1% stop loss.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="1" max="50" value={settings.stop_loss_pct * 1000} onChange={(e) => setSettings({...settings, stop_loss_pct: parseInt(e.target.value) / 1000})} style={{ flex: 1, height: '6px' }} />
                    <input type="number" min="0.001" max="0.1" step="0.001" value={settings.stop_loss_pct} onChange={(e) => setSettings({...settings, stop_loss_pct: parseFloat(e.target.value)})} style={{ width: '50px', padding: '4px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '11px' }} />
                  </div>
                </div>

                {/* Take Profit Multiplier */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Take Profit Multiplier</span>
                    <span onMouseEnter={() => setActiveTooltip('takeprofit')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 2.0</span>
                  </div>
                  {activeTooltip === 'takeprofit' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Risk:Reward ratio. 2.0 = 2:1 reward to risk. Higher = bigger wins but may not trigger.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="10" max="50" value={settings.take_profit_mult * 10} onChange={(e) => setSettings({...settings, take_profit_mult: parseInt(e.target.value) / 10})} style={{ flex: 1, height: '6px' }} />
                    <input type="number" min="1" max="5" step="0.1" value={settings.take_profit_mult} onChange={(e) => setSettings({...settings, take_profit_mult: parseFloat(e.target.value)})} style={{ width: '50px', padding: '4px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '11px' }} />
                  </div>
                </div>

                {/* Max Positions */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Max Positions</span>
                    <span onMouseEnter={() => setActiveTooltip('maxpos')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: 1</span>
                  </div>
                  {activeTooltip === 'maxpos' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Maximum concurrent open trades. Limits total risk exposure.
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                    <input type="range" min="1" max="10" value={settings.max_positions} onChange={(e) => setSettings({...settings, max_positions: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                    <input type="number" min="1" max="10" value={settings.max_positions} onChange={(e) => setSettings({...settings, max_positions: parseInt(e.target.value)})} style={{ width: '50px', padding: '4px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '11px' }} />
                  </div>
                </div>

                {/* Enable Bootstrap */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Bootstrap Mode</span>
                    <span onMouseEnter={() => setActiveTooltip('bootstrap')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: enabled</span>
                  </div>
                  {activeTooltip === 'bootstrap' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Allow first 5 trades without full PSR/DSR validation. Speeds up initial trading.
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={settings.enable_bootstrap} onChange={(e) => setSettings({...settings, enable_bootstrap: e.target.checked})} style={{ cursor: 'pointer' }} />
                      <span style={{ color: '#fff', fontSize: '12px' }}>{settings.enable_bootstrap ? 'Enabled' : 'Disabled'}</span>
                    </label>
                  </div>
                  {/* Bootstrap Trades Count */}
                  {settings.enable_bootstrap && (
                    <div style={{ marginTop: '10px', padding: '8px', background: 'rgba(0,0,0,0.15)', borderRadius: '4px' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                        <span style={{ color: '#9ca3af', fontSize: '11px' }}>Max Bootstrap Trades</span>
                        <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 5</span>
                      </div>
                      <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                        <input type="range" min="1" max="20" value={settings.bootstrap_trades || 5} onChange={(e) => setSettings({...settings, bootstrap_trades: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                        <input type="number" min="1" max="20" step="1" value={settings.bootstrap_trades || 5} onChange={(e) => setSettings({...settings, bootstrap_trades: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                      </div>
                    </div>
                  )}
                </div>

                {/* Require Signal Valid */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Require Signal Valid</span>
                    <span onMouseEnter={() => setActiveTooltip('signalvalid')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: required</span>
                  </div>
                  {activeTooltip === 'signalvalid' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Require signal_valid=True to trade. Disable to allow invalid signals (not recommended).
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={settings.require_signal_valid} onChange={(e) => setSettings({...settings, require_signal_valid: e.target.checked})} style={{ cursor: 'pointer' }} />
                      <span style={{ color: '#fff', fontSize: '12px' }}>{settings.require_signal_valid ? 'Required' : 'Optional'}</span>
                    </label>
                  </div>
                </div>

                {/* Require Direction */}
                <div style={{ padding: '10px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '5px', marginBottom: '8px' }}>
                    <span style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold' }}>Require Direction</span>
                    <span onMouseEnter={() => setActiveTooltip('direction')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '11px' }}>ℹ️</span>
                    <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>default: required</span>
                  </div>
                  {activeTooltip === 'direction' && (
                    <div style={{ fontSize: '10px', color: '#6b7280', marginBottom: '5px', padding: '5px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                      Require LONG/SHORT direction to trade. Disable to allow NEUTRAL signals (not recommended).
                    </div>
                  )}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    <label style={{ display: 'flex', alignItems: 'center', gap: '5px', cursor: 'pointer' }}>
                      <input type="checkbox" checked={settings.require_direction} onChange={(e) => setSettings({...settings, require_direction: e.target.checked})} style={{ cursor: 'pointer' }} />
                      <span style={{ color: '#fff', fontSize: '12px' }}>{settings.require_direction ? 'Required' : 'Optional'}</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Signal Component Parameters */}
              <div style={{ marginTop: '15px', padding: '10px', background: 'rgba(0,0,0,0.15)', borderRadius: '6px' }}>
                <div style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold', marginBottom: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }}>
                  📊 Signal Component Parameters
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                  {/* TSMOM Percentile Entry */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>TSMOM %</span>
                      <span onMouseEnter={() => setActiveTooltip('tsmom')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 0.667</span>
                    </div>
                    {activeTooltip === 'tsmom' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Min TSMOM percentile for momentum.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="95" value={settings.tsmom_percentile * 100} onChange={(e) => setSettings({...settings, tsmom_percentile: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="0.95" step="0.01" value={settings.tsmom_percentile} onChange={(e) => setSettings({...settings, tsmom_percentile: parseFloat(e.target.value)})} style={{ width: '50px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Signal Cooldown Hours */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>Cooldown Hrs</span>
                      <span onMouseEnter={() => setActiveTooltip('cooldown_hrs')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 4</span>
                    </div>
                    {activeTooltip === 'cooldown_hrs' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Hours between trades.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="24" value={settings.cooldown_hours} onChange={(e) => setSettings({...settings, cooldown_hours: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="24" step="1" value={settings.cooldown_hours} onChange={(e) => setSettings({...settings, cooldown_hours: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Min OFI Clean Value */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>Min OFI</span>
                      <span onMouseEnter={() => setActiveTooltip('ofi')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 0.01</span>
                    </div>
                    {activeTooltip === 'ofi' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Min OFI clean value.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="-400" max="100" value={settings.min_ofi_clean * 100} onChange={(e) => setSettings({...settings, min_ofi_clean: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="-4" max="1" step="0.01" value={settings.min_ofi_clean} onChange={(e) => setSettings({...settings, min_ofi_clean: parseFloat(e.target.value)})} style={{ width: '55px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Min MRR Rho */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>Min MRR</span>
                      <span onMouseEnter={() => setActiveTooltip('mrr')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 0.10</span>
                    </div>
                    {activeTooltip === 'mrr' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Min MRR autocorrelation.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="-100" max="100" value={settings.min_mrr_rho * 100} onChange={(e) => setSettings({...settings, min_mrr_rho: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="-1" max="1" step="0.01" value={settings.min_mrr_rho} onChange={(e) => setSettings({...settings, min_mrr_rho: parseFloat(e.target.value)})} style={{ width: '50px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Min CO Value */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>Min CO</span>
                      <span onMouseEnter={() => setActiveTooltip('co')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 0.0</span>
                    </div>
                    {activeTooltip === 'co' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Min Carry-Over value.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="-100" max="100" value={settings.min_co_value * 100} onChange={(e) => setSettings({...settings, min_co_value: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="-1" max="1" step="0.01" value={settings.min_co_value} onChange={(e) => setSettings({...settings, min_co_value: parseFloat(e.target.value)})} style={{ width: '50px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Min Asymmetric Sharpe */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>Min Sharpe</span>
                      <span onMouseEnter={() => setActiveTooltip('sharpe')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 0.5</span>
                    </div>
                    {activeTooltip === 'sharpe' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Min asymmetric Sharpe.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="-200" max="500" value={settings.min_asymmetric_sharpe * 100} onChange={(e) => setSettings({...settings, min_asymmetric_sharpe: parseInt(e.target.value) / 100})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="-2" max="5" step="0.1" value={settings.min_asymmetric_sharpe} onChange={(e) => setSettings({...settings, min_asymmetric_sharpe: parseFloat(e.target.value)})} style={{ width: '50px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Min Probability-Weighted Score */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>Min Prob-Weighted Score</span>
                      <span onMouseEnter={() => setActiveTooltip('prob_weighted')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 35</span>
                    </div>
                    {activeTooltip === 'prob_weighted' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Min probability-weighted score (prob * composite_score).
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="100" value={settings.min_prob_weighted_score} onChange={(e) => setSettings({...settings, min_prob_weighted_score: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="100" step="1" value={settings.min_prob_weighted_score} onChange={(e) => setSettings({...settings, min_prob_weighted_score: parseFloat(e.target.value)})} style={{ width: '50px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Regime Thresholds */}
              <div style={{ marginTop: '15px', padding: '10px', background: 'rgba(0,0,0,0.15)', borderRadius: '6px' }}>
                <div style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold', marginBottom: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }}>
                  🎯 Regime-Specific Signal Thresholds
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
                  {/* Regime 1 - Bullish */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#22c55e', fontSize: '11px', fontWeight: 'bold' }}>R1: Bullish</span>
                      <span onMouseEnter={() => setActiveTooltip('r1')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 70</span>
                    </div>
                    {activeTooltip === 'r1' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Lower threshold for momentum.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="100" value={settings.regime_1_threshold} onChange={(e) => setSettings({...settings, regime_1_threshold: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="100" step="1" value={settings.regime_1_threshold} onChange={(e) => setSettings({...settings, regime_1_threshold: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Regime 2 - Bull Volatile */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#eab308', fontSize: '11px', fontWeight: 'bold' }}>R2: Bull Vol</span>
                      <span onMouseEnter={() => setActiveTooltip('r2')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 75</span>
                    </div>
                    {activeTooltip === 'r2' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Bullish volatile regime.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="100" value={settings.regime_2_threshold} onChange={(e) => setSettings({...settings, regime_2_threshold: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="100" step="1" value={settings.regime_2_threshold} onChange={(e) => setSettings({...settings, regime_2_threshold: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Regime 3 - Range Bound */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#3b82f6', fontSize: '11px', fontWeight: 'bold' }}>R3: Range</span>
                      <span onMouseEnter={() => setActiveTooltip('r3')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 80</span>
                    </div>
                    {activeTooltip === 'r3' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Mean reversion threshold.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="100" value={settings.regime_3_threshold} onChange={(e) => setSettings({...settings, regime_3_threshold: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="100" step="1" value={settings.regime_3_threshold} onChange={(e) => setSettings({...settings, regime_3_threshold: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Regime 4 - High Volatility */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#f97316', fontSize: '11px', fontWeight: 'bold' }}>R4: High Vol</span>
                      <span onMouseEnter={() => setActiveTooltip('r4')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 85</span>
                    </div>
                    {activeTooltip === 'r4' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        High volatility safety threshold.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="100" value={settings.regime_4_threshold} onChange={(e) => setSettings({...settings, regime_4_threshold: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="100" step="1" value={settings.regime_4_threshold} onChange={(e) => setSettings({...settings, regime_4_threshold: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>

                  {/* Regime 5 - Crisis */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>R5: Crisis</span>
                      <span onMouseEnter={() => setActiveTooltip('r5')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 90</span>
                    </div>
                    {activeTooltip === 'r5' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Conservative crisis threshold.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="0" max="100" value={settings.regime_5_threshold} onChange={(e) => setSettings({...settings, regime_5_threshold: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="0" max="100" step="1" value={settings.regime_5_threshold} onChange={(e) => setSettings({...settings, regime_5_threshold: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Risk Management Parameters */}
              <div style={{ marginTop: '15px', padding: '10px', background: 'rgba(0,0,0,0.15)', borderRadius: '6px' }}>
                <div style={{ color: '#9ca3af', fontSize: '12px', fontWeight: 'bold', marginBottom: '12px', borderBottom: '1px solid rgba(255,255,255,0.1)', paddingBottom: '8px' }}>
                  ⚠️ Risk Management
                </div>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                  {/* Max Daily Trades */}
                  <div style={{ padding: '8px', background: 'rgba(0,0,0,0.2)', borderRadius: '6px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '3px', marginBottom: '6px' }}>
                      <span style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold' }}>Max Daily Trades</span>
                      <span onMouseEnter={() => setActiveTooltip('max_daily')} onMouseLeave={() => setActiveTooltip(null)} style={{ cursor: 'help', color: '#6b7280', fontSize: '10px' }}>ℹ️</span>
                      <span style={{ color: '#6b7280', fontSize: '9px', marginLeft: 'auto' }}>def: 5</span>
                    </div>
                    {activeTooltip === 'max_daily' && (
                      <div style={{ fontSize: '9px', color: '#6b7280', marginBottom: '4px', padding: '4px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px' }}>
                        Maximum trades per day. Prevents overtrading.
                      </div>
                    )}
                    <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
                      <input type="range" min="1" max="50" value={settings.max_daily_trades || 5} onChange={(e) => setSettings({...settings, max_daily_trades: parseInt(e.target.value)})} style={{ flex: 1, height: '6px' }} />
                      <input type="number" min="1" max="50" step="1" value={settings.max_daily_trades || 5} onChange={(e) => setSettings({...settings, max_daily_trades: parseInt(e.target.value)})} style={{ width: '45px', padding: '3px', background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.2)', borderRadius: '4px', color: '#fff', textAlign: 'center', fontSize: '10px' }} />
                    </div>
                  </div>
                </div>
              </div>

              {/* Save All Button */}
              <div style={{ marginTop: '15px', display: 'flex', gap: '10px' }}>
                <button
                  onClick={updateSettings}
                  disabled={settingsLoading}
                  style={{
                    flex: 1,
                    padding: '10px',
                    background: settingsLoading ? '#6b7280' : '#22c55e',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: settingsLoading ? 'not-allowed' : 'pointer',
                    fontSize: '13px',
                    fontWeight: 'bold'
                  }}
                >
                  {settingsLoading ? 'Saving All Settings...' : '💾 Save All Settings'}
                </button>
                <button
                  onClick={resetSettings}
                  style={{
                    padding: '10px 20px',
                    background: '#6b7280',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '13px'
                  }}
                >
                  Reset
                </button>
              </div>

              {settingsMessage && (
                <p style={{ 
                  color: settingsMessage.includes('Error') ? '#ef4444' : '#22c55e', 
                  fontSize: '12px', 
                  marginTop: '10px',
                  textAlign: 'center'
                }}>
                  {settingsMessage}
                </p>
              )}
            </div>

            {/* Trade Decision Diagnostics */}
            <div style={{ 
              padding: '15px', 
              background: 'rgba(255,255,255,0.05)', 
              borderRadius: '8px', 
              borderLeft: tradeDiagnostics?.can_trade ? "3px solid #22c55e" : "3px solid #ef4444",
              marginTop: '10px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                <span style={{ color: tradeDiagnostics?.can_trade ? '#22c55e' : '#ef4444', fontWeight: 'bold', fontSize: '14px' }}>
                  {tradeDiagnostics?.can_trade ? '🟢 READY TO TRADE' : '🔴 TRADE BLOCKED'}
                </span>
                <span style={{ color: '#6b7280', fontSize: '11px' }}>
                  {tradeDiagnostics?.signal_score ? `Score: ${tradeDiagnostics.signal_score}/105` : ''}
                </span>
              </div>

              {/* Blocking Reasons Summary */}
              {tradeDiagnostics?.blocking_reasons?.length > 0 && (
                <div style={{ 
                  padding: '8px 12px', 
                  background: 'rgba(239,68,68,0.1)', 
                  borderRadius: '6px', 
                  marginBottom: '12px',
                  border: '1px solid rgba(239,68,68,0.3)'
                }}>
                  <p style={{ color: '#ef4444', fontSize: '11px', fontWeight: 'bold', marginBottom: '4px' }}>
                    ⚠️ Blocking: {tradeDiagnostics.blocking_reasons.join(', ')}
                  </p>
                </div>
              )}

              {/* Signal Component Comparison */}
              {state?.latest_signal?.signal_metrics && (
                <div style={{ 
                  padding: '12px', 
                  background: 'rgba(0,0,0,0.2)', 
                  borderRadius: '6px', 
                  marginBottom: '12px'
                }}>
                  <p style={{ color: '#9ca3af', fontSize: '11px', fontWeight: 'bold', marginBottom: '8px' }}>
                    📊 Signal Components vs Thresholds
                  </p>
                  <div style={{ display: 'grid', gap: '6px', fontSize: '10px' }}>
                    {/* TSMOM */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#6b7280' }}>TSMOM Percentile:</span>
                      <span style={{ 
                        color: (state.latest_signal?.signal_metrics?.tsmom_percentile || 0) >= settings.tsmom_percentile ? '#22c55e' : '#ef4444',
                        fontWeight: 'bold' 
                      }}>
                        {(state.latest_signal?.signal_metrics?.tsmom_percentile || 0).toFixed(3)} ≥ {settings.tsmom_percentile}
                      </span>
                    </div>
                    {/* OFI */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#6b7280' }}>OFI Clean:</span>
                      <span style={{ 
                        color: (state.latest_signal?.signal_metrics?.ofi_clean || 0) >= settings.min_ofi_clean ? '#22c55e' : '#ef4444',
                        fontWeight: 'bold' 
                      }}>
                        {(state.latest_signal?.signal_metrics?.ofi_clean || 0).toFixed(3)} ≥ {settings.min_ofi_clean}
                      </span>
                    </div>
                    {/* MRR Rho */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#6b7280' }}>MRR Rho:</span>
                      <span style={{ 
                        color: (state.latest_signal?.signal_metrics?.mrr_rho || 0) >= settings.min_mrr_rho ? '#22c55e' : '#ef4444',
                        fontWeight: 'bold' 
                      }}>
                        {(state.latest_signal?.signal_metrics?.mrr_rho || 0).toFixed(3)} ≥ {settings.min_mrr_rho}
                      </span>
                    </div>
                    {/* CO Value */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#6b7280' }}>CO Value:</span>
                      <span style={{ 
                        color: (state.latest_signal?.signal_metrics?.co_value || 0) >= settings.min_co_value ? '#22c55e' : '#ef4444',
                        fontWeight: 'bold' 
                      }}>
                        {(state.latest_signal?.signal_metrics?.co_value || 0).toFixed(3)} ≥ {settings.min_co_value}
                      </span>
                    </div>
                    {/* Asymmetric Sharpe */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#6b7280' }}>Asymmetric Sharpe:</span>
                      <span style={{ 
                        color: (state.latest_signal?.asymmetric_payout_sharpe || 0) >= settings.min_asymmetric_sharpe ? '#22c55e' : '#ef4444',
                        fontWeight: 'bold' 
                      }}>
                        {(state.latest_signal?.asymmetric_payout_sharpe || 0).toFixed(3)} ≥ {settings.min_asymmetric_sharpe}
                      </span>
                    </div>
                    {/* Probability-Weighted Score */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <span style={{ color: '#6b7280' }}>Prob-Weighted Score:</span>
                      <span style={{ 
                        color: ((state.latest_signal?.probability_weighted || 0) * (state?.latest_signal?.composite_score || 0)) >= settings.min_prob_weighted_score ? '#22c55e' : '#ef4444',
                        fontWeight: 'bold' 
                      }}>
                        {((state.latest_signal?.probability_weighted || 0) * (state?.latest_signal?.composite_score || 0)).toFixed(2)} ≥ {settings.min_prob_weighted_score}
                      </span>
                    </div>
                    {/* Signal Score */}
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid rgba(255,255,255,0.1)', paddingTop: '6px', marginTop: '6px' }}>
                      <span style={{ color: '#9ca3af', fontWeight: 'bold' }}>Signal Score:</span>
                      <span style={{ 
                        color: (state?.latest_signal?.composite_score || 0) >= (state?.latest_signal?.regime === 1 ? settings.regime_1_threshold : state?.latest_signal?.regime === 2 ? settings.regime_2_threshold : state?.latest_signal?.regime === 3 ? settings.regime_3_threshold : state?.latest_signal?.regime === 4 ? settings.regime_4_threshold : settings.regime_5_threshold) ? '#22c55e' : '#ef4444',
                        fontWeight: 'bold' 
                      }}>
                        {state?.latest_signal?.composite_score || 0} / {state?.latest_signal?.regime === 1 ? settings.regime_1_threshold : state?.latest_signal?.regime === 2 ? settings.regime_2_threshold : state?.latest_signal?.regime === 3 ? settings.regime_3_threshold : state?.latest_signal?.regime === 4 ? settings.regime_4_threshold : settings.regime_5_threshold}
                      </span>
                    </div>
                  </div>
                </div>
              )}

              {/* Signal Component Checks */}
              {state?.latest_signal && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '8px', marginBottom: '12px' }}>
                  {/* TSMOM Percentile Check */}
                  {(() => {
                    const actual = state.latest_signal?.signal_metrics?.tsmom_percentile || 0;
                    const required = settings.tsmom_percentile;
                    const pass = actual >= required;
                    return (
                      <div style={{
                        padding: '8px',
                        background: pass ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        borderRadius: '6px',
                        border: `1px solid ${pass ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ color: pass ? '#22c55e' : '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>
                            {pass ? '✓' : '✗'} TSMOM %
                          </span>
                          <span style={{ color: '#6b7280', fontSize: '10px' }}>
                            {actual.toFixed(3)} / ≥{required}
                          </span>
                        </div>
                        <span style={{ color: '#9ca3af', fontSize: '9px' }}>
                          {pass ? 'TSMOM percentile meets threshold' : 'TSMOM too low for signal'}
                        </span>
                      </div>
                    );
                  })()}

                  {/* OFI Clean Check */}
                  {(() => {
                    const actual = state.latest_signal?.signal_metrics?.ofi_clean || 0;
                    const required = settings.min_ofi_clean;
                    const pass = actual >= required;
                    return (
                      <div style={{
                        padding: '8px',
                        background: pass ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        borderRadius: '6px',
                        border: `1px solid ${pass ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ color: pass ? '#22c55e' : '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>
                            {pass ? '✓' : '✗'} OFI Clean
                          </span>
                          <span style={{ color: '#6b7280', fontSize: '10px' }}>
                            {actual.toFixed(3)} / ≥{required}
                          </span>
                        </div>
                        <span style={{ color: '#9ca3af', fontSize: '9px' }}>
                          {pass ? 'Order flow imbalance OK' : 'OFI too low for signal'}
                        </span>
                      </div>
                    );
                  })()}

                  {/* MRR Rho Check */}
                  {(() => {
                    const actual = state.latest_signal?.signal_metrics?.mrr_rho || 0;
                    const required = settings.min_mrr_rho;
                    const pass = actual >= required;
                    return (
                      <div style={{
                        padding: '8px',
                        background: pass ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        borderRadius: '6px',
                        border: `1px solid ${pass ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ color: pass ? '#22c55e' : '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>
                            {pass ? '✓' : '✗'} MRR Rho
                          </span>
                          <span style={{ color: '#6b7280', fontSize: '10px' }}>
                            {actual.toFixed(3)} / ≥{required}
                          </span>
                        </div>
                        <span style={{ color: '#9ca3af', fontSize: '9px' }}>
                          {pass ? 'Autocorrelation meets threshold' : 'MRR rho too low'}
                        </span>
                      </div>
                    );
                  })()}

                  {/* CO Value Check */}
                  {(() => {
                    const actual = state.latest_signal?.signal_metrics?.co_value || 0;
                    const required = settings.min_co_value;
                    const pass = actual >= required;
                    return (
                      <div style={{
                        padding: '8px',
                        background: pass ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        borderRadius: '6px',
                        border: `1px solid ${pass ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ color: pass ? '#22c55e' : '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>
                            {pass ? '✓' : '✗'} CO Value
                          </span>
                          <span style={{ color: '#6b7280', fontSize: '10px' }}>
                            {actual.toFixed(3)} / ≥{required}
                          </span>
                        </div>
                        <span style={{ color: '#9ca3af', fontSize: '9px' }}>
                          {pass ? 'Carry-over meets threshold' : 'CO value too low'}
                        </span>
                      </div>
                    );
                  })()}

                  {/* Signal Score Check */}
                  {(() => {
                    const actual = state?.latest_signal?.composite_score || 0;
                    const regime = state?.latest_signal?.regime || 1;
                    const required = regime === 1 ? settings.regime_1_threshold :
                                    regime === 2 ? settings.regime_2_threshold :
                                    regime === 3 ? settings.regime_3_threshold :
                                    regime === 4 ? settings.regime_4_threshold :
                                    settings.regime_5_threshold;
                    const pass = actual >= required;
                    return (
                      <div style={{
                        padding: '8px',
                        background: pass ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)',
                        borderRadius: '6px',
                        border: `1px solid ${pass ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px'
                      }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <span style={{ color: pass ? '#22c55e' : '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>
                            {pass ? '✓' : '✗'} Score vs R{regime}
                          </span>
                          <span style={{ color: '#6b7280', fontSize: '10px' }}>
                            {actual} / ≥{required}
                          </span>
                        </div>
                        <span style={{ color: '#9ca3af', fontSize: '9px' }}>
                          {pass ? `Score meets regime ${regime} threshold` : `Score below regime ${regime} threshold`}
                        </span>
                      </div>
                    );
                  })()}
                </div>
              )}

              {/* Detailed Checks Grid */}
              {tradeDiagnostics?.checks && (
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '8px' }}>
                  {tradeDiagnostics.checks.map((check, idx) => (
                    <div key={idx} style={{ 
                      padding: '8px', 
                      background: check.status === 'pass' ? 'rgba(34,197,94,0.1)' : 'rgba(239,68,68,0.1)', 
                      borderRadius: '6px',
                      border: `1px solid ${check.status === 'pass' ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)'}`,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '2px'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <span style={{ color: check.status === 'pass' ? '#22c55e' : '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>
                          {check.status === 'pass' ? '✓' : '✗'} {check.name}
                        </span>
                        <span style={{ color: '#6b7280', fontSize: '10px' }}>
                          {check.actual} / {check.required}
                        </span>
                      </div>
                      <span style={{ color: '#9ca3af', fontSize: '9px' }}>
                        {check.detail}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {!tradeDiagnostics && (
                <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>
                  <p style={{ fontSize: '12px' }}>Loading trade diagnostics...</p>
                </div>
              )}

              {tradeDiagnostics?.status === 'no_signal' && (
                <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>
                  <p style={{ fontSize: '12px' }}>{tradeDiagnostics.message}</p>
                </div>
              )}
            </div>

            {/* Active Layers */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
              {/* Layer 2 - Feature Engineering */}
              <div style={{ padding: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', borderLeft: '3px solid #3b82f6' }}>
                <p style={{ color: '#3b82f6', fontSize: '11px', fontWeight: 'bold' }}>L2: Feature Engineering</p>
                <p style={{ color: '#9ca3af', fontSize: '10px' }}>Computing TSMOM, ADX, OBV, BB Width...</p>
                <p style={{ color: '#22c55e', fontSize: '10px' }}>✓ Active</p>
              </div>

              {/* Layer 3 - Regime Detection */}
              <div style={{ padding: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', borderLeft: "3px solid #8b5cf6" }}>
                <p style={{ color: '#8b5cf6', fontSize: '11px', fontWeight: 'bold' }}>L3: Regime Detection</p>
                <p style={{ color: '#fff', fontSize: '10px' }}>Regime: {state.regime?.regime || 'N/A'}</p>
                <p style={{ color: state.regime?.entries_allowed ? '#22c55e' : '#ef4444', fontSize: '10px' }}>
                  {state.regime?.entries_allowed ? '✓ Entries Allowed' : '✗ Entries Blocked'}
                </p>
              </div>

              {/* Layer 4 - Signal Generation */}
              <div style={{ padding: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', borderLeft: "3px solid #f59e0b" }}>
                <p style={{ color: '#f59e0b', fontSize: '11px', fontWeight: 'bold' }}>L4: Signal Generation</p>
                <p style={{ color: '#fff', fontSize: '10px' }}>Direction: {state.latest_signal.direction || 'NEUTRAL'}</p>
                <p style={{ color: state.latest_signal.signal_valid ? '#22c55e' : '#ef4444', fontSize: '10px' }}>
                  {state.latest_signal.signal_valid ? '✓ Valid Signal' : '✗ Invalid Signal'}
                </p>
              </div>

              {/* Layer 8 - Strategy Validity */}
              <div style={{ padding: '10px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px', borderLeft: "3px solid #ef4444" }}>
                <p style={{ color: '#ef4444', fontSize: '11px', fontWeight: 'bold' }}>L8: Strategy Validity</p>
                <p style={{ color: '#fff', fontSize: '10px' }}>
                  PSR: {state.metrics?.psr_sr0?.toFixed(2) || '0.50'} | DSR: {state.metrics?.dsr?.toFixed(2) || '0.50'}
                </p>
                {state.validity_bootstrap && (
                  <p style={{ color: '#f59e0b', fontSize: '10px' }}>🚀 Bootstrap Mode ({state.validity_bootstrap_count || 0}/5)</p>
                )}
              </div>
            </div>

            {/* Component Scores */}
            {state.latest_signal.component_scores && Object.keys(state.latest_signal.component_scores).length > 0 && (
              <div style={{ marginTop: '15px', padding: '10px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px' }}>
                <p style={{ color: '#9ca3af', fontSize: '11px', marginBottom: '8px' }}>Component Scores:</p>
                <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                  {Object.entries(state.latest_signal.component_scores).map(([key, score]) => (
                    <span key={key} style={{ 
                      padding: '4px 8px', 
                      background: 'rgba(59, 130, 246, 0.2)', 
                      borderRadius: '4px', 
                      fontSize: '10px',
                      color: '#3b82f6'
                    }}>
                      {key}: {score}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>
            <p>Signal calculation initializing...</p>
            <p style={{ fontSize: '11px', marginTop: '5px' }}>Waiting for first signal from backend</p>
          </div>
        )}
      </div>

      {/* TradingView Live Chart */}
      <div style={{
        width: '100%',
        height: '400px',
        background: 'rgba(0,0,0,0.2)',
        borderRadius: '8px',
        marginBottom: '15px',
        overflow: 'hidden'
      }}>
        <iframe
          src="https://s.tradingview.com/widgetembed/?frameElementId=tradingview_chart&symbol=BINANCE:BTCUSDT&interval=1&hidesidetoolbar=1&symboledit=0&saveimage=0&toolbarbg=f1f3f6&studies=[]&theme=dark&style=1&timezone=exchange&withdateranges=1&hideideas=1&hideideasbutton=1&showpopupbutton=1&studies_overrides={}&overrides={}&enabled_features=[]&disabled_features=[]&locale=en&utm_source=&utm_medium=widget&utm_campaign=chart&utm_term="
          style={{
            width: '100%',
            height: '100%',
            border: 'none'
          }}
          allowTransparency
          frameBorder="0"
          scrolling="no"
          title="TradingView BTC Chart"
        />
      </div>
      
      {/* Chart info */}
      <div style={{
        padding: '5px 10px',
        background: 'rgba(255,255,255,0.05)',
        borderRadius: '4px',
        marginBottom: '10px',
        fontSize: '12px',
        color: '#6b7280',
        display: 'flex',
        justifyContent: 'space-between'
      }}>
        <span>Candles: {candles.length} | Timeframe: {timeframe}</span>
        <span style={{ color: '#22c55e' }}>● Binance LIVE</span>
      </div>

      {/* Open Position Display */}
      {state && state.positions && state.positions.length > 0 && state.positions.filter(p => p.status === 'OPEN' || p.state === 'OPEN').length > 0 && (
        <div style={{
          padding: '12px',
          background: 'rgba(34, 197, 94, 0.1)',
          borderRadius: '8px',
          marginBottom: '15px',
          border: '1px solid rgba(34, 197, 94, 0.3)'
        }}>
          <p style={{ color: '#22c55e', fontSize: '12px', fontWeight: 'bold', marginBottom: '8px' }}>
            📊 Open Position
          </p>
          {state.positions.filter(p => p.status === 'OPEN' || p.state === 'OPEN').map((pos, idx) => {
            // Calculate live P&L based on entry price and current price
            const entryPrice = Number(pos.entry_price);
            const currentPrice = Number(state.current_price);
            const positionSize = Number(pos.size || pos.position_size_btc || 0);
            let livePnl = 0;

            if (pos.direction === 'LONG') {
              livePnl = (currentPrice - entryPrice) * positionSize;
            } else {
              livePnl = (entryPrice - currentPrice) * positionSize;
            }

            return (
              <div key={idx} style={{ display: 'grid', gap: '4px', fontSize: '11px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>Direction:</span>
                  <span style={{ color: pos.direction === 'LONG' ? '#22c55e' : '#ef4444', fontWeight: 'bold' }}>
                    {pos.direction}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>Entry:</span>
                  <span style={{ color: '#22c55e', fontWeight: 'bold' }}>
                    ${entryPrice.toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>TP1:</span>
                  <span style={{ color: '#3b82f6', fontWeight: 'bold' }}>
                    ${Number(pos.take_profit_1 || pos.take_profit || pos.risk_levels?.take_profit_1).toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>TP2:</span>
                  <span style={{ color: '#8b5cf6', fontWeight: 'bold' }}>
                    ${Number(pos.take_profit_2 || pos.risk_levels?.take_profit_2).toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>SL:</span>
                  <span style={{ color: '#ef4444', fontWeight: 'bold' }}>
                    ${Number(pos.stop_loss || pos.risk_levels?.stop_loss).toFixed(2)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: '#6b7280' }}>P&L:</span>
                  <span style={{ color: livePnl >= 0 ? '#22c55e' : '#ef4444', fontWeight: 'bold' }}>
                    ${livePnl >= 0 ? '+' : ''}${livePnl.toFixed(2)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
      
      <div style={{ 
        fontSize: '11px', 
        color: '#6b7280', 
        marginBottom: '20px',
        textAlign: 'center' 
      }}>
        Live market data from Binance. Updates every 2 seconds.
      </div>

      {/* CURRENT SIGNAL - Always visible */}
      {state && (
        <div style={{ 
          marginBottom: '20px',
          padding: '20px',
          borderRadius: '12px',
          background: state.latest_signal ? 
            (state.latest_signal.direction === 'LONG' ? 'linear-gradient(135deg, rgba(34, 197, 94, 0.2) 0%, rgba(34, 197, 94, 0.05) 100%)' : 
             state.latest_signal.direction === 'SHORT' ? 'linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(239, 68, 68, 0.05) 100%)' :
             'linear-gradient(135deg, rgba(156, 163, 175, 0.2) 0%, rgba(156, 163, 175, 0.05) 100%)') :
            'linear-gradient(135deg, rgba(156, 163, 175, 0.2) 0%, rgba(156, 163, 175, 0.05) 100%)',
          border: `3px solid ${state.latest_signal ? 
            (state.latest_signal.direction === 'LONG' ? '#22c55e' : 
             state.latest_signal.direction === 'SHORT' ? '#ef4444' : '#9ca3af') : '#9ca3af'}`,
          textAlign: 'center'
        }}>
          <h2 style={{ 
            margin: '0 0 15px 0', 
            fontSize: '14px', 
            color: '#9ca3af',
            textTransform: 'uppercase',
            letterSpacing: '2px'
          }}>
            🎯 Current Signal
          </h2>
          
          {state.latest_signal ? (
            <div>
              <div style={{ 
                fontSize: '48px', 
                fontWeight: 'bold',
                color: state.latest_signal.direction === 'LONG' ? '#22c55e' : 
                       state.latest_signal.direction === 'SHORT' ? '#ef4444' : '#9ca3af',
                marginBottom: '10px'
              }}>
                {state.latest_signal.direction}
              </div>
              
              <div style={{ 
                display: 'grid', 
                gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                gap: '15px',
                marginTop: '15px',
                fontSize: '14px'
              }}>
                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '8px' }}>
                  <div style={{ color: '#9ca3af', fontSize: '12px' }}>Score</div>
                  <div style={{ fontWeight: 'bold', fontSize: '18px' }}>
                    {state.latest_signal.composite_score}/{state.latest_signal.max_possible_score}
                  </div>
                </div>
                
                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '8px' }}>
                  <div style={{ color: '#9ca3af', fontSize: '12px' }}>Probability</div>
                  <div style={{ fontWeight: 'bold', fontSize: '18px' }}>
                    {(state.latest_signal.probability_weighted * 100).toFixed(1)}%
                  </div>
                </div>
                
                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '8px' }}>
                  <div style={{ color: '#9ca3af', fontSize: '12px' }}>R:R Ratio</div>
                  <div style={{ fontWeight: 'bold', fontSize: '18px' }}>
                    {state.latest_signal.expected_rr?.toFixed(2)}
                  </div>
                </div>
                
                <div style={{ background: 'rgba(0,0,0,0.2)', padding: '10px', borderRadius: '8px' }}>
                  <div style={{ color: '#9ca3af', fontSize: '12px' }}>Valid</div>
                  <div style={{ fontWeight: 'bold', fontSize: '18px', color: state.latest_signal.signal_valid ? '#22c55e' : '#ef4444' }}>
                    {state.latest_signal.signal_valid ? '✅ YES' : '❌ NO'}
                  </div>
                </div>
              </div>
              
              {state.latest_signal.component_scores && (
                <div style={{ marginTop: '15px', textAlign: 'left' }}>
                  <div style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '8px' }}>Signal Components:</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                    {Object.entries(state.latest_signal.component_scores).map(([key, value]) => (
                      <span key={key} style={{ 
                        background: 'rgba(59, 130, 246, 0.2)', 
                        color: '#3b82f6',
                        padding: '4px 8px',
                        borderRadius: '4px',
                        fontSize: '11px'
                      }}>
                        {key}: {value}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              
              <div style={{ marginTop: '15px', fontSize: '12px', color: '#9ca3af' }}>
                Regime: {state.latest_signal.regime_name || 'N/A'} | 
                Threshold: {state.latest_signal.signal_threshold} {threshold === state.latest_signal.signal_threshold ? '(Dynamic)' : '(Auto)'} | 
                Cooldown: {state.latest_signal.cooldown_active ? '⏱️ Active' : '✓ Ready'}
              </div>
            </div>
          ) : (
            <div style={{ fontSize: '24px', color: '#6b7280', padding: '20px' }}>
              ⚠️ No Signal Generated Yet
              <div style={{ fontSize: '14px', marginTop: '10px', color: '#9ca3af' }}>
                The bot needs more price data to generate the first signal
              </div>
            </div>
          )}
        </div>
      )}

      {/* Stats Grid */}
      {state && (
        <div>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '15px', marginTop: '20px' }}>
            <div style={{ background: 'rgba(255,255,255,0.05)', padding: '15px', borderRadius: '8px' }}>
              <h3 style={{ color: '#3b82f6' }}>Price</h3>
              <p style={{ fontSize: '24px', fontWeight: 'bold' }}>${state.current_price?.toFixed(2) || 'N/A'}</p>
              <p style={{ color: '#9ca3af' }}>Spread: {state.current_spread?.toFixed(2) || 'N/A'}</p>
            </div>
            
            <div style={{ background: 'rgba(255,255,255,0.05)', padding: '15px', borderRadius: '8px' }}>
              <h3 style={{ color: '#8b5cf6' }}>Equity</h3>
              <p style={{ fontSize: '24px', fontWeight: 'bold' }}>${state.equity?.toFixed(2) || 'N/A'}</p>
              <p style={{ color: state.drawdown_pct > 0.05 ? '#ef4444' : '#22c55e' }}>
                Drawdown: {(state.drawdown_pct * 100)?.toFixed(2) || 0}%
              </p>
            </div>
            
            <div style={{ background: 'rgba(255,255,255,0.05)', padding: '15px', borderRadius: '8px' }}>
              <h3 style={{ color: '#22c55e' }}>Regime</h3>
              <p style={{ fontSize: '18px', fontWeight: 'bold' }}>{state.regime?.regime_name || 'N/A'}</p>
              <p style={{ color: '#9ca3af' }}>Trading: {state.regime?.entries_allowed ? '✅ Allowed' : '❌ Blocked'}</p>
            </div>
            
            <div style={{ background: 'rgba(255,255,255,0.05)', padding: '15px', borderRadius: '8px' }}>
              <h3 style={{ color: '#f59e0b' }}>Positions</h3>
              <p style={{ fontSize: '24px', fontWeight: 'bold' }}>{state.open_positions || 0}</p>
              <p style={{ color: '#9ca3af' }}>Open Trades</p>
            </div>
          </div>

          {/* Performance Metrics */}
          <div style={{ marginTop: '20px', padding: '20px', background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1), rgba(139, 92, 246, 0.1))', borderRadius: '12px', border: '1px solid rgba(59, 130, 246, 0.3)' }}>
            <h3 style={{ color: '#3b82f6', marginBottom: '15px', fontSize: '18px' }}>📊 Performance Metrics</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '15px' }}>
              {/* Use backend equity value */}
              {(() => {
                const backendEquity = state.equity || state.current_equity || 10000;
                const startingEquity = state.starting_equity || 10000;
                const accountBlownUp = backendEquity <= 0;

                return (
                  <>
                    <div style={{ textAlign: 'center', padding: '12px', background: accountBlownUp ? 'rgba(239, 68, 68, 0.2)' : 'rgba(255,255,255,0.05)', borderRadius: '8px', border: accountBlownUp ? '1px solid rgba(239, 68, 68, 0.5)' : 'none' }}>
                      <p style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '5px' }}>
                        Total Balance {accountBlownUp && '🚨 BLOWN UP'}
                      </p>
                      <p style={{ fontSize: '20px', fontWeight: 'bold', color: accountBlownUp ? '#ef4444' : backendEquity >= startingEquity ? '#22c55e' : '#f59e0b' }}>
                        ${backendEquity.toFixed(2)}
                      </p>
                      {accountBlownUp && (
                        <p style={{ color: '#ef4444', fontSize: '10px', marginTop: '2px' }}>
                          Account wiped out
                        </p>
                      )}
                    </div>
                  </>
                );
              })()}
              <div style={{ textAlign: 'center', padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                <p style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '5px' }}>Total P&L</p>
                {(() => {
                  const startingEquity = state.starting_equity || 10000;
                  let unrealizedPnl = 0;
                  let totalFees = 0;

                  // Calculate unrealized P&L from open positions and track fees
                  if (state.positions && state.positions.length > 0) {
                    state.positions.filter(p => p.status === 'OPEN' || p.state === 'OPEN').forEach(pos => {
                      const entryPrice = Number(pos.entry_price);
                      const currentPrice = Number(state.current_price);
                      const positionSize = Number(pos.size || pos.position_size_btc || 0);

                      if (pos.direction === 'LONG') {
                        unrealizedPnl += (currentPrice - entryPrice) * positionSize;
                      } else {
                        unrealizedPnl += (entryPrice - currentPrice) * positionSize;
                      }

                      // Track entry fees (0.1% of position value as example)
                      const positionValue = entryPrice * positionSize;
                      totalFees += positionValue * 0.001; // 0.1% fee
                    });
                  }

                  const realizedPnl = state.total_pnl || 0;
                  const liveTotalPnl = realizedPnl + unrealizedPnl - totalFees;

                  return (
                    <p style={{ fontSize: '20px', fontWeight: 'bold', color: liveTotalPnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      {liveTotalPnl >= 0 ? '+' : ''}${liveTotalPnl.toFixed(2)}
                    </p>
                  );
                })()}
              </div>
              <div style={{ textAlign: 'center', padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                <p style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '5px' }}>Today's P&L</p>
                {(() => {
                  let unrealizedPnl = 0;

                  // Calculate unrealized P&L from open positions
                  if (state.positions && state.positions.length > 0) {
                    state.positions.filter(p => p.status === 'OPEN' || p.state === 'OPEN').forEach(pos => {
                      const entryPrice = Number(pos.entry_price);
                      const currentPrice = Number(state.current_price);
                      const positionSize = Number(pos.size || pos.position_size_btc || 0);

                      if (pos.direction === 'LONG') {
                        unrealizedPnl += (currentPrice - entryPrice) * positionSize;
                      } else {
                        unrealizedPnl += (entryPrice - currentPrice) * positionSize;
                      }
                    });
                  }

                  const todayRealizedPnl = state.daily_pnl || 0;
                  const liveTodayPnl = todayRealizedPnl + unrealizedPnl;

                  return (
                    <p style={{ fontSize: '20px', fontWeight: 'bold', color: liveTodayPnl >= 0 ? '#22c55e' : '#ef4444' }}>
                      {liveTodayPnl >= 0 ? '+' : ''}${liveTodayPnl.toFixed(2)}
                    </p>
                  );
                })()}
              </div>
              <div style={{ textAlign: 'center', padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                <p style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '5px' }}>Sharpe Ratio</p>
                <p style={{ fontSize: '20px', fontWeight: 'bold', color: '#8b5cf6' }}>{state.metrics?.sharpe_ratio?.toFixed(2) || '0.00'}</p>
              </div>
              <div style={{ textAlign: 'center', padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                <p style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '5px' }}>30D P&L</p>
                {(() => {
                  let unrealizedPnl = 0;

                  // Calculate unrealized P&L from open positions
                  if (state.positions && state.positions.length > 0) {
                    state.positions.filter(p => p.status === 'OPEN' || p.state === 'OPEN').forEach(pos => {
                      const entryPrice = Number(pos.entry_price);
                      const currentPrice = Number(state.current_price);
                      const positionSize = Number(pos.size || pos.position_size_btc || 0);

                      if (pos.direction === 'LONG') {
                        unrealizedPnl += (currentPrice - entryPrice) * positionSize;
                      } else {
                        unrealizedPnl += (entryPrice - currentPrice) * positionSize;
                      }
                    });
                  }

                  const pnl30d = state.pnl_30d || 0;
                  const livePnl30d = pnl30d + unrealizedPnl;

                  return (
                    <p style={{ fontSize: '20px', fontWeight: 'bold', color: livePnl30d >= 0 ? '#22c55e' : '#ef4444' }}>
                      {livePnl30d >= 0 ? '+' : ''}${livePnl30d.toFixed(2)}
                    </p>
                  );
                })()}
              </div>
              <div style={{ textAlign: 'center', padding: '12px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
                <p style={{ color: '#9ca3af', fontSize: '12px', marginBottom: '5px' }}>Total Fees</p>
                {(() => {
                  let totalFees = 0;

                  // Calculate fees from open positions (0.1% of position value)
                  if (state.positions && state.positions.length > 0) {
                    state.positions.filter(p => p.status === 'OPEN' || p.state === 'OPEN').forEach(pos => {
                      const entryPrice = Number(pos.entry_price);
                      const positionSize = Number(pos.size || pos.position_size_btc || 0);
                      const positionValue = entryPrice * positionSize;
                      totalFees += positionValue * 0.001; // 0.1% entry fee
                    });
                  }

                  // Add fees from closed trades (if available in trade history)
                  if (tradeHistory && tradeHistory.length > 0) {
                    tradeHistory.forEach(trade => {
                      if (trade.entry && trade.entry.price && trade.exit && trade.exit.price) {
                        const entryPrice = Number(trade.entry.price);
                        const exitPrice = Number(trade.exit.price);
                        const positionSize = Number(trade.size || 0);
                        const positionValue = entryPrice * positionSize;
                        totalFees += positionValue * 0.001 * 2; // Entry + exit fees
                      }
                    });
                  }

                  return (
                    <p style={{ fontSize: '20px', fontWeight: 'bold', color: '#f59e0b' }}>
                      ${totalFees.toFixed(2)}
                    </p>
                  );
                })()}
              </div>
            </div>
          </div>

          {/* Trade History - Closed Trades Only */}
          <div style={{ marginTop: '20px', padding: '20px', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <h3 style={{ color: '#f59e0b', marginBottom: '15px', fontSize: '18px' }}>📈 Trade History</h3>
            {tradeHistory && tradeHistory.length > 0 && tradeHistory.filter(t => t && (t.entry_price > 0 || t.entry?.price > 0)).length > 0 ? (
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
                      <th style={{ padding: '10px', textAlign: 'left', color: '#9ca3af' }}>Time</th>
                      <th style={{ padding: '10px', textAlign: 'left', color: '#9ca3af' }}>Symbol</th>
                      <th style={{ padding: '10px', textAlign: 'left', color: '#9ca3af' }}>Direction</th>
                      <th style={{ padding: '10px', textAlign: 'right', color: '#9ca3af' }}>Entry</th>
                      <th style={{ padding: '10px', textAlign: 'right', color: '#9ca3af' }}>Exit</th>
                      <th style={{ padding: '10px', textAlign: 'right', color: '#9ca3af' }}>P&L</th>
                      <th style={{ padding: '10px', textAlign: 'center', color: '#9ca3af' }}>Reason</th>
                      <th style={{ padding: '10px', textAlign: 'center', color: '#9ca3af' }}>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {/* Closed Trades Only */}
                    {tradeHistory.filter(t => t && (t.entry_price > 0 || t.entry?.price > 0)).slice(-10).reverse().map((trade, idx) => (
                      <tr key={`closed-${idx}`} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px', color: '#fff' }}>{new Date(trade.timestamp).toLocaleTimeString()}</td>
                        <td style={{ padding: '10px', color: '#fff' }}>{trade.symbol}</td>
                        <td style={{ padding: '10px', color: trade.direction === 'LONG' ? '#22c55e' : '#ef4444' }}>{trade.direction}</td>
                        <td style={{ padding: '10px', textAlign: 'right', color: '#fff' }}>${trade.entry_price ? Number(trade.entry_price).toFixed(2) : '-'}</td>
                        <td style={{ padding: '10px', textAlign: 'right', color: '#fff' }}>${trade.exit_price ? Number(trade.exit_price).toFixed(2) : '-'}</td>
                        <td style={{ padding: '10px', textAlign: 'right', color: Number(trade.pnl || 0) >= 0 ? '#22c55e' : '#ef4444' }}>
                          {Number(trade.pnl || 0) >= 0 ? '+' : ''}${Number(trade.pnl || 0).toFixed(2)}
                        </td>
                        <td style={{ padding: '10px', textAlign: 'center', color: trade.exit?.reason || trade.exit_reason ? '#f59e0b' : '#9ca3af' }}>
                          {trade.exit?.reason || trade.exit_reason || '-'}
                        </td>
                        <td style={{ padding: '10px', textAlign: 'center' }}>
                          <span style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            background: 'rgba(34, 197, 94, 0.2)',
                            color: '#22c55e'
                          }}>
                            CLOSED
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '20px', color: '#6b7280' }}>
                <p>No closed trades yet</p>
                <p style={{ fontSize: '11px', marginTop: '5px' }}>Closed trades will appear here with exit reasons (TP1, TP2, STOP_LOSS, TIME_EXPIRED)</p>
              </div>
            )}
          </div>

          {/* AutoQuant Validation Panel */}
          <div style={{ marginTop: '20px', padding: '20px', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h3 style={{ color: '#8b5cf6', margin: 0, fontSize: '18px' }}>🔬 AutoQuant Validation (Deng 2025)</h3>
              {autoquantStatus?.is_running && (
                <span style={{ color: '#f59e0b', fontSize: '12px' }}>⏳ Running...</span>
              )}
              {autoquantResult?.passed && (
                <span style={{ color: '#22c55e', fontSize: '12px' }}>✅ VALIDATED</span>
              )}
            </div>

            {/* AutoQuant running message */}
            {autoquantStatus?.is_running && (
              <div style={{ marginBottom: '20px', padding: '15px', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '8px', border: '1px solid rgba(245, 158, 11, 0.3)' }}>
                <p style={{ color: '#f59e0b', fontSize: '13px', margin: 0, textAlign: 'center' }}>
                  🔬 AutoQuant validation running in background (estimated 5-10 minutes)
                </p>
                <p style={{ color: '#9ca3af', fontSize: '11px', margin: '5px 0 0 0', textAlign: 'center' }}>
                  Running: T+1 execution, Cost-ablation ladder, PBO diagnostic, Bootstrap CI, Cross-asset validation
                </p>
              </div>
            )}

            {/* Tabs */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
              {['status', 'metrics', 'report', 'trades'].map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveAutoquantTab(tab)}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '6px',
                    border: 'none',
                    background: activeAutoquantTab === tab ? 'rgba(139, 92, 246, 0.3)' : 'rgba(0,0,0,0.2)',
                    color: activeAutoquantTab === tab ? '#8b5cf6' : '#9ca3af',
                    cursor: 'pointer',
                    fontSize: '12px',
                    textTransform: 'capitalize'
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            {activeAutoquantTab === 'status' && autoquantResult && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '15px' }}>
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Win Rate</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (autoquantResult?.win_rate || 0) > 0.333 ? '#22c55e' : '#ef4444' }}>
                    {((autoquantResult?.win_rate || 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 33.3%</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Profit Factor</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (autoquantResult?.profit_factor || 0) > 1.5 ? '#22c55e' : '#ef4444' }}>
                    {(autoquantResult?.profit_factor || 0).toFixed(2)}
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 1.5</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Sharpe Ratio</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (autoquantResult?.sharpe_ratio || 0) > 1.0 ? '#22c55e' : '#ef4444' }}>
                    {(autoquantResult?.sharpe_ratio || 0).toFixed(2)}
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 1.0</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>PSR (95% conf)</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (autoquantResult?.psr_0 || 0) > 0.95 ? '#22c55e' : '#ef4444' }}>
                    {((autoquantResult?.psr_0 || 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 95%</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Max Drawdown</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (autoquantResult?.max_drawdown || 0) < 0.20 ? '#22c55e' : '#ef4444' }}>
                    {((autoquantResult?.max_drawdown || 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &lt; 20%</div>
                </div>
              </div>
            )}

            {activeAutoquantTab === 'status' && !autoquantResult && (
              <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>
                <p>No validation results available. Run AutoQuant validation first.</p>
              </div>
            )}

            {activeAutoquantTab === 'metrics' && autoquantResult && (
              <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                <p style={{ marginBottom: '10px' }}><strong>Statistical Moments:</strong></p>
                <p>Skewness: {autoquantResult.skewness?.toFixed(3) || 'N/A'}</p>
                <p>Kurtosis: {autoquantResult.kurtosis?.toFixed(1) || 'N/A'} (BTC typical: ~466)</p>
                <p style={{ marginTop: '15px', marginBottom: '10px' }}><strong>Trade Distribution:</strong></p>
                <p>Winning Trades: {autoquantResult.winning_trades || 0}</p>
                <p>Losing Trades: {autoquantResult.losing_trades || 0}</p>
                <p>PSR (SR*=1): {((autoquantResult.psr_1 || 0) * 100).toFixed(1)}%</p>
              </div>
            )}

            {activeAutoquantTab === 'report' && autoquantReport && (
              <pre style={{ fontSize: '11px', color: '#9ca3af', background: 'rgba(0,0,0,0.2)', padding: '15px', borderRadius: '8px', overflow: 'auto', maxHeight: '300px' }}>
                {autoquantReport}
              </pre>
            )}

            {activeAutoquantTab === 'report' && !autoquantReport && autoquantResult && (
              <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>
                <p>Report not available. Run validation to generate a report.</p>
              </div>
            )}

            {activeAutoquantTab === 'report' && !autoquantReport && !autoquantResult && (
              <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>
                <p>No validation results available. Run validation first.</p>
              </div>
            )}

            {activeAutoquantTab === 'trades' && autoquantTrades.length === 0 && (
              <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>
                <p>No trades available. Run validation to generate trades.</p>
              </div>
            )}

            {activeAutoquantTab === 'trades' && autoquantTrades.length > 0 && (
              <div style={{ overflow: 'auto', maxHeight: '400px' }}>
                <table style={{ width: '100%', fontSize: '11px', borderCollapse: 'collapse' }}>
                  <thead style={{ position: 'sticky', top: 0, background: '#1f2937' }}>
                    <tr style={{ borderBottom: '1px solid #374151' }}>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>#</th>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>Entry Date</th>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>Exit Date</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>Entry Price</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>Exit Price</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>TP</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>SL</th>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>Exit Reason</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>P&L %</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>P&L $</th>
                    </tr>
                  </thead>
                  <tbody>
                    {autoquantTrades.map((trade, index) => (
                      <tr key={index} style={{ borderBottom: '1px solid #374151' }}>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.trade_num || index + 1}</td>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.entry_date}</td>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.exit_date}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#e5e7eb' }}>${trade.entry_price ? trade.entry_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#e5e7eb' }}>${trade.exit_price ? trade.exit_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#22c55e' }}>${trade.take_profit_price ? trade.take_profit_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#ef4444' }}>${trade.stop_loss_price ? trade.stop_loss_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.exit_reason}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: trade.is_win ? '#22c55e' : '#ef4444' }}>{trade.pnl_pct ? (trade.pnl_pct * 100).toFixed(2) + '%' : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: trade.is_win ? '#22c55e' : '#ef4444' }}>${trade.pnl_dollar ? trade.pnl_dollar.toFixed(2) : 'N/A'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!autoquantResult && !autoquantStatus?.is_running && (
              <div style={{ textAlign: 'center', padding: '30px' }}>
                <p style={{ color: '#6b7280', fontSize: '14px', marginBottom: '15px' }}>
                  Run comprehensive AutoQuant validation (Deng 2025)
                </p>
                <button
                  onClick={startAutoquant}
                  disabled={autoquantLoading}
                  style={{
                    background: '#8b5cf6',
                    color: 'white',
                    border: 'none',
                    padding: '12px 24px',
                    borderRadius: '8px',
                    cursor: autoquantLoading ? 'not-allowed' : 'pointer',
                    fontSize: '14px',
                    fontWeight: 'bold'
                  }}
                >
                  {autoquantLoading ? 'Starting...' : '🔬 Start AutoQuant Validation'}
                </button>
                <button
                  onClick={resetAutoquant}
                  style={{
                    background: '#ef4444',
                    color: 'white',
                    border: 'none',
                    padding: '12px 24px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: 'bold',
                    marginLeft: '10px'
                  }}
                >
                  🔄 Reset
                </button>
                <p style={{ color: '#6b7280', fontSize: '11px', marginTop: '10px' }}>
                  T+1 execution, Cost-ablation ladder, PBO diagnostic, Bootstrap CI, Cross-asset validation<br/>
                  Based on Deng (2025, arXiv:2512.22476)<br/>
                  Estimated time: 5-10 minutes
                </p>
              </div>
            )}

            {/* Overall Status */}
            {autoquantResult && (
              <div style={{ 
                marginTop: '15px', 
                padding: '12px', 
                borderRadius: '8px', 
                textAlign: 'center',
                background: autoquantResult.passed ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                border: `1px solid ${autoquantResult.passed ? '#22c55e' : '#ef4444'}`
              }}>
                <span style={{ 
                  fontSize: '14px', 
                  fontWeight: 'bold',
                  color: autoquantResult.passed ? '#22c55e' : '#ef4444'
                }}>
                  {autoquantResult.passed ? '✅ STRATEGY VALIDATED - You can turn OFF Bootstrap Mode' : '❌ NEEDS OPTIMIZATION - Continue Bootstrap Mode'}
                </span>
                <button
                  onClick={resetAutoquant}
                  style={{
                    background: '#ef4444',
                    color: 'white',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    fontWeight: 'bold',
                    marginLeft: '15px'
                  }}
                >
                  🔄 Reset
                </button>
              </div>
            )}
          </div>

          {/* 300-Trade Backtest Validation Panel */}
          <div style={{ marginTop: '20px', padding: '20px', background: 'rgba(255,255,255,0.05)', borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h3 style={{ color: '#8b5cf6', margin: 0, fontSize: '18px' }}>📊 300-Trade Statistical Validation</h3>
              {backtestStatus?.is_running && (
                <span style={{ color: '#f59e0b', fontSize: '12px' }}>⏳ Running...</span>
              )}
              {backtestResult?.passed && (
                <span style={{ color: '#22c55e', fontSize: '12px' }}>✅ VALIDATED</span>
              )}
            </div>
            
            {/* Progress Bar */}
            {backtestStatus?.is_running && (
              <div style={{ marginBottom: '20px' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '5px', fontSize: '12px', color: '#9ca3af' }}>
                  <span>Progress: {backtestStatus?.trades_completed || 0} / 300 trades</span>
                  <span>{backtestStatus?.progress_pct || 0}%</span>
                </div>
                <div style={{ width: '100%', height: '8px', background: 'rgba(0,0,0,0.3)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ 
                    width: `${backtestStatus?.progress_pct || 0}%`, 
                    height: '100%', 
                    background: backtestResult?.passed ? '#22c55e' : '#8b5cf6',
                    transition: 'width 0.3s ease'
                  }} />
                </div>
              </div>
            )}
            
            {/* Tabs */}
            <div style={{ display: 'flex', gap: '10px', marginBottom: '15px' }}>
              {['status', 'metrics', 'report', 'trades'].map(tab => (
                <button
                  key={tab}
                  onClick={() => setActiveBacktestTab(tab)}
                  style={{
                    padding: '8px 16px',
                    borderRadius: '6px',
                    border: 'none',
                    background: activeBacktestTab === tab ? 'rgba(139, 92, 246, 0.3)' : 'rgba(0,0,0,0.2)',
                    color: activeBacktestTab === tab ? '#8b5cf6' : '#9ca3af',
                    cursor: 'pointer',
                    fontSize: '12px',
                    textTransform: 'capitalize'
                  }}
                >
                  {tab}
                </button>
              ))}
            </div>

            {/* Tab Content */}
            {activeBacktestTab === 'status' && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '15px' }}>
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Win Rate</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (backtestResult?.win_rate || 0) > 0.333 ? '#22c55e' : '#ef4444' }}>
                    {((backtestResult?.win_rate || 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 33.3%</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Profit Factor</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (backtestResult?.profit_factor || 0) > 1.5 ? '#22c55e' : '#ef4444' }}>
                    {(backtestResult?.profit_factor || 0).toFixed(2)}
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 1.5</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Sharpe Ratio</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (backtestResult?.sharpe_ratio || 0) > 1.0 ? '#22c55e' : '#ef4444' }}>
                    {(backtestResult?.sharpe_ratio || 0).toFixed(2)}
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 1.0</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>PSR (95% conf)</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (backtestResult?.psr_0 || 0) > 0.95 ? '#22c55e' : '#ef4444' }}>
                    {((backtestResult?.psr_0 || 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &gt; 95%</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Max Drawdown</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (backtestResult?.max_drawdown || 0) < 0.20 ? '#22c55e' : '#ef4444' }}>
                    {((backtestResult?.max_drawdown || 0) * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need &lt; 20%</div>
                </div>
                
                <div style={{ padding: '15px', background: 'rgba(0,0,0,0.2)', borderRadius: '8px', textAlign: 'center' }}>
                  <div style={{ fontSize: '11px', color: '#9ca3af', marginBottom: '5px' }}>Total Trades</div>
                  <div style={{ fontSize: '20px', fontWeight: 'bold', color: (backtestResult?.total_trades || 0) >= 300 ? '#22c55e' : '#f59e0b' }}>
                    {backtestResult?.total_trades || 0}
                  </div>
                  <div style={{ fontSize: '10px', color: '#6b7280' }}>need ≥ 300</div>
                </div>
              </div>
            )}

            {activeBacktestTab === 'metrics' && backtestResult && (
              <div style={{ fontSize: '12px', color: '#9ca3af' }}>
                <p style={{ marginBottom: '10px' }}><strong>Statistical Moments:</strong></p>
                <p>Skewness: {backtestResult.skewness?.toFixed(3) || 'N/A'}</p>
                <p>Kurtosis: {backtestResult.kurtosis?.toFixed(1) || 'N/A'} (BTC typical: ~466)</p>
                <p style={{ marginTop: '15px', marginBottom: '10px' }}><strong>Trade Distribution:</strong></p>
                <p>Winning Trades: {backtestResult.winning_trades || 0}</p>
                <p>Losing Trades: {backtestResult.losing_trades || 0}</p>
                <p>PSR (SR*=1): {((backtestResult.psr_1 || 0) * 100).toFixed(1)}%</p>
              </div>
            )}

            {activeBacktestTab === 'report' && backtestReport && (
              <pre style={{ fontSize: '11px', color: '#9ca3af', background: 'rgba(0,0,0,0.2)', padding: '15px', borderRadius: '8px', overflow: 'auto', maxHeight: '300px' }}>
                {backtestReport}
              </pre>
            )}

            {activeBacktestTab === 'report' && !backtestReport && backtestResult && (
              <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>
                <p>Report not available. Run validation to generate a report.</p>
              </div>
            )}

            {activeBacktestTab === 'report' && !backtestReport && !backtestResult && (
              <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>
                <p>No validation results available. Run validation first.</p>
              </div>
            )}

            {activeBacktestTab === 'trades' && backtestTrades.length === 0 && (
              <div style={{ textAlign: 'center', padding: '30px', color: '#6b7280' }}>
                <p>No trades available. Run validation to generate trades.</p>
              </div>
            )}

            {activeBacktestTab === 'trades' && backtestTrades.length > 0 && (
              <div style={{ overflow: 'auto', maxHeight: '400px' }}>
                <table style={{ width: '100%', fontSize: '11px', borderCollapse: 'collapse' }}>
                  <thead style={{ position: 'sticky', top: 0, background: '#1f2937' }}>
                    <tr style={{ borderBottom: '1px solid #374151' }}>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>#</th>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>Entry Date</th>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>Exit Date</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>Entry Price</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>Exit Price</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>TP</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>SL</th>
                      <th style={{ padding: '8px', textAlign: 'left', color: '#9ca3af' }}>Exit Reason</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>P&L %</th>
                      <th style={{ padding: '8px', textAlign: 'right', color: '#9ca3af' }}>P&L $</th>
                    </tr>
                  </thead>
                  <tbody>
                    {backtestTrades.map((trade, index) => (
                      <tr key={index} style={{ borderBottom: '1px solid #374151' }}>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.trade_num || index + 1}</td>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.entry_date}</td>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.exit_date}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#e5e7eb' }}>${trade.entry_price ? trade.entry_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#e5e7eb' }}>${trade.exit_price ? trade.exit_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#22c55e' }}>${trade.take_profit_price ? trade.take_profit_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: '#ef4444' }}>${trade.stop_loss_price ? trade.stop_loss_price.toFixed(2) : 'N/A'}</td>
                        <td style={{ padding: '8px', color: '#e5e7eb' }}>{trade.exit_reason}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: trade.is_win ? '#22c55e' : '#ef4444' }}>{trade.pnl_pct ? (trade.pnl_pct * 100).toFixed(2) + '%' : 'N/A'}</td>
                        <td style={{ padding: '8px', textAlign: 'right', color: trade.is_win ? '#22c55e' : '#ef4444' }}>${trade.pnl_dollar ? trade.pnl_dollar.toFixed(2) : 'N/A'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            {!backtestResult && !backtestStatus?.is_running && (
              <div style={{ textAlign: 'center', padding: '30px' }}>
                <p style={{ color: '#6b7280', fontSize: '14px', marginBottom: '15px' }}>
                  Run 300-trade statistical validation with 700 days of historical data
                </p>
                <button
                  onClick={startBacktest}
                  disabled={backtestLoading}
                  style={{
                    background: '#8b5cf6',
                    color: 'white',
                    border: 'none',
                    padding: '12px 24px',
                    borderRadius: '8px',
                    cursor: backtestLoading ? 'not-allowed' : 'pointer',
                    fontSize: '14px',
                    fontWeight: 'bold'
                  }}
                >
                  {backtestLoading ? 'Starting...' : '📊 Start 300-Trade Validation'}
                </button>
                <button
                  onClick={resetBacktest}
                  style={{
                    background: '#ef4444',
                    color: 'white',
                    border: 'none',
                    padding: '12px 24px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontSize: '14px',
                    fontWeight: 'bold',
                    marginLeft: '10px'
                  }}
                >
                  🔄 Reset
                </button>
                <p style={{ color: '#6b7280', fontSize: '11px', marginTop: '10px' }}>
                  Uses 700 days of historical Binance data<br/>
                  Simulates 300 trades with real-time progress tracking<br/>
                  Estimated time: 2-3 minutes
                </p>
              </div>
            )}

            {/* Overall Status */}
            {backtestResult && (
              <div style={{ 
                marginTop: '15px', 
                padding: '12px', 
                borderRadius: '8px', 
                textAlign: 'center',
                background: backtestResult.passed ? 'rgba(34, 197, 94, 0.1)' : 'rgba(239, 68, 68, 0.1)',
                border: `1px solid ${backtestResult.passed ? '#22c55e' : '#ef4444'}`
              }}>
                <span style={{ 
                  fontSize: '14px', 
                  fontWeight: 'bold',
                  color: backtestResult.passed ? '#22c55e' : '#ef4444'
                }}>
                  {backtestResult.passed ? '✅ STRATEGY VALIDATED - You can turn OFF Bootstrap Mode' : '❌ NEEDS OPTIMIZATION - Continue Bootstrap Mode'}
                </span>
                <button
                  onClick={resetBacktest}
                  style={{
                    background: '#ef4444',
                    color: 'white',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    fontWeight: 'bold',
                    marginLeft: '15px'
                  }}
                >
                  🔄 Reset
                </button>
              </div>
            )}
          </div>

          {/* Latest Signal */}
          {state.latest_signal && (
            <div style={{ marginTop: '20px', padding: '15px', background: state.latest_signal.direction === 'LONG' ? 'rgba(34, 197, 94, 0.1)' : state.latest_signal.direction === 'SHORT' ? 'rgba(239, 68, 68, 0.1)' : 'rgba(255,255,255,0.05)', borderRadius: '8px', border: `2px solid ${state.latest_signal.direction === 'LONG' ? '#22c55e' : state.latest_signal.direction === 'SHORT' ? '#ef4444' : '#9ca3af'}` }}>
              <h3>Latest Signal</h3>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
                <p>Direction: <strong>{state.latest_signal.direction}</strong></p>
                <p>Score: {state.latest_signal.composite_score}/{state.latest_signal.max_possible_score}</p>
                <p>Valid: {state.latest_signal.signal_valid ? '✅' : '❌'}</p>
                <p>Regime: {state.latest_signal.regime_name}</p>
                <p>Probability: {(state.latest_signal.probability_weighted * 100)?.toFixed(1)}%</p>
                <p>R:R Ratio: {state.latest_signal.expected_rr?.toFixed(2)}</p>
              </div>
              {state.latest_signal.component_scores && (
                <div style={{ marginTop: '10px' }}>
                  <p style={{ color: '#9ca3af', fontSize: '12px' }}>Signal Components:</p>
                  <ul style={{ fontSize: '12px', color: '#9ca3af' }}>
                    {Object.entries(state.latest_signal.component_scores).map(([key, value]) => (
                      <li key={key}>{key}: {value} pts</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* 12 Layers */}
          <div style={{ marginTop: '20px', padding: '20px', background: 'rgba(255,255,255,0.05)', borderRadius: '8px' }}>
            <h3>12 Layers Active:</h3>
            <ul style={{ lineHeight: '1.8', color: '#9ca3af', display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '5px' }}>
              <li>✅ Layer 1: Data Ingestion</li>
              <li>✅ Layer 2: Feature Engineering</li>
              <li>✅ Layer 3: Regime Detection (5 regimes)</li>
              <li>✅ Layer 4: Signal Generation (105-point)</li>
              <li>✅ Layer 5: Risk Management (Kelly)</li>
              <li>✅ Layer 6: Execution (Paper Trading)</li>
              <li>✅ Layer 7: Performance Analytics</li>
              <li>✅ Layer 8: Strategy Validity</li>
              <li>✅ Layer 9: Jump-Diffusion</li>
              <li>✅ Layer 10: Microstructure (MRR, HARRVJ)</li>
              <li>✅ Layer 11: Prospect Theory</li>
              <li>✅ Layer 12: DQN Position Sizing</li>
            </ul>
          </div>
          
          <p style={{ marginTop: '20px', color: '#6b7280', fontSize: '12px' }}>
            Last updated: {new Date().toLocaleTimeString()}
          </p>
        </div>
      )}
    </div>
  );
}

export default App;
