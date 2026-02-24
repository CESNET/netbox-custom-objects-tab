# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
