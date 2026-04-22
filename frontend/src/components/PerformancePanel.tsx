import React from 'react';
import styled from 'styled-components';

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

const MetricsGrid = styled.div`
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
`;

const MetricCard = styled.div`
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  padding: 12px;
  
  .label {
    font-size: 10px;
    color: var(--color-text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  
  .value {
    font-size: 18px;
    font-weight: 700;
    color: var(--color-text-primary);
    margin-top: 4px;
  }
  
  .target {
    font-size: 10px;
    color: var(--color-text-secondary);
    margin-top: 2px;
  }
`;

const ProgressBar = styled.div<{ value: number; target: number }>`
  width: 100%;
  height: 4px;
  background: rgba(255, 255, 255, 0.1);
  border-radius: 2px;
  margin-top: 8px;
  overflow: hidden;
  
  .fill {
    height: 100%;
    width: ${props => Math.min((props.value / props.target) * 100, 100)}%;
    background: ${props => props.value >= props.target ? '#10b981' : '#3b82f6'};
    border-radius: 2px;
    transition: width 0.3s ease;
  }
`;

interface PerformancePanelProps {
  metrics: any;
}

export const PerformancePanel: React.FC<PerformancePanelProps> = ({ metrics }) => {
  if (!metrics) {
    return (
      <Container>
        <Title>Performance Metrics</Title>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#9ca3af' }}>
          No metrics available
        </div>
      </Container>
    );
  }

  const performanceMetrics = [
    { label: 'Sharpe Ratio', value: metrics.ratios?.sharpe || 0, target: 3.0, format: (v: number) => v.toFixed(2) },
    { label: 'Sortino Ratio', value: metrics.ratios?.sortino || 0, target: 4.5, format: (v: number) => v.toFixed(2) },
    { label: 'Calmar Ratio', value: metrics.ratios?.calmar || 0, target: 2.0, format: (v: number) => v.toFixed(2) },
    { label: 'Win Rate', value: (metrics.trades?.win_rate || 0) * 100, target: 50, format: (v: number) => `${v.toFixed(1)}%` },
    { label: 'Profit Factor', value: metrics.ratios?.profit_factor || 0, target: 1.8, format: (v: number) => v.toFixed(2) },
    { label: 'Total Return', value: (metrics.returns?.total || 0) * 100, target: 50, format: (v: number) => `${v.toFixed(1)}%` },
  ];

  const validationMetrics = [
    { label: 'PSR (SR=0)', value: (metrics.statistical_validation?.psr_sr0 || 0) * 100, target: 95, format: (v: number) => `${v.toFixed(1)}%` },
    { label: 'DSR', value: (metrics.statistical_validation?.dsr || 0) * 100, target: 95, format: (v: number) => `${v.toFixed(1)}%` },
    { label: 'P(Failure)', value: (metrics.statistical_validation?.prob_failure || 0) * 100, target: 5, format: (v: number) => `${v.toFixed(1)}%`, inverse: true },
  ];

  return (
    <Container>
      <Title>Performance & Validation</Title>
      
      <MetricsGrid>
        {performanceMetrics.map((metric) => (
          <MetricCard key={metric.label}>
            <div className="label">{metric.label}</div>
            <div className="value">{metric.format(metric.value)}</div>
            <div className="target">Target: {metric.format(metric.target)}</div>
            <ProgressBar value={metric.value} target={metric.target}>
              <div className="fill" />
            </ProgressBar>
          </MetricCard>
        ))}
        
        {validationMetrics.map((metric: any) => (
          <MetricCard key={metric.label}>
            <div className="label">{metric.label}</div>
            <div className="value">{metric.format(metric.value)}</div>
            <div className="target">Target: {metric.format(metric.target)}</div>
            <ProgressBar value={metric.inverse ? metric.target / (metric.value + 0.01) : metric.value} target={metric.target}>
              <div className="fill" />
            </ProgressBar>
          </MetricCard>
        ))}
      </MetricsGrid>
    </Container>
  );
};
