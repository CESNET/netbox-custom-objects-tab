import logging
from importlib.metadata import version

from netbox.plugins import PluginConfig

logger = logging.getLogger("netbox_custom_objects_tab")

_REMOVED_SETTINGS = ("combined_models", "combined_label", "combined_weight")


class NetBoxCustomObjectsTabConfig(PluginConfig):
    name = "netbox_custom_objects_tab"
    verbose_name = "Custom Object Type Tabs"
    description = "Adds one tab per Custom Object Type to NetBox object detail pages"
    version = version("netbox-custom-objects-tab")
    author = "Jan Krupa"
    author_email = "jan.krupa@cesnet.cz"
    base_url = "custom-objects-tab"
    min_version = "4.5.2"
    max_version = "4.7.99"
    default_settings = {
        # Models that get one tab per Custom Object Type referencing them (opt-in).
        # Accepts "app_label.model" or "app_label.*"; "netbox_custom_objects.*" enables
        # tabs on Custom Object detail pages themselves (CO -> CO references).
        "typed_models": [],
        # Tab sort weight shared by all typed tabs. netbox-custom-objects' own combined
        # "Custom Objects" tab sits at 2000, so typed tabs render right after it.
        "typed_weight": 2100,
    }

    def ready(self):
        super().ready()

        from django.apps import apps
        from django.conf import settings
        from django.core.exceptions import ImproperlyConfigured

        # netbox_custom_objects must actually be loaded, not merely installed: NetBox
        # skips a plugin whose max_version is below the running release, and importing
        # its models then fails with an opaque "isn't in INSTALLED_APPS" RuntimeError.
        if not apps.is_installed("netbox_custom_objects"):
            raise ImproperlyConfigured(
                "netbox-custom-objects-tab requires the netbox_custom_objects plugin to be loaded. "
                "Install/upgrade with: pip install -U 'netboxlabs-netbox-custom-objects>=0.7.0'"
            )

        # Hard gate: netbox-custom-objects >= 0.7.0. We probe for the related_tabs
        # package (new in 0.7.0) rather than parsing a version string, because forks
        # and pre-release tags can carry any label. 0.7.0 matters because (a) it ships
        # the combined "Custom Objects" tab this plugin used to provide, and (b) its
        # customobject.html calls {% plugin_extra_tabs %}, which is how our typed tabs
        # reach Custom Object detail pages without a template override.
        try:
            import netbox_custom_objects.related_tabs.registry  # noqa: F401
        except ImportError as exc:
            raise ImproperlyConfigured(
                "netbox-custom-objects-tab 3.0+ requires netbox-custom-objects>=0.7.0. "
                "Upgrade with: pip install -U 'netboxlabs-netbox-custom-objects>=0.7.0'"
            ) from exc

        stale = [k for k in _REMOVED_SETTINGS if k in settings.PLUGINS_CONFIG.get(self.name, {})]
        if stale:
            logger.warning(
                "netbox_custom_objects_tab: %s ignored — the combined 'Custom Objects' tab is built into "
                "netbox-custom-objects >= 0.7.0; remove these keys from PLUGINS_CONFIG",
                ", ".join(stale),
            )

        from . import views

        views.register_tabs()


config = NetBoxCustomObjectsTabConfig
