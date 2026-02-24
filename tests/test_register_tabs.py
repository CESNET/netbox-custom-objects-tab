"""
Unit tests for netbox_custom_objects_tab.views.

These tests do NOT require a live NetBox instance or database.
All NetBox-specific packages are mocked in tests/conftest.py;
Django is configured via tests/settings.py (in-memory SQLite, no migrations).
"""
import logging
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _filter_linked_objects
# ---------------------------------------------------------------------------

class TestFilterLinkedObjects:
    """Pure-Python filter helper — no DB or Django state required."""

    @pytest.fixture(autouse=True)
    def get_fn(self):
        from netbox_custom_objects_tab import views
        self.fn = views._filter_linked_objects

    def test_empty_query_returns_same_list(self):
        linked = [_make_pair('Device A', 'Server', 'dev_field')]
        assert self.fn(linked, '') is linked

    def test_whitespace_only_returns_same_list(self):
        linked = [_make_pair('Device A', 'Server', 'dev_field')]
        assert self.fn(linked, '   ') is linked

    def test_no_match_returns_empty(self):
        linked = [
            _make_pair('Device A', 'Server', 'dev_field'),
            _make_pair('Device B', 'Router', 'net_field'),
        ]
        assert self.fn(linked, 'zzznomatch') == []

    def test_match_on_object_str(self):
        linked = [
            _make_pair('Device Alpha', 'Server', 'dev_field'),
            _make_pair('Device Beta', 'Router', 'dev_field'),
        ]
        result = self.fn(linked, 'alpha')
        assert len(result) == 1
        # The filter returns new tuples; compare the contained mock objects by identity
        assert result[0][0] is linked[0][0]

    def test_match_on_type_str(self):
        linked = [
            _make_pair('Device A', 'ServerType', 'dev_field'),
            _make_pair('Device B', 'RouterType', 'dev_field'),
        ]
        result = self.fn(linked, 'router')
        assert len(result) == 1
        assert result[0][0] is linked[1][0]

    def test_match_on_field_str(self):
        linked = [
            _make_pair('Device A', 'Server', 'primary_device_field'),
            _make_pair('Device B', 'Router', 'network_interface_field'),
        ]
        result = self.fn(linked, 'network')
        assert len(result) == 1
        assert result[0][0] is linked[1][0]

    def test_case_insensitive(self):
        linked = [_make_pair('Device UPPERCASE', 'Server', 'dev_field')]
        assert self.fn(linked, 'uppercase') != []
        assert self.fn(linked, 'UPPERCASE') != []
        assert self.fn(linked, 'UpperCase') != []

    def test_leading_trailing_whitespace_stripped(self):
        linked = [_make_pair('Device A', 'Server', 'dev_field')]
        assert len(self.fn(linked, '  device  ')) == 1


# ---------------------------------------------------------------------------
# _count_linked_custom_objects
# ---------------------------------------------------------------------------

