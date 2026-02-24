import logging
from urllib.parse import urlencode

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.core.paginator import InvalidPage
from django.shortcuts import get_object_or_404, render
from django.views.generic import View

from extras.choices import CustomFieldTypeChoices
from netbox.plugins import get_plugin_config
from utilities.paginator import EnhancedPaginator, get_paginate_count
from utilities.views import ViewTab, register_model_view

logger = logging.getLogger('netbox_custom_objects_tab')

# Maximum number of related objects to show in the Value column for MULTIOBJECT fields.
# One extra is fetched to detect truncation without a COUNT query.
_MAX_MULTIOBJECT_DISPLAY = 3


def _get_linked_custom_objects(instance):
    """
    Return list of (custom_object_instance, CustomObjectTypeField) tuples for all
    custom objects that reference this instance via OBJECT or MULTIOBJECT fields.

    Mirrors the query logic in:
      netbox_custom_objects/template_content.py::CustomObjectLink.left_page()
    """
    from netbox_custom_objects.models import CustomObjectTypeField

    content_type = ContentType.objects.get_for_model(instance._meta.model)
    fields = CustomObjectTypeField.objects.filter(
        related_object_type=content_type,
        type__in=[
            CustomFieldTypeChoices.TYPE_OBJECT,
            CustomFieldTypeChoices.TYPE_MULTIOBJECT,
        ],
    ).select_related('custom_object_type')

    results = []
    for field in fields:
        try:
            model = field.custom_object_type.get_model()
        except Exception:
            logger.exception(
                'Could not get model for CustomObjectType %s',
                field.custom_object_type_id,
            )
            continue

        if field.type == CustomFieldTypeChoices.TYPE_OBJECT:
            for obj in model.objects.filter(**{f'{field.name}_id': instance.pk}):
                results.append((obj, field))
        elif field.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            for obj in model.objects.filter(**{field.name: instance.pk}):
                results.append((obj, field))

    return results


def _count_linked_custom_objects(instance):
    """
    Badge callable for ViewTab.
    Uses COUNT(*) per queryset — avoids fetching full object rows on every detail page.
    Returns None (not 0) when count is zero so hide_if_empty=True works correctly.
    """
    from netbox_custom_objects.models import CustomObjectTypeField

    content_type = ContentType.objects.get_for_model(instance._meta.model)
    fields = CustomObjectTypeField.objects.filter(
        related_object_type=content_type,
        type__in=[
            CustomFieldTypeChoices.TYPE_OBJECT,
            CustomFieldTypeChoices.TYPE_MULTIOBJECT,
        ],
    ).select_related('custom_object_type')

    total = 0
    for field in fields:
        try:
            model = field.custom_object_type.get_model()
        except Exception:
            logger.exception(
                'Could not get model for CustomObjectType %s',
                field.custom_object_type_id,
            )
            continue

        if field.type == CustomFieldTypeChoices.TYPE_OBJECT:
            total += model.objects.filter(**{f'{field.name}_id': instance.pk}).count()
        elif field.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
            total += model.objects.filter(**{field.name: instance.pk}).count()

    return total if total > 0 else None


def _filter_linked_objects(linked, q):
    """
    Case-insensitive substring search across the object display name,
    custom object type name, and field label.
    """
    q = q.strip().lower()
    if not q:
        return linked
    return [
        (obj, field) for obj, field in linked
        if q in str(obj).lower()
        or q in str(field.custom_object_type).lower()
        or q in str(field).lower()
    ]


def _get_field_value(obj, field):
    """
    Return the value stored in `field` on `obj`, for display in the Value column.

    TYPE_OBJECT     → the related model instance (or None if unset)
    TYPE_MULTIOBJECT → list of related instances, up to _MAX_MULTIOBJECT_DISPLAY+1
                       (the extra item lets the template detect truncation without a
                       separate COUNT query)
    """
    if field.type == CustomFieldTypeChoices.TYPE_OBJECT:
        return getattr(obj, field.name, None)
    elif field.type == CustomFieldTypeChoices.TYPE_MULTIOBJECT:
        qs = getattr(obj, field.name, None)
        if qs is None:
            return []
        return list(qs.all()[:_MAX_MULTIOBJECT_DISPLAY + 1])
    return None


# Sort key lambdas keyed by the ?sort= query parameter value.
_SORT_KEYS = {
    'type': lambda t: str(t[1].custom_object_type).lower(),
    'object': lambda t: str(t[0]).lower(),
    'field': lambda t: str(t[1]).lower(),
}


def _sort_header(sort_base, col, current_sort, current_dir):
    """
    Build the URL and directional icon for a sortable column header.

    Returns a dict with keys:
      url  – the href value for the <a> tag
      icon – MDI icon name (arrow-up / arrow-down) when this column is active,
             or None when it is not the active sort column
    """
    if current_sort == col:
        next_dir = 'desc' if current_dir == 'asc' else 'asc'
        icon = 'arrow-up' if current_dir == 'asc' else 'arrow-down'
    else:
        next_dir = 'asc'
        icon = None

    qs = f'{sort_base}&sort={col}&dir={next_dir}' if sort_base else f'sort={col}&dir={next_dir}'
    return {'url': f'?{qs}', 'icon': icon}


