"""Simple resource tracking for DoS attack demonstrations.

Tracks wall-clock time, token counts, and iteration counts to
quantify the impact of model denial-of-service attacks.
"""

import time
from typing import Any


class ResourceMonitor:
    """Tracks resource consumption during a DoS attack demonstration.

    Usage::

        monitor = ResourceMonitor()
        monitor.start()
        # ... run attack ...
        monitor.add_tokens(1500)
        monitor.increment_iterations()
        monitor.stop()
        print(monitor.format_report())
    """

    def __init__(self) -> None:
        self._start_time: float | None = None
        self._end_time: float | None = None
        self._token_count: int = 0
        self._iteration_count: int = 0
        self._running: bool = False

    def start(self) -> None:
        """Begin tracking resources."""
        self._start_time = time.monotonic()
        self._end_time = None
        self._token_count = 0
        self._iteration_count = 0
        self._running = True

    def check(self) -> dict[str, Any]:
        """Return a snapshot of current resource usage.

        Returns:
            Dict with elapsed_seconds, token_count, iteration_count, running.
        """
        elapsed = 0.0
        if self._start_time is not None:
            end = self._end_time if self._end_time is not None else time.monotonic()
            elapsed = end - self._start_time

        return {
            "elapsed_seconds": round(elapsed, 3),
            "token_count": self._token_count,
            "iteration_count": self._iteration_count,
            "running": self._running,
        }

    def stop(self) -> None:
        """Stop tracking resources."""
        if self._running and self._start_time is not None:
            self._end_time = time.monotonic()
        self._running = False

    def add_tokens(self, count: int) -> None:
        """Add to the cumulative token count."""
        self._token_count += count

    def increment_iterations(self, count: int = 1) -> None:
        """Increment the iteration counter."""
        self._iteration_count += count

    @property
    def elapsed_seconds(self) -> float:
        """Return elapsed wall-clock time in seconds."""
        return self.check()["elapsed_seconds"]

    @property
    def token_count(self) -> int:
        """Return cumulative token count."""
        return self._token_count

    @property
    def iteration_count(self) -> int:
        """Return cumulative iteration count."""
        return self._iteration_count

    def format_report(self) -> str:
        """Return a human-readable summary of resource consumption.

        Returns:
            Multi-line string suitable for terminal or log output.
        """
        snapshot = self.check()
        elapsed = snapshot["elapsed_seconds"]
        tokens = snapshot["token_count"]
        iterations = snapshot["iteration_count"]
        status = "RUNNING" if snapshot["running"] else "STOPPED"

        lines = [
            f"=== Resource Monitor Report [{status}] ===",
            f"  Wall-clock time : {elapsed:.3f}s",
            f"  Token count     : {tokens:,}",
            f"  Iteration count : {iterations}",
        ]

        if elapsed > 0 and tokens > 0:
            tokens_per_sec = tokens / elapsed
            lines.append(f"  Tokens/sec      : {tokens_per_sec:,.1f}")

        lines.append("=" * 42)
        return "\n".join(lines)
