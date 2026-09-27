"""Trading feature declaration."""
from app.runtime.features import FeatureModule
from app.runtime.gateway_installer import install_registrars


def _install_gateway(gateway, context):
    install_registrars(
        gateway,
        context,
        (("app.gateway.trading_routes", "register_trading_routes"),),
    )


FEATURE = FeatureModule(
    id="trading",
    title="Trading",
    installers=(_install_gateway,),
)
