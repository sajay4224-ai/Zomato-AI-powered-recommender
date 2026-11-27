from __future__ import annotations

from typing import Iterable

from app.models import RequestPreferences, RestaurantCandidate
from app.services.catalog import RestaurantCatalog


class PreferenceFilterService:
    """Applies deterministic location, cuisine, budget, and rating filters."""

    def __init__(self, default_candidate_limit: int = 20):
        self.default_candidate_limit = default_candidate_limit

    @staticmethod
    def _normalize_scalar(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            return None
        normalized = cleaned.lower()
        if normalized in {"-", "--", "n/a", "na", "nan", "new", "none", "null", "unknown"}:
            return None
        return cleaned

    @staticmethod
    def _matches_budget(candidate: RestaurantCandidate, budget: str) -> bool:
        cost = candidate.cost
        if cost is None:
            return False

        if budget == "low":
            return cost <= 500
        if budget == "medium":
            return 500 < cost <= 1000
        if budget == "high":
            return cost > 1000
        return False

    @staticmethod
    def _cost_fit_score(candidate: RestaurantCandidate, budget: str) -> float:
        cost = candidate.cost
        if cost is None:
            return 0.0

        if budget == "low":
            return max(0.0, 500.0 - cost)
        if budget == "medium":
            return max(0.0, 1000.0 - cost)
        if budget == "high":
            return max(0.0, cost - 1000.0)
        return 0.0

    def _normalize_location(self, input_value: str | None) -> str | None:
        return self._normalize_scalar(input_value)

    def _matches_location(self, candidate: RestaurantCandidate, location: str) -> bool:
        normalized_location = self._normalize_location(location)
        if normalized_location is None:
            return False

        city_value = self._normalize_scalar(candidate.city)
        if city_value and city_value.lower() == normalized_location.lower():
            return True

        alt_value = self._normalize_scalar(candidate.location)
        return bool(alt_value and alt_value.lower() == normalized_location.lower())

    def _matches_cuisine(self, candidate: RestaurantCandidate, requested_cuisines: Iterable[str]) -> bool:
        if not requested_cuisines:
            return True

        restaurant_cuisines = {c.lower() for c in candidate.cuisines if c}
        for cuisine in requested_cuisines:
            normalized = self._normalize_scalar(cuisine)
            if not normalized:
                continue
            if normalized.lower() in restaurant_cuisines:
                return True
        return False

    def filter_candidates(
        self,
        catalog: RestaurantCatalog,
        request: RequestPreferences,
    ) -> list[RestaurantCandidate]:
        normalized_location = self._normalize_location(request.location)
        if normalized_location is None:
            raise ValueError("Location is required.")

        selected: list[RestaurantCandidate] = []
        for restaurant in catalog.restaurants:
            if not self._matches_location(restaurant, normalized_location):
                continue
            if not self._matches_cuisine(restaurant, request.cuisine):
                continue
            if not self._matches_budget(restaurant, request.budget):
                continue
            if request.min_rating is not None:
                if restaurant.rating is None or restaurant.rating < request.min_rating:
                    continue
            selected.append(restaurant)

        selected.sort(
            key=lambda restaurant: (
                -(restaurant.rating if restaurant.rating is not None else 0.0),
                -self._cost_fit_score(restaurant, request.budget),
                restaurant.id.lower(),
            )
        )
        return selected[: self.default_candidate_limit]

    @staticmethod
    def build_explanation(candidate: RestaurantCandidate, request: RequestPreferences) -> str:
        rating_part = (
            f"rating {candidate.rating:.1f}/5" if candidate.rating is not None else "unavailable rating"
        )
        cost_part = (
            f"estimated cost {candidate.cost_display or f'₹{candidate.cost:g}'}"
            if candidate.cost is not None
            else "estimated cost unavailable"
        )
        cuisine_part = ", ".join(candidate.cuisines) if candidate.cuisines else "no cuisine data"
        explanation = (
            f"Matches {request.location} in {candidate.city or 'the requested city'} and includes "
            f"{cuisine_part}; it has {rating_part} and {cost_part} for the {request.budget} budget band."
        )
        if request.additional_preferences:
            explanation += " The additional preference was treated as a soft ranking signal rather than a guaranteed restaurant fact."
        return explanation


CandidateFilterService = PreferenceFilterService
RecommendationFilter = PreferenceFilterService
