import React from 'react';
import styled from 'styled-components';
import { FaChartLine, FaRobot, FaBell } from 'react-icons/fa';

const HeaderContainer = styled.header`
  background: linear-gradient(135deg, #1a1f2e 0%, #111827 100%);
  border-bottom: 1px solid #2a3142;
  padding: 16px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
`;

const Logo = styled.div`
  display: flex;
  align-items: center;
  gap: 12px;
`;

const LogoIcon = styled.div`
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  color: white;
`;

const Title = styled.div`
  h1 {
    font-size: 20px;
    font-weight: 700;
    background: linear-gradient(135deg, #3b82f6 0%, #8b5cf6 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
  }
  p {
    font-size: 12px;
    color: #9ca3af;
    margin-top: 2px;
  }
`;

const Status = styled.div`
  display: flex;
  align-items: center;
  gap: 16px;
`;

const StatusBadge = styled.div<{ color: string }>`
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  font-size: 12px;
  font-weight: 500;
  background: ${props => {
    switch (props.color) {
      case 'green': return 'rgba(16, 185, 129, 0.2)';
      case 'red': return 'rgba(239, 68, 68, 0.2)';
      case 'yellow': return 'rgba(245, 158, 11, 0.2)';
      default: return 'rgba(59, 130, 246, 0.2)';
    }
  }};
  color: ${props => {
    switch (props.color) {
      case 'green': return '#10b981';
      case 'red': return '#ef4444';
      case 'yellow': return '#f59e0b';
      default: return '#3b82f6';
    }
  }};
  border: 1px solid ${props => {
    switch (props.color) {
      case 'green': return 'rgba(16, 185, 129, 0.3)';
      case 'red': return 'rgba(239, 68, 68, 0.3)';
      case 'yellow': return 'rgba(245, 158, 11, 0.3)';
      default: return 'rgba(59, 130, 246, 0.3)';
    }
  }};
`;

const NotificationButton = styled.button`
  background: transparent;
  border: none;
  color: #9ca3af;
  font-size: 18px;
  cursor: pointer;
  padding: 8px;
  border-radius: 8px;
  transition: all 0.2s;
  
  &:hover {
    background: rgba(255, 255, 255, 0.1);
    color: #e0e0e0;
  }
`;

export const Header: React.FC = () => {
  return (
    <HeaderContainer>
      <Logo>
        <LogoIcon>
          <FaRobot />
        </LogoIcon>
        <Title>
          <h1>APEX-BTC</h1>
          <p>Autonomous Paper Trading Engine v6.0</p>
        </Title>
      </Logo>
      
      <Status>
        <StatusBadge color="green">
          <FaChartLine size={12} />
          Live Trading
        </StatusBadge>
        <NotificationButton>
          <FaBell />
        </NotificationButton>
      </Status>
    </HeaderContainer>
  );
};
