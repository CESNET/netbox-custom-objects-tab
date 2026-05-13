import logging
from collections import defaultdict
from urllib.parse import urlencode

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.db.utils import OperationalError, ProgrammingError
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.views.generic import View
from extras.choices import CustomFieldTypeChoices, CustomFieldUIVisibleChoices
from netbox.forms import NetBoxModelFilterSetForm
from netbox.registry import registry
from netbox_custom_objects import field_types
from netbox_custom_objects.filtersets import get_filterset_class
from netbox_custom_objects.models import CustomObjectTypeField
from netbox_custom_objects.tables import CustomObjectTable
from utilities.forms.fields import TagFilterField
from utilities.views import ViewTab, register_model_view

from ._co_common import _CO_BASE_TEMPLATE, _CUSTOM_OBJECTS_APP, _get_base_template  # noqa: F401

logger = logging.getLogger("netbox_custom_objects_tab")


def _build_q_for_field(host_ct_id, instance_pk, field_info):
    """
    Build a Q filter that selects custom-object rows of this type whose `field`
    references the host (host_ct_id, instance_pk).

    field_info = (name, type, label, is_polymorphic, through_model_name) — the
    last two are only meaningful for polymorphic fields. Returns Q() (an empty
    no-op filter) if the field can't be resolved, so callers can OR it safely.
    """
    field_name = field_info[0]
    field_type = field_info[1]
    is_poly = field_info[3] if len(field_info) >= 5 else False
    through_model_name = field_info[4] if len(field_info) >= 5 else None

    if field_type == CustomFieldTypeChoices.TYPE_OBJECT:
        if is_poly:
            return Q(
                **{
                    f"{field_name}_content_type_id": host_ct_id,
                    f"{field_name}_object_id": instance_pk,
                }
            )
        return Q(**{f"{field_name}_id": instance_pk})

    if field_type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
        if is_poly:
            try:
                through = apps.get_model(_CUSTOM_OBJECTS_APP, through_model_name)
            except LookupError:
                logger.exception(
                    "Could not resolve through model %r for polymorphic field %s",
                    through_model_name,
                    field_name,
                )
                return Q()
            return Q(
                pk__in=through.objects.filter(
                    content_type_id=host_ct_id,
                    object_id=instance_pk,
                ).values("source_id")
            )
        return Q(**{field_name: instance_pk})

    return Q()


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


def _build_add_links(custom_object_type_slug, host_instance, field_infos, return_url):
    """
    Build pre-filled "Add" URLs for the native customobject_add view.

    field_infos = list of (name, type, label, is_polymorphic, through_model_name).
    Returns list of {"field_name", "label", "url"} dicts (one per unique field).

    Upstream's add form binds polymorphic fields to differently-named sub-fields,
    not their concrete column names, so prefill keys differ per kind:

    - Non-poly OBJECT / MULTIOBJECT  → `?<name>=<host_pk>`
    - Poly OBJECT                    → `?<name>__ct=<host_ct_pk>&<name>__obj=<host_pk>`
    - Poly MULTIOBJECT               → `?<name>__<host_app>__<host_model>=<host_pk>`
      (the form synthesizes one DynamicModelMultipleChoiceField per allowed
      target type; we only fill the one matching the host)

    Returns [] when the customobject_add URL can't be reversed (e.g. plugin URL
    conf not loaded yet).
    """
    try:
        add_base = reverse(
            "plugins:netbox_custom_objects:customobject_add",
            kwargs={"custom_object_type": custom_object_type_slug},
        )
    except NoReverseMatch:
        return []

    host_pk = host_instance.pk
    host_app = host_instance._meta.app_label
    host_model = host_instance._meta.model_name
    host_ct_pk = ContentType.objects.get_for_model(host_instance._meta.model).pk

    links = []
    seen = set()
    for field_info in field_infos:
        field_name = field_info[0]
        if field_name in seen:
            continue
        seen.add(field_name)

        field_type = field_info[1]
        field_label = (field_info[2] if len(field_info) >= 3 and field_info[2] else field_name) or field_name
        is_poly = len(field_info) >= 5 and field_info[3]

        if not is_poly:
            prefill = {field_name: host_pk}
        elif field_type == CustomFieldTypeChoices.TYPE_OBJECT:
            prefill = {f"{field_name}__ct": host_ct_pk, f"{field_name}__obj": host_pk}
        elif field_type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            prefill = {f"{field_name}__{host_app}__{host_model}": host_pk}
        else:
            continue

        qs = urlencode({**prefill, "return_url": return_url})
        links.append(
            {
                "field_name": field_name,
                "label": field_label,
                "url": f"{add_base}?{qs}",
            }
        )
    return links


