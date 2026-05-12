import logging

from django.apps import apps
from netbox.plugins import get_plugin_config

from ._co_common import _CUSTOM_OBJECTS_APP
from .combined import register_combined_tabs
from .typed import register_typed_tabs

logger = logging.getLogger("netbox_custom_objects_tab")


def _resolve_dynamic_custom_object_models():
    """
    Return all dynamically-generated Custom Object model classes from the Django app registry.

    netbox_custom_objects.ready() runs before ours (it has a lower INSTALLED_APPS index) and
    registers all dynamic per-type models.  We read them directly from the registry rather than
    calling CustomObjectType.get_model() again — each get_model() call that misses the cache
    re-registers journal/changelog views, producing duplicate tabs.

    A restart is required whenever a new Custom Object Type is added.
    """
    try:
        from netbox_custom_objects.models import CustomObject
    except ImportError:
        logger.warning("netbox_custom_objects plugin not installed — skipping")
        return []

    try:
        app_config = apps.get_app_config(_CUSTOM_OBJECTS_APP)
    except LookupError:
        logger.warning("netbox_custom_objects app not found — skipping")
        return []

    # Filter to dynamic CO models only (subclasses of CustomObject, not CustomObject itself).
    return [m for m in app_config.get_models() if issubclass(m, CustomObject) and m is not CustomObject]


def _resolve_model_labels(labels):
    """
    Resolve a list of model label strings (e.g. ["dcim.*", "ipam.device"])
    into a deduplicated list of Django model classes.

    The special wildcard ``netbox_custom_objects.*`` resolves to all dynamically-
    generated Custom Object models (one per CustomObjectType row).  A NetBox
    restart is required whenever a new Custom Object Type is added.
    """
    seen = set()
    result = []
    for label in labels:
        label = label.lower()
        if label.endswith(".*"):
            app_label = label[:-2]
            # Special-case: dynamic Custom Object models are not discoverable via
            # the standard app registry wildcard — enumerate them explicitly.
            if app_label == _CUSTOM_OBJECTS_APP:
                model_classes = _resolve_dynamic_custom_object_models()
            else:
                try:
                    model_classes = list(apps.get_app_config(app_label).get_models())
                except LookupError:
                    logger.warning(
                        "could not find app %r — skipping",
                        app_label,
                    )
                    continue
        else:
            try:
                app_label, model_name = label.split(".", 1)
                model_classes = [apps.get_model(app_label, model_name)]
            except (ValueError, LookupError):
                logger.warning(
                    "could not find model %r — skipping",
                    label,
                )
                continue

        for model_class in model_classes:
            key = (model_class._meta.app_label, model_class._meta.model_name)
            if key not in seen:
                seen.add(key)
                result.append(model_class)

    return result


def _inject_co_urls():
    """
    Inject URL patterns for our tab views into netbox_custom_objects.urls.

    The netbox_custom_objects plugin serves all custom object detail pages through a
    single generic view at ``<str:custom_object_type>/<int:pk>/``.  It never calls
    ``get_model_urls()`` for dynamic models, so our registered views have no
    corresponding URL patterns.  We add them here at ready() time — before Django
    loads the URL conf on the first request.

    The URL names follow CustomObject._get_viewname():
      ``plugins:netbox_custom_objects:customobject_{action}``
    which means we need names like ``customobject_custom_objects`` and
    ``customobject_custom_objects_{slug}`` inside netbox_custom_objects.urls.
    """
    try:
        import netbox_custom_objects.urls as co_urls
        from django.urls import path as url_path
        from netbox.registry import registry
    except ImportError:
        return

    co_app = _CUSTOM_OBJECTS_APP
    # Collect all tab view classes our plugin registered for CO dynamic models
    # from the global registry, keyed by their action name.
    co_views_by_name = {}  # action_name -> view_class
    for model_name, view_entries in registry["views"].get(co_app, {}).items():
        if not model_name.startswith("table"):
            continue
        for entry in view_entries:
            name = entry["name"]
            view_cls = entry["view"]
            # Only inject views we registered (combined / typed tab views)
            if name.startswith("custom_objects") and name not in co_views_by_name:
                co_views_by_name[name] = (entry["path"], view_cls)

    existing_names = {p.name for p in co_urls.urlpatterns if hasattr(p, "name") and p.name}
    for action_name, (url_path_str, view_cls) in co_views_by_name.items():
        url_name = f"customobject_{action_name}"
        if url_name in existing_names:
            continue
        full_path = f"<str:custom_object_type>/<int:pk>/{url_path_str}/"
        co_urls.urlpatterns.append(url_path(full_path, view_cls.as_view(), name=url_name))
        logger.debug("injected URL pattern '%s'", url_name)


def _deduplicate_registry():
    """
    Remove duplicate view registrations from registry['views'].

    netbox_custom_objects calls get_model() multiple times during startup; each call
    that generates a new model instance re-registers journal/changelog views, producing
    duplicate tabs.  Since we run after netbox_custom_objects in INSTALLED_APPS, we can
    clean up the registry here by keeping only the first occurrence of each view name
    per model.
    """
    from netbox.registry import registry

    for app_label, model_map in registry["views"].items():
        for model_name, entries in model_map.items():
            seen = set()
            deduped = []
            for entry in entries:
                key = entry["name"]
                if key not in seen:
                    seen.add(key)
                    deduped.append(entry)
            if len(deduped) < len(entries):
                logger.debug(
                    "removed %d duplicate registry entries for %s.%s",
                    len(entries) - len(deduped),
                    app_label,
                    model_name,
                )
                model_map[model_name] = deduped


def register_tabs():
    """
    Read plugin config and register both combined and typed tabs.
    Called from AppConfig.ready().

    All registration must happen synchronously here: NetBox builds each model's
    URLconf (via ``get_model_urls()``) on the first ``resolve()`` call, snapshotting
    ``registry['views']`` at that moment.  Anything added to the registry after the
    URLconf is built has no URL pattern.  Likewise, ``_inject_co_urls()`` mutates
    ``netbox_custom_objects.urls.urlpatterns`` and must run before any URL resolver
    populates its lookup cache against that list.

    Earlier versions deferred typed-tab registration to the first HTTP request
    (commit 5bf09c3, PR #4) to silence DB-access warnings from Django and
    netbox_branching.  That broke typed-tab URL routing entirely — the Add-button
    feature in 2.3.0 was never reachable on a deployment.  See 2.3.0 release notes.

    The ``OperationalError`` / ``ProgrammingError`` safety net inside
    ``register_typed_tabs`` covers the ``manage.py migrate`` / fresh-DB case.
    """
    try:
        combined_labels = get_plugin_config("netbox_custom_objects_tab", "combined_models")
        combined_label = get_plugin_config("netbox_custom_objects_tab", "combined_label")
        combined_weight = get_plugin_config("netbox_custom_objects_tab", "combined_weight")
        typed_labels = get_plugin_config("netbox_custom_objects_tab", "typed_models")
        typed_weight = get_plugin_config("netbox_custom_objects_tab", "typed_weight")
    except Exception:
        logger.exception("Could not read netbox_custom_objects_tab plugin config")
        return

    combined_models = []
    if combined_labels:
        combined_models = _resolve_model_labels(combined_labels)
        register_combined_tabs(combined_models, combined_label, combined_weight)

    typed_models = []
    if typed_labels:
        typed_models = _resolve_model_labels(typed_labels)
        register_typed_tabs(typed_models, typed_weight)

    if any(m._meta.app_label == _CUSTOM_OBJECTS_APP for m in combined_models + typed_models):
        _inject_co_urls()

    _deduplicate_registry()
