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
    def test_registers_typed_tabs_synchronously(self):
        """register_tabs() registers typed tabs synchronously in ready().
        Registration must be synchronous because NetBox builds each model's
        URLconf on the first resolve() call by snapshotting registry['views'];
        anything added after that has no URL pattern. See 2.3.0 fix.
        """
        from netbox_custom_objects_tab import views

        typed_models = [MagicMock()]
        typed_models[0]._meta.app_label = "ipam"
        config_map = {"typed_models": ["ipam.prefix"], "typed_weight": 2100}

        with (
            patch.object(views, "get_plugin_config", side_effect=lambda _plugin, key: config_map[key]),
            patch.object(views, "_resolve_model_labels", return_value=typed_models),
            patch.object(views, "register_typed_tabs") as register_typed,
            patch.object(views, "_inject_co_urls") as inject_co_urls,
            patch.object(views, "_deduplicate_registry") as dedup,
        ):
            views.register_tabs()

        register_typed.assert_called_once_with(typed_models, 2100)
        # No CO models → CO URL injection skipped.
        inject_co_urls.assert_not_called()
        dedup.assert_called_once()

    def test_injects_co_urls_when_a_custom_object_model_is_configured(self):
        from netbox_custom_objects_tab import views

        co_model = MagicMock()
        co_model._meta.app_label = "netbox_custom_objects"
        config_map = {"typed_models": ["netbox_custom_objects.*"], "typed_weight": 2100}

        with (
            patch.object(views, "get_plugin_config", side_effect=lambda _plugin, key: config_map[key]),
            patch.object(views, "_resolve_model_labels", return_value=[co_model]),
            patch.object(views, "register_typed_tabs"),
            patch.object(views, "_inject_co_urls") as inject_co_urls,
            patch.object(views, "_deduplicate_registry"),
        ):
            views.register_tabs()

        inject_co_urls.assert_called_once()

    def test_skips_dispatch_when_typed_models_is_empty(self):
        from netbox_custom_objects_tab import views

        config_map = {"typed_models": [], "typed_weight": 2100}

        with (
            patch.object(views, "get_plugin_config", side_effect=lambda _plugin, key: config_map[key]),
            patch.object(views, "_resolve_model_labels") as resolve_labels,
            patch.object(views, "register_typed_tabs") as register_typed,
            patch.object(views, "_inject_co_urls"),
            patch.object(views, "_deduplicate_registry"),
        ):
            views.register_tabs()

        resolve_labels.assert_not_called()
        register_typed.assert_not_called()

    def test_config_exception_is_handled(self, caplog):
        from netbox_custom_objects_tab import views

        with (
            patch.object(views, "get_plugin_config", side_effect=RuntimeError("boom")),
            patch.object(views, "register_typed_tabs") as register_typed,
        ):
            with caplog.at_level(logging.ERROR, logger="netbox_custom_objects_tab"):
                views.register_tabs()

        register_typed.assert_not_called()
        assert any("Could not read netbox_custom_objects_tab plugin config" in r.message for r in caplog.records)


class TestCoDispatcher:
    """
    The CO-page URL `<slug>/<pk>/custom-objects-<x>/` is shared by every host
    Custom Object model, so it must resolve the host model from the slug per
    request and dispatch to the view registered for that model — not to the
    first model's view class (which would load the wrong object and put the
    wrong ViewTab in the context).
    """

    def test_dispatches_to_view_registered_for_slug_model(self):
        from netbox.registry import registry

        from netbox_custom_objects_tab import views

        view_b = MagicMock(name="view_b")
        view_c = MagicMock(name="view_c")
        registry["views"]["netbox_custom_objects"] = {
            "table28model": [{"name": "custom_objects_type-a", "path": "x", "view": view_c}],
            "table29model": [{"name": "custom_objects_type-a", "path": "x", "view": view_b}],
        }
        cot = MagicMock()
        cot.get_model.return_value._meta.model_name = "table29model"
        request = MagicMock()

        try:
            with patch.object(views, "get_object_or_404", return_value=cot):
                dispatch = views._make_co_dispatcher("custom_objects_type-a")
                response = dispatch(request, custom_object_type="type-b", pk=5)
        finally:
            registry["views"].pop("netbox_custom_objects", None)

        view_b.as_view.return_value.assert_called_once_with(request, custom_object_type="type-b", pk=5)
        view_c.as_view.assert_not_called()
        assert response is view_b.as_view.return_value.return_value

    def test_404_when_no_view_registered_for_slug_model(self):
        import pytest
        from django.http import Http404
        from netbox.registry import registry

        from netbox_custom_objects_tab import views

        registry["views"]["netbox_custom_objects"] = {"table28model": []}
        cot = MagicMock()
        cot.get_model.return_value._meta.model_name = "table28model"

        try:
            with patch.object(views, "get_object_or_404", return_value=cot):
                dispatch = views._make_co_dispatcher("custom_objects_type-a")
                with pytest.raises(Http404):
                    dispatch(MagicMock(), custom_object_type="type-b", pk=5)
        finally:
            registry["views"].pop("netbox_custom_objects", None)