def _count_for_type(custom_object_type, field_infos, host_ct_id):
    """
    Return a badge callable for one Custom Object Type.

    Mirrors View.get's queryset construction (Q-OR-Q + .distinct()) so a row
    matching the parent via multiple fields is counted exactly once. Earlier
    versions summed per-field counts, which over-counted when a row matched
    via multiple Device-pointing fields (e.g. primary_device + affected_devices
    both point at the same parent). See 2.3.0 release notes.

    host_ct_id is captured at registration time and is needed to build the
    polymorphic-field filters (which key the GFK / through table by
    content_type + object_id, not by a plain FK column).

    field_infos = list of (name, type, label, is_polymorphic, through_model_name).
    Returns None when the count is 0 (so ViewTab.hide_if_empty hides the tab).
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

        q_filter = Q()
        has_filter = False
        for info in field_infos:
            q = _build_q_for_field(host_ct_id, instance.pk, info)
            if q.children:
                q_filter |= q
                has_filter = True

        if not has_filter:
            return None

        total = dynamic_model.objects.filter(q_filter).distinct().count()
        return total if total > 0 else None

    return _badge


def _make_typed_tab_view(model_class, custom_object_type, field_infos, weight, host_ct_id):
    """
    Factory returning a View subclass for a per-type tab.
    field_infos = list of (name, type, label, is_polymorphic, through_model_name)
    for fields of this Custom Object Type that reference model_class.
    host_ct_id pins the host content type so polymorphic Q-filters can select
    by (content_type, object_id) instead of a single FK column.
    """
    badge_fn = _count_for_type(custom_object_type, field_infos, host_ct_id)
    cot_pk = custom_object_type.pk
    cot_label = str(custom_object_type)

    class _TypedTabView(View):
        tab = ViewTab(
            label=cot_label,
            badge=badge_fn,
            weight=weight,
            hide_if_empty=True,
        )

        def get(self, request, pk, **kwargs):
            try:
                qs = model_class.objects.restrict(request.user, "view")
            except AttributeError:
                qs = model_class.objects.all()

            instance = get_object_or_404(qs, pk=pk)

            # Re-fetch CustomObjectType at request time (may have changed since ready())
            from netbox_custom_objects.models import CustomObjectType as COTModel

            error_context = {
                "object": instance,
                "tab": self.tab,
                "base_template": _get_base_template(instance),
                "table": None,
                "preferences": {"pagination.placement": "bottom"},
            }
            try:
                cot = COTModel.objects.get(pk=cot_pk)
            except COTModel.DoesNotExist:
                return render(request, "netbox_custom_objects_tab/typed/tab.html", error_context)

            try:
                dynamic_model = cot.get_model()
            except Exception:
                logger.exception("Could not get model for CustomObjectType %s", cot_pk)
                return render(request, "netbox_custom_objects_tab/typed/tab.html", error_context)

            # Build base queryset: union of all field filters for this type.
            # Polymorphic fields contribute Q(pk__in=<through subquery>) or a
            # (content_type_id, object_id) pair, both handled by _build_q_for_field.
            #
            # An empty Q() is the identity element of `|`, so filter(Q()) returns
            # ALL rows. Track has_filter (mirrors _count_for_type) and short-circuit
            # to .none() if every _build_q_for_field call returned an empty Q —
            # otherwise an unresolvable through model or unknown field type would
            # silently widen the tab to every row of the target type.
            q_filter = Q()
            has_filter = False
            for info in field_infos:
                q = _build_q_for_field(host_ct_id, instance.pk, info)
                if q.children:
                    q_filter |= q
                    has_filter = True

            if has_filter:
                base_qs = dynamic_model.objects.filter(q_filter).distinct()
            else:
                base_qs = dynamic_model.objects.none()

            # Apply filterset
            filterset_class = get_filterset_class(dynamic_model)
            filterset = filterset_class(request.GET, queryset=base_qs)
            filtered_qs = filterset.qs

            # Build filterset form for the filter sidebar
            filterset_form_class = _build_filterset_form(cot, dynamic_model)
            filter_form = filterset_form_class(request.GET)

            # Build table class and instantiate
            table_class = _build_typed_table_class(cot, dynamic_model)
            table = table_class(filtered_qs)
            table.columns.show("pk")

            # Shadow @cached_property to avoid reverse error for dynamic models
            table.htmx_url = request.path
            table.embedded = False

            table.configure(request)

            # User preferences for paginator placement
            if request.user.is_authenticated and (userconfig := getattr(request.user, "config", None)):
                preferences = {"pagination.placement": userconfig.get("pagination.placement", "bottom")}
            else:
                preferences = {"pagination.placement": "bottom"}

            return_url = request.get_full_path()

            # Toolbar permissions: checked against the BASE CustomObject model, not the
            # per-type dynamic subclass. NetBox grants
            # `netbox_custom_objects.{add,change,delete}_customobject` (the perms enforced
            # by `customobject_add` / `customobject_bulk_edit` / `customobject_bulk_delete`),
            # never `{add,change,delete}_table28model`. Mirrors the pattern used inside
            # `CustomObjectActionsColumn`.
            can_add = request.user.has_perm("netbox_custom_objects.add_customobject")
            can_change = request.user.has_perm("netbox_custom_objects.change_customobject")
            can_delete = request.user.has_perm("netbox_custom_objects.delete_customobject")
            # Known issue (2.3.0): Add button below routes saved objects through upstream
            # customobject_add and immediately back to this typed tab. Clicking the per-row
            # Delete on the just-created row in the same flow triggers an upstream ValueError
            # in CustomObjectDeleteView (model class identity drift across the Create→Delete
            # request boundary; see netbox_custom_objects/views.py:977). User-facing
            # workarounds: refresh the list between Create and Delete, or use Bulk Delete.
            # Documented in README "Known Issues" and CHANGELOG [2.3.0].
            add_links = _build_add_links(cot.slug, instance, field_infos, return_url) if can_add else []

            try:
                add_label = cot.get_verbose_name() or str(cot)
            except AttributeError:
                add_label = str(cot)

            context = {
                "object": instance,
                "tab": self.tab,
                "base_template": _get_base_template(instance),
                "table": table,
                "filter_form": filter_form,
                "return_url": return_url,
                "custom_object_type": cot,
                "model": dynamic_model,
                "preferences": preferences,
                "can_add": can_add,
                "can_change": can_change,
                "can_delete": can_delete,
                "add_links": add_links,
                "add_label": add_label,
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
        type_choices = [
            CustomFieldTypeChoices.TYPE_OBJECT,
            CustomFieldTypeChoices.TYPE_MULTIOBJECT,
        ]

        # Non-polymorphic fields: single related_object_type FK.
        # is_polymorphic=False keeps this queryset disjoint from poly_fields
        # below — a field row with both attrs set (legacy misconfig:
        # is_polymorphic is immutable upstream but related_object_type isn't
        # nulled when toggled) would otherwise hit both querysets. _record's
        # seen_field_keys stays as defence in depth.
        non_poly_fields = list(
            CustomObjectTypeField.objects.filter(
                is_polymorphic=False,
                type__in=type_choices,
            ).select_related("custom_object_type")
        )

        # Polymorphic fields: related_object_types M2M (one field → many target CTs).
        # Fetched as a separate queryset so we can iterate prefetched M2M targets
        # without an extra query per field.
        poly_fields = list(
            CustomObjectTypeField.objects.filter(
                is_polymorphic=True,
                type__in=type_choices,
            )
            .select_related("custom_object_type")
            .prefetch_related("related_object_types")
        )

        # Group by (host_content_type_id, custom_object_type_pk)
        # -> list of (name, type, label, is_polymorphic, through_model_name)
        ct_cot_fields = defaultdict(list)
        ct_cot_map = {}  # (ct_id, cot_pk) -> CustomObjectType
        seen_field_keys = set()  # (field.pk, ct_id) — de-dup if a field appears in both querysets

        def _record(field, ct_id, is_poly):
            if ct_id is None:
                return
            key_dup = (field.pk, ct_id)
            if key_dup in seen_field_keys:
                return
            seen_field_keys.add(key_dup)
            key = (ct_id, field.custom_object_type_id)
            label = getattr(field, "label", "") or field.name
            through_name = field.through_model_name if is_poly else None
            ct_cot_fields[key].append((field.name, field.type, label, is_poly, through_name))
            ct_cot_map[key] = field.custom_object_type

        for field in non_poly_fields:
            # Skip purely polymorphic fields that have no FK target.
            if field.related_object_type_id is None:
                continue
            _record(field, field.related_object_type_id, is_poly=False)

        for field in poly_fields:
            for ct in field.related_object_types.all():
                _record(field, ct.pk, is_poly=True)

        # Sort each group by field name for deterministic Add-button order
        for key in ct_cot_fields:
            ct_cot_fields[key].sort(key=lambda f: f[0])

        # Build a set of content_type_ids we care about
        model_ct_map = {}  # content_type_id -> model_class
        for model_class in model_classes:
            ct = ContentType.objects.get_for_model(model_class)
            model_ct_map[ct.pk] = model_class
    except (OperationalError, ProgrammingError):
        logger.warning("database unavailable — typed tabs not registered. Restart NetBox once the database is ready.")
        return

    for (ct_id, cot_pk), field_infos in ct_cot_fields.items():
        if ct_id not in model_ct_map:
            continue

        model_class = model_ct_map[ct_id]
        custom_object_type = ct_cot_map[(ct_id, cot_pk)]
        slug = custom_object_type.slug

        # Skip if already registered (idempotent — guards against reloader re-runs).
        existing = registry["views"].get(model_class._meta.app_label, {}).get(model_class._meta.model_name, [])
        if any(e["name"] == f"custom_objects_{slug}" for e in existing):
            logger.debug(
                "typed tab '%s' already registered for %s.%s — skipping",
                slug,
                model_class._meta.app_label,
                model_class._meta.model_name,
            )
            continue

        view_class = _make_typed_tab_view(model_class, custom_object_type, field_infos, weight, ct_id)
        register_model_view(
            model_class,
            name=f"custom_objects_{slug}",
            path=f"custom-objects-{slug}",
        )(view_class)
        logger.debug(
            "registered typed tab '%s' for %s.%s",
            slug,
            model_class._meta.app_label,
            model_class._meta.model_name,
        )
