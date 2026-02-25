# netbox-custom-objects-tab

[![CI](https://github.com/CESNET/netbox-custom-objects-tab/actions/workflows/ci.yml/badge.svg)](https://github.com/CESNET/netbox-custom-objects-tab/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/netbox-custom-objects-tab)](https://pypi.org/project/netbox-custom-objects-tab/)
[![Python](https://img.shields.io/pypi/pyversions/netbox-custom-objects-tab)](https://pypi.org/project/netbox-custom-objects-tab/)
[![NetBox](https://img.shields.io/badge/NetBox-4.5.x-blue)](https://github.com/netbox-community/netbox)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

A NetBox 4.5.x plugin that adds **Custom Objects** tabs to standard object detail pages,
showing Custom Object instances from the `netbox_custom_objects` plugin that reference
those objects via OBJECT or MULTIOBJECT fields.

Two tab modes are available:

- **Combined tab** — a single tab showing all Custom Object Types in one table, with
  pagination, text search, column sorting, type/tag filtering, and HTMX partial updates.
- **Typed tabs** — each Custom Object Type gets its own tab with a full-featured list view
  (type-specific columns, filterset sidebar, bulk actions, configure table) matching the
  native Custom Objects list page.

## Screenshot

![Custom Objects tab showing 3 linked objects with type filter dropdown](https://raw.githubusercontent.com/CESNET/netbox-custom-objects-tab/master/docs/screenshot.png)

## Requirements

- NetBox 4.5.0 – 4.5.99
- `netbox_custom_objects` plugin **≥ 0.4.6** installed and configured

## Compatibility

| Plugin version | NetBox version | `netbox_custom_objects` version |
|----------------|----------------|---------------------------------|
| 2.0.x          | 4.5.x          | ≥ 0.4.6                        |
| 1.0.x          | 4.5.x          | ≥ 0.4.4                        |

## Installation

```bash
source /opt/netbox/venv/bin/activate
pip install netbox-custom-objects-tab
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
        'combined_models': ['dcim.*', 'ipam.*', 'virtualization.*', 'tenancy.*'],
        'combined_label': 'Custom Objects',
        'combined_weight': 2000,
        'typed_models': [],       # opt-in: e.g. ['dcim.*']
        'typed_weight': 2100,
    }
}
```

Restart NetBox. No database migrations required.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `combined_models` | `['dcim.*', 'ipam.*', 'virtualization.*', 'tenancy.*']` | Models that get the combined "Custom Objects" tab. Accepts `app_label.model_name` or `app_label.*` wildcards. |
| `combined_label` | `'Custom Objects'` | Text displayed on the combined tab. |
| `combined_weight` | `2000` | Tab position for the combined tab; lower = further left. |
| `typed_models` | `[]` | Models that get per-type tabs (opt-in, empty by default). Same format as `combined_models`. |
| `typed_weight` | `2100` | Tab position for all typed tabs. |

A model can appear in both `combined_models` and `typed_models` to get both tab styles.

### Examples

```python
# Combined tab only (default)
'combined_models': ['dcim.*', 'ipam.*', 'virtualization.*', 'tenancy.*']

# Per-type tabs for dcim models
'typed_models': ['dcim.*']

# Both modes for dcim, combined only for others
'combined_models': ['dcim.*', 'ipam.*', 'virtualization.*', 'tenancy.*'],
'typed_models': ['dcim.*'],

# Only specific models
'combined_models': ['dcim.device', 'dcim.site', 'ipam.prefix']

# Third-party plugin models work identically
'combined_models': ['dcim.*', 'ipam.*', 'inventory_monitor.*']
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

### Tag filter
A dropdown (shown when at least one linked Custom Object has a tag) lets you narrow
results to objects with a specific tag. Uses the `?tag=<slug>` query parameter. The
dropdown auto-submits on selection and is populated from the tags present across the
full result set. Tag data is pre-fetched in bulk so there is no N+1 query cost.

### Column sorting
Clicking the **Type**, **Object**, or **Field** column header sorts the table
in-memory. A second click on the same header reverses the direction. The active
column shows an up/down arrow icon. Sort state is preserved when the search form
is submitted.

### HTMX / Partial updates
Pagination clicks, column sort clicks, search form submissions, type-dropdown changes,
and tag-dropdown changes all update the table zone in-place using HTMX — no full page
reload. The URL is updated via `pushState` so links stay shareable and the browser back
button returns to the previous filter/page state.

### Value column
Each row includes a **Value** column showing the actual field value on the Custom
Object instance:
- **Object** fields: a link to the related object.
- **Multi-Object** fields: comma-separated links to the related objects, truncated
  at 3 with an ellipsis when more are present.

### Configure Table
A **Configure Table** button in the card header opens a NetBox modal that lets
authenticated users show, hide, and reorder the table columns (Type, Object, Value,
Field, Tags). Preferences are stored per-user in `UserConfig` and respected on every
subsequent page load, including HTMX partial updates. The Actions column is always
visible and cannot be hidden.

### Action buttons
Each row has right-aligned action buttons, shown only when the user has the relevant permission:

- **Edit** (pencil icon) — links to the Custom Object instance's edit page. Shown when the user has `change` permission on the object.
- **Delete** (trash icon) — links to the Custom Object instance's delete confirmation page. Shown when the user has `delete` permission on the object.

Users without either permission see no action buttons in the row. After completing either
action, NetBox redirects back to the Custom Objects tab on the same parent object.

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
| **Type** | Custom Object Type name (sortable); links to the type detail page when the user has view permission |
| **Object** | Link to the Custom Object instance (sortable) |
| **Value** | The value stored in the linking field — a link for Object fields, comma-separated links for Multi-Object fields |
| **Field** | The field that holds the reference (sortable) |
| **Tags** | Colored tag badges assigned to the Custom Object instance; `—` when none |
| *(actions)* | Edit and Delete buttons, each shown only when the user has the corresponding permission |

## Support

- Open an issue on [GitHub](https://github.com/CESNET/netbox-custom-objects-tab/issues)

## Contributing

Pull requests are welcome. For significant changes, please open an issue first.

## License

Apache-2.0
