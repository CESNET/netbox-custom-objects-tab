# netbox-custom-objects-tab

A NetBox 4.5.x plugin that adds a **Custom Objects** tab to standard object detail pages,
showing any Custom Object instances from the `netbox_custom_objects` plugin that reference
those objects via OBJECT or MULTIOBJECT fields.

The tab includes **pagination** and **text search** so it stays usable even when thousands
of custom objects are linked.

## Screenshot

![Custom Objects tab showing 3 linked objects with type filter dropdown](https://raw.githubusercontent.com/CESNET/netbox-custom-objects-tab/main/docs/screenshot.png)

## Requirements

- NetBox 4.5.0 – 4.5.99
- `netbox_custom_objects` plugin installed and configured

## Compatibility

| Plugin version | NetBox version |
|----------------|----------------|
| 1.0.x          | 4.5.x          |

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

# Optional — defaults shown below
PLUGINS_CONFIG = {
    'netbox_custom_objects_tab': {
        'models': ['dcim.*', 'ipam.*']
    }
}
```

Restart NetBox. No database migrations required.

## Configuration

| Setting  | Default | Description |
|----------|---------|-------------|
| `models` | `['dcim.*', 'ipam.*']` | Models that get the Custom Objects tab. Accepts `app_label.model_name` strings **or** `app_label.*` wildcards to register every model in an app. |

### Examples

```python
# All DCIM and IPAM models (default)
'models': ['dcim.*', 'ipam.*']

# Only specific models
'models': ['dcim.device', 'dcim.site', 'ipam.prefix']

# Mix wildcards and specifics
'models': ['dcim.*', 'virtualization.*', 'ipam.ipaddress']

# Third-party plugin models work identically
'models': ['dcim.*', 'ipam.*', 'inventory_monitor.*']
```

Third-party plugin models are fully supported — Django treats plugin apps and built-in apps
the same way in the app registry. Add the plugin's app label and restart NetBox once.

The tab is hidden automatically (`hide_if_empty=True`) when no custom objects reference
the object being viewed, so it only appears when relevant.

## Features

### Pagination
Results are paginated using NetBox's standard `EnhancedPaginator`. The page size respects
the user's personal NetBox preference and can be overridden with `?per_page=N` in the URL.
Page controls appear at the top and bottom of the table.

### Text search
A search box in the card header filters results by:
- Custom Object instance display name
- Custom Object Type name
- Field label

Filtering uses the `?q=` query parameter and is applied before pagination.

### Type filter
A dropdown (shown when 2 or more Custom Object Types are present) lets you narrow
results to a single type. Uses the `?type=<slug>` query parameter. The dropdown
auto-submits on selection and is populated from the types actually present in the
current result set.

### Efficient badge counts
The tab badge (shown in the tab bar on every detail page) is computed with a
`COUNT(*)` query per field — no object rows are fetched. Full object rows are only
loaded when the tab itself is opened. This keeps detail page loads fast even when
thousands of custom objects reference an object.

## How It Works

When a Custom Object Type has a field of type **Object** or **Multi-Object** pointing to
a NetBox model (e.g. Device), any Custom Object instances with that field set will appear
in the "Custom Objects" tab on the referenced object's detail page.

The tab displays:

| Column | Content |
|--------|---------|
| **Type** | Custom Object Type name |
| **Object** | Link to the Custom Object instance |
| **Field** | The field that holds the reference |

## Support

- Open an issue on [GitHub](https://github.com/CESNET/netbox-custom-objects-tab/issues)

## Contributing

Pull requests are welcome. For significant changes, please open an issue first.

## License

Apache-2.0
