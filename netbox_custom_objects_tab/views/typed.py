import logging

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import get_object_or_404, render
from django.views.generic import View
from extras.choices import CustomFieldTypeChoices, CustomFieldUIVisibleChoices
from netbox.forms import NetBoxModelFilterSetForm
from netbox_custom_objects import field_types
from netbox_custom_objects.filtersets import get_filterset_class
from netbox_custom_objects.models import CustomObjectTypeField
from netbox_custom_objects.tables import CustomObjectTable
from utilities.forms.fields import TagFilterField
from utilities.views import ViewTab, register_model_view

logger = logging.getLogger("netbox_custom_objects_tab")


def _build_typed_table_class(custom_object_type, dynamic_model):
    """
    Dynamically build a django-tables2 table class for a Custom Object Type.
    Replicates CustomObjectTableMixin.get_table() logic.
    """
    model_fields = custom_object_type.fields.all()
    fields = ["id"] + [field.name for field in model_fields if field.ui_visible != CustomFieldUIVisibleChoices.HIDDEN]

    meta = type(
        "Meta",
        (),
        {
            "model": dynamic_model,
            "fields": fields,
            "attrs": {
                "class": "table table-hover object-list",
            },
        },
    )

    attrs = {
        "Meta": meta,
        "__module__": "database.tables",
    }

    for field in model_fields:
        if field.ui_visible == CustomFieldUIVisibleChoices.HIDDEN:
            continue
        field_type = field_types.FIELD_TYPE_CLASS[field.type]()
        try:
            attrs[field.name] = field_type.get_table_column_field(field)
        except NotImplementedError:
            logger.debug("typed tab: %s field type not implemented; using default column", field.name)

        linkable_field_types = [
            CustomFieldTypeChoices.TYPE_TEXT,
            CustomFieldTypeChoices.TYPE_LONGTEXT,
        ]
        if field.primary and field.type in linkable_field_types:
            attrs[f"render_{field.name}"] = field_type.render_table_column_linkified
        else:
            try:
                attrs[f"render_{field.name}"] = field_type.render_table_column
            except AttributeError:
                pass

    return type(
        f"{dynamic_model._meta.object_name}Table",
        (CustomObjectTable,),
        attrs,
    )


def _build_filterset_form(custom_object_type, dynamic_model):
    """
    Dynamically build a filterset form class for a Custom Object Type.
    Replicates CustomObjectListView.get_filterset_form() logic.
    """
    attrs = {
        "model": dynamic_model,
        "__module__": "database.filterset_forms",
        "tag": TagFilterField(dynamic_model),
    }

    for field in custom_object_type.fields.all():
        field_type = field_types.FIELD_TYPE_CLASS[field.type]()
        try:
            attrs[field.name] = field_type.get_filterform_field(field)
        except NotImplementedError:
            logger.debug("typed tab: %s filter field not supported", field.name)

    return type(
        f"{dynamic_model._meta.object_name}FilterForm",
        (NetBoxModelFilterSetForm,),
        attrs,
    )


def _count_for_type(custom_object_type, field_infos):
    """
    Return a badge callable for one Custom Object Type.
    field_infos = list of (field_name, field_type) for fields referencing the parent model.
    Uses COUNT(*) only. Returns None when 0.
    """

    def _badge(instance):
        try:
            dynamic_model = custom_object_type.get_model()
        except Exception:
            logger.exception(
                "Could not get model for CustomObjectType %s",
                custom_object_type.pk,
            )
            return None

        total = 0
        for field_name, field_type in field_infos:
            if field_type == CustomFieldTypeChoices.TYPE_OBJECT:
                total += dynamic_model.objects.filter(**{f"{field_name}_id": instance.pk}).count()
            elif field_type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
                total += dynamic_model.objects.filter(**{field_name: instance.pk}).count()

        return total if total > 0 else None

    return _badge


