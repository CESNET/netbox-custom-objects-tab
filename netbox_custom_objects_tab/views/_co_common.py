_CUSTOM_OBJECTS_APP = "netbox_custom_objects"
# Dynamic CO models use a single shared detail template; per-model templates don't exist.
_CO_BASE_TEMPLATE = "netbox_custom_objects/customobject.html"


def _get_base_template(instance):
    """Return the correct base_template for an object's detail page."""
    if instance._meta.app_label == _CUSTOM_OBJECTS_APP:
        return _CO_BASE_TEMPLATE
    return f"{instance._meta.app_label}/{instance._meta.model_name}.html"