def _make_tab_view(model_class, label='Custom Objects', weight=2000):
    """
    Factory that returns a unique View subclass for model_class.
    Each model needs its own class so that NetBox's view registry stores
    separate entries and URL names do not collide.
    """

    class _TabView(View):
        tab = ViewTab(
            label=label,
            badge=_count_linked_custom_objects,
            weight=weight,
            hide_if_empty=True,
        )

        def get(self, request, pk):
            try:
                qs = model_class.objects.restrict(request.user, 'view')
            except AttributeError:
                qs = model_class.objects.all()

            instance = get_object_or_404(qs, pk=pk)
            linked_all = _get_linked_custom_objects(instance)

            # Collect unique types for the dropdown (always from the unfiltered list)
            seen_type_pks = set()
            available_types = []
            for _obj, field in linked_all:
                cot = field.custom_object_type
                if cot.pk not in seen_type_pks:
                    seen_type_pks.add(cot.pk)
                    available_types.append(cot)
            available_types.sort(key=lambda t: str(t))

            # Read filter/sort params
            q = request.GET.get('q', '')
            type_slug = request.GET.get('type', '')
            sort_col = request.GET.get('sort', '')
            sort_dir = request.GET.get('dir', 'asc')
            per_page = request.GET.get('per_page', '')

            # Apply filters
            linked = _filter_linked_objects(linked_all, q)
            if type_slug:
                linked = [
                    (obj, field) for obj, field in linked
                    if field.custom_object_type.slug == type_slug
                ]

            # In-memory sort (applied after filters, before pagination)
            if sort_col in _SORT_KEYS:
                linked.sort(key=_SORT_KEYS[sort_col], reverse=(sort_dir == 'desc'))

            # Pagination
            paginator = EnhancedPaginator(linked, get_paginate_count(request))
            try:
                page = paginator.page(int(request.GET.get('page', 1)))
            except (InvalidPage, ValueError):
                page = paginator.page(1)

            # Resolve field values for just the current page (avoids N+1 on full list)
            page_rows = [
                (obj, field, _get_field_value(obj, field))
                for obj, field in page.object_list
            ]

            # Build the base query string (without sort/dir) for column sort links
            base_params = {}
            if q:
                base_params['q'] = q
            if type_slug:
                base_params['type'] = type_slug
            if per_page:
                base_params['per_page'] = per_page
            sort_base = urlencode(base_params)

            sort_headers = {
                col: _sort_header(sort_base, col, sort_col, sort_dir)
                for col in ('type', 'object', 'field')
            }

            return render(
                request,
                'netbox_custom_objects_tab/custom_objects_tab.html',
                {
                    'object': instance,
                    'tab': self.tab,
                    # base_template must match the parent model's detail template
                    # so that tabs, breadcrumbs, and the page header render correctly.
                    'base_template': (
                        f'{instance._meta.app_label}/{instance._meta.model_name}.html'
                    ),
                    'page_obj': page,
                    'paginator': paginator,
                    'page_rows': page_rows,
                    'q': q,
                    'type_slug': type_slug,
                    'available_types': available_types,
                    'sort': sort_col,
                    'sort_dir': sort_dir,
                    'sort_headers': sort_headers,
                },
            )

    _TabView.__name__ = f'{model_class.__name__}CustomObjectsTabView'
    _TabView.__qualname__ = f'{model_class.__name__}CustomObjectsTabView'
    return _TabView


def register_tabs():
    """
    Programmatically register a Custom Objects tab view for each model listed
    in the plugin's 'models' setting. Called from AppConfig.ready().
    """
    try:
        model_labels = get_plugin_config('netbox_custom_objects_tab', 'models')
        tab_label = get_plugin_config('netbox_custom_objects_tab', 'label')
        tab_weight = get_plugin_config('netbox_custom_objects_tab', 'weight')
    except Exception:
        logger.exception('Could not read netbox_custom_objects_tab plugin config')
        return

    for model_label in model_labels:
        model_label = model_label.lower()
        if model_label.endswith('.*'):
            app_label = model_label[:-2]
            try:
                model_classes = list(apps.get_app_config(app_label).get_models())
            except LookupError:
                logger.warning(
                    'netbox_custom_objects_tab: could not find app %r — skipping',
                    app_label,
                )
                continue
        else:
            try:
                app_label, model_name = model_label.split('.', 1)
                model_classes = [apps.get_model(app_label, model_name)]
            except (ValueError, LookupError):
                logger.warning(
                    'netbox_custom_objects_tab: could not find model %r — skipping',
                    model_label,
                )
                continue

        for model_class in model_classes:
            app_label = model_class._meta.app_label
            model_name = model_class._meta.model_name
            view_class = _make_tab_view(model_class, label=tab_label, weight=tab_weight)
            # Programmatic equivalent of:
            #   @register_model_view(model_class, name='custom_objects', path='custom-objects')
            register_model_view(
                model_class,
                name='custom_objects',
                path='custom-objects',
            )(view_class)
            logger.debug(
                'netbox_custom_objects_tab: registered tab for %s.%s',
                app_label,
                model_name,
            )
