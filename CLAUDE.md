# netbox_custom_objects_tab — Project Notes for Claude

## Git Conventions

- **Never** add `Co-Authored-By: Claude` (or any Claude/Anthropic credit) to commit messages.

## Linting & Formatting

[ruff](https://docs.astral.sh/ruff/) is the project linter and formatter.
Configuration lives in `ruff.toml` (line-length = 120, ruleset E/F/W/I).

```bash
# Install dev dependencies (includes ruff)
pip install -e ".[dev]"

# Check
ruff check netbox_custom_objects_tab/

# Format
ruff format netbox_custom_objects_tab/
```

Always run both before committing Python changes.

## Purpose

Adds **two tab modes** to NetBox object detail pages (Device, Site, Rack, etc.):

1. **Combined tab** — a single "Custom Objects" tab showing all Custom Object instances
   from any Custom Object Type that reference the parent object. Supports pagination,
   text search, type/tag filters, column sorting, and per-user column preferences.

2. **Typed tabs** (per-type) — each Custom Object Type gets its own tab with a
   **full-featured** type-specific list view: same columns, filters, search, bulk actions,
   edit/delete, and configure table as the native `/plugins/custom-objects/<slug>/` page.

Both modes coexist. Config variables control which models get which behavior.

## Architecture

**NO models, NO migrations, NO API, NO forms, NO navigation menu.**

| File | Role |
|------|------|
| `netbox_custom_objects_tab/__init__.py` | `PluginConfig`; calls `views.register_tabs()` in `ready()` |
| `netbox_custom_objects_tab/views/__init__.py` | `register_tabs()` + `_resolve_model_labels()` helper |
| `netbox_custom_objects_tab/views/combined.py` | Combined-tab view factory + helpers |
| `netbox_custom_objects_tab/views/typed.py` | Per-type tab view factory + dynamic table/filterset builders |
| `netbox_custom_objects_tab/urls.py` | Empty `urlpatterns` (required by NetBox plugin loader) |
| `templates/.../combined/tab.html` | Combined tab full page (extends base_template) |
| `templates/.../combined/tab_partial.html` | Combined tab HTMX zone (no extends) |
| `templates/.../typed/tab.html` | Typed tab full page (extends base_template, mirrors `generic/object_list.html`) |

## Config Design

```python
# __init__.py default_settings
default_settings = {
    "typed_models": [],       # per-type tabs (opt-in, empty by default)
    "combined_models": [      # combined tab (current behavior)
        "dcim.*", "ipam.*", "virtualization.*", "tenancy.*",
    ],
    "combined_label": "Custom Objects",
    "combined_weight": 2000,
    "typed_weight": 2100,     # all typed tabs share this weight
}
```

Both `typed_models` and `combined_models` accept the same label formats:

| Format | Behaviour |
|--------|-----------|
| `dcim.device` | Registers for that single model |
| `dcim.*` | Registers for **every model** in the `dcim` app |

A model can appear in both lists and get both tab styles.

**Third-party plugin models are fully supported:**
```python
'combined_models': ['dcim.*', 'ipam.*', 'inventory_monitor.*']
```

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
from extras.choices import CustomFieldTypeChoices, CustomFieldUIVisibleChoices
from netbox.plugins import get_plugin_config
from utilities.htmx import htmx_partial
from netbox_custom_objects.tables import CustomObjectTable
from netbox_custom_objects import field_types
from netbox_custom_objects.filtersets import get_filterset_class
from netbox.forms import NetBoxModelFilterSetForm
from netbox.forms.mixins import SavedFiltersMixin
from utilities.forms.fields import TagFilterField
```

## Combined Tab — Pagination & Filtering Design

- **`_get_linked_custom_objects(instance)`** — returns a Python `list` of `(obj, field)` tuples
  by querying across multiple dynamic model tables. A single queryset is not possible.
  Each queryset uses `.prefetch_related('tags')` so tag data is batch-fetched.
- **`_filter_linked_objects(linked, q)`** — filters that list in Python; case-insensitive
  match against `str(obj)`, `str(field.custom_object_type)`, `str(field)`.
- **`available_tags`** — collected from `linked_all` (unfiltered), deduplicated by slug.
- **Tag filter** — applied after the type filter by checking tag slugs (cache hit, no query).
- **`EnhancedPaginator`** — paginates the filtered list.
- **`htmx_partial(request)`** — returns partial template for HTMX requests.
- Badge count uses `.count()` (DB-side `COUNT(*)`) per field — no full rows fetched.

## Typed Tab — Architecture

The typed tab reuses components from `netbox_custom_objects`:

| What | Import path |
|------|-------------|
| `CustomObjectTable` | `netbox_custom_objects.tables.CustomObjectTable` — base table with pk, id, actions, tags |
| `FIELD_TYPE_CLASS` | `netbox_custom_objects.field_types.FIELD_TYPE_CLASS` — column + filter generation |
| `get_filterset_class()` | `netbox_custom_objects.filtersets.get_filterset_class` — dynamic filterset |
| Bulk action template tags | `netbox_custom_objects.templatetags.custom_object_buttons` |

Key functions in `views/typed.py`:

- **`_build_typed_table_class(cot, model)`** — dynamically creates a table class replicating
  `CustomObjectTableMixin.get_table()` logic from `netbox_custom_objects`.
- **`_build_filterset_form(cot, model)`** — dynamically creates a filter form replicating
  `CustomObjectListView.get_filterset_form()`.
- **`_count_for_type(cot, field_infos)`** — returns a badge callable (COUNT-only).
- **`_make_typed_tab_view(model, cot, field_infos, weight)`** — view factory. The `get()`
  method builds a base queryset (union of field filters + `.distinct()`), applies filterset,
  builds table, calls `table.configure(request)`, and returns the typed template.
- **`register_typed_tabs(models, weight)`** — pre-fetches all fields, groups by
  `(content_type, custom_object_type)`, registers one view per pair.

HTMX for typed tabs: the view returns `htmx/table.html` (NetBox standard) for HTMX requests.
No custom partial needed — `table.configure(request)` handles pagination and ordering.

## Permission Checks in Template

Combined tab uses inline `<a>` buttons with `can_change`/`can_delete` filters (see combined templates).
Typed tab uses `CustomObjectActionsColumn` from `netbox_custom_objects.tables` which handles
permissions internally via `get_permission_for_model()`.

- Do **not** add bulk-edit or bulk-delete buttons to the **combined** tab — it shows objects
  from multiple different Custom Object Types, so bulk editing across types is meaningless.
- Typed tabs **do** support bulk actions since all objects are the same type.

## Gotchas

- `register_model_view` must run inside `AppConfig.ready()` — not at module level
- `hide_if_empty=True` on ViewTab requires the badge callable to return `None` (not `0`)
  when the count is zero
- Template must `{% extends base_template %}` where `base_template` is set in view context
  as `f"{app_label}/{model_name}.html"`
- `CustomObjectTypeField.related_object_type` is a FK to `core.ObjectType` (proxy of ContentType)
- Each model needs its own View subclass (factory pattern) for distinct registry entries
- `inc/paginator.html` uses `page.smart_pages` — always use `EnhancedPaginator`
- Combined tab template is split: `combined/tab.html` (full page) and `combined/tab_partial.html`
  (HTMX zone). Typed tab uses NetBox's `htmx/table.html` directly.
- `table.htmx_url` must be set on the instance to shadow `@cached_property` (avoids reverse
  error for dynamic models)
- Typed tabs use `custom-objects-{slug}` path prefix — avoids collisions with built-in paths
- Multiple fields of same type → union querysets with `.distinct()`
- Tabs registered at `ready()` — new Custom Object Types need a restart
- `SavedFiltersMixin` lives at `netbox.forms.mixins`, not `extras.forms.mixins`

## Critical Reference Files

| File | Purpose |
|------|---------|
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/template_content.py` | Query pattern to replicate |
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/models.py` | `CustomObjectTypeField` model structure |
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/views.py` | `CustomObjectTableMixin.get_table()` + `get_filterset_form()` |
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/tables.py` | `CustomObjectTable`, `CustomObjectActionsColumn` |
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/filtersets.py` | `get_filterset_class()` |
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/field_types.py` | `FIELD_TYPE_CLASS` dict |
| `/opt/netbox/netbox/utilities/views.py` | `register_model_view` + `ViewTab` API |
| `/opt/netbox/netbox/utilities/paginator.py` | `EnhancedPaginator` + `get_paginate_count` |
| `/opt/netbox/netbox/templates/htmx/table.html` | HTMX table template used by typed tabs |
| `/opt/netbox/netbox/templates/generic/object_list.html` | Full list view layout pattern |

## Verification Steps

1. Activate venv and install: `pip install -e /opt/custom_objects_additional_tab_plugin/`
2. Add to NetBox config, restart
3. Combined tab: navigate to Device detail → "Custom Objects" tab appears with badge
4. Typed tab: with `typed_models: ['dcim.*']`, per-type tabs appear (e.g. "Link - ISISs")
5. Typed tab: type-specific columns, filters sidebar, bulk actions, configure table all work
6. HTMX: pagination and sorting update in-place (no full reload)
7. Bulk actions: select rows → bulk edit/delete work, return URL correct
8. Per-row edit/delete: action buttons work, return URL preserves tab
9. Remove all objects of one type → typed tab disappears
10. Combined tab unchanged when typed tabs enabled
