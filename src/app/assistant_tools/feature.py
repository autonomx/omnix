"""Assistant tools feature declaration."""
from app.runtime.features import FeatureModule
from app.runtime.gateway_installer import install_registrars


def _install_gateway(gateway, context):
    install_registrars(
        gateway,
        context,
        (("app.assistant_tools.routes", "register_assistant_tool_routes"),),
    )


FEATURE = FeatureModule(
    id="assistant-tools",
    title="Assistant Tools",
    installers=(_install_gateway,),
)
