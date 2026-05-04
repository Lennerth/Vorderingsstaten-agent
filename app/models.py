"""Pydantic models for request / response validation."""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Agent 1 output (mirrors Bestekpostmapping schema)
# ---------------------------------------------------------------------------

class Agent1Bestekpost(BaseModel):
    nummer: str
    image_indices: list[int] = Field(default_factory=list)
    camera_labels: list[str] = Field(default_factory=list)
    observaties: list[str] = Field(default_factory=list, description="Alleen nieuw of gewijzigd werk, geen bestaande toestand.")
    zekerheid: str = Field(pattern=r"^(hoog|middel|laag)$")
    toelichting: str | None = None


class Agent1Output(BaseModel):
    bestekposten: list[Agent1Bestekpost] = Field(default_factory=list)
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
    image_indices: list[int] = Field(default_factory=list)
    camera_labels: list[str] = Field(default_factory=list)
    zekerheid: str = Field(pattern=r"^(hoog|middel|laag)$")
    zichtbaar_uitgevoerd: list[str] = Field(description="Werk uitgevoerd in deze periode (delta), geen statische site-condities.")
    bestekeisen: list[str]
    bron: BronInfo
    open_punten: list[str]
    volgende_stap: str


class Agent2Output(BaseModel):
    bestekposten: list[BestekpostDetail] = Field(default_factory=list)
    aandachtspunten_globaal: list[str] = Field(default_factory=list)
    extra_input_nodig: list[str] = Field(default_factory=list)
