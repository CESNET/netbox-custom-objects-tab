import logging

from django.apps import apps
from django.http import Http404
from django.shortcuts import get_object_or_404
from netbox.plugins import get_plugin_config

from .typed import _CUSTOM_OBJECTS_APP, register_typed_tabs

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


def _make_co_dispatcher(action_name):
    """
    Return a view function serving ``<str:custom_object_type>/<int:pk>/<path>/`` for
    every Custom Object host type.

    One typed-tab action (``custom_objects_<slug>``) may be registered on several host
    CO models (Type A referencing both Type B and Type C). The URL pattern is shared, so
    it cannot be bound to one model's view class: we resolve the host model from the
    slug per request and dispatch to the view registered for exactly that model. That
    also puts the host's own ``ViewTab`` in the template context, which is what
    upstream's ``{% plugin_extra_tabs %}`` compares against to mark the tab active.
    """
    from netbox.registry import registry

    def dispatch(request, custom_object_type, pk, **kwargs):
        from netbox_custom_objects.models import CustomObjectType

        cot = get_object_or_404(CustomObjectType, slug=custom_object_type)
        model_name = cot.get_model()._meta.model_name
        entries = registry["views"].get(_CUSTOM_OBJECTS_APP, {}).get(model_name, [])
        view_cls = next((e["view"] for e in entries if e["name"] == action_name), None)
        if view_cls is None:
            raise Http404(f"No '{action_name}' tab registered for {custom_object_type}")
        return view_cls.as_view()(request, custom_object_type=custom_object_type, pk=pk, **kwargs)

    dispatch.__name__ = f"{action_name}_co_dispatch"
    return dispatch


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
    so each typed tab gets ``customobject_custom_objects_{slug}``.
    """
    try:
        import netbox_custom_objects.urls as co_urls
        from django.urls import path as url_path
        from netbox.registry import registry
    except ImportError:
        return

    # Action names of the typed-tab views we registered on CO dynamic models.
    action_names = set()
    for model_name, view_entries in registry["views"].get(_CUSTOM_OBJECTS_APP, {}).items():
        if not model_name.startswith("table"):
            continue
        for entry in view_entries:
            if entry["name"].startswith("custom_objects_"):
                action_names.add((entry["name"], entry["path"]))

    existing_names = {p.name for p in co_urls.urlpatterns if hasattr(p, "name") and p.name}
    for action_name, url_path_str in sorted(action_names):
        url_name = f"customobject_{action_name}"
        if url_name in existing_names:
            continue
        full_path = f"<str:custom_object_type>/<int:pk>/{url_path_str}/"
        co_urls.urlpatterns.append(url_path(full_path, _make_co_dispatcher(action_name), name=url_name))
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
    Read plugin config and register the typed (per Custom Object Type) tabs.
    Called from AppConfig.ready().

    All registration must happen synchronously here: NetBox builds each model's
    URLconf (via ``get_model_urls()``) on the first ``resolve()`` call, snapshotting
    ``registry['views']`` at that moment.  Anything added to the registry after the
    URLconf is built has no URL pattern.  Likewise, ``_inject_co_urls()`` mutates
    ``netbox_custom_objects.urls.urlpatterns`` and must run before any URL resolver
    populates its lookup cache against that list.

    Earlier versions deferred typed-tab registration to the first HTTP request
    (commit 5bf09c3, PR #4) to silence DB-access warnings from Django and
    netbox_branching.  That broke typed-tab URL routing entirely.  See 2.3.0 notes.

    The ``OperationalError`` / ``ProgrammingError`` safety net inside
    ``register_typed_tabs`` covers the ``manage.py migrate`` / fresh-DB case.
    """
    try:
        typed_labels = get_plugin_config("netbox_custom_objects_tab", "typed_models")
        typed_weight = get_plugin_config("netbox_custom_objects_tab", "typed_weight")
    except Exception:
        logger.exception("Could not read netbox_custom_objects_tab plugin config")
        return

    if not typed_labels:
        return

    typed_models = _resolve_model_labels(typed_labels)
    register_typed_tabs(typed_models, typed_weight)

    if any(m._meta.app_label == _CUSTOM_OBJECTS_APP for m in typed_models):
        _inject_co_urls()

    _deduplicate_registry()
