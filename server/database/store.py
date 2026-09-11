"""
Global DataStore singleton.
All route modules should import data_store from this module
instead of creating their own DataStore instances.
"""

from server.database.db import DataStore

data_store = DataStore()
