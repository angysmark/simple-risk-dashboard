"""
Module-level singleton for the shared simulation state.

The dashboard view imports ``store`` from here so it always references the
same DataStore instance that the background SimulationLoop writes to.

Set to None at module import; populated by SimulationConfig.ready() before
any HTTP request can arrive.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.data_store import DataStore

store: "DataStore | None" = None
