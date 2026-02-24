from netbox.plugins import PluginConfig


class NetBoxCustomObjectsTabConfig(PluginConfig):
    name = 'netbox_custom_objects_tab'
    verbose_name = 'Custom Objects Tab'
    description = 'Adds a "Custom Objects" tab to NetBox object detail pages'
    version = '1.0.0'
    author = 'Jan Krupa'
    author_email = 'jan.krupa@cesnet.cz'
    base_url = 'custom-objects-tab'
    min_version = '4.5.0'
    max_version = '4.5.99'
    default_settings = {
        # app_label.model_name strings, or app_label.* to include all models in an app.
        'models': [
            'dcim.*',
            'ipam.*',
            'virtualization.*',
            'tenancy.*',
            'contacts.*',
        ],
        # Label shown on the tab; override in PLUGINS_CONFIG.
        'label': 'Custom Objects',
        # Tab sort weight; lower values appear further left.
        'weight': 2000,
    }

    def ready(self):
        super().ready()
        from . import views
        views.register_tabs()


config = NetBoxCustomObjectsTabConfig
