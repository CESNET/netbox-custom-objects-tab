"""
Smoke/unit tests for netbox_custom_objects_tab.views.typed.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
from extras.choices import CustomFieldTypeChoices, CustomFieldUIVisibleChoices
from netbox_custom_objects.tables import CustomObjectTable


def test_typed_module_imports_under_test_mocks():
    import netbox_custom_objects_tab.views.typed as typed_views

    assert typed_views is not None


# ---------------------------------------------------------------------------
# _count_for_type
# ---------------------------------------------------------------------------
class TestCountForType:
    def _make_custom_object_type(self, distinct_count):
        """
        Build a mock custom_object_type returning a dynamic model whose
        filter(Q(...)).distinct().count() resolves to ``distinct_count``.

        The badge logic must call filter exactly ONCE with a Q object (not N
        separate filters per field) and chain .distinct().count() on it. The
        mock collects the Q passed to filter so tests can inspect it.
        """
        dynamic_model = MagicMock()
        captured = {}

        def filter_side_effect(*args, **kwargs):
            captured["args"] = args
            captured["kwargs"] = kwargs
            qs = MagicMock()
            qs.distinct.return_value.count.return_value = distinct_count
            return qs

        dynamic_model.objects.filter.side_effect = filter_side_effect

        cot = MagicMock()
        cot.get_model.return_value = dynamic_model
        cot.pk = 123
        return cot, dynamic_model, captured

    def test_returns_none_when_zero_total(self):
        from netbox_custom_objects_tab.views.typed import _count_for_type

        cot, _, _ = self._make_custom_object_type(distinct_count=0)
        badge = _count_for_type(
            cot,
            [
                ("ref_object", CustomFieldTypeChoices.TYPE_OBJECT),
                ("ref_multi", CustomFieldTypeChoices.TYPE_MULTIOBJECT),
            ],
            host_ct_id=10,
        )
        instance = MagicMock(pk=42)

        assert badge(instance) is None

    def test_uses_single_filter_with_OR_of_field_predicates(self):
        """The badge must build one Q-OR-Q expression and pass it to a single
        filter() call so .distinct() can deduplicate rows matching multiple
        fields at the SQL level. Earlier versions made N separate filter calls
        and summed their counts, which over-counted overlapping rows.
        """
        from django.db.models import Q

        from netbox_custom_objects_tab.views.typed import _count_for_type

        cot, dynamic_model, captured = self._make_custom_object_type(distinct_count=4)
        badge = _count_for_type(
            cot,
            [
                ("primary_device", CustomFieldTypeChoices.TYPE_OBJECT),
                ("backup_device", CustomFieldTypeChoices.TYPE_OBJECT),
                ("affected_devices", CustomFieldTypeChoices.TYPE_MULTIOBJECT),
            ],
            host_ct_id=10,
        )
        instance = MagicMock(pk=42)

        assert badge(instance) == 4
        # filter must be called exactly once (not three times — one per field)
        assert dynamic_model.objects.filter.call_count == 1
        # ...and the single positional arg must be a Q expression
        (q_arg,) = captured["args"]
        assert isinstance(q_arg, Q)
        # The Q must combine the three field predicates with OR
        assert q_arg.connector == "OR"
        assert len(q_arg.children) == 3

    def test_returns_none_when_field_infos_empty(self):
        """Defensive: empty field_infos must not yield filter() — that would
        return all rows, producing a wrong tab badge.
        """
        from netbox_custom_objects_tab.views.typed import _count_for_type

        cot, dynamic_model, _ = self._make_custom_object_type(distinct_count=999)
        badge = _count_for_type(cot, [], host_ct_id=10)
        assert badge(MagicMock(pk=42)) is None
        # filter() must not be called when there are no fields to OR together
        assert dynamic_model.objects.filter.call_count == 0

    def test_returns_none_when_get_model_raises(self, caplog):
        from netbox_custom_objects_tab.views.typed import _count_for_type

        cot = MagicMock()
        cot.get_model.side_effect = RuntimeError("broken model")
        cot.pk = 123
        badge = _count_for_type(cot, [("ref_object", CustomFieldTypeChoices.TYPE_OBJECT)], host_ct_id=10)
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

        with patch.dict(
            "netbox_custom_objects.field_types.FIELD_TYPE_CLASS",
            {
                CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
            },
        ):
            cot, model = self._make_cot_and_model(
                [
                    {"name": "visible_field", "type": CustomFieldTypeChoices.TYPE_TEXT, "ui_visible": "visible"},
                    {
                        "name": "hidden_field",
                        "type": CustomFieldTypeChoices.TYPE_TEXT,
                        "ui_visible": CustomFieldUIVisibleChoices.HIDDEN,
                    },
                ]
            )
            table_cls = _build_typed_table_class(cot, model)

        assert "visible_field" in table_cls.Meta.fields
        assert "hidden_field" not in table_cls.Meta.fields

    def test_get_table_column_field_called_per_visible_field(self):
        from netbox_custom_objects_tab.views.typed import _build_typed_table_class

        ft_instance = MagicMock()
        ft_instance.get_table_column_field.return_value = MagicMock()
        ft_instance.render_table_column = MagicMock()
        ft_mock = MagicMock(return_value=ft_instance)

        with patch.dict(
            "netbox_custom_objects.field_types.FIELD_TYPE_CLASS",
            {
                CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
            },
        ):
            cot, model = self._make_cot_and_model(
                [
                    {"name": "field_a", "type": CustomFieldTypeChoices.TYPE_TEXT},
                    {"name": "field_b", "type": CustomFieldTypeChoices.TYPE_TEXT},
                ]
            )
            _build_typed_table_class(cot, model)

        assert ft_instance.get_table_column_field.call_count == 2

    def test_primary_text_field_gets_linkified_render(self):
        from netbox_custom_objects_tab.views.typed import _build_typed_table_class

        ft_instance = MagicMock()
        ft_instance.get_table_column_field.return_value = MagicMock()
        ft_instance.render_table_column_linkified = MagicMock()
        ft_mock = MagicMock(return_value=ft_instance)

        with patch.dict(
            "netbox_custom_objects.field_types.FIELD_TYPE_CLASS",
            {
                CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
            },
        ):
            cot, model = self._make_cot_and_model(
                [
                    {"name": "title", "type": CustomFieldTypeChoices.TYPE_TEXT, "primary": True},
                ]
            )
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
            cot, model = self._make_cot_and_model(
                [
                    {"name": "weird_field", "type": "custom_type"},
                ]
            )
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

        with patch.dict(
            "netbox_custom_objects.field_types.FIELD_TYPE_CLASS",
            {
                CustomFieldTypeChoices.TYPE_TEXT: ft_mock,
            },
        ):
            cot, model = self._make_cot_and_model(
                [
                    {"name": "field_a", "type": CustomFieldTypeChoices.TYPE_TEXT},
                    {"name": "field_b", "type": CustomFieldTypeChoices.TYPE_TEXT},
                ]
            )
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
            cot, model = self._make_cot_and_model(
                [
                    {"name": "weird_field", "type": "custom_type"},
                ]
            )
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
            # register_typed_tabs makes two filter() calls: non-poly fields
            # (.select_related) and polymorphic fields (.select_related.prefetch_related).
            non_poly_qs = MagicMock()
            non_poly_qs.select_related.return_value = [field1, field2]
            poly_qs = MagicMock()
            poly_qs.select_related.return_value.prefetch_related.return_value = []
            mock_cotf.objects.filter.side_effect = [non_poly_qs, poly_qs]
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
            non_poly_qs = MagicMock()
            non_poly_qs.select_related.return_value = [field]
            poly_qs = MagicMock()
            poly_qs.select_related.return_value.prefetch_related.return_value = []
            mock_cotf.objects.filter.side_effect = [non_poly_qs, poly_qs]
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
            non_poly_qs = MagicMock()
            non_poly_qs.select_related.return_value = [field]
            poly_qs = MagicMock()
            poly_qs.select_related.return_value.prefetch_related.return_value = []
            mock_cotf.objects.filter.side_effect = [non_poly_qs, poly_qs]
            mock_ct.objects.get_for_model.return_value = ct
            mock_register.return_value = lambda cls: cls

            register_typed_tabs([model_class], weight=2100)

        mock_register.assert_not_called()


# ---------------------------------------------------------------------------
# register_typed_tabs -- label population + deterministic ordering
# ---------------------------------------------------------------------------
class TestRegisterTypedTabsLabelAndOrder:
    def test_field_label_and_name_populated_in_field_infos_and_sorted(self):
        from netbox_custom_objects_tab.views.typed import register_typed_tabs

        model_class = MagicMock(__name__="Device")
        model_class._meta.app_label = "dcim"
        model_class._meta.model_name = "device"

        ct = MagicMock()
        ct.pk = 10

        # Two fields on the same CustomObjectType; registered in order b, a; expect sorted a, b
        field_b = MagicMock()
        field_b.related_object_type_id = 10
        field_b.custom_object_type_id = 100
        field_b.custom_object_type = MagicMock(slug="server", pk=100)
        field_b.name = "b_device"
        field_b.label = "B Device"
        field_b.type = CustomFieldTypeChoices.TYPE_OBJECT

        field_a = MagicMock()
        field_a.related_object_type_id = 10
        field_a.custom_object_type_id = 100
        field_a.custom_object_type = MagicMock(slug="server", pk=100)
        field_a.name = "a_device"
        field_a.label = ""  # blank label -> should fall back to name
        field_a.type = CustomFieldTypeChoices.TYPE_MULTIOBJECT

        captured_field_infos = {}

        # _make_typed_tab_view's signature gained a 5th positional `host_ct_id`
        # in 2.4.0 (used to build polymorphic Q-filters). Accept it here so the
        # mock matches the call site, then capture field_infos for assertion.
        def fake_make_view(model_cls, cot, field_infos, weight, host_ct_id):
            captured_field_infos["infos"] = list(field_infos)
            return MagicMock()

        with (
            patch("netbox_custom_objects_tab.views.typed.CustomObjectTypeField") as mock_cotf,
            patch("netbox_custom_objects_tab.views.typed.ContentType") as mock_ct,
            patch("netbox_custom_objects_tab.views.typed.register_model_view") as mock_register,
            patch("netbox_custom_objects_tab.views.typed._make_typed_tab_view", side_effect=fake_make_view),
        ):
            non_poly_qs = MagicMock()
            non_poly_qs.select_related.return_value = [field_b, field_a]
            poly_qs = MagicMock()
            poly_qs.select_related.return_value.prefetch_related.return_value = []
            mock_cotf.objects.filter.side_effect = [non_poly_qs, poly_qs]
            mock_ct.objects.get_for_model.return_value = ct
            mock_register.return_value = lambda cls: cls

            register_typed_tabs([model_class], weight=2100)

        infos = captured_field_infos["infos"]
        assert len(infos) == 2
        # Sorted by field name ascending
        assert infos[0][0] == "a_device"
        assert infos[1][0] == "b_device"
        # Labels: blank -> falls back to name; populated -> kept
        assert infos[0][2] == "a_device"
        assert infos[1][2] == "B Device"


# ---------------------------------------------------------------------------
# _get_base_template
# ---------------------------------------------------------------------------
class TestGetBaseTemplate:
    def _make_instance(self, app_label, model_name):
        from unittest.mock import MagicMock

        instance = MagicMock()
        instance._meta.app_label = app_label
        instance._meta.model_name = model_name
        return instance

    def test_co_model_returns_shared_template(self):
        from netbox_custom_objects_tab.views.typed import _CO_BASE_TEMPLATE, _get_base_template

        instance = self._make_instance("netbox_custom_objects", "table28model")
        assert _get_base_template(instance) == _CO_BASE_TEMPLATE

    def test_non_co_model_returns_per_model_template(self):
        from netbox_custom_objects_tab.views.typed import _get_base_template

        instance = self._make_instance("dcim", "device")
        assert _get_base_template(instance) == "dcim/device.html"


# ---------------------------------------------------------------------------
# _build_add_links
# ---------------------------------------------------------------------------
class TestBuildAddLinks:
    @pytest.fixture(autouse=True)
    def _patch_content_type(self):
        # _build_add_links calls ContentType.objects.get_for_model(host._meta.model)
        # unconditionally; patch it so MagicMock hosts don't reach the real ORM.
        with patch("netbox_custom_objects_tab.views.typed.ContentType"):
            yield

    def _make_host(self, pk=42, app_label="dcim", model_name="device"):
        host = MagicMock()
        host.pk = pk
        host._meta.app_label = app_label
        host._meta.model_name = model_name
        return host

    def test_returns_empty_when_reverse_fails(self):
        from django.urls import NoReverseMatch

        from netbox_custom_objects_tab.views.typed import _build_add_links

        with patch("netbox_custom_objects_tab.views.typed.reverse", side_effect=NoReverseMatch):
            links = _build_add_links(
                "server",
                self._make_host(42),
                [("device", CustomFieldTypeChoices.TYPE_OBJECT, "Device")],
                "/dcim/devices/42/",
            )
        assert links == []

    def test_single_field_produces_one_link_with_prefill_and_return_url(self):
        from netbox_custom_objects_tab.views.typed import _build_add_links

        with patch(
            "netbox_custom_objects_tab.views.typed.reverse",
            return_value="/plugins/custom-objects/server/add/",
        ):
            links = _build_add_links(
                "server",
                self._make_host(42),
                [("device", CustomFieldTypeChoices.TYPE_OBJECT, "Device")],
                "/dcim/devices/42/custom-objects-server/",
            )

        assert len(links) == 1
        assert links[0]["field_name"] == "device"
        assert links[0]["label"] == "Device"
        # Query string contains both the field prefill and the return_url, in either order
        url = links[0]["url"]
        assert url.startswith("/plugins/custom-objects/server/add/?")
        assert "device=42" in url
        assert "return_url=%2Fdcim%2Fdevices%2F42%2Fcustom-objects-server%2F" in url

    def test_multiple_fields_produce_multiple_links(self):
        from netbox_custom_objects_tab.views.typed import _build_add_links

        with patch(
            "netbox_custom_objects_tab.views.typed.reverse",
            return_value="/plugins/custom-objects/link/add/",
        ):
            links = _build_add_links(
                "link",
                self._make_host(7),
                [
                    ("primary_device", CustomFieldTypeChoices.TYPE_OBJECT, "Primary"),
                    ("backup_device", CustomFieldTypeChoices.TYPE_OBJECT, "Backup"),
                ],
                "/dcim/devices/7/",
            )

        assert len(links) == 2
        names = {link["field_name"] for link in links}
        labels = {link["label"] for link in links}
        assert names == {"primary_device", "backup_device"}
        assert labels == {"Primary", "Backup"}
        for link in links:
            assert f"{link['field_name']}=7" in link["url"]

    def test_duplicate_field_names_deduplicated(self):
        from netbox_custom_objects_tab.views.typed import _build_add_links

        with patch(
            "netbox_custom_objects_tab.views.typed.reverse",
            return_value="/plugins/custom-objects/x/add/",
        ):
            links = _build_add_links(
                "x",
                self._make_host(1),
                [
                    ("device", CustomFieldTypeChoices.TYPE_OBJECT, "Device"),
                    ("device", CustomFieldTypeChoices.TYPE_MULTIOBJECT, "Device"),
                ],
                "/dcim/devices/1/",
            )
        assert len(links) == 1
        assert links[0]["field_name"] == "device"

    def test_label_falls_back_to_field_name_when_label_blank(self):
        from netbox_custom_objects_tab.views.typed import _build_add_links

        with patch(
            "netbox_custom_objects_tab.views.typed.reverse",
            return_value="/plugins/custom-objects/x/add/",
        ):
            links = _build_add_links(
                "x",
                self._make_host(1),
                [("device_ref", CustomFieldTypeChoices.TYPE_OBJECT, "")],
                "/dcim/devices/1/",
            )
        assert links[0]["label"] == "device_ref"

    def test_two_tuple_field_infos_supported_label_defaults_to_name(self):
        """Backward-compatible: 2-tuples (no label) work via star unpacking."""
        from netbox_custom_objects_tab.views.typed import _build_add_links

        with patch(
            "netbox_custom_objects_tab.views.typed.reverse",
            return_value="/plugins/custom-objects/x/add/",
        ):
            links = _build_add_links(
                "x",
                self._make_host(1),
                [("device", CustomFieldTypeChoices.TYPE_OBJECT)],
                "/dcim/devices/1/",
            )
        assert links[0]["label"] == "device"

    def test_return_url_with_query_string_is_url_encoded(self):
        """A return_url containing & and ? must be URL-encoded so it doesn't break the outer query string."""
        from netbox_custom_objects_tab.views.typed import _build_add_links

        with patch(
            "netbox_custom_objects_tab.views.typed.reverse",
            return_value="/plugins/custom-objects/x/add/",
        ):
            links = _build_add_links(
                "x",
                self._make_host(1),
                [("device", CustomFieldTypeChoices.TYPE_OBJECT, "Device")],
                "/dcim/devices/1/custom-objects-x/?tag=foo&q=bar",
            )
        url = links[0]["url"]
        # The inner '?' and '&' must be percent-encoded inside the return_url value
        assert "return_url=%2Fdcim%2Fdevices%2F1%2Fcustom-objects-x%2F%3Ftag%3Dfoo%26q%3Dbar" in url
        # Outer URL must have exactly one literal '?'
        assert url.count("?") == 1
