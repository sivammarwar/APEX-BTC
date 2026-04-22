import React from 'react';
import styled from 'styled-components';
import { FaArrowUp, FaArrowDown, FaMinus, FaExclamationTriangle, FaBan } from 'react-icons/fa';

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

const RegimeCard = styled.div<{ color: string }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 20px;
  border-radius: 12px;
  background: ${props => {
    switch (props.color) {
      case 'green': return 'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.1) 100%)';
      case 'red': return 'linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(220, 38, 38, 0.1) 100%)';
      case 'yellow': return 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.1) 100%)';
      case 'orange': return 'linear-gradient(135deg, rgba(249, 115, 22, 0.2) 0%, rgba(234, 88, 12, 0.1) 100%)';
      case 'purple': return 'linear-gradient(135deg, rgba(139, 92, 246, 0.2) 0%, rgba(124, 58, 237, 0.1) 100%)';
      default: return 'linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(139, 92, 246, 0.1) 100%)';
    }
  }};
  border: 2px solid ${props => {
    switch (props.color) {
      case 'green': return '#10b981';
      case 'red': return '#ef4444';
      case 'yellow': return '#f59e0b';
      case 'orange': return '#f97316';
      case 'purple': return '#8b5cf6';
      default: return '#3b82f6';
    }
  }};
`;

const RegimeIcon = styled.div<{ color: string }>`
  font-size: 32px;
  margin-bottom: 12px;
  color: ${props => {
    switch (props.color) {
      case 'green': return '#10b981';
      case 'red': return '#ef4444';
      case 'yellow': return '#f59e0b';
      case 'orange': return '#f97316';
      case 'purple': return '#8b5cf6';
      default: return '#3b82f6';
    }
  }};
`;

const RegimeName = styled.div`
  font-size: 16px;
  font-weight: 700;
  color: var(--color-text-primary);
  text-align: center;
`;

const RegimeDetail = styled.div`
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: 8px;
  text-align: center;
`;

const MetricsRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 16px;
`;

const Metric = styled.div`
  background: rgba(255, 255, 255, 0.05);
  padding: 12px;
  border-radius: 8px;
  
  .label {
    font-size: 11px;
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

interface RegimeIndicatorProps {
  regime: any;
}

export const RegimeIndicator: React.FC<RegimeIndicatorProps> = ({ regime }) => {
  if (!regime) {
    return (
      <Container>
        <Title>Market Regime</Title>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#9ca3af' }}>
          No regime data
        </div>
      </Container>
    );
  }

  const regimeColors: { [key: number]: string } = {
    1: 'green',
    2: 'red',
    3: 'yellow',
    4: 'orange',
    5: 'purple',
  };

  const regimeIcons: { [key: number]: any } = {
    1: FaArrowUp,
    2: FaArrowDown,
    3: FaMinus,
    4: FaExclamationTriangle,
    5: FaBan,
  };

  const color = regimeColors[regime.regime] || 'blue';
  const IconComponent = regimeIcons[regime.regime] || FaMinus;

  return (
    <Container>
      <Title>Market Regime</Title>
      <RegimeCard color={color}>
        <RegimeIcon color={color}>
          <IconComponent />
        </RegimeIcon>
        <RegimeName>{regime.regime_name}</RegimeName>
        <RegimeDetail>
          {regime.entries_allowed ? 'Entries Allowed' : 'Entries Blocked'} • 
          Size: {(regime.position_size_scale * 100).toFixed(0)}%
        </RegimeDetail>
      </RegimeCard>
      
      <MetricsRow>
        <Metric>
          <div className="label">TSMOM Rank</div>
          <div className="value">{(regime.tsmom_percentile * 100).toFixed(1)}%</div>
        </Metric>
        <Metric>
          <div className="label">Liquidity</div>
          <div className="value">{regime.liquidity_score?.toFixed(2) || 'N/A'}</div>
        </Metric>
      </MetricsRow>
    </Container>
  );
};
