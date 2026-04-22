import React from 'react';
import styled from 'styled-components';
import { FaExclamationTriangle, FaCheckCircle, FaTimesCircle, FaBan, FaClock } from 'react-icons/fa';

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

const AlertList = styled.div`
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 8px;
`;

const AlertCard = styled.div<{ level: string }>`
  background: ${props => {
    switch (props.level) {
      case 'red': return 'linear-gradient(135deg, rgba(239, 68, 68, 0.2) 0%, rgba(220, 38, 38, 0.1) 100%)';
      case 'orange': return 'linear-gradient(135deg, rgba(249, 115, 22, 0.2) 0%, rgba(234, 88, 12, 0.1) 100%)';
      case 'yellow': return 'linear-gradient(135deg, rgba(245, 158, 11, 0.2) 0%, rgba(217, 119, 6, 0.1) 100%)';
      default: return 'linear-gradient(135deg, rgba(59, 130, 246, 0.2) 0%, rgba(139, 92, 246, 0.1) 100%)';
    }
  }};
  border: 1px solid ${props => {
    switch (props.level) {
      case 'red': return '#ef4444';
      case 'orange': return '#f97316';
      case 'yellow': return '#f59e0b';
      default: return '#3b82f6';
    }
  }};
  border-radius: 6px;
  padding: 10px;
  display: flex;
  align-items: flex-start;
  gap: 10px;
`;

const AlertIcon = styled.div<{ level: string }>`
  color: ${props => {
    switch (props.level) {
      case 'red': return '#ef4444';
      case 'orange': return '#f97316';
      case 'yellow': return '#f59e0b';
      default: return '#3b82f6';
    }
  }};
  font-size: 16px;
  flex-shrink: 0;
  margin-top: 2px;
`;

const AlertContent = styled.div`
  flex: 1;
  
  .category {
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
    color: var(--color-text-secondary);
  }
  
  .message {
    font-size: 12px;
    color: var(--color-text-primary);
    margin-top: 2px;
  }
  
  .action {
    font-size: 10px;
    color: var(--color-text-secondary);
    margin-top: 4px;
    font-style: italic;
  }
`;

const ManualReviewBanner = styled.div`
  background: linear-gradient(135deg, rgba(239, 68, 68, 0.3) 0%, rgba(220, 38, 38, 0.2) 100%);
  border: 2px solid #ef4444;
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
  color: #ef4444;
  font-weight: 600;
  font-size: 12px;
`;

const NoAlerts = styled.div`
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--color-text-secondary);
  font-size: 14px;
`;

interface AlertsPanelProps {
  alerts: any[];
  manualReview: boolean;
}

const getAlertIcon = (level: string) => {
  switch (level) {
    case 'red': return <FaBan />;
    case 'orange': return <FaExclamationTriangle />;
    case 'yellow': return <FaClock />;
    default: return <FaCheckCircle />;
  }
};

export const AlertsPanel: React.FC<AlertsPanelProps> = ({ alerts, manualReview }) => {
  const activeAlerts = alerts.filter(a => !a.acknowledged);
  
  return (
    <Container>
      <Title>Active Alerts ({activeAlerts.length})</Title>
      
      {manualReview && (
        <ManualReviewBanner>
          <FaBan />
          MANUAL REVIEW REQUIRED - Trading Halted
        </ManualReviewBanner>
      )}
      
      <AlertList>
        {activeAlerts.length === 0 ? (
          <NoAlerts>No active alerts</NoAlerts>
        ) : (
          activeAlerts.map((alert, idx) => (
            <AlertCard key={idx} level={alert.level}>
              <AlertIcon level={alert.level}>
                {getAlertIcon(alert.level)}
              </AlertIcon>
              <AlertContent>
                <div className="category">{alert.category}</div>
                <div className="message">{alert.message}</div>
                <div className="action">{alert.action}</div>
              </AlertContent>
            </AlertCard>
          ))
        )}
      </AlertList>
    </Container>
  );
};
