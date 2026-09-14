from django import template
from django.urls.exceptions import NoReverseMatch
from django.utils.module_loading import import_string
from netbox.registry import registry
from utilities.views import get_action_url

__all__ = ("plugin_extra_tabs",)

register = template.Library()

# NetBox auto-registers ObjectContactsView/ObjectJournalView/ObjectChangeLogView
# for every model that supports them (see netbox/models/features.py). On Custom
# Object detail pages we render those tabs as hardcoded <li> blocks instead,
# because upstream's CustomObjectContactsView/JournalView/ChangeLogView put the
# string "contacts"/"journal"/"changelog" in the template context as the
# active-tab marker, which `model_view_tabs` cannot match against its ViewTab
# object. Filtering them out here prevents duplicate, never-active tabs.
_HARDCODED_TAB_NAMES = frozenset({"contacts", "journal", "changelog"})


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

    active_tab = context.get("tab")
    # Upstream's CO journal/changelog/contacts/configcontext views put a plain str in
    # context["tab"]; only a ViewTab has label/weight (issue #19).
    active_key = (getattr(active_tab, "label", None), getattr(active_tab, "weight", None))

    for config in views:
        if config["name"] in _HARDCODED_TAB_NAMES:
            continue
        view = import_string(config["view"]) if type(config["view"]) is str else config["view"]
        if tab := getattr(view, "tab", None):
            if tab.permission and not user.has_perm(tab.permission):
                continue
            if attrs := tab.render(instance):
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
                        # Identity check first; fall back to (label, weight) because the
                        # generic CO-page URL (see views._inject_co_urls) is bound to the
                        # first model's view class, whose ViewTab instance differs from the
                        # registry entry for the page's actual model.
                        "is_active": active_tab == tab or active_key == (tab.label, tab.weight),
                    }
                )

    tabs = sorted(tabs, key=lambda x: x["weight"])
    return {"tabs": tabs}
