# APEX-BTC: Autonomous Paper Trading Engine v6.0

A high-frequency, autonomous Bitcoin paper trading bot engineered to institutional-grade standards, integrating nine foundational quantitative frameworks into a unified trading system.

## 9 Foundational Frameworks

1. **Kelly (1956)** — Optimal growth position sizing with fee-drag adjustment
2. **López de Prado / Bailey (2012, 2014, 2018)** — PSR, DSR, MinTRL, P(Strategy Failure), TuW
3. **Han, Kang & Ryu (2026)** — TSMOM with 28-day look-back, CO measure, jump-diffusion
4. **Dimpfl (2017)** — BTC microstructure: adverse selection, MRR model, liquidity windows
5. **Pichl & Kaizoji (2017)** — HARRVJ volatility forecasting, algo order slicing detection
6. **Avellaneda & Lee (2010)** — PCA factor extraction, s-score mean-reversion
7. **Zhang, Zohren & Roberts (2020)** — DQN position sizing with volatility scaling
8. **Kahneman & Tversky (1979)** — Prospect theory: S-shaped value function, π(p) weighting

## 12-Layer Architecture

| Layer | Name | Function |
|-------|------|----------|
| 1 | Data Ingestion | Binance WebSocket + REST, multi-asset for PCA |
| 2 | Feature Engineering | 8 families: TSMOM, HARRVJ, MRR, PCA, Prospect Theory |
| 3 | Regime Detection | 5 regimes with TSMOM primary gate |
| 4 | Signal Generation | 105-point composite scoring |
| 5 | Risk Management | Kelly-Correct sizing with all adjustments |
| 6 | Execution | Paper trading with microstructure costs |
| 7 | Performance Analytics | PSR, DSR, MinTRL, TuW, CPV |
| 8 | Strategy Validity | Sentinel system with circuit breakers |
| 9 | Jump-Diffusion | Merton model parameter estimation |
| 10 | Microstructure | MRR engine, HARRVJ, algo-slicing detection |
| 11 | Prospect Theory | S-shaped valuation, reference point adaptation |
| 12 | DQN Position Sizing | Learned position sizing from Zhang et al. |

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Binance API key (for paper trading use testnet)

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/apex-btc.git
cd apex-btc
```

2. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your Binance API credentials
```

3. Start all services:
```bash
docker-compose up -d
```

4. Access the dashboard:
- Frontend: http://localhost:3000
- API: http://localhost:8000
- API Docs: http://localhost:8000/docs

### Manual Installation (without Docker)

**Backend:**
```bash
cd backend
pip install -r requirements.txt
python main.py
```

**Frontend:**
```bash
cd frontend
npm install
npm start
```

## Key Features

### Signal Generation (105-point composite)
- 4H 200 EMA slope: 15 points
- TSMOM rank >66.7th percentile: 20 points
- CO positive: 15 points
- Price within 1.5 ATR: 10 points
- RSI 40-60: 5 points
- Stoch RSI crossover: 5 points
- MACD bullish: 5 points
- OFI_clean > 0.1: 10 points
- OBV trending: 5 points
- Volume POC below price: 5 points
- MRR ρ > 0.10: 5 points
- s-score < -1.25: 5 points

### Risk Management
- **Kelly Criterion**: Half-Kelly with jump-diffusion haircut
- **HARRVJ Volatility Scaling**: 15% annualized target
- **Prospect Theory Adjustments**: House money/break-even effects
- **Liquidity Scaling**: Dimpfl (2017) window optimization
- **Circuit Breakers**: Yellow (5%), Orange (8%), Red (15%)

### Statistical Validation
- **PSR**: Probabilistic Sharpe Ratio ≥95%
- **DSR**: Deflated Sharpe Ratio ≥95%
- **MinTRL**: Fat-tail adjusted track record length
- **P(Strategy Failure)**: Beta posterior probability <5%
- **Time Under Water**: Median, 75th, 95th percentile tracking

## API Endpoints

### Core
- `GET /api/v1/state` - Complete engine state
- `GET /api/v1/price` - Current price and spread
- `GET /api/v1/regime` - Current market regime

### Trading
- `GET /api/v1/signal/latest` - Latest signal
- `GET /api/v1/positions` - Open positions
- `GET /api/v1/trades/history` - Trade history

### Analytics
- `GET /api/v1/performance` - Performance metrics
- `GET /api/v1/performance/criteria` - Acceptance criteria status
- `GET /api/v1/risk/state` - Risk state

### Research
- `GET /api/v1/jump/params` - Jump-diffusion parameters
- `GET /api/v1/microstructure/mrr` - MRR estimates
- `GET /api/v1/microstructure/harrvj` - HARRVJ forecast
- `GET /api/v1/prospect/state` - Prospect theory state

### Control
- `POST /api/v1/manual-override` - Emergency controls
- `POST /api/v1/dqn/training` - Enable/disable DQN training

### WebSocket
- `ws://localhost:8000/ws` - Real-time updates

## Configuration

Key settings in `.env`:
```env
# Trading
INITIAL_CAPITAL=10.0
TRADING_SYMBOL=BTCUSDT

# Binance (Paper Trading)
BINANCE_API_KEY=your_key
BINANCE_SECRET_KEY=your_secret
BINANCE_TESTNET=true

# Risk
TARGET_VOLATILITY=0.15
MAX_DRAWDOWN_PCT=0.15
MAX_DAILY_TRADES=5

# DQN
DQN_LEARNING_RATE=0.0001
DQN_GAMMA=0.3
```

## Target Metrics

| Metric | Target |
|--------|--------|
| Sharpe Ratio | ≥ 3.0 |
| Sortino Ratio | ≥ 4.5 |
| Calmar Ratio | ≥ 2.0 |
| Win Rate | 40-65% |
| Profit Factor | ≥ 1.8 |
| PSR(SR*=0) | ≥ 95% |
| DSR | ≥ 95% |
| P(Strategy Failure) | < 5% |

## Project Structure

```
apex-btc/
├── backend/
│   ├── src/
│   │   ├── layers/           # All 12 layers
│   │   ├── engine/           # Trading engine
│   │   ├── api/              # FastAPI routes
│   │   └── models/           # Database models
│   ├── config/               # Settings
│   ├── main.py               # Entry point
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── components/       # React components
│   │   └── hooks/            # Custom hooks
│   └── package.json
├── docker-compose.yml
└── README.md
```

## License

MIT License - See LICENSE file for details

## Disclaimer

This is a paper trading system for research and educational purposes. Not financial advice. Trading cryptocurrencies involves substantial risk of loss.

## Citation

If you use APEX-BTC in your research, please cite:

```bibtex
@software{apex_btc_2024,
  title = {APEX-BTC: Autonomous Paper Trading Engine},
  version = {6.0.0},
  year = {2024},
  note = {Integrates Kelly, López de Prado, Han et al., Dimpfl, 
          Pichl & Kaizoji, Avellaneda & Lee, Zhang et al., 
          and Kahneman & Tversky frameworks}
}
```
