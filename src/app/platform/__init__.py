"""Kernel-level platform summary services."""

from .diagnostics import DiagnosticsPayload, get_diagnostics_payload
from .legacy_sessions import (
    LegacyGenerateTitleRequest,
    LegacyGenerateTitleResponse,
    LegacySessionCreateResponse,
    LegacySessionListResponse,
    LegacySessionResponse,
    LegacySessionUpdateRequest,
    LegacySuccessResponse,
    create_legacy_session,
    delete_legacy_session,
    generate_legacy_session_title,
    get_legacy_session,
    list_legacy_sessions,
    update_legacy_session,
)
from .reports import ReportListResponse, list_report_artifacts
from .settings_control import (
    SettingsPayload,
    SettingsSaveResponse,
    get_settings_payload,
    save_settings_payload,
)

__all__ = [
    "DiagnosticsPayload",
    "LegacyGenerateTitleRequest",
    "LegacyGenerateTitleResponse",
    "LegacySessionCreateResponse",
    "LegacySessionListResponse",
    "LegacySessionResponse",
    "LegacySessionUpdateRequest",
    "LegacySuccessResponse",
    "ReportListResponse",
    "SettingsPayload",
    "SettingsSaveResponse",
    "create_legacy_session",
    "delete_legacy_session",
    "generate_legacy_session_title",
    "get_diagnostics_payload",
    "get_legacy_session",
    "get_settings_payload",
    "list_legacy_sessions",
    "list_report_artifacts",
    "save_settings_payload",
    "update_legacy_session",
]
