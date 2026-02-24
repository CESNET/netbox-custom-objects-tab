# netbox_custom_objects_tab — Project Notes for Claude

## Git Conventions

- **Never** add `Co-Authored-By: Claude` (or any Claude/Anthropic credit) to commit messages.

## Purpose

Adds a **"Custom Objects"** tab to NetBox object detail pages (Device, Site, Rack, etc.),
showing Custom Object instances from the `netbox_custom_objects` plugin that reference
those objects via OBJECT or MULTIOBJECT typed fields.

The tab supports **pagination** (NetBox `EnhancedPaginator`) and **`?q=` text search**
so it stays usable with large numbers of linked objects.

## Architecture

**NO models, NO migrations, NO API, NO forms, NO navigation menu.**

| File | Role |
|------|------|
| `netbox_custom_objects_tab/__init__.py` | `PluginConfig`; calls `views.register_tabs()` in `ready()` |
| `netbox_custom_objects_tab/views.py` | View factory + `register_tabs()` using `register_model_view` + `ViewTab` |
| `netbox_custom_objects_tab/urls.py` | Empty `urlpatterns` (required by NetBox plugin loader) |
| `netbox_custom_objects_tab/templates/netbox_custom_objects_tab/custom_objects_tab.html` | Tab content template |

## How Custom Objects Link to NetBox Objects

The `netbox_custom_objects` plugin uses **direct ForeignKey / M2M** relationships,
not GenericForeignKey. Each Custom Object Type generates a real Django model with
its own database table.

To find all custom objects referencing a Device (pk=42):
1. Get ContentType for Device
2. `CustomObjectTypeField.objects.filter(related_object_type=content_type)` — finds all
   fields in any Custom Object Type that point to Device
3. For each field: `field.custom_object_type.get_model()` — gets the dynamic model class
4. `TYPE_OBJECT` (ForeignKey): `model.objects.filter({field.name}_id=42)`
5. `TYPE_MULTIOBJECT` (M2M): `model.objects.filter({field.name}=42)`

Reference: `netbox_custom_objects/template_content.py::CustomObjectLink.left_page()`

## Key Import Paths (NetBox 4.5.x)

```python
from utilities.views import ViewTab, register_model_view
from utilities.paginator import EnhancedPaginator, get_paginate_count
from netbox_custom_objects.models import CustomObjectTypeField
from extras.choices import CustomFieldTypeChoices
from netbox.plugins import get_plugin_config
```

## Pagination & Filtering Design

- **`_get_linked_custom_objects(instance)`** — returns a Python `list` of `(obj, field)` tuples
  by querying across multiple dynamic model tables. A single queryset is not possible.
- **`_filter_linked_objects(linked, q)`** — filters that list in Python; case-insensitive
  match against `str(obj)`, `str(field.custom_object_type)`, `str(field)`.
- **`EnhancedPaginator(linked, get_paginate_count(request))`** — paginates the filtered list.
  `get_paginate_count` respects `?per_page=`, user prefs, and global `PAGINATE_COUNT`.
- **`inc/paginator.html`** — NetBox's standard paginator partial; pass `paginator=paginator`
  and `page=page_obj` (do NOT pass `htmx=True` — we use plain GET links, not HTMX).
- Badge count (`_count_linked_custom_objects`) still counts the **unfiltered** total so the
  badge reflects all linked objects regardless of active search.
- **`_count_linked_custom_objects`** uses `.count()` (DB-side `COUNT(*)`) per field —
  no object rows are fetched. Full rows are loaded only when the tab view itself is
  called (`_get_linked_custom_objects`). Verified empirically: on a Device with 2214
  linked custom objects, the detail page (`/dcim/devices/<pk>/`) runs only COUNT queries;
  the full fetch fires only on `/dcim/devices/<pk>/custom-objects/`.

## Model Registration

`register_tabs()` in `views.py` supports two label formats in the `models` config:

| Format | Behaviour |
|--------|-----------|
| `dcim.device` | Registers the tab for that single model |
| `dcim.*` | Registers the tab for **every model** in the `dcim` app |

Default: `['dcim.*', 'ipam.*']`

