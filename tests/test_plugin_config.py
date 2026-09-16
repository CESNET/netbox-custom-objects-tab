"""
Startup gate in NetBoxCustomObjectsTabConfig.ready(): requires netbox-custom-objects >= 0.7.0
(probed via the related_tabs package) and warns about removed combined_* settings.
"""

import logging
import sys
from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings


def _config():
    from netbox.plugins import PluginConfig

    from netbox_custom_objects_tab import NetBoxCustomObjectsTabConfig

    PluginConfig.ready = lambda self: None
    return NetBoxCustomObjectsTabConfig.__new__(NetBoxCustomObjectsTabConfig)


@override_settings(PLUGINS_CONFIG={})
def test_ready_registers_tabs_on_0_7():
    from netbox_custom_objects_tab import views

    with (
        patch("django.apps.apps.is_installed", return_value=True),
        patch.object(views, "register_tabs") as register_tabs,
    ):
        _config().ready()

    register_tabs.assert_called_once()


@override_settings(PLUGINS_CONFIG={})
def test_ready_raises_when_related_tabs_missing():
    # A None entry in sys.modules makes `import x` raise ImportError — simulates 0.6.x.
    with (
        patch("django.apps.apps.is_installed", return_value=True),
        patch.dict(sys.modules, {"netbox_custom_objects.related_tabs.registry": None}),
    ):
        with pytest.raises(ImproperlyConfigured, match="0.7.0"):
            _config().ready()


@override_settings(PLUGINS_CONFIG={})
def test_ready_raises_when_upstream_not_loaded():
    with patch("django.apps.apps.is_installed", return_value=False):
        with pytest.raises(ImproperlyConfigured, match="netbox_custom_objects plugin"):
            _config().ready()


@override_settings(PLUGINS_CONFIG={"netbox_custom_objects_tab": {"combined_models": ["dcim.*"], "typed_models": []}})
def test_ready_warns_about_removed_combined_settings(caplog):
    from netbox_custom_objects_tab import views

    with (
        patch("django.apps.apps.is_installed", return_value=True),
        patch.object(views, "register_tabs", MagicMock()),
        caplog.at_level(logging.WARNING, logger="netbox_custom_objects_tab"),
    ):
        _config().ready()

    assert any("combined_models" in r.message for r in caplog.records)
