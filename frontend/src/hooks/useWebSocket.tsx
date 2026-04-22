import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';

interface EngineState {
  timestamp: string;
  is_running: boolean;
  is_trading_allowed: boolean;
  current_price: number;
  current_spread: number;
  regime: any;
  latest_signal: any;
  equity: number;
  high_water_mark: number;
  drawdown_pct: number;
  open_positions: number;
  metrics: any;
  active_alerts: any[];
  manual_review_required: boolean;
}

interface WebSocketContextType {
  state: EngineState | null;
  isConnected: boolean;
  error: string | null;
}

const WebSocketContext = createContext<WebSocketContextType>({
  state: null,
  isConnected: false,
  error: null,
});

export const useWebSocket = () => useContext(WebSocketContext);

interface WebSocketProviderProps {
  children: ReactNode;
}

export const WebSocketProvider: React.FC<WebSocketProviderProps> = ({ children }) => {
  const [state, setState] = useState<EngineState | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const connectWebSocket = () => {
      const ws = new WebSocket('ws://localhost:8000/ws');

      ws.onopen = () => {
        setIsConnected(true);
        setError(null);
        console.log('WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setState(data);
        } catch (err) {
          console.error('Failed to parse WebSocket message:', err);
        }
      };

      ws.onerror = (err) => {
        setError('WebSocket error');
        setIsConnected(false);
        console.error('WebSocket error:', err);
      };

      ws.onclose = () => {
        setIsConnected(false);
        console.log('WebSocket disconnected, retrying in 5s...');
        setTimeout(connectWebSocket, 5000);
      };

      return ws;
    };

    const ws = connectWebSocket();

    return () => {
      if (ws) {
        ws.close();
      }
    };
  }, []);

  return (
    <WebSocketContext.Provider value={{ state, isConnected, error }}>
      {children}
    </WebSocketContext.Provider>
  );
};
