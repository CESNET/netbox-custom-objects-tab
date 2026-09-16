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

Always run both before committing Python changes. Tests: `pytest tests/ -v` (offline, NetBox
is mocked in `tests/conftest.py`; no DB, no `/opt/netbox`).

## Purpose

Adds **one tab per Custom Object Type** ("typed tabs") to NetBox object detail pages (Device,
Site, Rack, …, third-party plugin models, and Custom Object detail pages themselves). Each tab is
a full-featured type-specific list view: same columns, filters, search, bulk actions,
edit/delete, Add buttons and configure-table as the native `/plugins/custom-objects/<slug>/` page.

The **combined "Custom Objects" tab is NOT this plugin's job any more.** Since
`netbox-custom-objects` 0.7.0 it is built into upstream
(`netbox_custom_objects/related_tabs/`, registry name `custom_objects`, path `custom-objects`,
weight 2000, label "Custom Objects", no config, registered on every public model, live badge with
`hide_if_empty`). Plugin ≤ 2.6 shipped its own combined tab; 3.0.0 removed it. Do not re-add it.

## Requirements / Gate

- NetBox 4.5.2 – 4.7.99 (`min_version` / `max_version` in `PluginConfig`).
- `netbox-custom-objects` **≥ 0.7.0**, enforced in `ready()` by importing
  `netbox_custom_objects.related_tabs.registry` (feature probe, not a version string). Missing →
  `ImproperlyConfigured`. Also checks `apps.is_installed("netbox_custom_objects")` first, because
  NetBox silently skips a plugin whose `max_version` is below the running release.
- Leftover `combined_models` / `combined_label` / `combined_weight` in `PLUGINS_CONFIG` → one
  `logger.warning`, otherwise ignored.

## Architecture

**NO models, NO migrations, NO API, NO forms, NO navigation menu, NO templates overriding upstream,
NO templatetags.**

| File | Role |
|------|------|
| `netbox_custom_objects_tab/__init__.py` | `PluginConfig`; gate checks, then `views.register_tabs()` in `ready()` |
| `netbox_custom_objects_tab/views/__init__.py` | `register_tabs()`, `_resolve_model_labels()`, `_inject_co_urls()` + `_make_co_dispatcher()`, `_deduplicate_registry()` |
| `netbox_custom_objects_tab/views/typed.py` | Per-type tab view factory, dynamic table builder, Q-filter builder, Add-link builder, `_get_base_template()` |
| `netbox_custom_objects_tab/urls.py` | Empty `urlpatterns` (required by NetBox plugin loader) |
| `templates/netbox_custom_objects_tab/typed/tab.html` | Typed tab full page (extends `base_template`, mirrors `generic/object_list.html`); HTMX requests get NetBox's `htmx/table.html` |
| `tools/` | Standalone `manage.py shell <` scripts: demo data and the 2.4.0 polymorphic smoke test (not packaged) |

## Config

```python
default_settings = {
    "typed_models": [],   # opt-in; "app.model" or "app.*"; "netbox_custom_objects.*" = CO→CO tabs
    "typed_weight": 2100, # upstream combined tab is 2000 → typed tabs render right after it
}
```

## How Custom Objects Link to NetBox Objects

`netbox_custom_objects` uses **direct FK / M2M** relationships (plus GFK-style
`<name>_content_type_id`/`<name>_object_id` and a through model for polymorphic fields), not a
single GenericForeignKey. Each Custom Object Type generates a real Django model (`Table<N>Model`).

`register_typed_tabs()` pre-fetches all `CustomObjectTypeField` rows of type OBJECT/MULTIOBJECT
(non-poly via `related_object_type`, poly via `related_object_types` M2M), groups them by
`(host_content_type_id, custom_object_type_pk)` → `field_infos = [(name, type, label, is_poly,
through_model_name)]`, and registers one view per pair with `register_model_view(model,
name=f"custom_objects_{slug}", path=f"custom-objects-{slug}")`.

`_build_q_for_field()` turns one field_info into a `Q`; the view ORs them and applies
`.distinct()`. An empty `Q()` means "unresolvable" and must be skipped (`filter(Q())` = all rows).

Upstream reference for the same shapes: `netbox_custom_objects/related_tabs/views/combined.py::reference_q`.

## Key Import Paths (NetBox 4.5.x / 4.6.x / 4.7.x, netbox-custom-objects 0.7.x)

```python
from utilities.views import ViewTab, register_model_view, get_default_template
from netbox_custom_objects.models import CustomObjectTypeField, CustomObjectType, CustomObject
from netbox_custom_objects.tables import CustomObjectTable
from netbox_custom_objects import field_types                      # FIELD_TYPE_CLASS
from netbox_custom_objects.filtersets import get_filterset_class
from netbox_custom_objects.dynamic_forms import build_filterset_form_class
from extras.choices import CustomFieldTypeChoices, CustomFieldUIVisibleChoices
from netbox.plugins import get_plugin_config
from netbox.registry import registry
```

## CO→CO Tabs (`netbox_custom_objects.*` in `typed_models`)

Type A has a field → Type B ⇒ Type B's detail page shows a "Type A" tab.

