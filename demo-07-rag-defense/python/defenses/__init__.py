"""Backwards-compatibility shim — 'defenses' was renamed to 'retrieval_defenses'.

Import from ``retrieval_defenses`` directly in new code.  This shim re-exports
all public names so that existing scripts referencing ``from defenses import …``
continue to work.
"""

import warnings as _warnings

_warnings.warn(
    "The 'defenses' package has been renamed to 'retrieval_defenses'. "
    "Update your imports to use 'from retrieval_defenses import …'.",
    DeprecationWarning,
    stacklevel=2,
)

from retrieval_defenses import document_validator, injection_detector, relevance_scorer, source_verifier  # noqa: F401, E402
from retrieval_defenses import *  # noqa: F401, F403, E402
