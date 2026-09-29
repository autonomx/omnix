"""Trading feature declaration."""
from app.runtime.features import FeatureModule

from .route_registration import create_trading_router, trading_background_worker_factories


FEATURE = FeatureModule(
    id="trading",
    title="Trading",
    routers=(create_trading_router,),
    background_workers=trading_background_worker_factories(),
)
