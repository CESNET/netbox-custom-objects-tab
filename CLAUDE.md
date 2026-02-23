# netbox_custom_objects_tab — Project Notes for Claude

## Purpose

Adds a **"Custom Objects"** tab to NetBox object detail pages (Device, Site, Rack, etc.),
showing Custom Object instances from the `netbox_custom_objects` plugin that reference
those objects via OBJECT or MULTIOBJECT typed fields.

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
from netbox_custom_objects.models import CustomObjectTypeField
from extras.choices import CustomFieldTypeChoices
from netbox.plugins import get_plugin_config
```

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

## TODO — Step-by-step Implementation Checklist

- [x] 1. Create `.gitignore`
- [x] 2. Create `pyproject.toml`
- [x] 3. Create `netbox_custom_objects_tab/__init__.py` (PluginConfig)
- [x] 4. Create `netbox_custom_objects_tab/views.py` (view factory + register_tabs)
- [x] 5. Create `netbox_custom_objects_tab/urls.py` (empty urlpatterns)
- [x] 6. Create `netbox_custom_objects_tab/templates/netbox_custom_objects_tab/custom_objects_tab.html`
- [x] 7. Create `README.md` and `CLAUDE.md`
- [ ] 8. Initialize git repo: `git init && git add -A && git commit -m "Initial plugin scaffold"`
- [ ] 9. Install into NetBox venv: `source /opt/netbox/venv/bin/activate && pip install -e /opt/custom_objects_additional_tab_plugin/`
- [ ] 10. Add plugin to NetBox `configuration.py` under `PLUGINS` and `PLUGINS_CONFIG`
- [ ] 11. Restart NetBox: `sudo systemctl restart netbox netbox-rq`
- [ ] 12. Test: create a Custom Object Type with a Device field, create a Custom Object
          instance referencing a Device, verify the "Custom Objects" tab appears on the
          Device detail page with badge count = 1

## Critical Reference Files

| File | Purpose |
|------|---------|
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/template_content.py` | Query pattern to replicate |
| `/opt/netbox/venv/lib/python3.12/site-packages/netbox_custom_objects/models.py` | `CustomObjectTypeField` model structure |
| `/opt/netbox/netbox/utilities/views.py` | `register_model_view` + `ViewTab` API |
| `/opt/netbox/netbox/netbox/views/generic/object_views.py` | How `base_template` context is constructed |

## Verification Steps

1. Activate venv and install: `pip install -e /opt/custom_objects_additional_tab_plugin/`
2. Add to NetBox config, restart
3. In NetBox UI: Customization → Custom Object Types → create a type with a Device field
4. Create a Custom Object instance that references an existing Device
5. Navigate to that Device's detail page — "Custom Objects" tab appears (badge = 1)
6. Click tab — table shows: type name | object link | field name
7. Delete the custom object — tab disappears
8. Check logs: `journalctl -u netbox` for any import errors
