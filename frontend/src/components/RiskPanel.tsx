import React from 'react';
import styled from 'styled-components';
import { FaChartLine, FaShieldAlt } from 'react-icons/fa';

const Container = styled.div`
  height: 100%;
  display: flex;
  flex-direction: column;
`;

const Title = styled.h3`
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text-primary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 16px;
`;

const EquityDisplay = styled.div`
  background: linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(139, 92, 246, 0.1) 100%);
  border: 1px solid rgba(59, 130, 246, 0.3);
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 12px;
  
  .label {
    font-size: 12px;
    color: var(--color-text-secondary);
    text-transform: uppercase;
  }
  
  .value {
    font-size: 24px;
    font-weight: 700;
    color: var(--color-text-primary);
    margin-top: 4px;
  }
`;

const MetricsGrid = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
`;

const Metric = styled.div`
  background: rgba(255, 255, 255, 0.03);
  padding: 12px;
  border-radius: 8px;
  
  .label {
    font-size: 10px;
    color: var(--color-text-secondary);
    text-transform: uppercase;
  }
  
  .value {
    font-size: 14px;
    font-weight: 600;
    color: var(--color-text-primary);
    margin-top: 4px;
  }
`;

const DrawdownBar = styled.div<{ pct: number }>`
  width: 100%;
  height: 6px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 3px;
  margin-top: 8px;
  overflow: hidden;
  
  .fill {
    height: 100%;
    width: ${props => Math.min(props.pct * 100, 100)}%;
    background: ${props => {
      if (props.pct > 0.15) return '#ef4444';
      if (props.pct > 0.08) return '#f97316';
      if (props.pct > 0.05) return '#f59e0b';
      return '#10b981';
    }};
    border-radius: 3px;
  }
`;

interface RiskPanelProps {
  equity: number;
  highWaterMark: number;
  drawdown: number;
  openPositions: number;
}

export const RiskPanel: React.FC<RiskPanelProps> = ({ equity, highWaterMark, drawdown, openPositions }) => {
  const drawdownPct = Math.max(0, drawdown * 100);
  
  return (
    <Container>
      <Title><FaShieldAlt /> Risk State</Title>
      
      <EquityDisplay>
        <div className="label">Current Equity</div>
        <div className="value">${equity.toFixed(2)}</div>
      </EquityDisplay>
      
      <MetricsGrid>
        <Metric>
          <div className="label">High Water Mark</div>
          <div className="value">${highWaterMark.toFixed(2)}</div>
        </Metric>
        <Metric>
          <div className="label">Open Positions</div>
          <div className="value">{openPositions}</div>
        </Metric>
      </MetricsGrid>
      
      <div style={{ marginTop: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--color-text-secondary)', marginBottom: '4px' }}>
          <span>DRAWDOWN</span>
          <span>{drawdownPct.toFixed(1)}%</span>
        </div>
        <DrawdownBar pct={drawdown}>
          <div className="fill" />
        </DrawdownBar>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '9px', color: 'var(--color-text-secondary)', marginTop: '4px' }}>
          <span>Green &lt; 5%</span>
          <span>Yellow 5-8%</span>
          <span>Orange 8-15%</span>
          <span>Red &gt; 15%</span>
        </div>
      </div>
    </Container>
  );
};
