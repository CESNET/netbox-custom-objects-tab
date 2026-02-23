# netbox-custom-objects-tab

A NetBox 4.5.x plugin that adds a **Custom Objects** tab to standard object detail pages
(Device, Site, Rack, etc.), showing any Custom Object instances from the
`netbox_custom_objects` plugin that reference those objects via OBJECT or MULTIOBJECT fields.

## Requirements

- NetBox 4.5.0 – 4.5.99
- `netbox_custom_objects` plugin installed and configured

## Installation

```bash
source /opt/netbox/venv/bin/activate
pip install -e /opt/custom_objects_additional_tab_plugin/
```

Add to NetBox `configuration.py`:

```python
PLUGINS = [
    'netbox_custom_objects',
    'netbox_custom_objects_tab',
]

PLUGINS_CONFIG = {
    'netbox_custom_objects_tab': {
        'models': [
            'dcim.device',
            'dcim.site',
            'dcim.rack',
            'ipam.prefix',
            'ipam.ipaddress',
        ]
    }
}
```

Restart NetBox. No database migrations required.

## Configuration

| Setting  | Default | Description |
|----------|---------|-------------|
| `models` | `['dcim.device', 'dcim.site', 'dcim.rack', 'ipam.prefix', 'ipam.ipaddress']` | List of `app_label.model_name` strings for models that should get the Custom Objects tab |

The tab is hidden automatically (`hide_if_empty=True`) when no custom objects reference
the object being viewed, so it only appears when relevant.

## How It Works

When a Custom Object Type has a field of type **Object** or **Multi-Object** pointing to
a NetBox model (e.g. Device), any Custom Object instances with that field set will appear
in the "Custom Objects" tab on the referenced object's detail page.

The tab displays:
- **Type** — the Custom Object Type name
- **Object** — a link to the Custom Object instance
- **Field** — the field name that holds the reference

## License

Apache-2.0
