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
- Default configuration: `['dcim.*', 'ipam.*']`.
- Tab is hidden automatically (`hide_if_empty=True`) when no custom objects reference
  the viewed object.
