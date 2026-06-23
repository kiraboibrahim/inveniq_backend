import os
import subprocess
import sys

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Starts the standalone Model Context Protocol (MCP) server."

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("Starting InvenIQ MCP Server..."))

        # Resolve path to server.py relative to the workspace root
        base_dir = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        server_path = os.path.join(base_dir, "mcp", "server.py")

        try:
            # Execute python mcp/server.py as a subprocess using the current python executable
            subprocess.run([sys.executable, server_path], check=True)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("\nMCP Server stopped."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error starting MCP Server: {e}"))
            sys.exit(1)
