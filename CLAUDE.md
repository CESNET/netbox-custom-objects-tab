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
| `netbox_custom_objects_tab/templates/netbox_custom_objects_tab/custom_objects_tab.html` | Tab content template (full page, extends base_template) |
| `netbox_custom_objects_tab/templates/netbox_custom_objects_tab/custom_objects_tab_partial.html` | Swappable HTMX zone — returned for HTMX partial requests; no `{% extends %}` |

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
from utilities.htmx import htmx_partial
from types import SimpleNamespace
```

## Pagination & Filtering Design

- **`_get_linked_custom_objects(instance)`** — returns a Python `list` of `(obj, field)` tuples
  by querying across multiple dynamic model tables. A single queryset is not possible.
  Each queryset uses `.prefetch_related('tags')` so tag data is batch-fetched (one extra
  query per field) and cached on each object instance — no N+1 cost in the template.
- **`_filter_linked_objects(linked, q)`** — filters that list in Python; case-insensitive
  match against `str(obj)`, `str(field.custom_object_type)`, `str(field)`.
- **`available_tags`** — collected in the view from `linked_all` (unfiltered) by iterating
  `_obj.tags.all()` (uses prefetch cache). Deduplicated by slug, sorted by `name.lower()`.
  Passed to context as `available_tags`; the active tag filter slug is `tag_slug`.
- **Tag filter** — `tag_slug = request.GET.get('tag', '').strip()`; applied after the type
  filter by checking `tag_slug in {t.slug for t in obj.tags.all()}` (cache hit, no query).
- **`EnhancedPaginator(linked, get_paginate_count(request))`** — paginates the filtered list.
  `get_paginate_count` respects `?per_page=`, user prefs, and global `PAGINATE_COUNT`.
- **`inc/paginator.html`** — pass `htmx=True table=htmx_table` to emit `hx-get` links.
  `htmx_table = SimpleNamespace(htmx_url=request.path, embedded=False)`.
  The paginator uses `{% querystring request page=p %}` which copies all current GET params
  (including `?tag=`, `?type=`, `?q=`, etc.) so filter state is preserved across pages.
- **`htmx_partial(request)`** — returns `True` when the request carries `HX-Request` and
  is not boosted. View returns `custom_objects_tab_partial.html` in that case.
- The partial wraps everything in `<div id="custom_objects_list" class="htmx-container">`.
  Paginator and sort-header links target this div via `hx-target` / `hx-swap="outerHTML"`.
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

## Permission Checks in Template

Action buttons and column links use the `perms` templatetag from `utilities.templatetags.perms`:

```django
{% load perms %}
{% if request.user|can_change:obj %}
<a href="{% url 'plugins:netbox_custom_objects:customobject_edit' pk=obj.pk custom_object_type=obj.custom_object_type.slug %}?return_url={{ return_url|urlencode }}" class="btn btn-yellow" role="button">...</a>
{% endif %}
{% if request.user|can_delete:obj %}
<a href="{% url 'plugins:netbox_custom_objects:customobject_delete' pk=obj.pk custom_object_type=obj.custom_object_type.slug %}?return_url={{ return_url|urlencode }}" class="btn btn-red" role="button">...</a>
{% endif %}
{% if request.user|can_view:field.custom_object_type %}<a href="...">...{% endif %}
```

- `can_change`, `can_delete`, `can_view` are template filters that take the user as the
  left-hand value and the object instance as the argument.
- Edit and Delete are rendered as **inline `<a>` buttons** (not inclusion tags) so that
  `?return_url={{ return_url|urlencode }}` can be appended. `return_url` is set in the
  view context as `request.get_full_path()` (path + query string, e.g.
  `/dcim/devices/42/custom-objects/?q=foo&sort=type&dir=asc`), so active filters are
  preserved when the user returns from Edit or Delete.
- The `custom_object_edit_button` / `custom_object_delete_button` inclusion tags from
  `netbox_custom_objects` do **not** accept a `return_url` argument — do not use them.
- Do **not** add bulk-edit or bulk-delete buttons to this tab — the tab shows objects
  from multiple different Custom Object Types, so bulk editing across types is meaningless.

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
- Template is split into two files: `custom_objects_tab.html` (full page, extends base_template)
  and `custom_objects_tab_partial.html` (no extends — just the htmx-container div). The view
  returns the partial when `htmx_partial(request)` is True.
- The search form uses `hx-get` (no `method="get"`). The type select uses `hx-include="closest
  form"` to pull in sibling fields (q, sort, dir, per_page) when it fires on change.
- `CustomObjectDeleteView.get_return_url()` overrides the mixin and ignores request params.
  However, `ObjectDeleteView.post()` checks `form.cleaned_data['return_url']` **before**
  calling `get_return_url()`, so passing `?return_url=` in the delete button URL still works
  — NetBox initialises the delete confirmation form's hidden `return_url` field from the
  GET param, which is then submitted with the form.

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
- [x] 16. Add permission-gated Edit button (`can_change`) and Delete button (`can_delete`) per row
- [x] 17. Link the Type column to the CustomObjectType detail page (`can_view`-gated)
- [x] 18. Add HTMX partial rendering (paginator, sort headers, search form, type dropdown)
- [x] 19. Fix Edit/Delete return URL to redirect back to the Custom Objects tab
- [x] 20. Add Tags column and tag filter dropdown to the Custom Objects tab
- [x] 21. Add "Configure Table" button with per-user column show/hide/reorder preferences

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
6. Click tab — table shows: type name | object link | value | field name | actions
7. Paginator appears when results exceed the per-page threshold
8. Type a search term — table filters; badge count stays at total
8a. Click a paginator link — only the table zone re-renders (no full page reload)
8b. Click a sort column — table updates in-place; URL bar reflects new sort params
8c. Change the type dropdown — table filters without full reload
8d. Network tab in devtools: HTMX requests carry `HX-Request: true`; response has no `<html>` tag
9. As a superuser: Edit and Delete buttons appear; Type column is a clickable link
10. As a read-only user: no action buttons; Type column is a link if user has `view_customobjecttype`, plain text otherwise
11. Click Edit → navigates to the Custom Object instance edit page; save → returns to the tab
12. Click Delete → navigates to the delete confirmation page; confirm → returns to the tab
13. Click the Type column link → navigates to the Custom Object Type detail page
14. Delete the custom object — tab disappears
15. Check logs: `journalctl -u netbox` for any import errors
