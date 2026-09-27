"""Agent runtime feature declaration."""
from app.runtime.features import FeatureModule
from app.runtime.gateway_installer import install_registrars


def _install_gateway(gateway, context):
    install_registrars(
        gateway,
        context,
        (("app.gateway.agent_runtime_routes", "register_agent_runtime_routes"),),
    )


FEATURE = FeatureModule(
    id="agent-runtime",
    title="Agent Runtime",
    installers=(_install_gateway,),
)
