"""
Unit tests for netbox_custom_objects_tab.views.combined helpers.
"""

from unittest.mock import MagicMock, patch

import pytest
from extras.choices import CustomFieldTypeChoices


def _make_pair(obj_str, type_str, field_str):
    """Return a mock (custom_object_instance, field) tuple."""
    obj = MagicMock()
    obj.__str__ = lambda self: obj_str

    cot = MagicMock()
    cot.__str__ = lambda self: type_str

    field = MagicMock()
    field.__str__ = lambda self: field_str
    field.custom_object_type = cot

    return (obj, field)


class TestFilterLinkedObjects:
    """Pure-Python filter helper — no DB or Django state required."""

    @pytest.fixture(autouse=True)
    def get_fn(self):
        from netbox_custom_objects_tab.views.combined import _filter_linked_objects

        self.fn = _filter_linked_objects

    def test_empty_query_returns_same_list(self):
        linked = [_make_pair("Device A", "Server", "dev_field")]
        assert self.fn(linked, "") is linked

    def test_whitespace_only_returns_same_list(self):
        linked = [_make_pair("Device A", "Server", "dev_field")]
        assert self.fn(linked, "   ") is linked

    def test_no_match_returns_empty(self):
        linked = [
            _make_pair("Device A", "Server", "dev_field"),
            _make_pair("Device B", "Router", "net_field"),
        ]
        assert self.fn(linked, "zzznomatch") == []

    def test_match_on_object_str(self):
        linked = [
            _make_pair("Device Alpha", "Server", "dev_field"),
            _make_pair("Device Beta", "Router", "dev_field"),
        ]
        result = self.fn(linked, "alpha")
        assert len(result) == 1
        assert result[0][0] is linked[0][0]

    def test_match_on_type_str(self):
        linked = [
            _make_pair("Device A", "ServerType", "dev_field"),
            _make_pair("Device B", "RouterType", "dev_field"),
        ]
        result = self.fn(linked, "router")
        assert len(result) == 1
        assert result[0][0] is linked[1][0]

    def test_match_on_field_str(self):
        linked = [
            _make_pair("Device A", "Server", "primary_device_field"),
            _make_pair("Device B", "Router", "network_interface_field"),
        ]
        result = self.fn(linked, "network")
        assert len(result) == 1
        assert result[0][0] is linked[1][0]

    def test_case_insensitive(self):
        linked = [_make_pair("Device UPPERCASE", "Server", "dev_field")]
        assert self.fn(linked, "uppercase") != []
        assert self.fn(linked, "UPPERCASE") != []
        assert self.fn(linked, "UpperCase") != []

    def test_leading_trailing_whitespace_stripped(self):
        linked = [_make_pair("Device A", "Server", "dev_field")]
        assert len(self.fn(linked, "  device  ")) == 1


class TestCountLinkedCustomObjects:
    """Badge callable must return None (not 0) when nothing is linked."""

    def _count(self, fields_and_counts):
        """
        Build mock fields, patch query dependencies, then call the count function.

        fields_and_counts: list of (field_type_value, count_int)
        """
        mock_fields = []
        for field_type, count in fields_and_counts:
            model = MagicMock()
            model.objects.filter.return_value.count.return_value = count

            cot = MagicMock()
            cot.get_model.return_value = model

            field = MagicMock()
            field.type = field_type
            field.custom_object_type = cot
            field.name = "some_field"
            mock_fields.append(field)

        instance = MagicMock()
        instance.pk = 1
        instance._meta.model = MagicMock()

        with (
            patch("netbox_custom_objects_tab.views.combined.CustomObjectTypeField") as mock_cotf,
            patch("netbox_custom_objects_tab.views.combined.ContentType") as mock_ct,
        ):
            mock_ct.objects.get_for_model.return_value = MagicMock()
            mock_cotf.objects.filter.return_value.select_related.return_value = mock_fields

            from netbox_custom_objects_tab.views.combined import _count_linked_custom_objects

            return _count_linked_custom_objects(instance)

    def test_returns_none_when_no_fields(self):
        assert self._count([]) is None

    def test_returns_none_not_zero(self):
        result = self._count([])
        assert result is None
        assert result != 0

    def test_returns_total_when_positive(self):
        result = self._count(
            [
                (CustomFieldTypeChoices.TYPE_OBJECT, 3),
                (CustomFieldTypeChoices.TYPE_OBJECT, 2),
            ]
        )
        assert result == 5

    def test_returns_none_when_all_counts_are_zero(self):
        result = self._count(
            [
                (CustomFieldTypeChoices.TYPE_OBJECT, 0),
                (CustomFieldTypeChoices.TYPE_MULTIOBJECT, 0),
            ]
        )
        assert result is None


