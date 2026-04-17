"""OTel telemetry shutdown and flush utilities.

MUST be called in short-lived scripts to ensure all buffered spans
are exported before the process exits. BatchSpanProcessor buffers
spans and exports them in batches — without flushing, the last
batch may be lost on process exit.
"""

import logging

__all__ = ["flush_telemetry"]

logger = logging.getLogger(__name__)


def flush_telemetry(timeout_millis: int = 5000) -> bool:
    """Flush all buffered OTel spans to the configured exporter.

    Args:
        timeout_millis: Maximum time to wait for flush in milliseconds.

    Returns:
        True if flush succeeded, False if skipped or failed.
    """
    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()

        # TracerProvider has force_flush; the proxy provider does not
        if hasattr(provider, "force_flush"):
            result = provider.force_flush(timeout_millis=timeout_millis)
            logger.debug("OTel flush completed (result=%s)", result)
            return bool(result)
        else:
            logger.debug("OTel provider has no force_flush method, skipping")
            return False

    except ImportError:
        logger.debug("OTel packages not installed, skipping flush")
        return False
    except Exception as e:
        logger.warning("OTel flush failed: %s", e)
        return False
