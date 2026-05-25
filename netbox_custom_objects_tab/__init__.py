from importlib.metadata import version

from netbox.plugins import PluginConfig


class NetBoxCustomObjectsTabConfig(PluginConfig):
    name = "netbox_custom_objects_tab"
    verbose_name = "Custom Objects Tab"
    description = 'Adds a "Custom Objects" tab to NetBox object detail pages'
    version = version("netbox-custom-objects-tab")
    author = "Jan Krupa"
    author_email = "jan.krupa@cesnet.cz"
    base_url = "custom-objects-tab"
    min_version = "4.5.2"
    max_version = "4.6.99"
    default_settings = {
        # Per-type tabs: each Custom Object Type gets its own tab (opt-in, empty by default).
        "typed_models": [],
        # Combined tab: single "Custom Objects" tab showing all types (current behavior).
        "combined_models": [
            "dcim.*",
            "ipam.*",
            "virtualization.*",
            "tenancy.*",
        ],
        # Label shown on the combined tab; override in PLUGINS_CONFIG.
        "combined_label": "Custom Objects",
        # Tab sort weight for the combined tab.
        "combined_weight": 2000,
        # Tab sort weight for all typed tabs.
        "typed_weight": 2100,
    }

    def ready(self):
        super().ready()

        # Hard gate: require netbox-custom-objects >= 0.5.0. We probe behaviour
        # (the `is_polymorphic` model field added in 0.5.0) rather than parsing
        # a version string, because forks and pre-release tags can carry any
        # version label but either have or lack the field we actually use.
        # Raising ImproperlyConfigured here aborts NetBox startup with a clean,
        # named error in the logs — preferable to letting a half-loaded plugin
        # ImportError mid-request.
        from django.core.exceptions import FieldDoesNotExist, ImproperlyConfigured
        from netbox_custom_objects.models import CustomObjectTypeField

        try:
            CustomObjectTypeField._meta.get_field("is_polymorphic")
        except FieldDoesNotExist as exc:
            raise ImproperlyConfigured(
                "netbox-custom-objects-tab 2.4+ requires netbox-custom-objects>=0.5.1. "
                "Upgrade with: pip install -U 'netbox-custom-objects>=0.5.1'"
            ) from exc

        from . import template_override, views

        template_override.install()
        views.register_tabs()


config = NetBoxCustomObjectsTabConfig
