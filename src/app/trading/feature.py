"""Trading feature declaration."""
from app.runtime.features import FeatureModule

from .route_registration import create_trading_router, trading_scheduled_task_factories


FEATURE = FeatureModule(
    id="trading",
    title="Trading",
    routers=(create_trading_router,),
    scheduled_tasks=trading_scheduled_task_factories(),
)
