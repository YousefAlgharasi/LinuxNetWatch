#!/usr/bin/env python3
"""Command-line entry point for netctl, invoked as root (directly, or via pkexec from the GUI).

Usage:
  netwatch-ctl block <app_name>
  netwatch-ctl unblock <app_name>
  netwatch-ctl limit <app_name> <kbps>
  netwatch-ctl unlimit <app_name>
  netwatch-ctl daily-cap <app_name> <mb>
  netwatch-ctl daily-cap-clear <app_name>
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from netwatch import netctl


def main():
    if os.geteuid() != 0:
        print("netwatch-ctl must run as root", file=sys.stderr)
        sys.exit(1)

    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    command = args[0]
    try:
        if command == "block" and len(args) == 2:
            netctl.set_blocked(args[1], True)
        elif command == "unblock" and len(args) == 2:
            netctl.set_blocked(args[1], False)
        elif command == "limit" and len(args) == 3:
            netctl.set_limit(args[1], int(args[2]))
        elif command == "unlimit" and len(args) == 2:
            netctl.set_limit(args[1], None)
        elif command == "daily-cap" and len(args) == 3:
            netctl.set_daily_cap(args[1], float(args[2]))
        elif command == "daily-cap-clear" and len(args) == 2:
            netctl.set_daily_cap(args[1], None)
        else:
            print(__doc__)
            sys.exit(1)
    except netctl.NetCtlError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
