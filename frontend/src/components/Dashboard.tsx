import React from 'react';
import styled from 'styled-components';
import { PriceChart } from './PriceChart';
import { RegimeIndicator } from './RegimeIndicator';
import { SignalPanel } from './SignalPanel';
import { PositionPanel } from './PositionPanel';
import { PerformancePanel } from './PerformancePanel';
import { RiskPanel } from './RiskPanel';
import { AlertsPanel } from './AlertsPanel';
import { useWebSocket } from '../hooks/useWebSocket';

const DashboardGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  grid-template-rows: auto auto auto;
  gap: 16px;
  max-width: 1800px;
  margin: 0 auto;
  
  @media (max-width: 1400px) {
    grid-template-columns: repeat(2, 1fr);
  }
  
  @media (max-width: 768px) {
    grid-template-columns: 1fr;
  }
`;

const ChartContainer = styled.div`
  grid-column: span 2;
  grid-row: span 2;
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
  min-height: 500px;
  
  @media (max-width: 1400px) {
    grid-column: span 2;
    grid-row: span 1;
  }
  
  @media (max-width: 768px) {
    grid-column: span 1;
    min-height: 400px;
  }
`;

const Panel = styled.div<{ span?: number }>`
  grid-column: span ${props => props.span || 1};
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  padding: 16px;
  min-height: 200px;
  
  @media (max-width: 768px) {
    grid-column: span 1;
  }
`;

const PanelHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  
  h3 {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text-primary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
`;

const LoadingOverlay = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--color-text-secondary);
  font-size: 14px;
`;

export const Dashboard: React.FC = () => {
  const { state, isConnected, error } = useWebSocket();

  if (error) {
    return (
      <LoadingOverlay>
        Connection error. Retrying...
      </LoadingOverlay>
    );
  }

  if (!state) {
    return (
      <LoadingOverlay>
        Connecting to APEX-BTC...
      </LoadingOverlay>
    );
  }

  return (
    <DashboardGrid>
      {/* Main Chart */}
      <ChartContainer>
        <PanelHeader>
          <h3>BTC/USD Price Action</h3>
          <span style={{ color: isConnected ? '#10b981' : '#ef4444', fontSize: '12px' }}>
            {isConnected ? '● Live' : '● Disconnected'}
          </span>
        </PanelHeader>
        <PriceChart state={state} />
      </ChartContainer>

      {/* Regime Indicator */}
      <Panel>
        <RegimeIndicator regime={state.regime} />
      </Panel>

      {/* Latest Signal */}
      <Panel>
        <SignalPanel signal={state.latest_signal} />
      </Panel>

      {/* Open Positions */}
      <Panel span={2}>
        <PositionPanel 
          positions={state.open_positions} 
          equity={state.equity}
        />
      </Panel>

      {/* Performance Metrics */}
      <Panel span={2}>
        <PerformancePanel metrics={state.metrics} />
      </Panel>

      {/* Risk State */}
      <Panel>
        <RiskPanel 
          equity={state.equity}
          highWaterMark={state.high_water_mark}
          drawdown={state.drawdown_pct}
          openPositions={state.open_positions}
        />
      </Panel>

      {/* Active Alerts */}
      <Panel>
        <AlertsPanel 
          alerts={state.active_alerts} 
          manualReview={state.manual_review_required}
        />
      </Panel>
    </DashboardGrid>
  );
};
