#!/usr/bin/env python3
"""Credential sanity check utility for P-Art."""

from __future__ import annotations

import sys

from health_checks import run_checks


def main() -> int:
    results = run_checks()
    failures = [name for name, status in results.items() if not status.get("ok")]

    print("Credential sanity check\n")
    for name, status in results.items():
        ok = bool(status.get("ok"))
        detail = status.get("detail", "")
        icon = "OK" if ok else "!!"
        print(f"{icon} {name.upper()}: {detail}")

    print()
    if failures:
        print(f"{len(failures)} provider(s) failed: {', '.join(failures)}")
        return 1

    print("All providers look good.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(1)
