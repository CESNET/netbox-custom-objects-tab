"""
Unit tests for the plugin_extra_tabs template tag.
"""

from types import SimpleNamespace
from unittest.mock import patch


def _tab(label, weight):
    return SimpleNamespace(
        label=label, weight=weight, permission=None, render=lambda obj: {"label": label, "badge": 3, "weight": weight}
    )


def _render(active_tab, registered_tab):
    from netbox_custom_objects_tab.templatetags import custom_object_tab_tags as tags

    instance = SimpleNamespace(
        _meta=SimpleNamespace(app_label="netbox_custom_objects", model_name="table149model"), pk=1
    )
    view = SimpleNamespace(tab=registered_tab)
    registry = {"views": {"netbox_custom_objects": {"table149model": [{"name": "custom_objects", "view": view}]}}}
    context = {"request": SimpleNamespace(user=SimpleNamespace(has_perm=lambda p: True)), "tab": active_tab}
    with patch.object(tags, "registry", registry), patch.object(tags, "get_action_url", return_value="/x/"):
        return tags.plugin_extra_tabs(context, instance)["tabs"]


def test_same_instance_is_active():
    tab = _tab("Custom Objects", 2000)
    assert _render(tab, tab)[0]["is_active"] is True


def test_equal_label_and_weight_but_different_instance_is_active():
    # Generic CO-page URL serves another model's view class -> different ViewTab object.
    assert _render(_tab("Custom Objects", 2000), _tab("Custom Objects", 2000))[0]["is_active"] is True


def test_different_label_is_not_active():
    assert _render(_tab("Service", 2100), _tab("Custom Objects", 2000))[0]["is_active"] is False


def test_no_active_tab_in_context():
    assert _render(None, _tab("Custom Objects", 2000))[0]["is_active"] is False