def _make_typed_tab_view(model_class, custom_object_type, field_infos, weight):
    """
    Factory returning a View subclass for a per-type tab.
    field_infos = list of (field_name, field_type) for fields of this Custom Object Type
    that reference model_class.
    """
    badge_fn = _count_for_type(custom_object_type, field_infos)
    cot_pk = custom_object_type.pk
    cot_label = str(custom_object_type)

    class _TypedTabView(View):
        tab = ViewTab(
            label=cot_label,
            badge=badge_fn,
            weight=weight,
            hide_if_empty=True,
        )

        def get(self, request, pk):
            try:
                qs = model_class.objects.restrict(request.user, "view")
            except AttributeError:
                qs = model_class.objects.all()

            instance = get_object_or_404(qs, pk=pk)

            # Re-fetch CustomObjectType at request time (may have changed since ready())
            from netbox_custom_objects.models import CustomObjectType as COTModel

            try:
                cot = COTModel.objects.get(pk=cot_pk)
            except COTModel.DoesNotExist:
                return render(
                    request,
                    "netbox_custom_objects_tab/typed/tab.html",
                    {
                        "object": instance,
                        "tab": self.tab,
                        "base_template": f"{instance._meta.app_label}/{instance._meta.model_name}.html",
                        "table": None,
                    },
                )

            try:
                dynamic_model = cot.get_model()
            except Exception:
                logger.exception("Could not get model for CustomObjectType %s", cot_pk)
                return render(
                    request,
                    "netbox_custom_objects_tab/typed/tab.html",
                    {
                        "object": instance,
                        "tab": self.tab,
                        "base_template": f"{instance._meta.app_label}/{instance._meta.model_name}.html",
                        "table": None,
                    },
                )

            # Build base queryset: union of all field filters for this type
            q_filter = Q()
            for field_name, field_type in field_infos:
                if field_type == CustomFieldTypeChoices.TYPE_OBJECT:
                    q_filter |= Q(**{f"{field_name}_id": instance.pk})
                elif field_type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
                    q_filter |= Q(**{field_name: instance.pk})

            base_qs = dynamic_model.objects.filter(q_filter).distinct()

            # Apply filterset
            filterset_class = get_filterset_class(dynamic_model)
            filterset = filterset_class(request.GET, queryset=base_qs)
            filtered_qs = filterset.qs

            # Build filterset form for the filter sidebar
            filterset_form_class = _build_filterset_form(cot, dynamic_model)
            filter_form = filterset_form_class(request.GET)

            # Build table class and instantiate
            table_class = _build_typed_table_class(cot, dynamic_model)
            table = table_class(filtered_qs, user=request.user)
            table.columns.show("pk")

            # Shadow @cached_property to avoid reverse error for dynamic models
            table.htmx_url = request.path
            table.embedded = False

            table.configure(request)

            # User preferences for paginator placement
            preferences = {}
            if request.user.is_authenticated and (userconfig := getattr(request.user, "config", None)):
                preferences["pagination.placement"] = userconfig.get("pagination.placement", "bottom")
            else:
                preferences = {"pagination.placement": "bottom"}

            return_url = request.get_full_path()

            context = {
                "object": instance,
                "tab": self.tab,
                "base_template": f"{instance._meta.app_label}/{instance._meta.model_name}.html",
                "table": table,
                "filter_form": filter_form,
                "return_url": return_url,
                "custom_object_type": cot,
                "model": dynamic_model,
                "preferences": preferences,
            }

            if request.htmx and not request.htmx.boosted:
                return render(request, "htmx/table.html", context)
            return render(request, "netbox_custom_objects_tab/typed/tab.html", context)

    _TypedTabView.__name__ = f"{model_class.__name__}_{custom_object_type.slug}_TypedTabView"
    _TypedTabView.__qualname__ = f"{model_class.__name__}_{custom_object_type.slug}_TypedTabView"
    return _TypedTabView


def register_typed_tabs(model_classes, weight):
    """
    Register per-type tabs for each model × CustomObjectType pair.
    Pre-fetches all relevant CustomObjectTypeFields and groups them.
    """

    try:
        # Collect all relevant fields
        all_fields = CustomObjectTypeField.objects.filter(
            type__in=[
                CustomFieldTypeChoices.TYPE_OBJECT,
                CustomFieldTypeChoices.TYPE_MULTIOBJECT,
            ],
        ).select_related("custom_object_type")

        # Group by (content_type_id, custom_object_type_pk)
        # -> list of (field_name, field_type)
        from collections import defaultdict

        ct_cot_fields = defaultdict(list)
        ct_cot_map = {}  # (ct_id, cot_pk) -> CustomObjectType
        for field in all_fields:
            if field.related_object_type_id is None:
                continue
            key = (field.related_object_type_id, field.custom_object_type_id)
            ct_cot_fields[key].append((field.name, field.type))
            ct_cot_map[key] = field.custom_object_type

        # Build a set of content_type_ids we care about
        model_ct_map = {}  # content_type_id -> model_class
        for model_class in model_classes:
            ct = ContentType.objects.get_for_model(model_class)
            model_ct_map[ct.pk] = model_class
    except (OperationalError, ProgrammingError):
        logger.warning(
            "netbox_custom_objects_tab: database unavailable — typed tabs not registered. "
            "Restart NetBox once the database is ready."
        )
        return

    for (ct_id, cot_pk), field_infos in ct_cot_fields.items():
        if ct_id not in model_ct_map:
            continue

        model_class = model_ct_map[ct_id]
        custom_object_type = ct_cot_map[(ct_id, cot_pk)]
        slug = custom_object_type.slug

        view_class = _make_typed_tab_view(model_class, custom_object_type, field_infos, weight)
        register_model_view(
            model_class,
            name=f"custom_objects_{slug}",
            path=f"custom-objects-{slug}",
        )(view_class)
        logger.debug(
            "netbox_custom_objects_tab: registered typed tab '%s' for %s.%s",
            slug,
            model_class._meta.app_label,
            model_class._meta.model_name,
        )