class TestCustomObjectsTabTable:
    """Column-preference machinery on the lightweight table class."""

    @pytest.fixture(autouse=True)
    def table_cls(self):
        from netbox_custom_objects_tab.views.combined import CustomObjectsTabTable

        self.cls = CustomObjectsTabTable

    def test_default_columns_contains_all_six(self):
        assert set(self.cls.Meta.default_columns) == {"type", "object", "value", "field", "tags", "actions"}

    def test_actions_is_exempt(self):
        assert "actions" in self.cls.exempt_columns

    def test_name_property(self):
        t = self.cls([], empty_text="")
        assert t.name == "CustomObjectsTabTable"

    def test_all_columns_visible_by_default(self):
        t = self.cls([], empty_text="")
        t._set_columns(list(self.cls.Meta.default_columns))
        visible = {col for col, _ in t.selected_columns}
        assert {"type", "object", "value", "field", "tags"}.issubset(visible)

    def test_hidden_column_not_in_selected(self):
        t = self.cls([], empty_text="")
        cols_without_value = [c for c in self.cls.Meta.default_columns if c != "value"]
        t._set_columns(cols_without_value)
        visible = {col for col, _ in t.selected_columns}
        assert "value" not in visible

    def test_exempt_column_always_visible(self):
        t = self.cls([], empty_text="")
        t._set_columns(["type"])
        selected_names = {col for col, _ in t.selected_columns}
        assert "actions" not in selected_names


class TestSortHeader:
    @pytest.fixture(autouse=True)
    def get_fn(self):
        from netbox_custom_objects_tab.views.combined import _sort_header

        self.fn = _sort_header

    def test_inactive_column_points_to_asc(self):
        result = self.fn("", "type", "object", "asc")
        assert "sort=type" in result["url"]
        assert "dir=asc" in result["url"]
        assert result["icon"] is None

    def test_active_asc_column_icon_is_arrow_up(self):
        result = self.fn("", "type", "type", "asc")
        assert result["icon"] == "arrow-up"
        assert "dir=desc" in result["url"]

    def test_active_desc_column_icon_is_arrow_down(self):
        result = self.fn("", "type", "type", "desc")
        assert result["icon"] == "arrow-down"
        assert "dir=asc" in result["url"]

    def test_base_params_preserved(self):
        result = self.fn("q=foo&tag=bar", "type", "", "asc")
        assert result["url"].startswith("?q=foo&tag=bar&")


# ---------------------------------------------------------------------------
# _get_field_value
# ---------------------------------------------------------------------------
class TestGetFieldValue:
    @pytest.fixture(autouse=True)
    def get_fn(self):
        from netbox_custom_objects_tab.views.combined import _get_field_value

        self.fn = _get_field_value

    def test_type_object_returns_getattr(self):
        obj = MagicMock()
        obj.device_ref = MagicMock(name="Device-1")
        field = MagicMock()
        field.type = CustomFieldTypeChoices.TYPE_OBJECT
        field.name = "device_ref"

        result = self.fn(obj, field)
        assert result is obj.device_ref

    def test_type_multiobject_returns_sliced_list(self):
        from netbox_custom_objects_tab.views.combined import _MAX_MULTIOBJECT_DISPLAY

        related = [MagicMock() for _ in range(_MAX_MULTIOBJECT_DISPLAY + 2)]
        qs = MagicMock()
        qs.all.return_value.__getitem__ = lambda self, s: related[: s.stop]

        obj = MagicMock()
        obj.multi_ref = qs
        field = MagicMock()
        field.type = CustomFieldTypeChoices.TYPE_MULTIOBJECT
        field.name = "multi_ref"

        result = self.fn(obj, field)
        assert isinstance(result, list)
        assert len(result) == _MAX_MULTIOBJECT_DISPLAY + 1

    def test_type_multiobject_none_qs_returns_empty(self):
        obj = MagicMock(spec=[])  # no attributes
        field = MagicMock()
        field.type = CustomFieldTypeChoices.TYPE_MULTIOBJECT
        field.name = "missing_ref"

        result = self.fn(obj, field)
        assert result == []

    def test_unknown_field_type_returns_none(self):
        obj = MagicMock()
        field = MagicMock()
        field.type = "unknown_type"
        field.name = "whatever"

        result = self.fn(obj, field)
        assert result is None


# ---------------------------------------------------------------------------
# register_combined_tabs
# ---------------------------------------------------------------------------
class TestRegisterCombinedTabs:
    def test_register_called_once_per_model(self):
        from netbox_custom_objects_tab.views.combined import register_combined_tabs

        m1 = MagicMock()
        m1.__name__ = "Device"
        m1._meta.app_label = "dcim"
        m1._meta.model_name = "device"
        m2 = MagicMock()
        m2.__name__ = "Site"
        m2._meta.app_label = "dcim"
        m2._meta.model_name = "site"

        with patch("netbox_custom_objects_tab.views.combined.register_model_view") as mock_register:
            mock_register.return_value = lambda cls: cls
            register_combined_tabs([m1, m2], "Custom Objects", 2000)

        assert mock_register.call_count == 2

    def test_view_class_name_matches_model(self):
        from netbox_custom_objects_tab.views.combined import _make_tab_view

        model = MagicMock()
        model.__name__ = "Device"
        model._meta.app_label = "dcim"
        model._meta.model_name = "device"

        view_cls = _make_tab_view(model)
        assert view_cls.__name__ == "DeviceCustomObjectsTabView"
