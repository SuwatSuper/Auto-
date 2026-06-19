# Layer 2 — Orchestration (agents/spec)
from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel


class Department(StrEnum):
    NEWS_SENTIMENT = "news_sentiment"
    HISTORICAL_RESEARCH = "historical_research"
    ENTRY_EXIT = "entry_exit"
    PROBABILITY = "probability"
    RISK = "risk"
    SIMULATION = "simulation"
    SUPREME = "supreme"


class AgentSpec(BaseModel, frozen=True):
    name: str
    department: Department
    topic_in: str
    topic_out: str
    description: str = ""
