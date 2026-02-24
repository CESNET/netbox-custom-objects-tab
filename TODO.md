# TODO — netbox_custom_objects_tab backlog

## Truncation count for MULTIOBJECT values

Currently MULTIOBJECT values truncate at 3 items with a bare `…`.

**Goal:** show `obj1, obj2, obj3 and N more` where N is the actual remaining count.

**Implementation notes:**
- `_get_field_value` already fetches up to MAX+1 items to detect overflow.
- To compute N, either:
  - Add a `.count()` call on the queryset before slicing, or
  - Fetch all items into a list and slice in Python (simpler, acceptable for typical M2M sizes).
- Pass the full count alongside the truncated list in the row tuple, then use it in the template.

---

## Configurable columns

Allow operators to hide columns via `PLUGINS_CONFIG`.

**Proposed setting:**
```python
PLUGINS_CONFIG = {
    'netbox_custom_objects_tab': {
        'columns': ['type', 'object', 'value', 'field', 'actions'],  # default: all
    }
}
```

**Implementation notes:**
- View builds a `visible_columns` set from config, falling back to the full set.
- Pass `visible_columns` in the template context.
- Each `<th>` / `<td>` is wrapped in `{% if 'colname' in visible_columns %}`.
- Removing `'actions'` hides both Edit and Delete buttons.
