import React from 'react';
import styled from 'styled-components';
import { FaArrowUp, FaArrowDown } from 'react-icons/fa';

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

const PositionGrid = styled.div`
  display: grid;
  gap: 12px;
`;

const PositionCard = styled.div<{ direction: string; pnl: number }>`
  background: ${props => props.pnl >= 0 
    ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)'
    : 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%)'
  };
  border: 1px solid ${props => props.pnl >= 0 ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)' };
  border-radius: 8px;
  padding: 12px;
`;

const PositionHeader = styled.div`
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
`;

const Direction = styled.div<{ direction: string }>`
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: ${props => props.direction === 'LONG' ? '#10b981' : '#ef4444'};
`;

const PnL = styled.div<{ pnl: number }>`
  font-size: 14px;
  font-weight: 700;
  color: ${props => props.pnl >= 0 ? '#10b981' : '#ef4444'};
`;

const PositionDetails = styled.div`
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 8px;
  font-size: 12px;
  
  .label {
    color: var(--color-text-secondary);
    font-size: 10px;
  }
  
  .value {
    color: var(--color-text-primary);
    font-weight: 500;
    margin-top: 2px;
  }
`;

const NoPositions = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-secondary);
  font-size: 14px;
`;

interface PositionPanelProps {
  positions: any[];
  equity: number;
}

export const PositionPanel: React.FC<PositionPanelProps> = ({ positions, equity }) => {
  return (
    <Container>
      <Title>Open Positions ({positions.length})</Title>
      
      {positions.length === 0 ? (
        <NoPositions>No open positions</NoPositions>
      ) : (
        <PositionGrid>
          {positions.map((pos) => (
            <PositionCard key={pos.position_id} direction={pos.direction} pnl={pos.unrealized_pnl}>
              <PositionHeader>
                <Direction direction={pos.direction}>
                  {pos.direction === 'LONG' ? <FaArrowUp size={12} /> : <FaArrowDown size={12} />}
                  {pos.direction}
                </Direction>
                <PnL pnl={pos.unrealized_pnl}>
                  {pos.unrealized_pnl >= 0 ? '+' : ''}{pos.unrealized_pnl.toFixed(2)} USD
                </PnL>
              </PositionHeader>
              
              <PositionDetails>
                <div>
                  <div className="label">Size</div>
                  <div className="value">{pos.position_size_btc.toFixed(4)} BTC</div>
                </div>
                <div>
                  <div className="label">Entry</div>
                  <div className="value">{pos.entry_price.toFixed(2)}</div>
                </div>
                <div>
                  <div className="label">Stop</div>
                  <div className="value">{pos.stop_loss.toFixed(2)}</div>
                </div>
                <div>
                  <div className="label">TP1</div>
                  <div className="value">{pos.take_profit_1.toFixed(2)}</div>
                </div>
              </PositionDetails>
            </PositionCard>
          ))}
        </PositionGrid>
      )}
    </Container>
  );
};
