import logging

from django.apps import apps
from netbox.plugins import get_plugin_config

from .combined import register_combined_tabs
from .typed import register_typed_tabs

logger = logging.getLogger("netbox_custom_objects_tab")


def _resolve_model_labels(labels):
    """
    Resolve a list of model label strings (e.g. ["dcim.*", "ipam.device"])
    into a deduplicated list of Django model classes.
    """
    seen = set()
    result = []
    for label in labels:
        label = label.lower()
        if label.endswith(".*"):
            app_label = label[:-2]
            try:
                model_classes = list(apps.get_app_config(app_label).get_models())
            except LookupError:
                logger.warning(
                    "netbox_custom_objects_tab: could not find app %r — skipping",
                    app_label,
                )
                continue
        else:
            try:
                app_label, model_name = label.split(".", 1)
                model_classes = [apps.get_model(app_label, model_name)]
            except (ValueError, LookupError):
                logger.warning(
                    "netbox_custom_objects_tab: could not find model %r — skipping",
                    label,
                )
                continue

        for model_class in model_classes:
            key = (model_class._meta.app_label, model_class._meta.model_name)
            if key not in seen:
                seen.add(key)
                result.append(model_class)

    return result


def register_tabs():
    """
    Read plugin config and register both combined and typed tabs.
    Called from AppConfig.ready().
    """
    try:
        combined_labels = get_plugin_config("netbox_custom_objects_tab", "combined_models")
        combined_label = get_plugin_config("netbox_custom_objects_tab", "combined_label")
        combined_weight = get_plugin_config("netbox_custom_objects_tab", "combined_weight")
        typed_labels = get_plugin_config("netbox_custom_objects_tab", "typed_models")
        typed_weight = get_plugin_config("netbox_custom_objects_tab", "typed_weight")
    except Exception:
        logger.exception("Could not read netbox_custom_objects_tab plugin config")
        return

    if combined_labels:
        combined_models = _resolve_model_labels(combined_labels)
        register_combined_tabs(combined_models, combined_label, combined_weight)

    if typed_labels:
        typed_models = _resolve_model_labels(typed_labels)
        register_typed_tabs(typed_models, typed_weight)
