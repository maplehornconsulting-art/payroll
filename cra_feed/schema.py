"""Pydantic v2 schema models for the CRA payroll tax feed (v1)."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, field_validator


class BPAFRange(BaseModel):
    min: float
    max: float


class TaxBracket(BaseModel):
    up_to: Optional[float]  # None means "and above" (top bracket)
    rate: float


class FederalData(BaseModel):
    bpaf: BPAFRange
    k1_rate: float
    tax_brackets: list[TaxBracket]
    cea: Optional[float] = None  # Canada Employment Amount


class CPPData(BaseModel):
    rate: float
    ympe: float
    basic_exemption: float
    max_contribution: Optional[float] = None  # maximum annual employee contribution
    base_rate: Optional[float] = None         # base CPP employee rate (excl. enhancement)


class CPP2Data(BaseModel):
    rate: float
    yampe: float
    max_contribution: Optional[float] = None  # maximum annual employee CPP2


class EIData(BaseModel):
    rate: float
    max_insurable_earnings: float
    max_premium: Optional[float] = None  # maximum annual employee premium


class TaxReduction(BaseModel):
    """Provincial tax reduction (T4127 factor S) that phases out with income."""

    base: float        # S2 — the full reduction
    phase_from: float  # income where the phase-out starts
    phase_to: float    # income where the reduction reaches nil
    rate: float        # phase-out rate (0–1)


class ProvinceData(BaseModel):
    bpa: float
    tax_brackets: list[TaxBracket]
    surtax: list[list[float]] = []
    k1p: Optional[float] = None
    reduction: Optional[TaxReduction] = None  # BC
    reduction_base: Optional[float] = None    # ON — S2 in "2 × (S2 + Y) − (T4 + V1)"


class CRAFeed(BaseModel):
    schema_version: str
    jurisdiction: str
    effective_date: str          # ISO date string, e.g. "2026-07-01"
    published_at: str            # ISO datetime string with Z suffix
    source_urls: list[str]
    federal: FederalData
    cpp: CPPData
    cpp2: CPP2Data
    ei: EIData
    provinces: dict[str, ProvinceData]
    checksum_sha256: str

    @field_validator("jurisdiction")
    @classmethod
    def jurisdiction_upper(cls, v: str) -> str:
        return v.upper()
