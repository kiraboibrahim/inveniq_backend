import os
import selectors
import signal
import subprocess
import sys

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# (name, manage.py subcommand args) for the services that run via manage.py
MANAGE_SERVICES = {
    "django": ["runserver"],
    "huey": ["run_huey"],
}


class Command(BaseCommand):
    help = "Starts Django development server, Huey task worker, and MCP server concurrently."

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
            help="Override path to the MCP server script (default: <BASE_DIR>/mcp/server.py)",
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
            if "django" not in skip or "huey" not in skip:
                if not os.path.isfile(required):
                    raise CommandError(f"manage.py not found at {required}")
        if "mcp" not in skip and not os.path.isfile(mcp_path):
            raise CommandError(f"MCP server script not found at {mcp_path}")

        self.stdout.write(self.style.SUCCESS("Starting InvenIQ Dev Environment..."))

        processes = []
        sel = selectors.DefaultSelector()

        # popen_kwargs spawns each child in its own process group (POSIX) so we
        # can signal the whole subtree it spawns, not just the direct child.
        popen_kwargs = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        if os.name == "posix":
            popen_kwargs["start_new_session"] = True

        try:
            for name, cmd in specs:
                try:
                    proc = subprocess.Popen(cmd, **popen_kwargs)
                except FileNotFoundError as exc:
                    raise CommandError(f"Failed to start {name}: {exc}")
                processes.append([name, proc])
                if proc.stdout:
                    os.set_blocking(proc.stdout.fileno(), False)
                    sel.register(proc.stdout, selectors.EVENT_READ, (name, proc))

            self.stdout.write(
                self.style.SUCCESS(
                    "All services started! Logs are multiplexed below. Press Ctrl+C to stop.\n"
                )
            )

            self._run_loop(sel, processes)

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nStopping all services..."))
        finally:
            sel.close()
            self._shutdown(processes)
            self.stdout.write(self.style.SUCCESS("All services stopped successfully."))

    def _run_loop(self, sel, processes):
        while True:
            for name, proc in processes:
                if proc.poll() is not None:
                    self.stdout.write(
                        self.style.ERROR(
                            f"\n{name} exited unexpectedly with code {proc.returncode}"
                        )
                    )
                    raise KeyboardInterrupt

            events = sel.select(timeout=0.1)
            for key, _mask in events:
                name, proc = key.data
                try:
                    line = key.fileobj.readline()
                except (ValueError, OSError):
                    # stream closed underneath us
                    sel.unregister(key.fileobj)
                    continue

                if line:
                    self._write_line(name, line)
                elif proc.poll() is not None:
                    # process is gone and stream is drained, stop polling it
                    sel.unregister(key.fileobj)

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

        for name, proc in processes:
            if proc.poll() is None:
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    pass

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
