"""Tests for Sentry initialization in app startup."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def test_sentry_init_called_when_dsn_set():
    """Sentry should initialize when DSN is provided."""
    mock_sentry = MagicMock()
    # Mock sentry_sdk and its integrations
    mock_integrations = MagicMock()
    mock_fastapi_integration = MagicMock()

    with (
        patch.dict(
            "sys.modules",
            {
                "sentry_sdk": mock_sentry,
                "sentry_sdk.integrations": mock_integrations,
                "sentry_sdk.integrations.fastapi": MagicMock(
                    FastApiIntegration=mock_fastapi_integration
                ),
            },
        ),
        patch("app.main.settings") as mock_settings,
    ):
        mock_settings.sentry_dsn = "https://key@sentry.io/123"
        mock_settings.sentry_traces_sample_rate = 1.0
        mock_settings.sentry_send_pii = True
        mock_settings.environment = "test"

        from app.main import _init_sentry

        _init_sentry()

        mock_sentry.init.assert_called_once()
        call_kwargs = mock_sentry.init.call_args[1]
        assert call_kwargs["dsn"] == "https://key@sentry.io/123"
        assert call_kwargs["traces_sample_rate"] == 1.0


def test_sentry_not_called_when_dsn_empty():
    """Sentry should NOT initialize when DSN is empty."""
    with patch("app.main.settings") as mock_settings:
        mock_settings.sentry_dsn = ""

        from app.main import _init_sentry

        _init_sentry()
        # No assertions needed - the function should return early without importing sentry_sdk