class TestCountLinkedCustomObjects:
    """Badge callable must return None (not 0) when nothing is linked."""

    def _count(self, fields_and_counts):
        """
        Build mock fields, patch CustomObjectTypeField (local import target)
        and ContentType (module-level name), then call the count function.

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
            field.name = 'some_field'
            mock_fields.append(field)

        instance = MagicMock()
        instance.pk = 1
        instance._meta.model = MagicMock()

        # CustomObjectTypeField is imported *locally* inside the function, so we
        # must patch the source module, not netbox_custom_objects_tab.views.
        with patch('netbox_custom_objects.models.CustomObjectTypeField') as MockCOTF, \
             patch('netbox_custom_objects_tab.views.ContentType') as MockCT:
            MockCT.objects.get_for_model.return_value = MagicMock()
            MockCOTF.objects.filter.return_value.select_related.return_value = mock_fields

            from netbox_custom_objects_tab import views
            return views._count_linked_custom_objects(instance)

    def test_returns_none_when_no_fields(self):
        assert self._count([]) is None

    def test_returns_none_not_zero(self):
        result = self._count([])
        # Must be None, not 0 — hide_if_empty checks truthiness
        assert result is None
        assert result != 0

    def test_returns_total_when_positive(self):
        from extras.choices import CustomFieldTypeChoices
        result = self._count([
            (CustomFieldTypeChoices.TYPE_OBJECT, 3),
            (CustomFieldTypeChoices.TYPE_OBJECT, 2),
        ])
        assert result == 5

    def test_returns_none_when_all_counts_are_zero(self):
        from extras.choices import CustomFieldTypeChoices
        result = self._count([
            (CustomFieldTypeChoices.TYPE_OBJECT, 0),
            (CustomFieldTypeChoices.TYPE_MULTIOBJECT, 0),
        ])
        assert result is None


# ---------------------------------------------------------------------------
# register_tabs — graceful handling of unknown app labels
# ---------------------------------------------------------------------------

class TestRegisterTabs:

    def test_unknown_wildcard_app_logs_warning_no_exception(self, caplog):
        """register_tabs() with 'unknownapp.*' must warn and not raise."""
        with patch('netbox_custom_objects_tab.views.get_plugin_config') as mock_cfg, \
             patch('netbox_custom_objects_tab.views.register_model_view'), \
             patch('netbox_custom_objects_tab.views.apps') as mock_apps:

            mock_cfg.return_value = ['nonexistent_app_xyz.*']
            mock_apps.get_app_config.side_effect = LookupError('no such app')

            from netbox_custom_objects_tab import views

            with caplog.at_level(logging.WARNING, logger='netbox_custom_objects_tab'):
                views.register_tabs()  # must not raise

        assert any('nonexistent_app_xyz' in r.message for r in caplog.records)

    def test_unknown_specific_model_logs_warning_no_exception(self, caplog):
        """register_tabs() with 'unknownapp.somemodel' must warn and not raise."""
        with patch('netbox_custom_objects_tab.views.get_plugin_config') as mock_cfg, \
             patch('netbox_custom_objects_tab.views.register_model_view'), \
             patch('netbox_custom_objects_tab.views.apps') as mock_apps:

            mock_cfg.return_value = ['nonexistent_app_xyz.somemodel']
            mock_apps.get_model.side_effect = LookupError('no such model')

            from netbox_custom_objects_tab import views

            with caplog.at_level(logging.WARNING, logger='netbox_custom_objects_tab'):
                views.register_tabs()  # must not raise

        assert any('nonexistent_app_xyz.somemodel' in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# CustomObjectsTabTable
# ---------------------------------------------------------------------------

class TestCustomObjectsTabTable:
    """Column-preference machinery on the lightweight table class."""

    @pytest.fixture(autouse=True)
    def table_cls(self):
        from netbox_custom_objects_tab.views import CustomObjectsTabTable
        self.cls = CustomObjectsTabTable

    def test_default_columns_contains_all_six(self):
        assert set(self.cls.Meta.default_columns) == {
            'type', 'object', 'value', 'field', 'tags', 'actions'
        }

    def test_actions_is_exempt(self):
        assert 'actions' in self.cls.exempt_columns

    def test_name_property(self):
        t = self.cls([], empty_text='')
        assert t.name == 'CustomObjectsTabTable'

    def test_all_columns_visible_by_default(self):
        t = self.cls([], empty_text='')
        t._set_columns(list(self.cls.Meta.default_columns))
        visible = {col for col, _ in t.selected_columns}
        assert {'type', 'object', 'value', 'field', 'tags'}.issubset(visible)

    def test_hidden_column_not_in_selected(self):
        t = self.cls([], empty_text='')
        cols_without_value = [c for c in self.cls.Meta.default_columns if c != 'value']
        t._set_columns(cols_without_value)
        visible = {col for col, _ in t.selected_columns}
        assert 'value' not in visible

    def test_exempt_column_always_visible(self):
        t = self.cls([], empty_text='')
        # Pass only non-exempt, non-actions columns
        t._set_columns(['type'])
        # 'actions' is exempt — must not appear in selected_columns
        # (exempt columns are excluded from the modal, not from rendering)
        selected_names = {col for col, _ in t.selected_columns}
        assert 'actions' not in selected_names   # exempt cols excluded from selected_columns


# ---------------------------------------------------------------------------
# _sort_header
# ---------------------------------------------------------------------------

class TestSortHeader:
    @pytest.fixture(autouse=True)
    def get_fn(self):
        from netbox_custom_objects_tab.views import _sort_header
        self.fn = _sort_header

    def test_inactive_column_points_to_asc(self):
        result = self.fn('', 'type', 'object', 'asc')
        assert 'sort=type' in result['url']
        assert 'dir=asc' in result['url']
        assert result['icon'] is None

    def test_active_asc_column_icon_is_arrow_up(self):
        result = self.fn('', 'type', 'type', 'asc')
        assert result['icon'] == 'arrow-up'
        assert 'dir=desc' in result['url']

    def test_active_desc_column_icon_is_arrow_down(self):
        result = self.fn('', 'type', 'type', 'desc')
        assert result['icon'] == 'arrow-down'
        assert 'dir=asc' in result['url']

    def test_base_params_preserved(self):
        result = self.fn('q=foo&tag=bar', 'type', '', 'asc')
        assert result['url'].startswith('?q=foo&tag=bar&')
