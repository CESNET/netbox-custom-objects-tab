# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.4.1] - 2026-05-25

### Changed

- **Bumped supported version floors** to track upstream
  `netbox-custom-objects` v0.5.1
  ([release notes](https://github.com/netboxlabs/netbox-custom-objects/releases/tag/v0.5.1)):
  - `PluginConfig.min_version`: `4.5.0` → **`4.5.2`** (mirrors upstream's
    own NetBox floor bump in
    [#511](https://github.com/netboxlabs/netbox-custom-objects/pull/511) —
    keeps both gates consistent so a NetBox 4.5.0/4.5.1 host cannot end
    up with our plugin loading while `netbox-custom-objects` itself
    refuses to start).
  - `netbox-custom-objects` runtime floor: **`≥ 0.5.1`** (was `≥ 0.5.0`).
    The `ImproperlyConfigured` message in `PluginConfig.ready()` now
    points users at `pip install -U 'netbox-custom-objects>=0.5.1'`. The
    behavioural probe (`CustomObjectTypeField._meta.get_field("is_polymorphic")`)
    is unchanged — it still keys off the 0.5.0 schema sentinel, since
    no field added in 0.5.1 is a reliable runtime marker — but the
    user-facing recommendation advances to 0.5.1, which fixes the
    upstream Delete bug previously called out under
    [Known Issues](README.md#known-issues) as well as several
    cross-COT FK and M2M-deletion regressions.
- **No code-logic changes** were required to follow v0.5.1.
  `combined.py::_iter_linked_fields` and `typed.py::_build_q_for_field`
  already filter by `instance.pk` (int) rather than by model instance,
  so upstream's fix for issue
  [#508](https://github.com/netboxlabs/netbox-custom-objects/issues/508)
  (`CustomObjectLink.left_page()` rewrite from
  `filter(**{field.name: target_obj})` to
  `filter(**{f"{field.name}_id": target_obj.pk})`) does not affect us.
  The M2M `path_infos` repair from
  [#483](https://github.com/netboxlabs/netbox-custom-objects/issues/483)
  is applied inside `CustomObjectType.get_model()`, which we call per
  request, so we inherit the fix for free.

### Fixed

- **Active CSS class missing on Custom Object Journal/Changelog tabs**
  ([#15](https://github.com/CESNET/netbox-custom-objects-tab/issues/15)) —
  on Custom Object detail pages, clicking the Journal or Changelog tab
  loaded the right page but never highlighted the clicked tab. Root cause
  was the 2.1.0 template-override refactor (commit `37ccf6b`), which
  replaced upstream's hardcoded Journal/Changelog `<li>` blocks with a
  single `{% model_view_tabs object %}` call. Upstream
  `CustomObjectJournalView` / `CustomObjectChangeLogView`
  (`netbox_custom_objects/views.py:1321, 1393`) inject the literal
  strings `"journal"` / `"changelog"` into the template context as the
  active-tab marker, while `model_view_tabs`
  (`utilities/templatetags/tabs.py:53`) computes
  `is_active = active_tab == tab` where `tab` is a `ViewTab` *object*
  registered for the model — the string-vs-object comparison is always
  False, so the `active` class is never emitted. Verified still present
  on `netboxlabs-netbox-custom-objects` 0.5.0 and 0.5.1 under NetBox
  4.6.1. Fix renders Journal and Changelog as hardcoded `<li>` blocks
  in the override template (matching upstream's pre-override markup,
  with the string equality check) and introduces a new
  `{% plugin_extra_tabs %}` template tag
  (`netbox_custom_objects_tab/templatetags/custom_object_tab_tags.py`)
  that mirrors `model_view_tabs` but skips the `journal` / `changelog`
  actions — required because NetBox auto-registers `ObjectJournalView` /
  `ObjectChangeLogView` for every ChangeLoggedModel subclass in
  `netbox/models/features.py:737-742`, so without the filter the
  registry-driven render would emit duplicate inert Journal/Changelog
  tabs. Tab order is now Primary → combined/typed (registry) → Journal
  → Changelog, which incidentally matches the natural ViewTab weight
  ordering (combined=2000, typed=2100, Journal=5000, Changelog=10000)
  and stays stable if upstream later switches their context to
  `tab=self.tab` (at which point the hardcoded blocks and the custom
  tag can be retired).

## [2.4.0] - 2026-05-12

### Added

- **Polymorphic Object / MultiObject field support**
  ([#12](https://github.com/CESNET/netbox-custom-objects-tab/issues/12)) —
  `netbox-custom-objects` v0.5.0 introduced `is_polymorphic=True` fields
  whose targets live in the `related_object_types` M2M (and, for MultiObject,
  in a per-field through table keyed by `(source_id, content_type_id, object_id)`).
  The plugin's discovery logic previously filtered only on the single-FK
  `related_object_type`, so polymorphic links were invisible: tabs disappeared
  from referenced hosts (Device, Interface, Site, other CO Types) until the
  field was switched back to non-polymorphic. Both tab styles now mirror
  upstream's `CustomObjectLink.left_page` query shape — a non-polymorphic
  queryset plus a polymorphic queryset, with per-field branching into four
  reverse lookups (FK column, GFK `(content_type_id, object_id)` pair, M2M,
  polymorphic through table).
- **Polymorphic-field "Add *Type*" toolbar on typed tabs** — the toolbar
  shortcut now works for polymorphic Object and MultiObject fields using
  upstream's add-view sub-field prefill format: `?<name>__ct=<host_ct>&<name>__obj=<host_pk>`
  for polymorphic Object, and `?<name>__<host_app>__<host_model>=<host_pk>`
  for polymorphic MultiObject (the upstream form synthesizes one
  `DynamicModelMultipleChoiceField` per allowed target type; we fill only
  the one matching the host). The previous behaviour silently skipped the
  Add link for polymorphic fields.

### Changed

- **Minimum `netbox-custom-objects` is now 0.5.0.** Enforced at startup:
  `PluginConfig.ready()` probes for the `is_polymorphic` model field and
  raises `ImproperlyConfigured` with a clear upgrade message if the
  installed upstream is older. The check is behaviour-based (looks for the
  field directly, not a version string) so it remains correct against forks
  and pre-release tags. The pre-0.5 compat shims (`getattr` guards, module
  feature probes) have been removed from both `combined.py` and `typed.py`.

### Known Issues

- **Upstream Delete bug on `netbox-custom-objects == 0.5.0` (fixed in 0.5.1).**
  Deleting a Custom Object via the NetBox UI on 0.5.0 can raise
  `ValueError: Cannot query "...": Must be "Table<N>Model" instance.` from
  `CustomObjectDeleteView._get_dependent_objects`. The same crash also hits
  `CustomObjectBulkDeleteView` (NetBox's generic `BulkDeleteView.post()`
  iterates and calls `obj.delete()` per row — same code path), so
  **Bulk Delete is NOT a workaround** (2.3.0 README claim corrected).
  **Resolution:** upgrade upstream — PR
  [#501](https://github.com/netboxlabs/netbox-custom-objects/pull/501)
  (merged into `main` 2026-05-11) eliminates the entire bug class. As of
  the 2.4.0 release date, no `0.5.1` release tag exists yet; install from
  `main` (`pip install git+...@main`) or pin to `>=0.5.1` once tagged.
  Adjacent fixes for related drift paths (#504, #505, #510) also ship in
  `main` / `0.5.1`.
- **Polymorphic-MultiObject rows amplify the failure rate on 0.5.0.** Each
  polymorphic Object field adds a `GenericForeignKey` descriptor and each
  polymorphic MultiObject field adds a per-field through model; Django's
  collector traverses every related model during deletion, so polymorphic
  rows give the drift more chances to land. Plugin 2.4.0's discovery code
  walks these descriptors (the original goal of 2.4.0) and warms the
  cache enough that the upstream drift becomes deterministic rather than
  intermittent on 0.5.0.
- **Workarounds for installs that cannot upgrade yet:** `manage.py shell`
  direct delete (single-process model cache, no drift — see README) or
  `systemctl restart netbox` (clears the cache). No UI-side workaround
  exists for 0.5.0.
- **Root cause is upstream** (`netbox-custom-objects` dynamic-model caching).
  This plugin does not override delete or model caching and cannot fix it
  from its own code; PR #501 fixes it inside upstream's delete view.
- **Cosmetic post-fix issue on patched builds.** On builds containing
  PR #501 (upstream `main` / forthcoming 0.5.1), the delete-success toast
  for some dynamic models renders as `"Deleted <Type> <Type> None"` — the
  patched view calls `str(obj)` *after* the row's deletion, so the
  primary field returns `None`. Cosmetic only; the delete itself works.
  Worth a small upstream follow-up issue but not a blocker.

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

### Known Issues

- **Upstream `netbox_custom_objects` bug surfaced by the new Add button**:
  deleting a custom object **immediately** after creating it via the
  2.3.0 Add button (Create → row dropdown → Delete in the typed tab list)
  raises `ValueError: Cannot query "X": Must be "Table<N>Model" instance.`
  from `CustomObjectDeleteView._get_dependent_objects` (upstream
  `netbox_custom_objects/views.py:977`). The error fires only on the
  *first* delete GET in that flow; refreshing the list page before
  clicking Delete works around it, and Bulk Delete (different code path)
  is unaffected. Root cause is dynamic-model class identity drift across
  the Create → Delete request boundary in upstream code (the dynamic
  model class registry rebuilds during Create, but the immediately-
  following Delete request still holds a reference to the previous class
  in some scope). Tracked here as a documentation-only release note since
  the fix needs to land in `netbox_custom_objects`, not in this plugin.
  See README "Known Issues" section for user-facing workarounds.

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
