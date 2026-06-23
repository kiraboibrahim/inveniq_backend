import subprocess  # nosec
import sys
import threading
import time
from dataclasses import dataclass, field

from django.core.management.base import BaseCommand

MAX_RESTARTS = 5
BACKOFF_BASE = 2
BACKOFF_CAP = 30


@dataclass
class ManagedProcess:
    name: str
    cmd: list[str]
    proc: subprocess.Popen | None = None
    restart_count: int = 0
    _log_thread: threading.Thread | None = field(default=None, repr=False)

    def backoff(self) -> float:
        return min(BACKOFF_BASE**self.restart_count, BACKOFF_CAP)


class Command(BaseCommand):
    help = "Starts the Django dev server and Huey worker, with auto-restart."

    def add_arguments(self, parser):
        parser.add_argument("--port", default="8000")
        parser.add_argument(
            "--no-restart",
            action="store_true",
            help="Exit immediately when any process dies instead of restarting.",
        )

    def handle(self, *args, **options):
        port = options["port"]
        auto_restart = not options["no_restart"]

        managed = [
            ManagedProcess("server", [sys.executable, "manage.py", "runserver", port]),
            ManagedProcess("huey", [sys.executable, "manage.py", "run_huey"]),
        ]

        self.stdout.write(self.style.SUCCESS("Starting dev server and Huey worker..."))

        for mp in managed:
            self._start(mp)

        try:
            while True:
                time.sleep(1)
                for mp in managed:
                    if mp.proc.poll() is None:
                        continue

                    rc = mp.proc.returncode
                    if not auto_restart or mp.restart_count >= MAX_RESTARTS:
                        self.stdout.write(
                            self.style.ERROR(
                                f"[{mp.name}] exited (rc={rc}). "
                                f"{'Restart limit reached.' if auto_restart else 'Auto-restart disabled.'}"
                            )
                        )
                        return

                    wait = mp.backoff()
                    mp.restart_count += 1
                    self.stdout.write(
                        self.style.WARNING(
                            f"[{mp.name}] exited (rc={rc}). "
                            f"Restarting in {wait:.0f}s "
                            f"(attempt {mp.restart_count}/{MAX_RESTARTS})..."
                        )
                    )
                    time.sleep(wait)
                    self._start(mp)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nShutting down..."))

        finally:
            self._shutdown(managed)

    def _start(self, mp: ManagedProcess):
        mp.proc = subprocess.Popen(  # nosec
            mp.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        mp._log_thread = threading.Thread(
            target=self._stream_output,
            args=(mp.proc, mp.name),
            daemon=True,
        )
        mp._log_thread.start()
        self.stdout.write(
            self.style.SUCCESS(f"[{mp.name}] started (pid={mp.proc.pid})")
        )

    def _stream_output(self, proc: subprocess.Popen, label: str):
        prefix = f"[{label}] "
        try:
            for line in proc.stdout:
                self.stdout.write(prefix + line.rstrip())
        except ValueError:
            pass

    def _shutdown(self, managed: list[ManagedProcess]):
        still_running = []
        for mp in managed:
            if mp.proc and mp.proc.poll() is None:
                mp.proc.terminate()
                still_running.append(mp.proc)

        deadline = time.time() + 5
        while still_running and time.time() < deadline:
            still_running = [p for p in still_running if p.poll() is None]
            time.sleep(0.2)

        for proc in still_running:
            proc.kill()

        for mp in managed:
            if mp._log_thread and mp._log_thread.is_alive():
                mp._log_thread.join(timeout=2)

        self.stdout.write(self.style.SUCCESS("All processes stopped."))
