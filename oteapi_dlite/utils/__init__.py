"""`oteapi_dlite.utils` module.

This module provide some utility functions.
"""
from .nputils import dict2recarray
from .utils import get_collection, get_driver, get_meta

__all__ = ("dict2recarray", "get_driver", "get_meta", "get_collection")
