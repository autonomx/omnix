from app.image.providers.registry import get_image_provider_definition


def test_z_image_turbo_uses_offload_by_default():
    definition = get_image_provider_definition("z_image_turbo")

    assert definition is not None
    assert definition["repo_id"] == "Tongyi-MAI/Z-Image-Turbo"
    assert definition["default_cpu_offload"] is True
    assert definition["default_steps"] == 9
    assert definition["default_guidance_scale"] == 0.0
