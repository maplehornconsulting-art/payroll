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


class CPPData(BaseModel):
    rate: float
    ympe: float
    basic_exemption: float


class CPP2Data(BaseModel):
    rate: float
    yampe: float


class EIData(BaseModel):
    rate: float
    max_insurable_earnings: float


class ProvinceData(BaseModel):
    bpa: float
    tax_brackets: list[TaxBracket]


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