**Third-party plugin models are fully supported.** Django's `apps.get_app_config()` and
`apps.get_model()` treat plugin apps identically to built-in apps, so any installed plugin's
models work with the same syntax:

```python
'models': ['dcim.*', 'ipam.*', 'inventory_monitor.*']
```

Verified working with `inventory_monitor` and other third-party NetBox plugins.

## Gotchas

- `register_model_view` must run inside `AppConfig.ready()` — not at module level
- `hide_if_empty=True` on ViewTab requires the badge callable to return `None` (not `0`)
  when the count is zero; `0` is falsy but some NetBox versions check truthiness
- Template must `{% extends base_template %}` where `base_template` is set in view context
  as `f"{app_label}/{model_name}.html"` — this gives proper breadcrumbs, tabs, page header
- `CustomObjectTypeField.related_object_type` is a FK to `core.ObjectType` (a proxy of
  Django's ContentType); using `ContentType.objects.get_for_model()` works because the
  underlying DB table and IDs are shared
- Each model needs its own View subclass (factory pattern) so the view registry stores
  distinct entries and URL reverse names don't collide
- `inc/paginator.html` uses `page.smart_pages` (from `EnhancedPage`) — this is **not**
  available on Django's built-in `Page`; always use `EnhancedPaginator`

## TODO — Step-by-step Implementation Checklist

- [x] 1. Create `.gitignore`
- [x] 2. Create `pyproject.toml`
- [x] 3. Create `netbox_custom_objects_tab/__init__.py` (PluginConfig)
- [x] 4. Create `netbox_custom_objects_tab/views.py` (view factory + register_tabs)
- [x] 5. Create `netbox_custom_objects_tab/urls.py` (empty urlpatterns)
- [x] 6. Create `netbox_custom_objects_tab/templates/netbox_custom_objects_tab/custom_objects_tab.html`
- [x] 7. Create `README.md` and `CLAUDE.md`
- [x] 8. Initialize git repo: `git init && git add -A && git commit -m "Initial plugin scaffold"`
- [x] 9. Install into NetBox venv: `source /opt/netbox/venv/bin/activate && pip install -e /opt/custom_objects_additional_tab_plugin/`
- [x] 10. Add plugin to NetBox `configuration.py` under `PLUGINS` and `PLUGINS_CONFIG`
- [x] 11. Restart NetBox: `sudo systemctl restart netbox netbox-rq`
- [x] 12. Test: create a Custom Object Type with a Device field, create a Custom Object
          instance referencing a Device, verify the "Custom Objects" tab appears on the
          Device detail page with badge count = 1
- [x] 13. Add wildcard model registration (`dcim.*`, `ipam.*`)
- [x] 14. Add pagination (`EnhancedPaginator`) and `?q=` text search
- [x] 15. Verify badge COUNT vs full fetch split (COUNT-only on detail page; full fetch only on tab)

## Critical Reference Files

| File | Purpose |
|------|---------|
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/template_content.py` | Query pattern to replicate |
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/models.py` | `CustomObjectTypeField` model structure |
| `/opt/netbox/netbox/utilities/views.py` | `register_model_view` + `ViewTab` API |
| `/opt/netbox/netbox/utilities/paginator.py` | `EnhancedPaginator` + `get_paginate_count` |
| `/opt/netbox/netbox/templates/inc/paginator.html` | Pagination partial — expects `page` + `paginator` context vars |
| `/opt/netbox/netbox/netbox/views/generic/object_views.py` | How `base_template` context is constructed |

## Verification Steps

1. Activate venv and install: `pip install -e /opt/custom_objects_additional_tab_plugin/`
2. Add to NetBox config, restart
3. In NetBox UI: Customization → Custom Object Types → create a type with a Device field
4. Create a Custom Object instance that references an existing Device
5. Navigate to that Device's detail page — "Custom Objects" tab appears (badge = 1)
6. Click tab — table shows: type name | object link | field name
7. Paginator appears when results exceed the per-page threshold
8. Type a search term — table filters; badge count stays at total
9. Delete the custom object — tab disappears
10. Check logs: `journalctl -u netbox` for any import errors
