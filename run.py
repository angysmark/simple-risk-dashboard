"""
Convenience launcher — equivalent to:

    python manage.py runserver 127.0.0.1:8050 --noreload

Using --noreload avoids Django's autoreloader, which would otherwise spawn
a file-watcher process that also calls AppConfig.ready() and unnecessarily
duplicates work.  The SimulationConfig._started guard prevents double thread
startup, but --noreload is cleaner and faster for this use case.

Usage
-----
    uv run python run.py [--host HOST] [--port PORT] [--reload]
"""

from __future__ import annotations

import argparse
import os
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Finalto Risk Management Dashboard",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", default=8050, type=int, help="Bind port")
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable Django's autoreloader (useful during development)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "fintech.settings")

    from django.core.management import execute_from_command_line

    addr = f"{args.host}:{args.port}"
    cmd = ["manage.py", "runserver", addr]
    if not args.reload:
        cmd.append("--noreload")

    print(f"Dashboard → http://{args.host}:{args.port}/")
    print("Press Ctrl-C to stop.\n")

    execute_from_command_line(cmd)


if __name__ == "__main__":
    main()
