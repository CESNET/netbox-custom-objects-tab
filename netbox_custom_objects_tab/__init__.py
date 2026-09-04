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
    max_version = "4.7.99"
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

        # Hard gate: require netbox-custom-objects >= 0.6.0. We probe behaviour
        # (the `coordinates` field type added in 0.6.0) rather than parsing a
        # version string, because forks and pre-release tags can carry any
        # version label but either have or lack the feature we actually use.
        # Our customobject.html override is a copy of the 0.6.0 stock template
        # (Contacts/Config Context tabs, coordinates rendering, owner header),
        # which reverses URLs that don't exist on 0.5.x — hence the hard floor.
        # Raising ImproperlyConfigured here aborts NetBox startup with a clean,
        # named error in the logs — preferable to letting a half-loaded plugin
        # NoReverseMatch mid-request.
        from django.apps import apps
        from django.core.exceptions import ImproperlyConfigured

        # netbox_custom_objects must actually be loaded, not merely installed.
        # NetBox skips a plugin whose max_version is below the running release
        # (netbox-custom-objects 0.6.0 caps at 4.6.99, so NetBox 4.7 drops it
        # with only a warning); importing its models then fails with an opaque
        # "isn't in INSTALLED_APPS" RuntimeError at startup.
        if not apps.is_installed("netbox_custom_objects"):
            raise ImproperlyConfigured(
                "netbox-custom-objects-tab requires the netbox_custom_objects plugin to be loaded. "
                "On NetBox 4.7+ that needs netbox-custom-objects>=0.6.1 (0.6.0 declares max_version 4.6.99 "
                "and is skipped by NetBox). Upgrade with: pip install -U 'netbox-custom-objects>=0.6.1'"
            )

        from netbox_custom_objects.choices import CustomObjectFieldTypeChoices

        if not hasattr(CustomObjectFieldTypeChoices, "TYPE_COORDINATES"):
            raise ImproperlyConfigured(
                "netbox-custom-objects-tab 2.5+ requires netbox-custom-objects>=0.6.0. "
                "Upgrade with: pip install -U 'netbox-custom-objects>=0.6.0'"
            )

        from . import template_override, views

        template_override.install()
        views.register_tabs()


config = NetBoxCustomObjectsTabConfig
