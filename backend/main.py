"""
APEX-BTC Main Entry Point
Starts the trading engine and API server
"""
import asyncio
import uvicorn
from fastapi import FastAPI
from contextlib import asynccontextmanager
from loguru import logger
import sys

from config.settings import settings
from src.engine.trading_engine import TradingEngine
from src.api.routes import app as api_app, set_engine


# Configure logging
logger.remove()
logger.add(sys.stderr, format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}", level="INFO")
logger.add("logs/apex_btc_{time}.log", rotation="1 day", retention="7 days")


trading_engine: TradingEngine = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global trading_engine
    
    logger.info("=" * 60)
    logger.info("APEX-BTC v6.0 - Autonomous Paper Trading Engine")
    logger.info("=" * 60)
    logger.info("Initializing 12 quantitative layers...")
    
    # Initialize trading engine
    trading_engine = TradingEngine(settings)
    set_engine(trading_engine)
    
    # Start trading engine
    await trading_engine.start()
    
    logger.info("APEX-BTC is live and trading!")
    
    yield
    
    # Shutdown
    logger.info("Shutting down APEX-BTC...")
    await trading_engine.stop()
    logger.info("Shutdown complete")


# Create main application
app = FastAPI(
    title="APEX-BTC API",
    description="Autonomous Bitcoin Paper Trading Engine",
    version="6.0.0",
    lifespan=lifespan
)

# Include API routes
app.include_router(api_app.router)

# Include validation routes (AutoQuant)
from src.api.validation_routes import router as validation_router
app.include_router(validation_router)


async def main():
    """Main entry point"""
    config = uvicorn.Config(
        "main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        log_level="info",
        reload=False
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        sys.exit(1)
