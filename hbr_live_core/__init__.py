"""HBR Live core: reading, calculation and storage, independent of any UI.

Rules for this package (see docs/roadmap-ui-split-2026-11.md):

* never import tkinter (or any other UI toolkit);
* exchange plain, JSON-serialisable data only (dicts / lists / numbers / strings);
* the snapshot contract lives in :mod:`hbr_live_core.schema` and
  docs/snapshot-contract.md.
"""
from .schema import SCHEMA_VERSION, SchemaError, check, validate
from . import damage_service
from .live_session import LiveSession
from .offline_session import OfflineSession, sanitize_team_payload
from .http_api import LocalApi, create_server

__all__ = [
    'SCHEMA_VERSION',
    'SchemaError',
    'check',
    'validate',
    'damage_service',
    'LiveSession',
    'OfflineSession',
    'sanitize_team_payload',
    'LocalApi',
    'create_server',
]
