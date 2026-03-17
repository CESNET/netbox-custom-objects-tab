"""
Prepend our templates directory to Django's filesystem loader search path.

netbox_custom_objects/customobject.html has a hardcoded {% block tabs %} that
does not call {% model_view_tabs object %}.  We ship an override that adds the
call.  Because our app comes after netbox_custom_objects in INSTALLED_APPS, the
app_directories loader would find the original first.  Prepending to engine.dirs
ensures our override is found first by the filesystem loader, before any templates
are cached.
"""

import logging
import os

logger = logging.getLogger("netbox_custom_objects_tab")

_TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "templates")


def install():
    try:
        from django.template import engines

        engine = engines["django"].engine

        # engine.dirs is the filesystem loader's search path.
        # Prepending here ensures our override is found before the original in
        # netbox_custom_objects (which comes earlier in INSTALLED_APPS).
        if _TEMPLATES_DIR not in engine.dirs:
            engine.dirs = [_TEMPLATES_DIR] + list(engine.dirs)
            logger.debug("prepended templates dir to engine.dirs")
    except Exception:
        logger.exception("netbox_custom_objects_tab: could not install template override")
