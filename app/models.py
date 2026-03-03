"""Pydantic models for request / response validation."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent 1 output (mirrors Bestekpostmapping schema)
# ---------------------------------------------------------------------------

class Transition(BaseModel):
    from_photo: int = Field(ge=1)
    to_photo: int = Field(ge=1)
    observaties: list[str] = Field(default_factory=list)
    bestekpostnummers: list[str] = Field(default_factory=list)
    zekerheid: str = Field(pattern=r"^(hoog|middel|laag)$")
    toelichting: str | None = None


class Agent1Output(BaseModel):
    transitions: list[Transition] = Field(min_length=1)
    globale_opmerkingen: str | None = None


# ---------------------------------------------------------------------------
# Agent 2 output (structured report)
# ---------------------------------------------------------------------------

class BronInfo(BaseModel):
    deel: str
    sectie: str
    fragmenten: list[str]


class BestekpostDetail(BaseModel):
    nummer: str
    titel: str
    zichtbaar_uitgevoerd: list[str]
    bestekeisen: list[str]
    bron: BronInfo
    open_punten: list[str]
    volgende_stap: str


class TransitionReport(BaseModel):
    from_photo: int
    to_photo: int
    zekerheid: str
    samenvatting: str
    bestekposten: list[BestekpostDetail]


class Agent2Output(BaseModel):
    transitions: list[TransitionReport]
    aandachtspunten_globaal: list[str]
    extra_input_nodig: list[str]


# ---------------------------------------------------------------------------
# API response helpers
# ---------------------------------------------------------------------------

class RetrievalLogEntry(BaseModel):
    bestekpostnummer: str
    deel: int
    query: str
    fragments: list[str]


class ProgressReportResponse(BaseModel):
    markdown_report: str
    agent2_json: dict
    agent1_json: dict
    retrieval_log: list[RetrievalLogEntry]
