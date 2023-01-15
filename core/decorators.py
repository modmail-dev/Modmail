import warnings

from core.utils import trigger_typing as _trigger_typing


def trigger_typing(func):
    warnings.warn(
        "trigger_typing has been moved to core.utils.trigger_typing, this will be removed.",
        DeprecationWarning,
        stacklevel=2,
    )
    return _trigger_typing(func)
