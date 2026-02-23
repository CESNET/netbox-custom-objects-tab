import logging

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.shortcuts import get_object_or_404, render
from django.views.generic import View

from extras.choices import CustomFieldTypeChoices
from netbox.plugins import get_plugin_config
from utilities.views import ViewTab, register_model_view

logger = logging.getLogger('netbox_custom_objects_tab')


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
    Badge callable for ViewTab. Returns the count of linked custom objects,
    or None (falsy) when there are none so that hide_if_empty=True works correctly.
    """
    try:
        count = len(_get_linked_custom_objects(instance))
        return count if count > 0 else None
    except Exception:
        logger.exception('Error counting linked custom objects for %r', instance)
        return None


def _make_tab_view(model_class):
    """
    Factory that returns a unique View subclass for model_class.
    Each model needs its own class so that NetBox's view registry stores
    separate entries and URL names do not collide.
    """

    class _TabView(View):
        tab = ViewTab(
            label='Custom Objects',
            badge=_count_linked_custom_objects,
            weight=2000,
            hide_if_empty=True,
        )

        def get(self, request, pk):
            try:
                qs = model_class.objects.restrict(request.user, 'view')
            except AttributeError:
                qs = model_class.objects.all()

            instance = get_object_or_404(qs, pk=pk)
            linked = _get_linked_custom_objects(instance)

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
                    'linked_custom_objects': linked,
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
    except Exception:
        logger.exception('Could not read netbox_custom_objects_tab plugin config')
        return

    for label in model_labels:
        label = label.lower()
        if label.endswith('.*'):
            app_label = label[:-2]
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
                app_label, model_name = label.split('.', 1)
                model_classes = [apps.get_model(app_label, model_name)]
            except (ValueError, LookupError):
                logger.warning(
                    'netbox_custom_objects_tab: could not find model %r — skipping',
                    label,
                )
                continue

        for model_class in model_classes:
            app_label = model_class._meta.app_label
            model_name = model_class._meta.model_name
            view_class = _make_tab_view(model_class)
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
