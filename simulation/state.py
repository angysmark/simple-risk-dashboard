"""
Module-level singletons for the shared simulation state.

Views in the dashboard app import from here so they always reference the
same DataStore and RiskEngine instances that the background threads write to.

These are set to None at module import and populated by SimulationConfig.ready()
before any HTTP request can arrive.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from simulation.data_store import DataStore
    from simulation.risk_engine import RiskEngine

store: "DataStore | None" = None
risk_engine: "RiskEngine | None" = None
