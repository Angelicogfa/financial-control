"""CLI: `python -m fincontrol_api hash-password` or `python -m fincontrol_api new-secret`."""

from core.security import main

if __name__ == "__main__":
    raise SystemExit(main())
