# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.3.0] - 2026-05-12

### Added

- **Add button on Typed tabs** ([#9](https://github.com/CESNET/netbox-custom-objects-tab/issues/9)) —
  each Typed tab now shows an "Add *Type*" button in the bottom toolbar
  (alongside Bulk Edit and Bulk Delete) that opens the native
  `customobject_add` view with the reverse-reference field pre-filled to the
  parent object's PK and `return_url` set back to the tab. After saving, the
  user lands back on the same tab, with any active filters preserved. When a
  Custom Object Type has multiple fields referencing the same parent model
  (e.g. `primary_device` and `backup_device` both → Device), the button
  becomes a split-dropdown listing each field. The button is hidden for
  users without `add_customobject` permission.

### Fixed

- **Typed-tab URL registration**: typed-tab views are now registered
  synchronously inside `AppConfig.ready()` instead of from a `request_started`
  signal handler. The earlier deferral (commit `5bf09c3`, PR #4) silenced
  some startup warnings but broke typed-tab routing entirely — NetBox's
  `get_model_urls()` snapshots `registry['views']` when each model's
  `urls.py` is first imported, so any view added afterward has no URL
  pattern. Combined tabs were unaffected because they were already
  synchronous; typed tabs were unreachable on every deployment with
  `typed_models` configured. The `OperationalError`/`ProgrammingError`
  safety net inside `register_typed_tabs` still covers the
  `manage.py migrate` / fresh-DB case.
- **Typed-tab badge no longer over-counts** rows that match the parent via
  multiple fields. `_count_for_type` previously summed per-field counts
  with no deduplication, so a Custom Object Type with several fields
  pointing to the same parent model (e.g. `primary_device` +
  `backup_device` + `affected_devices` all → `dcim.device`) reported a
  badge number larger than the actual table row count whenever a row
  matched the parent via more than one field. Now uses the same
  `Q-OR-Q + .distinct()` pattern as the table queryset, so the badge and
  the table always agree. Bonus: one SQL query per tab badge instead of N
  (one per Device-pointing field). Bug existed since the typed-tab
  feature was introduced in 2.0.0; only became visible with multi-FK or
  M2M field combinations.
- **Typed-tab Bulk Edit / Bulk Delete buttons are now permission-gated**
  against `netbox_custom_objects.change_customobject` /
  `delete_customobject` respectively, matching the gating pattern the
  Add button uses. Previously these buttons rendered unconditionally on
  Typed tabs; clicks were rejected server-side by NetBox's
  `customobject_bulk_*` views but the unguarded UI render was confusing
  for non-superusers. Per-button guards (rather than gating the whole
  toolbar on `change AND delete`) so a user with only `change` perm
  sees Bulk Edit but not Bulk Delete, and vice versa. Surfaced by the
  2.3.0 smoke test with non-admin test users.

## [2.2.0] - 2026-05-11

### Changed

- Widen supported NetBox range to **4.5.0 – 4.6.99** (`max_version` bumped from
  `4.5.99` to `4.6.99`). No code or template changes were required: every NetBox
  API the plugin depends on — `ViewTab`, `register_model_view`, `htmx_partial`,
  `EnhancedPaginator`, `get_paginate_count`, `BaseTable`,
  `NetBoxModelFilterSetForm`, `SavedFiltersMixin`, `TagFilterField`,
  `CustomFieldTypeChoices`, `CustomFieldUIVisibleChoices`, and the
  `registry['views']` shape — is unchanged in NetBox 4.6 (verified against the
  `v4.6.0` upstream tag). The 4.6 deprecations of `registry['models']` and
  legacy `actions = {...}` view dicts do not affect this plugin.
- On NetBox 4.6, the upstream `netbox_custom_objects` plugin **≥ 0.5.0** is
  recommended (its `max_version` covers 4.6.99). The CO detail-page template
  override remains necessary — `customobject.html` in upstream v0.5.0 still
  hardcodes its `{% block tabs %}` without `{% model_view_tabs object %}`.

## [2.1.0] - 2026-03-16

### Added

- **CO→CO tabs** — `netbox_custom_objects.*` is now a valid value for both `combined_models`
  and `typed_models`. This enables tabs on Custom Object detail pages themselves: when
  Custom Object Type A has a field (FK or M2M) pointing to Custom Object Type B, navigating
  to a Type B instance shows a tab listing all Type A instances that reference it.
  A NetBox restart is required whenever a new Custom Object Type is added (same requirement
  as all typed tabs).
- `template_override.py` — prepends our templates directory to Django's filesystem loader
  at `ready()` time so that our `netbox_custom_objects/customobject.html` override (which
  adds `{% model_view_tabs object %}`) is found before the original template.

### Fixed

- Tab views now accept `**kwargs` in their `get()` method, accommodating the extra
  `custom_object_type` URL keyword argument present on Custom Object detail URLs.
- `base_template` for Custom Object model instances now correctly resolves to
  `netbox_custom_objects/customobject.html` instead of the nonexistent per-model template.
- `_inject_co_urls()` appends the necessary URL patterns for CO tab views into
  `netbox_custom_objects.urls` at startup, enabling URL reversal for registered tabs
  (the `netbox_custom_objects` plugin uses a single generic view and never registers
  per-model URL patterns for dynamic models).

## [2.0.2] - 2026-03-06

### Fixed

- **TypeError on typed tab** — removed `user=` keyword argument from `CustomObjectTable`
  instantiation. `django_tables2.Table.__init__` does not accept this kwarg; it was
  redundant because `table.configure(request)` already applies per-user column preferences.
  Fixes crash on NetBox 4.5.4-Docker (`netbox_custom_objects` 0.4.6).

### Changed

- Plugin version is now defined only in `pyproject.toml` and read at runtime via
  `importlib.metadata.version()`, eliminating the duplicate version string in `__init__.py`.

## [2.0.1] - 2026-02-25

### Added

- **Typed tabs (per-type)** — each Custom Object Type gets its own tab with a full-featured
  list view: type-specific columns, filterset sidebar, bulk edit/delete, configure table,
  and HTMX pagination.
- `typed_models` and `typed_weight` config settings.
- Third-party plugin model support for both tab modes.

### Changed

- Renamed `models` config to `combined_models`; `label` to `combined_label`; `weight` to
  `combined_weight`.
- Refactored views from single `views.py` to `views/` package (`__init__.py`, `combined.py`,
  `typed.py`).
- Templates reorganized into `combined/` and `typed/` subdirectories.

### Fixed

- Handle missing database during startup — `register_typed_tabs()` now catches
  `OperationalError` and `ProgrammingError` so NetBox can start even when the database
  is unavailable or migrations haven't run yet.
- Bulk action return URL in typed tabs — uses query parameter `?return_url=` on `formaction`
  for reliable redirect.

## [1.0.1] - 2026-02-24

### Fixed

- **Templates missing from built wheel** — added `[tool.setuptools.package-data]` in
  `pyproject.toml` and `MANIFEST.in` so HTML templates are included when installing
  from PyPI or a pre-built wheel (fixes `TemplateDoesNotExist` in Docker deployments).

## [1.0.0] - 2026-02-24

### Added

- **Custom Objects tab** on NetBox object detail pages (Device, Site, Rack, and any
  configured model), showing Custom Object instances that reference the viewed object
  via OBJECT or MULTIOBJECT typed fields.
- **Pagination** using NetBox's `EnhancedPaginator`; respects the user's personal
  per-page preference and the `?per_page=N` URL parameter.
- **Text search** (`?q=`) filtering results by Custom Object instance display name,
  Custom Object Type name, and field label.
- **Type filter dropdown** (`?type=<slug>`) to narrow results to a single Custom Object
  Type, populated dynamically from types present in the current result set.
- **Efficient badge counts** — the tab badge on every detail page is computed with
  `COUNT(*)` queries (no full object rows fetched). Full rows are loaded only when the
  tab itself is opened, keeping detail page loads fast even with thousands of linked
  custom objects.
- **Wildcard model registration** — the `models` plugin config setting accepts
  `app_label.*` to register the tab for every model in an app (e.g. `dcim.*`, `ipam.*`).
- **Third-party plugin model support** — any installed Django app (including NetBox
  plugins) can be listed in `models`; Django's app registry treats them identically to
  built-in apps.
- Default configuration: `['dcim.*', 'ipam.*', 'virtualization.*', 'tenancy.*', 'contacts.*']`.
- Tab is hidden automatically (`hide_if_empty=True`) when no custom objects reference
  the viewed object.
- **Configurable tab label and weight** — set `label` and `weight` in `PLUGINS_CONFIG`
  to control the tab text and position (defaults: `'Custom Objects'`, `2000`).
- **Column sorting** — clicking the **Type**, **Object**, or **Field** column headers
  sorts the table in-memory; a second click toggles direction. Sort state is preserved
  across filter submissions.
- **Value column** — shows the actual field value on each Custom Object instance:
  a link for OBJECT fields, or comma-separated links (truncated at 3) for MULTIOBJECT fields.
- **Clickable Type column** — the Type column links to the Custom Object Type detail
  page when the user has `view` permission; otherwise renders as plain text.
- **Permission-gated action buttons** — each row has an Edit button (requires `change`
  permission) and a Delete button (requires `delete` permission). Users without either
  permission see no action buttons.
- **HTMX partial updates** — pagination, column sorting, search form submission, and
  type-dropdown changes now swap only the table zone in-place, without a full page reload.
  The URL is updated via `pushState` so links remain shareable and the browser back button
  restores the previous filter/page state.
- **Tags column** — each row in the Custom Objects table now shows the tags assigned to
  that Custom Object instance as colored badges. Rows with no tags display `—`.
- **Tag filter dropdown** (`?tag=<slug>`) — a tag dropdown appears in the search bar
  whenever at least one linked Custom Object has a tag, letting users narrow the table to
  objects with a specific tag. Tag filtering composes with `?q=`, `?type=`, sort, and
  pagination. Tags are pre-fetched in bulk (`prefetch_related('tags')`) so there is no
  N+1 query cost.
- **Configure Table** — a "Configure Table" button in the card header opens a NetBox
  modal that lets authenticated users show, hide, and reorder columns (Type, Object,
  Value, Field, Tags). Preferences are persisted per-user in `UserConfig` under
  `tables.CustomObjectsTabTable.columns` and respected on every subsequent page load,
  including HTMX partial updates. The Actions column is always visible and cannot be
  hidden.

### Fixed

- **Edit/Delete return URL** — after saving an edit or confirming a deletion, NetBox now
  redirects back to the Custom Objects tab instead of to the Custom Object list page.
- **Filter state preserved on return** — active filters (`?q=`, `?type=`, `?sort=`, `?dir=`,
  `?per_page=`, `?page=`) are retained in the return URL so the user lands back on the same
  filtered/sorted view after editing or deleting a custom object.
