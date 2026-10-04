"""Package entry so `python -m __PKG__` behaves like the `__NAME__` script."""

import sys

from __PKG__.cli import main

sys.exit(main())
