import React from 'react';
import styled from 'styled-components';
import { FaCheckCircle, FaTimesCircle } from 'react-icons/fa';

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

const SignalCard = styled.div<{ valid: boolean; direction: string }>`
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  border-radius: 12px;
  background: ${props => {
    if (!props.valid) return 'rgba(156, 163, 175, 0.1)';
    return props.direction === 'LONG' 
      ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.15) 0%, rgba(5, 150, 105, 0.05) 100%)'
      : 'linear-gradient(135deg, rgba(239, 68, 68, 0.15) 0%, rgba(220, 38, 38, 0.05) 100%)';
  }};
  border: 2px solid ${props => {
    if (!props.valid) return '#6b7280';
    return props.direction === 'LONG' ? '#10b981' : '#ef4444';
  }};
`;

const ScoreRow = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
`;

const Score = styled.div`
  display: flex;
  align-items: baseline;
  gap: 4px;
  
  .value {
    font-size: 32px;
    font-weight: 700;
    color: var(--color-text-primary);
  }
  
  .max {
    font-size: 14px;
    color: var(--color-text-secondary);
  }
`;

const DirectionBadge = styled.div<{ direction: string }>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border-radius: 20px;
  font-size: 14px;
  font-weight: 600;
  background: ${props => props.direction === 'LONG' ? '#10b981' : props.direction === 'SHORT' ? '#ef4444' : '#6b7280'};
  color: white;
`;

const DetailRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
`;

const Detail = styled.div`
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

interface SignalPanelProps {
  signal: any;
}

export const SignalPanel: React.FC<SignalPanelProps> = ({ signal }) => {
  if (!signal) {
    return (
      <Container>
        <Title>Latest Signal</Title>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: '#9ca3af' }}>
          No signal generated
        </div>
      </Container>
    );
  }

  const isValid = signal.signal_valid;
  const direction = signal.direction;

  return (
    <Container>
      <Title>Latest Signal</Title>
      <SignalCard valid={isValid} direction={direction}>
        <ScoreRow>
          <Score>
            <span className="value">{signal.composite_score}</span>
            <span className="max">/ 105</span>
          </Score>
          <DirectionBadge direction={direction}>
            {isValid ? <FaCheckCircle size={14} /> : <FaTimesCircle size={14} />}
            {direction}
          </DirectionBadge>
        </ScoreRow>
        
        <DetailRow>
          <Detail>
            <div className="label">Probability</div>
            <div className="value">{(signal.probability_weighted * 100).toFixed(1)}%</div>
          </Detail>
          <Detail>
            <div className="label">Prospect Value</div>
            <div className="value">{signal.prospect_value?.toFixed(2) || 'N/A'}</div>
          </Detail>
          <Detail>
            <div className="label">R:R Ratio</div>
            <div className="value">{signal.expected_rr?.toFixed(2) || 'N/A'}</div>
          </Detail>
          <Detail>
            <div className="label">Cooldown</div>
            <div className="value">{signal.cooldown_active ? `${signal.cooldown_remaining}h` : 'Ready'}</div>
          </Detail>
        </DetailRow>
      </SignalCard>
    </Container>
  );
};
