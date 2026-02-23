from netbox.plugins import PluginConfig


class NetBoxCustomObjectsTabConfig(PluginConfig):
    name = 'netbox_custom_objects_tab'
    verbose_name = 'Custom Objects Tab'
    description = 'Adds a "Custom Objects" tab to NetBox object detail pages'
    version = '1.0.0'
    author = ''
    author_email = ''
    base_url = 'custom-objects-tab'
    min_version = '4.5.0'
    max_version = '4.5.99'
    default_settings = {
        # List of app_label.model_name strings for models to add the tab to.
        # Each must be a valid NetBox model with object detail pages.
        'models': [
            'dcim.device',
            'dcim.site',
            'dcim.rack',
            'ipam.prefix',
            'ipam.ipaddress',
        ]
    }

    def ready(self):
        super().ready()
        from . import views
        views.register_tabs()


config = NetBoxCustomObjectsTabConfig
