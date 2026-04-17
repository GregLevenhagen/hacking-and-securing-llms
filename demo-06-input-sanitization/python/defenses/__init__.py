"""Backwards-compatibility shim — 'defenses' was renamed to 'input_defenses'.

Import from ``input_defenses`` directly in new code.  This shim re-exports
all public names so that existing scripts referencing ``from defenses import …``
continue to work.
"""

import warnings as _warnings

_warnings.warn(
    "The 'defenses' package has been renamed to 'input_defenses'. "
    "Update your imports to use 'from input_defenses import …'.",
    DeprecationWarning,
    stacklevel=2,
)

from input_defenses import regex_filter, input_sanitizer, llm_judge, llm_guard_scanner  # noqa: F401, E402
from input_defenses import *  # noqa: F401, F403, E402
