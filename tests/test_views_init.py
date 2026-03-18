"""
Unit tests for netbox_custom_objects_tab.views package init helpers.
"""

import logging
from unittest.mock import MagicMock, patch


class TestResolveModelLabels:
    def test_deduplicates_models_across_wildcard_and_explicit(self):
        from netbox_custom_objects_tab import views

        m1 = MagicMock()
        m1._meta.app_label = "dcim"
        m1._meta.model_name = "device"
        m2 = MagicMock()
        m2._meta.app_label = "dcim"
        m2._meta.model_name = "site"

        app_config = MagicMock()
        app_config.get_models.return_value = [m1, m2]

        with patch.object(views, "apps") as mock_apps:
            mock_apps.get_app_config.return_value = app_config
            mock_apps.get_model.return_value = m1

            result = views._resolve_model_labels(["dcim.*", "dcim.device"])

        assert result == [m1, m2]

    def test_unknown_wildcard_app_logs_warning_no_exception(self, caplog):
        from netbox_custom_objects_tab import views

        with patch.object(views, "apps") as mock_apps:
            mock_apps.get_app_config.side_effect = LookupError("no such app")

            with caplog.at_level(logging.WARNING, logger="netbox_custom_objects_tab"):
                result = views._resolve_model_labels(["nonexistent_app_xyz.*"])

        assert result == []
        assert any("nonexistent_app_xyz" in r.message for r in caplog.records)

    def test_unknown_specific_model_logs_warning_no_exception(self, caplog):
        from netbox_custom_objects_tab import views

        with patch.object(views, "apps") as mock_apps:
            mock_apps.get_model.side_effect = LookupError("no such model")

            with caplog.at_level(logging.WARNING, logger="netbox_custom_objects_tab"):
                result = views._resolve_model_labels(["nonexistent_app_xyz.somemodel"])

        assert result == []
        assert any("nonexistent_app_xyz.somemodel" in r.message for r in caplog.records)


class TestRegisterTabs:
    def test_dispatches_combined_tabs_immediately_and_defers_typed(self):
        """register_tabs() registers combined tabs in ready() and defers typed tabs."""
        from netbox_custom_objects_tab import views

        combined_models = [MagicMock()]

        config_map = {
            "combined_models": ["dcim.device"],
            "combined_label": "Custom Objects",
            "combined_weight": 2000,
            "typed_models": ["ipam.prefix"],
            "typed_weight": 2100,
        }

        with (
            patch.object(views, "get_plugin_config", side_effect=lambda _plugin, key: config_map[key]),
            patch.object(views, "_resolve_model_labels", return_value=combined_models),
            patch.object(views, "register_combined_tabs") as register_combined,
            patch.object(views, "register_typed_tabs") as register_typed,
            patch("django.core.signals.request_started") as mock_signal,
        ):
            views.register_tabs()

        # Combined tabs registered immediately
        register_combined.assert_called_once_with(combined_models, "Custom Objects", 2000)
        # Typed tabs NOT called during register_tabs() — deferred to first request
        register_typed.assert_not_called()
        # Signal handler connected for deferred init
        mock_signal.connect.assert_called_once()

    def test_deferred_init_dispatches_typed_tabs(self):
        """_deferred_typed_init() resolves labels and registers typed tabs."""
        from netbox_custom_objects_tab import views

        typed_models = [MagicMock()]
        typed_models[0]._meta.app_label = "ipam"

        # Reset the deferred state so the handler can run
        views._deferred_init_done = False
        views._deferred_config.update(
            {
                "combined_models": [],
                "typed_labels": ["ipam.prefix"],
                "typed_weight": 2100,
            }
        )

        try:
            with (
                patch.object(views, "_resolve_model_labels", return_value=typed_models),
                patch.object(views, "register_typed_tabs") as register_typed,
                patch.object(views, "_inject_co_urls"),
                patch.object(views, "_deduplicate_registry"),
                patch("django.core.signals.request_started"),
            ):
                views._deferred_typed_init()

            register_typed.assert_called_once_with(typed_models, 2100)
        finally:
            # Clean up global state
            views._deferred_init_done = False
            views._deferred_config.clear()

    def test_skips_dispatch_when_configured_model_lists_are_empty(self):
        from netbox_custom_objects_tab import views

        config_map = {
            "combined_models": [],
            "combined_label": "Custom Objects",
            "combined_weight": 2000,
            "typed_models": [],
            "typed_weight": 2100,
        }

        with (
            patch.object(views, "get_plugin_config", side_effect=lambda _plugin, key: config_map[key]),
            patch.object(views, "_resolve_model_labels") as resolve_labels,
            patch.object(views, "register_combined_tabs") as register_combined,
            patch("django.core.signals.request_started"),
        ):
            views.register_tabs()

        resolve_labels.assert_not_called()
        register_combined.assert_not_called()

    def test_config_exception_is_handled(self, caplog):
        from netbox_custom_objects_tab import views

        with (
            patch.object(views, "get_plugin_config", side_effect=RuntimeError("boom")),
            patch.object(views, "register_combined_tabs") as register_combined,
        ):
            with caplog.at_level(logging.ERROR, logger="netbox_custom_objects_tab"):
                views.register_tabs()

        register_combined.assert_not_called()
        assert any("Could not read netbox_custom_objects_tab plugin config" in r.message for r in caplog.records)
