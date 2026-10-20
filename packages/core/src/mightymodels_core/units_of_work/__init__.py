"""The entry the Works build their stores and services on."""

from .entry import Entry, read_entry, write_entry
from .errors import UnknownRepositoryError

__all__ = ['Entry', 'UnknownRepositoryError', 'read_entry', 'write_entry']
