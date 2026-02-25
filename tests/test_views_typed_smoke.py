"""
Smoke/unit tests for netbox_custom_objects_tab.views.typed.
"""

import logging
from collections import defaultdict
from unittest.mock import MagicMock, patch

from extras.choices import CustomFieldTypeChoices, CustomFieldUIVisibleChoices
from netbox_custom_objects.tables import CustomObjectTable


def test_typed_module_imports_under_test_mocks():
    import netbox_custom_objects_tab.views.typed as typed_views

    assert typed_views is not None


# ---------------------------------------------------------------------------
# _count_for_type
# ---------------------------------------------------------------------------
class TestCountForType:
    def _make_custom_object_type(self, field_count_map):
        """
        Build a mock custom_object_type returning a dynamic model where:
        filter(**{field_name condition})->count() returns field_count_map[field_name].
        """
        dynamic_model = MagicMock()

        def filter_side_effect(**kwargs):
            query_key = next(iter(kwargs.keys()))
            field_name = query_key[:-3] if query_key.endswith("_id") else query_key
            count = field_count_map.get(field_name, 0)
            qs = MagicMock()
            qs.count.return_value = count
            return qs

        dynamic_model.objects.filter.side_effect = filter_side_effect

        cot = MagicMock()
        cot.get_model.return_value = dynamic_model
        cot.pk = 123
        return cot

    def test_returns_none_when_zero_total(self):
        from netbox_custom_objects_tab.views.typed import _count_for_type

        cot = self._make_custom_object_type({"ref_object": 0, "ref_multi": 0})
        badge = _count_for_type(
            cot,
            [
                ("ref_object", CustomFieldTypeChoices.TYPE_OBJECT),
                ("ref_multi", CustomFieldTypeChoices.TYPE_MULTIOBJECT),
            ],
        )
        instance = MagicMock(pk=42)

        assert badge(instance) is None

    def test_returns_sum_for_object_and_multiobject_fields(self):
        from netbox_custom_objects_tab.views.typed import _count_for_type

        cot = self._make_custom_object_type({"ref_object": 2, "ref_multi": 3})
        badge = _count_for_type(
            cot,
            [
                ("ref_object", CustomFieldTypeChoices.TYPE_OBJECT),
                ("ref_multi", CustomFieldTypeChoices.TYPE_MULTIOBJECT),
            ],
        )
        instance = MagicMock(pk=42)

        assert badge(instance) == 5

    def test_returns_none_when_get_model_raises(self, caplog):
        from netbox_custom_objects_tab.views.typed import _count_for_type

        cot = MagicMock()
        cot.get_model.side_effect = RuntimeError("broken model")
        cot.pk = 123
        badge = _count_for_type(cot, [("ref_object", CustomFieldTypeChoices.TYPE_OBJECT)])
        instance = MagicMock(pk=42)

        assert badge(instance) is None
        assert any("Could not get model for CustomObjectType" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# _build_typed_table_class
# ---------------------------------------------------------------------------
class TestBuildTypedTableClass:
    def _make_cot_and_model(self, field_specs):
        """
        field_specs: list of dicts with keys: name, type, ui_visible, primary.
        Returns (cot, dynamic_model).
        """
        fields = []
        for spec in field_specs:
            f = MagicMock()
            f.name = spec["name"]
            f.type = spec.get("type", CustomFieldTypeChoices.TYPE_TEXT)
            f.ui_visible = spec.get("ui_visible", "visible")
            f.primary = spec.get("primary", False)
            fields.append(f)

        cot = MagicMock()
        cot.fields.all.return_value = fields

        dynamic_model = MagicMock()
        dynamic_model._meta.object_name = "TestDynModel"

        return cot, dynamic_model

    def test_inherits_from_custom_object_table(self):
        from netbox_custom_objects_tab.views.typed import _build_typed_table_class

        cot, model = self._make_cot_and_model([])
        table_cls = _build_typed_table_class(cot, model)
        assert issubclass(table_cls, CustomObjectTable)

    def test_visible_fields_included_hidden_excluded(self):
        from netbox_custom_objects_tab.views.typed import _build_typed_table_class

        ft_mock = MagicMock()
        ft_mock.return_value.get_table_column_field.return_value = MagicMock()
        ft_mock.return_value.render_table_column = MagicMock()

        with patch.dict("netbox_custom_objects.field_types.FIELD_TYPE_CLASS", {
            CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
        }):
            cot, model = self._make_cot_and_model([
                {"name": "visible_field", "type": CustomFieldTypeChoices.TYPE_TEXT, "ui_visible": "visible"},
                {"name": "hidden_field", "type": CustomFieldTypeChoices.TYPE_TEXT, "ui_visible": CustomFieldUIVisibleChoices.HIDDEN},
            ])
            table_cls = _build_typed_table_class(cot, model)

        assert "visible_field" in table_cls.Meta.fields
        assert "hidden_field" not in table_cls.Meta.fields

    def test_get_table_column_field_called_per_visible_field(self):
        from netbox_custom_objects_tab.views.typed import _build_typed_table_class

        ft_instance = MagicMock()
        ft_instance.get_table_column_field.return_value = MagicMock()
        ft_instance.render_table_column = MagicMock()
        ft_mock = MagicMock(return_value=ft_instance)

        with patch.dict("netbox_custom_objects.field_types.FIELD_TYPE_CLASS", {
            CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
        }):
            cot, model = self._make_cot_and_model([
                {"name": "field_a", "type": CustomFieldTypeChoices.TYPE_TEXT},
                {"name": "field_b", "type": CustomFieldTypeChoices.TYPE_TEXT},
            ])
            _build_typed_table_class(cot, model)

        assert ft_instance.get_table_column_field.call_count == 2

    def test_primary_text_field_gets_linkified_render(self):
        from netbox_custom_objects_tab.views.typed import _build_typed_table_class

        ft_instance = MagicMock()
        ft_instance.get_table_column_field.return_value = MagicMock()
        ft_instance.render_table_column_linkified = MagicMock()
        ft_mock = MagicMock(return_value=ft_instance)

        with patch.dict("netbox_custom_objects.field_types.FIELD_TYPE_CLASS", {
            CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
        }):
            cot, model = self._make_cot_and_model([
                {"name": "title", "type": CustomFieldTypeChoices.TYPE_TEXT, "primary": True},
            ])
            table_cls = _build_typed_table_class(cot, model)

        assert hasattr(table_cls, "render_title")
        assert table_cls.render_title is ft_instance.render_table_column_linkified

    def test_not_implemented_column_logged_and_skipped(self, caplog):
        from netbox_custom_objects_tab.views.typed import _build_typed_table_class

        ft_instance = MagicMock()
        ft_instance.get_table_column_field.side_effect = NotImplementedError
        ft_mock = MagicMock(return_value=ft_instance)

        with (
            patch.dict("netbox_custom_objects.field_types.FIELD_TYPE_CLASS", {"custom_type": ft_mock}),
            caplog.at_level(logging.DEBUG, logger="netbox_custom_objects_tab"),
        ):
            cot, model = self._make_cot_and_model([
                {"name": "weird_field", "type": "custom_type"},
            ])
            table_cls = _build_typed_table_class(cot, model)

        # Should still produce a valid class
        assert issubclass(table_cls, CustomObjectTable)


# ---------------------------------------------------------------------------
# _build_filterset_form
# ---------------------------------------------------------------------------
class TestBuildFiltersetForm:
    def _make_cot_and_model(self, field_specs):
        fields = []
        for spec in field_specs:
            f = MagicMock()
            f.name = spec["name"]
            f.type = spec.get("type", CustomFieldTypeChoices.TYPE_TEXT)
            fields.append(f)

        cot = MagicMock()
        cot.fields.all.return_value = fields

        dynamic_model = MagicMock()
        dynamic_model._meta.object_name = "TestDynModel"

        return cot, dynamic_model

    def test_inherits_from_netbox_model_filter_set_form(self):
        from netbox.forms import NetBoxModelFilterSetForm
        from netbox_custom_objects_tab.views.typed import _build_filterset_form

        cot, model = self._make_cot_and_model([])
        form_cls = _build_filterset_form(cot, model)
        assert issubclass(form_cls, NetBoxModelFilterSetForm)

    def test_tag_field_present(self):
        from netbox_custom_objects_tab.views.typed import _build_filterset_form

        cot, model = self._make_cot_and_model([])
        form_cls = _build_filterset_form(cot, model)
        assert hasattr(form_cls, "tag")

    def test_get_filterform_field_called_per_field(self):
        from netbox_custom_objects_tab.views.typed import _build_filterset_form

        ft_instance = MagicMock()
        ft_instance.get_filterform_field.return_value = MagicMock()
        ft_mock = MagicMock(return_value=ft_instance)

        with patch.dict("netbox_custom_objects.field_types.FIELD_TYPE_CLASS", {
            CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
        }):
            cot, model = self._make_cot_and_model([
                {"name": "field_a", "type": CustomFieldTypeChoices.TYPE_TEXT},
                {"name": "field_b", "type": CustomFieldTypeChoices.TYPE_TEXT},
            ])
            _build_filterset_form(cot, model)

        assert ft_instance.get_filterform_field.call_count == 2

    def test_not_implemented_filter_logged_and_skipped(self, caplog):
        from netbox_custom_objects_tab.views.typed import _build_filterset_form

        ft_instance = MagicMock()
        ft_instance.get_filterform_field.side_effect = NotImplementedError
        ft_mock = MagicMock(return_value=ft_instance)

        with (
            patch.dict("netbox_custom_objects.field_types.FIELD_TYPE_CLASS", {"custom_type": ft_mock}),
            caplog.at_level(logging.DEBUG, logger="netbox_custom_objects_tab"),
        ):
            cot, model = self._make_cot_and_model([
                {"name": "weird_field", "type": "custom_type"},
            ])
            form_cls = _build_filterset_form(cot, model)

        assert not hasattr(form_cls, "weird_field")


# ---------------------------------------------------------------------------
# register_typed_tabs
# ---------------------------------------------------------------------------
class TestRegisterTypedTabs:
    def test_register_called_once_per_model_cot_pair(self):
        from netbox_custom_objects_tab.views.typed import register_typed_tabs

        model_class = MagicMock(__name__="Device")
        model_class._meta.app_label = "dcim"
        model_class._meta.model_name = "device"

        ct = MagicMock()
        ct.pk = 10

        field1 = MagicMock()
        field1.related_object_type_id = 10
        field1.custom_object_type_id = 100
        field1.custom_object_type = MagicMock(slug="server", pk=100)
        field1.custom_object_type.__str__ = lambda self: "Server"
        field1.name = "device_ref"
        field1.type = CustomFieldTypeChoices.TYPE_OBJECT

        field2 = MagicMock()
        field2.related_object_type_id = 10
        field2.custom_object_type_id = 200
        field2.custom_object_type = MagicMock(slug="link", pk=200)
        field2.custom_object_type.__str__ = lambda self: "Link"
        field2.name = "device_link"
        field2.type = CustomFieldTypeChoices.TYPE_MULTIOBJECT

        with (
            patch("netbox_custom_objects_tab.views.typed.CustomObjectTypeField") as mock_cotf,
            patch("netbox_custom_objects_tab.views.typed.ContentType") as mock_ct,
            patch("netbox_custom_objects_tab.views.typed.register_model_view") as mock_register,
        ):
            mock_cotf.objects.filter.return_value.select_related.return_value = [field1, field2]
            mock_ct.objects.get_for_model.return_value = ct
            mock_register.return_value = lambda cls: cls

            register_typed_tabs([model_class], weight=2100)

        # Two distinct COTs -> two register calls
        assert mock_register.call_count == 2

    def test_fields_with_no_related_object_type_skipped(self):
        from netbox_custom_objects_tab.views.typed import register_typed_tabs

        model_class = MagicMock()
        model_class._meta.app_label = "dcim"
        model_class._meta.model_name = "device"

        ct = MagicMock()
        ct.pk = 10

        field = MagicMock()
        field.related_object_type_id = None  # should be skipped
        field.custom_object_type_id = 100
        field.name = "orphan"
        field.type = CustomFieldTypeChoices.TYPE_OBJECT

        with (
            patch("netbox_custom_objects_tab.views.typed.CustomObjectTypeField") as mock_cotf,
            patch("netbox_custom_objects_tab.views.typed.ContentType") as mock_ct,
            patch("netbox_custom_objects_tab.views.typed.register_model_view") as mock_register,
        ):
            mock_cotf.objects.filter.return_value.select_related.return_value = [field]
            mock_ct.objects.get_for_model.return_value = ct
            mock_register.return_value = lambda cls: cls

            register_typed_tabs([model_class], weight=2100)

        mock_register.assert_not_called()

    def test_models_not_in_model_classes_skipped(self):
        from netbox_custom_objects_tab.views.typed import register_typed_tabs

        model_class = MagicMock()
        model_class._meta.app_label = "dcim"
        model_class._meta.model_name = "device"

        ct = MagicMock()
        ct.pk = 10

        # Field references content_type 99, not 10
        field = MagicMock()
        field.related_object_type_id = 99
        field.custom_object_type_id = 100
        field.custom_object_type = MagicMock(slug="server", pk=100)
        field.name = "other_ref"
        field.type = CustomFieldTypeChoices.TYPE_OBJECT

        with (
            patch("netbox_custom_objects_tab.views.typed.CustomObjectTypeField") as mock_cotf,
            patch("netbox_custom_objects_tab.views.typed.ContentType") as mock_ct,
            patch("netbox_custom_objects_tab.views.typed.register_model_view") as mock_register,
        ):
            mock_cotf.objects.filter.return_value.select_related.return_value = [field]
            mock_ct.objects.get_for_model.return_value = ct
            mock_register.return_value = lambda cls: cls

            register_typed_tabs([model_class], weight=2100)

        mock_register.assert_not_called()
