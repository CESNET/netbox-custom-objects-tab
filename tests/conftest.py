"""
Populate sys.modules with lightweight mocks for NetBox-specific packages.

This file is loaded by pytest before collection, ensuring mocks exist before
plugin modules are imported.
"""
import sys
from types import ModuleType
from unittest.mock import MagicMock

import django_tables2 as _tables2


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
    TYPE_TEXT = 'text'
    TYPE_LONGTEXT = 'longtext'


class _CustomFieldUIVisibleChoices:
    HIDDEN = 'hidden'


# --- netbox.* ---
_mock('netbox')
_mock('netbox.plugins',
      PluginConfig=type('PluginConfig', (), {}),
      get_plugin_config=MagicMock(return_value=[]))
_NetBoxModelFilterSetForm = type('NetBoxModelFilterSetForm', (), {})
_mock('netbox.forms', NetBoxModelFilterSetForm=_NetBoxModelFilterSetForm)
_mock('netbox.forms.mixins', SavedFiltersMixin=type('SavedFiltersMixin', (), {}))

# --- extras.* ---
_mock('extras')
_mock(
    'extras.choices',
    CustomFieldTypeChoices=_CustomFieldTypeChoices,
    CustomFieldUIVisibleChoices=_CustomFieldUIVisibleChoices,
)

# --- utilities.* ---
_mock('utilities')
_mock('utilities.views', ViewTab=MagicMock(), register_model_view=MagicMock())
_mock('utilities.paginator', EnhancedPaginator=MagicMock(), get_paginate_count=MagicMock())
_mock('utilities.htmx', htmx_partial=MagicMock())
_mock('utilities.forms')
_mock('utilities.forms.fields', TagFilterField=MagicMock())


class _FakeBaseTable(_tables2.Table):
    exempt_columns = ()

    class Meta:
        attrs = {}

    @property
    def name(self):
        return self.__class__.__name__

    def _get_columns(self, visible=True):
        return [
            (name, col.verbose_name)
            for name, col in self.columns.items()
            if col.visible == visible and name not in self.exempt_columns
        ]

    @property
    def available_columns(self):
        return sorted(self._get_columns(visible=False))

    @property
    def selected_columns(self):
        return self._get_columns(visible=True)

    def _set_columns(self, selected_columns):
        for name, column in self.columns.items():
            if column.name not in [*selected_columns, *self.exempt_columns]:
                self.columns.hide(column.name)
            else:
                self.columns.show(column.name)
        self.sequence = [
            *[c for c in selected_columns if c in self.columns.names()],
            *[c for c in self.columns.names() if c not in selected_columns],
        ]


_mock('netbox.tables', BaseTable=_FakeBaseTable)

# --- netbox_custom_objects.* ---
_mock('netbox_custom_objects')
_mock('netbox_custom_objects.models', CustomObjectTypeField=MagicMock())
_mock('netbox_custom_objects.field_types', FIELD_TYPE_CLASS={})
_mock('netbox_custom_objects.filtersets', get_filterset_class=MagicMock())
_CustomObjectTable = type('CustomObjectTable', (), {})
_mock('netbox_custom_objects.tables', CustomObjectTable=_CustomObjectTable)
