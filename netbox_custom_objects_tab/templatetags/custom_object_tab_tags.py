from django import template
from django.urls.exceptions import NoReverseMatch
from django.utils.module_loading import import_string
from netbox.registry import registry
from utilities.views import get_action_url

__all__ = ("plugin_extra_tabs",)

register = template.Library()

# NetBox's `extras` framework auto-registers ObjectJournalView/ObjectChangeLogView
# for every model that supports them (see netbox/models/features.py). On Custom
# Object detail pages we render those two tabs as hardcoded <li> blocks instead,
# because upstream's CustomObjectJournalView/CustomObjectChangeLogView put the
# string "journal"/"changelog" in the template context as the active-tab marker,
# which `model_view_tabs` cannot match against its ViewTab object. Filtering them
# out here prevents duplicate, never-active tabs from being rendered.
_HARDCODED_TAB_NAMES = frozenset({"journal", "changelog"})


@register.inclusion_tag("tabs/model_view_tabs.html", takes_context=True)
def plugin_extra_tabs(context, instance):
    """
    Render registered model-view tabs for `instance`, excluding tabs that the
    Custom Object detail template already renders by hand (Journal, Changelog).
    """
    app_label = instance._meta.app_label
    model_name = instance._meta.model_name
    user = context["request"].user
    tabs = []

    try:
        views = registry["views"][app_label][model_name]
    except KeyError:
        views = []

    for config in views:
        if config["name"] in _HARDCODED_TAB_NAMES:
            continue
        view = import_string(config["view"]) if type(config["view"]) is str else config["view"]
        if tab := getattr(view, "tab", None):
            if tab.permission and not user.has_perm(tab.permission):
                continue
            if attrs := tab.render(instance):
                active_tab = context.get("tab")
                try:
                    url = get_action_url(instance, action=config["name"], kwargs={"pk": instance.pk})
                except NoReverseMatch:
                    continue
                tabs.append(
                    {
                        "name": config["name"],
                        "url": url,
                        "label": attrs["label"],
                        "badge": attrs["badge"],
                        "weight": attrs["weight"],
                        "is_active": active_tab and active_tab == tab,
                    }
                )

    tabs = sorted(tabs, key=lambda x: x["weight"])
    return {"tabs": tabs}
