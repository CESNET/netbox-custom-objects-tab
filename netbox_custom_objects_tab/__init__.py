from netbox.plugins import PluginConfig


class NetBoxCustomObjectsTabConfig(PluginConfig):
    name = "netbox_custom_objects_tab"
    verbose_name = "Custom Objects Tab"
    description = 'Adds a "Custom Objects" tab to NetBox object detail pages'
    version = "2.0.0"
    author = "Jan Krupa"
    author_email = "jan.krupa@cesnet.cz"
    base_url = "custom-objects-tab"
    min_version = "4.5.0"
    max_version = "4.5.99"
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
        from . import views

        views.register_tabs()


config = NetBoxCustomObjectsTabConfig