1. **Model resolution** — dynamic models are read from
   `apps.get_app_config("netbox_custom_objects").get_models()` filtered to `CustomObject`
   subclasses (safe after upstream's `ready()`). **Never call `CustomObjectType.get_model()` in
   `ready()`** — a cache miss re-registers journal/changelog views → duplicate tabs.
2. **URL patterns** — upstream serves all CO detail pages via one generic `CustomObjectView` and
   never calls `get_model_urls()` for dynamic models, so our registry entries have no routes.
   `_inject_co_urls()` appends `<str:custom_object_type>/<int:pk>/custom-objects-<slug>/` named
   `customobject_custom_objects_<slug>` to `netbox_custom_objects.urls.urlpatterns` at `ready()`.
3. **Dispatcher** — one slug's action may be registered on several host CO models (Type A →
   Type B *and* Type C). The route is bound to `_make_co_dispatcher(action_name)`, which per
   request does `CustomObjectType(slug).get_model()._meta.model_name` → registry lookup →
   `view_cls.as_view()(request, custom_object_type=…, pk=…)`. This loads the right host model and
   puts *that model's* `ViewTab` in the context. (≤ 2.6 bound the route to the first model's view
   class: wrong object for other hosts, and never-active tab — the 2.6.0 `(label, weight)` hack.)
4. **Rendering** — upstream 0.7.0 `customobject.html` calls `{% plugin_extra_tabs object %}`
   (upstream's own tag in `netbox_custom_objects/templatetags/custom_object_tab_tags.py`). It
   renders every registry tab except exact names `journal`, `changelog`, `contacts`,
   `custom_objects`, drops tabs whose URL doesn't reverse, and marks active by identity
   `context["tab"] == view.tab`. Our names `custom_objects_<slug>` pass the filter; the dispatcher
   makes the identity check succeed.

## Gotchas

- `register_model_view` must run inside `AppConfig.ready()` — not at module level.
- **Do NOT defer typed-tab registration** to `request_started` or any post-`ready()` signal.
  NetBox's `get_model_urls(app, model)` snapshots `registry['views']` when the model's `urls.py`
  is first imported. PR #4 / commit `5bf09c3` deferred it to silence DB-access startup warnings
  and broke all typed tabs (reverted in 2.3.0). The warning is acceptable.
- `hide_if_empty=True` requires the badge callable to return `None` (not `0`) when empty.
- `base_template` for CO instances is `netbox_custom_objects/customobject.html`; per-model
  templates (`table28model.html`) don't exist. For native models use `get_default_template()`
  (falls back to `generic/object.html` for models without a detail template, e.g. `ipam.vrf`).
- Tab view `get()` must accept `**kwargs` — CO routes pass `custom_object_type`.
- `table.htmx_url` must be set on the instance to shadow `@cached_property` (avoids reverse error
  for dynamic models).
- Upstream views set `context["tab"]` to a plain **str** (`"journal"`, `"changelog"`, `"contacts"`,
  `"configcontext"`) — never assume it's a `ViewTab`.
- **Never ship a templatetag module named `custom_object_tab_tags`** (or any name upstream uses).
  Django's `get_installed_libraries()` lets the later `INSTALLED_APPS` entry win; 2.6.x shadowed
  upstream's library and would have broken `{% custom_objects_tab_link %}` on 0.7.0.
- Tabs are registered at `ready()` — a new Custom Object Type needs a NetBox restart.
- Toolbar permissions are checked against the **base** `customobject` model
  (`netbox_custom_objects.add_customobject` etc.), not the dynamic subclass.
- Known upstream issue (documented 2.3.0): Create via the typed-tab Add button and then per-row
  Delete on the new row in the same flow can raise `ValueError` in `CustomObjectDeleteView`
  (model class identity drift). Refresh between the two, or use Bulk Delete.

## Critical Reference Files

Upstream editable checkout (also what the venv imports): `/opt/netbox-custom-objects/netbox_custom_objects/`

| File | Purpose |
|------|---------|
| `related_tabs/registry.py`, `related_tabs/views/combined.py` | Upstream combined tab + `reference_q()`; the pattern our Q builder mirrors |
| `templatetags/custom_object_tab_tags.py` | Upstream `plugin_extra_tabs` (renders our typed tabs on CO pages) |
| `templates/netbox_custom_objects/customobject.html` | CO detail template (tabs block) |
| `models.py` | `CustomObjectTypeField`, `CustomObjectType.get_model()` |
| `views.py` | `CustomObjectTableMixin.get_table()` — table-building logic we replicate |
| `tables.py`, `filtersets.py`, `field_types.py`, `dynamic_forms.py` | Reused building blocks |
| `/opt/netbox/netbox/utilities/views.py` | `register_model_view` + `ViewTab` |
| `/opt/netbox/netbox/templates/htmx/table.html`, `generic/object_list.html` | Templates the typed tab mirrors |

## Verification Steps

1. `pip install -e /opt/custom_objects_additional_tab_plugin/` into the NetBox venv; restart.
2. `typed_models: ['dcim.*', 'netbox_custom_objects.*']` → Device detail shows upstream's
   "Custom Objects" tab (weight 2000) followed by one tab per referencing type; no duplicates.
3. Typed tab: type-specific columns, filter sidebar, bulk actions, Add buttons, configure table.
4. HTMX: pagination and sorting update in place.
5. CO detail page (`/plugins/custom-objects/<slug>/<pk>/`): typed tabs render, the open one is
   `active`, upstream's `/custom-objects/`, `/journal/`, `/changelog/`, `/contacts/` still 200.
6. Remove all objects of one type → its tab disappears.
7. `manage.py check` clean (no `netbox_custom_objects.W002`).
