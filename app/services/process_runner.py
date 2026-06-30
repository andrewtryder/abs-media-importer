"""Process runner helper: non-blocking subprocess streaming with responsive cancellation."""

from __future__ import annotations

import contextlib
import logging
import queue
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessResult:
    returncode: int
    cancelled: bool = False
    timed_out: bool = False
    error: str | None = None


def run_streaming_process(
    cmd: list[str],
    log_line: Callable[[str], None],
    check_cancelled: Callable[[], bool] | None = None,
    on_line: Callable[[str], None] | None = None,
    cancel_check_interval: float = 1.0,
    terminate_timeout: float = 5.0,
) -> ProcessResult:
    """
    Run *cmd* via subprocess, reading stdout/stderr non-blockingly using a background thread.
    Checks for cancellation periodically on *cancel_check_interval*.
    """
    logger.debug("Starting subprocess: %s", cmd)
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        err_msg = f"Binary not found: {exc}"
        log_line(f"ERROR: {err_msg}")
        return ProcessResult(returncode=-1, error=err_msg)

    q: queue.Queue[str] = queue.Queue()

    def reader(stream: object, q: queue.Queue[str]) -> None:
        try:
            for line in stream:  # type: ignore[attr-defined]
                q.put(line)
        except Exception as exc:
            logger.error("Error reading subprocess pipe: %s", exc)
        finally:
            with contextlib.suppress(Exception):
                stream.close()  # type: ignore[attr-defined]

    t = threading.Thread(target=reader, args=(proc.stdout, q), daemon=True)
    t.start()

    cancelled = False

    while True:
        ret = proc.poll()

        # Drain the queue non-blockingly
        while True:
            try:
                line = q.get_nowait()
                line_str = line.rstrip()
                log_line(line_str)
                if on_line:
                    on_line(line_str)
            except queue.Empty:
                break

        if ret is not None:
            # Subprocess finished
            break

        # Check cancellation
        if check_cancelled and check_cancelled():
            cancelled = True
            log_line("Cancellation requested. Terminating subprocess...")
            proc.terminate()

            # Wait for graceful exit
            start_wait = time.time()
            while time.time() - start_wait < terminate_timeout:
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            else:
                log_line(f"Subprocess did not exit after {terminate_timeout}s. Killing...")
                proc.kill()
                proc.wait()

            # Drain any remaining lines
            while True:
                try:
                    line = q.get_nowait()
                    log_line(line.rstrip())
                except queue.Empty:
                    break

            log_line("Subprocess terminated.")
            return ProcessResult(returncode=proc.returncode or -9, cancelled=True)

        # Wait for the next check interval
        time.sleep(cancel_check_interval)

    return ProcessResult(returncode=proc.returncode, cancelled=cancelled)
