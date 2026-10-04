"""Trading feature declaration."""
from app.runtime.features import FeatureModule
from app.trading.strategy_range_backtest_jobs import STRATEGY_RANGE_BACKTEST_JOB

from .route_registration import create_trading_router, trading_scheduled_task_factories


FEATURE = FeatureModule(
    id="trading",
    title="Trading",
    tier="app",
    routers=(create_trading_router,),
    scheduled_tasks=trading_scheduled_task_factories(),
    job_handlers=(STRATEGY_RANGE_BACKTEST_JOB,),
)
