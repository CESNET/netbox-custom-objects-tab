from utilities.views import get_default_template

_CUSTOM_OBJECTS_APP = "netbox_custom_objects"
# Dynamic CO models use a single shared detail template; per-model templates don't exist.
_CO_BASE_TEMPLATE = "netbox_custom_objects/customobject.html"


def _get_base_template(instance):
    """Return the correct base_template for an object's detail page."""
    if instance._meta.app_label == _CUSTOM_OBJECTS_APP:
        return _CO_BASE_TEMPLATE
    # Not every model has an "{app}/{model}.html" detail template (e.g. ipam/vrf.html
    # and dcim/macaddress.html don't exist). get_default_template falls back to
    # generic/object.html — the same resolution NetBox's Journal/Changelog tabs use.
    return get_default_template(instance._meta.model)
