"""Monorail - Session continuity daemon for AI coding tools."""

# Patch importlib.metadata for Python 3.9 compatibility BEFORE anything else
import sys
import os

# Suppress all stderr during patching and imports
import io
_original_stderr = sys.stderr
sys.stderr = io.StringIO()

try:
    # Patch packages_distributions if it doesn't exist (Python 3.9)
    import importlib.metadata
    if not hasattr(importlib.metadata, 'packages_distributions'):
        def _packages_distributions():
            """Stub for Python 3.9 compatibility."""
            return {}
        importlib.metadata.packages_distributions = _packages_distributions

    # Also suppress warnings
    import warnings
    os.environ["GRPC_VERBOSITY"] = "ERROR"
    os.environ["GRPC_TRACE"] = ""
    warnings.filterwarnings("ignore")

finally:
    sys.stderr = _original_stderr

__version__ = "0.1.0"
