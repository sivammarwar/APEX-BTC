import React, { useEffect, useRef } from 'react';
import { createChart, IChartApi, ISeriesApi, CandlestickData, LineData } from 'lightweight-charts';
import styled from 'styled-components';

const ChartContainer = styled.div`
  width: 100%;
  height: calc(100% - 40px);
  position: relative;
`;

interface PriceChartProps {
  state: any;
}

export const PriceChart: React.FC<PriceChartProps> = ({ state }) => {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const ema21Ref = useRef<ISeriesApi<'Line'> | null>(null);
  const ema200Ref = useRef<ISeriesApi<'Line'> | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
      layout: {
        background: { color: 'transparent' },
        textColor: '#9ca3af',
      },
      grid: {
        vertLines: { color: '#2a3142' },
        horzLines: { color: '#2a3142' },
      },
      crosshair: {
        mode: 1,
        vertLine: {
          color: '#3b82f6',
          labelBackgroundColor: '#3b82f6',
        },
        horzLine: {
          color: '#3b82f6',
          labelBackgroundColor: '#3b82f6',
        },
      },
      rightPriceScale: {
        borderColor: '#2a3142',
      },
      timeScale: {
        borderColor: '#2a3142',
        timeVisible: true,
      },
    });

    const candleSeries = chart.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderUpColor: '#10b981',
      borderDownColor: '#ef4444',
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });

    const ema21Series = chart.addLineSeries({
      color: '#3b82f6',
      lineWidth: 2,
      title: 'EMA 21',
    });

    const ema200Series = chart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      title: 'EMA 200',
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    ema21Ref.current = ema21Series;
    ema200Ref.current = ema200Series;

    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth,
          height: chartContainerRef.current.clientHeight,
        });
      }
    };

    window.addEventListener('resize', handleResize);
    handleResize();

    return () => {
      window.removeEventListener('resize', handleResize);
      chart.remove();
    };
  }, []);

  // Update chart when new data arrives
  useEffect(() => {
    if (!state?.regime || !candleSeriesRef.current) return;

    // In a real implementation, we'd fetch candle data from the API
    // For now, show current price as a marker
    const currentTime = new Date().getTime() / 1000;
    
    if (state.current_price) {
      candleSeriesRef.current.update({
        time: currentTime as any,
        open: state.current_price * 0.999,
        high: state.current_price * 1.001,
        low: state.current_price * 0.998,
        close: state.current_price,
      });
    }
  }, [state]);

  return <ChartContainer ref={chartContainerRef} />;
};
