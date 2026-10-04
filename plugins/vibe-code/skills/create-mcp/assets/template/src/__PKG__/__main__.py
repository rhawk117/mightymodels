"""Package entry so `python -m __PKG__` behaves like the `__NAME__` script."""

from __PKG__.cli import main

raise SystemExit(main())
