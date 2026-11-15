from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Budget = Literal["low", "medium", "high"]
RecommendationStatus = Literal["success", "invalid_request", "no_results", "service_error"]


class RestaurantCandidate(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    location: str | None = None
    city: str | None = None
    cuisines: list[str] = Field(default_factory=list)
    cost: float | None = None
    cost_display: str | None = None
    rating: float | None = None
    source_fields: dict[str, str | int | float | None] = Field(default_factory=dict)


class RequestPreferences(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    location: str = Field(..., max_length=200)
    budget: Budget
    cuisine: list[str] = Field(default_factory=list)
    min_rating: float | None = Field(default=None, ge=0, le=5)
    additional_preferences: str | None = Field(default=None, max_length=500)

    @field_validator("cuisine")
    @classmethod
    def normalize_cuisine_values(cls, values: list[str]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = value.strip()
            if not cleaned:
                continue
            lowered = cleaned.lower()
            if lowered not in seen:
                normalized.append(cleaned)
                seen.add(lowered)
        return normalized


class Recommendation(BaseModel):
    restaurant_id: str
    rank: int = Field(..., ge=1)
    name: str
    location: str | None = None
    city: str | None = None
    cuisines: list[str] = Field(default_factory=list)
    rating: float | None = None
    estimated_cost: str | None = None
    explanation: str


class LLMRecommendation(BaseModel):
    restaurant_id: str
    rank: int = Field(..., ge=1)
    explanation: str = Field(..., max_length=1500)


class LLMRankingResponse(BaseModel):
    recommendations: list[LLMRecommendation] = Field(default_factory=list)
    summary: str | None = None


class RecommendationResponse(BaseModel):
    status: RecommendationStatus
    recommendations: list[Recommendation] = Field(default_factory=list)
    summary: str | None = None
    catalog_version: str | None = None
    error: str | None = None
    ai_ranked: bool = True
    fallback_used: bool = False
