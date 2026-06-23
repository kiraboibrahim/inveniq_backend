import contextlib
import os
import queue
import signal
import subprocess  # nosec B404
import sys
import threading

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# (name, manage.py subcommand args) for the services that run via manage.py
MANAGE_SERVICES = {
    "django": ["runserver"],
    "huey": ["run_huey"],
}


class Command(BaseCommand):
    help = (
        "Starts Django development server, Huey task worker, "
        "and MCP server concurrently."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--addrport",
            default="0.0.0.0:8000",
            help="Address/port for runserver (default: 0.0.0.0:8000)",
        )
        parser.add_argument(
            "--skip",
            action="append",
            default=[],
            choices=["django", "huey", "mcp"],
            help="Service(s) to skip. Can be passed multiple times.",
        )
        parser.add_argument(
            "--mcp-path",
            default=None,
            help=(
                "Override path to the MCP server script "
                "(default: <BASE_DIR>/mcp/server.py)"
            ),
        )

    def handle(self, *args, **options):
        base_dir = str(settings.BASE_DIR)
        manage_py = os.path.join(base_dir, "manage.py")
        mcp_path = options["mcp_path"] or os.path.join(base_dir, "mcp", "server.py")
        skip = set(options["skip"])

        specs = []
        if "django" not in skip:
            specs.append(
                (
                    "Django",
                    [sys.executable, manage_py, "runserver", options["addrport"]],
                )
            )
        if "huey" not in skip:
            specs.append(("Huey", [sys.executable, manage_py, "run_huey"]))
        if "mcp" not in skip:
            specs.append(("MCP", [sys.executable, mcp_path]))

        if not specs:
            raise CommandError("Nothing to start, every service was skipped.")

        for required in (manage_py,):
            if ("django" not in skip or "huey" not in skip) and not os.path.isfile(
                required
            ):
                raise CommandError(f"manage.py not found at {required}")
        if "mcp" not in skip and not os.path.isfile(mcp_path):
            raise CommandError(f"MCP server script not found at {mcp_path}")

        self.stdout.write(self.style.SUCCESS("Starting InvenIQ Dev Environment..."))

        processes = []
        out_queue = queue.Queue()

        # popen_kwargs spawns each child in its own process group (POSIX) so we
        # can signal the whole subtree it spawns, not just the direct child.
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "bufsize": 1,
        }
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True

        try:
            for name, cmd in specs:
                try:
                    proc = subprocess.Popen(cmd, **popen_kwargs)  # nosec B603
                except FileNotFoundError as exc:
                    raise CommandError(f"Failed to start {name}: {exc}") from exc
                processes.append([name, proc])
                if proc.stdout:
                    t = threading.Thread(
                        target=self._reader_thread,
                        args=(name, proc, out_queue),
                        daemon=True,
                    )
                    t.start()

            self.stdout.write(
                self.style.SUCCESS(
                    "All services started! Logs are multiplexed below. "
                    "Press Ctrl+C to stop.\n"
                )
            )

            self._run_loop(out_queue, processes)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nStopping all services..."))
        finally:
            self._shutdown(processes)
            self.stdout.write(self.style.SUCCESS("All services stopped successfully."))

    def _reader_thread(self, name, proc, out_queue):
        with contextlib.suppress(Exception):
            for line in iter(proc.stdout.readline, ""):
                if line:
                    out_queue.put((name, line))
        with contextlib.suppress(Exception):
            proc.stdout.close()

    def _run_loop(self, out_queue, processes):
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    while not out_queue.empty():
                        with contextlib.suppress(queue.Empty):
                            q_name, line = out_queue.get_nowait()
                            self._write_line(q_name, line)
                    self.stdout.write(
                        self.style.ERROR(
                            f"\n{name} exited unexpectedly with code {proc.returncode}"
                        )
                    )
                    raise KeyboardInterrupt

            try:
                name, line = out_queue.get(timeout=0.1)
                self._write_line(name, line)
            except queue.Empty:
                continue

    def _write_line(self, name, line):
        if name == "Django":
            prefix = self.style.SUCCESS(f"[{name}]")
        elif name == "Huey":
            prefix = self.style.WARNING(f"[{name}]")
        else:
            prefix = self.style.NOTICE(f"[{name}]")
        self.stdout.write(f"{prefix} {line.rstrip()}")
        self.stdout.flush()

    def _shutdown(self, processes):
        # Phase 1: ask nicely (SIGINT/terminate to the whole process group)
        for name, proc in processes:
            if proc.poll() is None:
                self.stdout.write(f"Stopping {name}...")
                self._signal(
                    proc, signal.SIGINT if os.name == "posix" else signal.SIGTERM
                )

        for _, proc in processes:
            if proc.poll() is None:
                with contextlib.suppress(subprocess.TimeoutExpired):
                    proc.wait(timeout=5)

        # Phase 2: force-kill anything still alive
        for name, proc in processes:
            if proc.poll() is None:
                self.stdout.write(f"Force-killing {name}...")
                self._signal(
                    proc, signal.SIGKILL if os.name == "posix" else signal.SIGTERM
                )
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self.stdout.write(
                        self.style.ERROR(f"{name} did not exit, giving up.")
                    )

            if proc.stdout:
                proc.stdout.close()

    def _signal(self, proc, sig):
        try:
            if os.name == "posix":
                # negative pid targets the whole process group
                os.killpg(proc.pid, sig)
            else:
                proc.send_signal(sig)
        except ProcessLookupError:
            pass
        except Exception as e:
            self.stdout.write(f"Error signaling pid {proc.pid}: {e}")
