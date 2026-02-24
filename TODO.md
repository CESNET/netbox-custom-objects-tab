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
