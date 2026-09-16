# netbox-custom-objects-tab

[![CI](https://github.com/CESNET/netbox-custom-objects-tab/actions/workflows/ci.yml/badge.svg)](https://github.com/CESNET/netbox-custom-objects-tab/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/netbox-custom-objects-tab)](https://pypi.org/project/netbox-custom-objects-tab/)
[![Python](https://img.shields.io/pypi/pyversions/netbox-custom-objects-tab)](https://pypi.org/project/netbox-custom-objects-tab/)
[![NetBox](https://img.shields.io/badge/NetBox-4.5.x_|_4.6.x_|_4.7.x-blue)](https://github.com/netbox-community/netbox)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)

A NetBox 4.5.x / 4.6.x / 4.7.x plugin that adds **one tab per Custom Object Type** to object
detail pages. Each tab is a full-featured list of the Custom Object instances (from the
[`netbox-custom-objects`](https://github.com/netboxlabs/netbox-custom-objects) plugin) that
reference the viewed object via an OBJECT or MULTIOBJECT field — with type-specific columns,
filter sidebar, bulk actions, pre-filled Add buttons and per-user table configuration, matching
the native `/plugins/custom-objects/<type>/` list page.

Works on standard NetBox models (Device, Site, Rack, …), third-party plugin models, and Custom
Object detail pages themselves (CO→CO relationships).

> **Looking for the combined "Custom Objects" tab?** Since `netbox-custom-objects` 0.7.0 it is
> built into the upstream plugin (one tab listing every referencing Custom Object, any type, with
> search / type / tag filters). It needs no configuration and appears on every referenced object.
> This plugin only adds the per-type tabs; versions ≤ 2.6 shipped a combined tab of their own,
> which was removed in 3.0.0.

## Requirements

- NetBox 4.5.2 – 4.7.99
- `netbox-custom-objects` **≥ 0.7.0** installed and loaded (`netboxlabs-netbox-custom-objects` on PyPI)

## Compatibility

| Plugin version | NetBox version         | `netbox_custom_objects` version              |
|----------------|------------------------|----------------------------------------------|
| 3.0.x          | 4.5.2+ / 4.6.x / 4.7.x | **≥ 0.7.0 required**                         |
| 2.6.x          | 4.5.2+ / 4.6.x / 4.7.x | ≥ 0.6.0 (≥ 0.6.1 on NetBox 4.7), < 0.7.0     |
| 2.5.x          | 4.5.2+ / 4.6.x         | ≥ 0.6.0                                      |
| 2.4.x          | 4.5.2+ / 4.6.x         | ≥ 0.5.1                                      |
| 2.0.x – 2.3.x  | 4.5.x / 4.6.x          | ≥ 0.4.6                                      |
| 1.0.x          | 4.5.x                  | ≥ 0.4.4                                      |

The 0.7.0 minimum is **enforced at startup**: `PluginConfig.ready()` probes for the upstream
`related_tabs` package (new in 0.7.0) and raises `ImproperlyConfigured` with an upgrade hint
if it is missing. The check is behaviour-based (looks for the feature, not a version string)
so it stays correct across forks and pre-release tags. 0.7.0 is required because its Custom
Object detail template renders registered model-view tabs, which is how the per-type tabs reach
Custom Object pages; older releases needed a template override that 3.0.0 no longer ships.

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

PLUGINS_CONFIG = {
    'netbox_custom_objects_tab': {
        'typed_models': ['dcim.*'],   # required — the plugin does nothing until set
        'typed_weight': 2100,         # optional, default shown
    }
}
```

Restart NetBox. No database migrations required.

### Upgrading from 2.x

1. `pip install -U 'netboxlabs-netbox-custom-objects>=0.7.0' netbox-custom-objects-tab`
2. Remove `combined_models`, `combined_label` and `combined_weight` from `PLUGINS_CONFIG`
   (a leftover key only logs a warning at startup; it has no effect).
3. Restart NetBox. The combined tab keeps working — it is now served by `netbox-custom-objects`.

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `typed_models` | `[]` | Models that get one tab per Custom Object Type referencing them. Accepts `app_label.model_name` or `app_label.*` wildcards. Empty = plugin inactive. |
| `typed_weight` | `2100` | Tab position for all typed tabs; lower = further left. Upstream's combined tab sits at 2000, so typed tabs follow it by default. |

### Examples

```python
# Per-type tabs on every dcim model
'typed_models': ['dcim.*']

# Only specific models
'typed_models': ['dcim.device', 'dcim.site', 'ipam.prefix']

# Third-party plugin models work identically
'typed_models': ['dcim.*', 'ipam.*', 'inventory_monitor.*']

# Tabs on Custom Object detail pages too (CO → CO relationships)
'typed_models': ['dcim.*', 'netbox_custom_objects.*']
```

Third-party plugin models are fully supported — Django treats plugin apps and built-in apps
the same way in the app registry. Add the plugin's app label and restart NetBox once.

#### Tabs on Custom Object detail pages

Setting `netbox_custom_objects.*` in `typed_models` enables tabs on Custom Object detail pages
themselves. When Custom Object Type A has a field referencing Type B, every Type B instance gets
a "Type A" tab listing the Type A objects that link to it.

Because Custom Object model classes are generated dynamically (one per type),
**a NetBox restart is required whenever a new Custom Object Type is added** — this applies to
all typed tabs, on native models and on Custom Object pages alike.

Tabs are hidden automatically (`hide_if_empty=True`) when nothing references the viewed object.

## Features

Each typed tab reuses the building blocks of the native Custom Objects list view from
`netbox-custom-objects`, so it looks and behaves like `/plugins/custom-objects/<type>/`
pre-filtered to the current object:

- **Type-specific columns** — every visible field of the Custom Object Type, rendered by the
  upstream field-type renderers (links, badges, coordinates, …), plus ID, tags and actions.
- **Filter sidebar** — the upstream dynamic filterset and filter form for that type, including
  polymorphic fields and the owner filter.
- **Quick search, sorting, pagination** — NetBox's standard table controls, updated in place via
  HTMX (`htmx/table.html`), so paging and sorting never reload the page.
- **Configure Table** — per-user column selection and ordering, stored in `UserConfig`.
- **Add buttons** — one per referencing field, opening the upstream create form with the
  reference to the current object pre-filled; returns to the tab afterwards.
- **Bulk edit / bulk delete** — row checkboxes and the upstream bulk views, with the return URL
  pointing back to the tab. Available because all rows in a typed tab share one type.
- **Per-row Edit / Delete** — via upstream's `CustomObjectActionsColumn`, permission-aware.
- **Cheap badge counts** — the tab badge is a single `COUNT(*)` with `.distinct()`; a row that
  references the object through several fields is counted once. Full rows load only when the
  tab is opened.
- **Permission-aware** — rows are restricted with `.restrict(user, "view")`; Add / bulk buttons
  honour `netbox_custom_objects.{add,change,delete}_customobject`.

## How It Works

At startup (`PluginConfig.ready()`), the plugin reads every `CustomObjectTypeField` of type
Object / Multi-Object (polymorphic ones included), groups them by
(referenced model, Custom Object Type), and registers one `ViewTab` view per pair on each model
listed in `typed_models` using NetBox's `register_model_view`. Each view builds a base queryset
(`Q` per referencing field, OR-ed, `.distinct()`), applies the upstream filterset, and renders a
dynamically built `CustomObjectTable` subclass.

On Custom Object detail pages, which upstream serves through a single generic URL, the plugin
appends one `<type-slug>/<pk>/custom-objects-<slug>/` route per referencing type to the upstream
URLconf. The route resolves the host type from the slug per request and dispatches to the view
registered for exactly that model, so the correct object loads and the tab highlights as active.

## Support

- Open an issue on [GitHub](https://github.com/CESNET/netbox-custom-objects-tab/issues)

## Contributing

Pull requests are welcome. For significant changes, please open an issue first.

## License

Apache-2.0
