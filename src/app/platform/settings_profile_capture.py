"""Image and speech-input settings profile models."""
from pydantic import BaseModel


class ImageSettingsProfile(BaseModel):
    width: int = 768
    height: int = 768
    aspect_ratio: str = "1:1"
    portrait_preset: str = ""
    scene_preset: str = ""
    unload_after_generation: bool = True


class SttSettingsProfile(BaseModel):
    language: str = ""
    alignment: bool = True
    save_transcript: bool = True
    microphone_device_id: str = ""
    noise_suppression: bool = True
    echo_cancellation: bool = True


class StorageSettingsProfile(BaseModel):
    save_output_by_default: bool = True
    retention_days: int = 30
    temporary_asset_cleanup: bool = True
