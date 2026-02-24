"""
Populate sys.modules with lightweight mocks for all NetBox-specific packages
so the plugin's views.py can be imported without a live NetBox installation.

This file is loaded by pytest automatically before any test collection,
ensuring the mocks are in place before test modules import plugin code.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock


def _mock(dotted_name, **attrs):
    """
    Create a mock module at `dotted_name` and register it (and any missing
    parent packages) in sys.modules.  Does NOT overwrite already-present entries.
    """
    parts = dotted_name.split('.')
    # Ensure every parent package exists
    for i in range(1, len(parts)):
        parent = '.'.join(parts[:i])
        if parent not in sys.modules:
            sys.modules[parent] = ModuleType(parent)

    if dotted_name not in sys.modules:
        mod = ModuleType(dotted_name)
        sys.modules[dotted_name] = mod
    else:
        mod = sys.modules[dotted_name]

    for k, v in attrs.items():
        setattr(mod, k, v)

    # Attach as attribute on parent so `from parent import child` works
    if len(parts) > 1:
        parent_mod = sys.modules['.'.join(parts[:-1])]
        setattr(parent_mod, parts[-1], mod)

    return mod


# ---------------------------------------------------------------------------
# CustomFieldTypeChoices — must use real-looking string values so that the
# comparisons inside views.py work correctly when we set field.type = TYPE_OBJECT.
# ---------------------------------------------------------------------------
class _CustomFieldTypeChoices:
    TYPE_OBJECT = 'object'
    TYPE_MULTIOBJECT = 'multiobject'


# --- netbox.* ---
_mock('netbox')
_mock('netbox.plugins',
      PluginConfig=type('PluginConfig', (), {}),
      get_plugin_config=MagicMock(return_value=[]))

# --- extras.* ---
_mock('extras')
_mock('extras.choices', CustomFieldTypeChoices=_CustomFieldTypeChoices)

# --- utilities.* ---
_mock('utilities')
_mock('utilities.views', ViewTab=MagicMock(), register_model_view=MagicMock())
_mock('utilities.paginator', EnhancedPaginator=MagicMock(), get_paginate_count=MagicMock())

# --- netbox_custom_objects.* ---
_mock('netbox_custom_objects')
_mock('netbox_custom_objects.models', CustomObjectTypeField=MagicMock())
