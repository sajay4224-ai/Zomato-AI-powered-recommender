import logging

from app.config import Settings
from app.models import Recommendation, RecommendationResponse, RequestPreferences
from app.services.catalog import DatasetIngestionError, RestaurantCatalog
from app.services.filtering import PreferenceFilterService
from app.services.llm import LLMAdapter, LLMAdapterError

logger = logging.getLogger("zomato_ai")


class RecommendationService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.catalog = RestaurantCatalog.empty()
        self.catalog_error: str | None = None
        self.filter_service = PreferenceFilterService(settings.default_candidate_limit)
        self.llm_adapter = LLMAdapter(settings)
        self.refresh_catalog()

    @property
    def is_ready(self) -> bool:
        return not self.catalog_error and bool(self.catalog.restaurants)

    def refresh_catalog(self) -> RestaurantCatalog:
        logger.info("Refreshing dataset catalog from %s", self.settings.dataset_url)
        try:
            catalog = RestaurantCatalog.from_csv_url(self.settings.dataset_url)
        except DatasetIngestionError as exc:
            self.catalog = RestaurantCatalog.empty()
            self.catalog_error = str(exc)
            logger.error("Catalog refresh failed: %s", exc)
            return self.catalog

        self.catalog = catalog
        self.catalog_error = None
        logger.info("Catalog refresh succeeded with %d restaurants (version=%s).", len(catalog.restaurants), catalog.catalog_version)
        return catalog

    def _build_deterministic_recommendations(
        self,
        candidates: list,
        request: RequestPreferences,
    ) -> list[Recommendation]:
        return [
            Recommendation(
                restaurant_id=candidate.id,
                rank=index + 1,
                name=candidate.name,
                location=candidate.location,
                city=candidate.city,
                cuisines=candidate.cuisines,
                rating=candidate.rating,
                estimated_cost=(
                    f"₹{candidate.cost:g} (dataset-derived estimate)"
                    if candidate.cost is not None
                    else "Unavailable"
                ),
                explanation=self.filter_service.build_explanation(candidate, request),
            )
            for index, candidate in enumerate(candidates[: self.settings.default_result_limit])
        ]

    def generate(self, request: RequestPreferences) -> RecommendationResponse:
        logger.info(
            "Recommendation request received: location=%s budget=%s cuisines=%s min_rating=%s",
            request.location,
            request.budget,
            request.cuisine,
            request.min_rating,
        )

        if not request.location.strip():
            return RecommendationResponse(
                status="invalid_request",
                error="Location is required.",
                catalog_version=self.catalog.catalog_version,
            )

        if self.catalog_error:
            return RecommendationResponse(
                status="service_error",
                error=self.catalog_error,
                summary="The restaurant catalog could not be loaded successfully.",
                catalog_version=self.catalog.catalog_version,
            )

        if not self.catalog.restaurants:
            return RecommendationResponse(
                status="service_error",
                error="The restaurant catalog is empty or unavailable.",
                summary="No valid restaurants were loaded into the active catalog.",
                catalog_version=self.catalog.catalog_version,
            )

        try:
            candidates = self.filter_service.filter_candidates(self.catalog, request)
        except ValueError as exc:
            return RecommendationResponse(
                status="invalid_request",
                error=str(exc),
                catalog_version=self.catalog.catalog_version,
            )

        if not candidates:
            logger.info("No eligible candidates for request in %s.", request.location)
            return RecommendationResponse(
                status="no_results",
                error="No restaurants matched the supplied filters.",
                summary="No restaurants met the request's location, cuisine, budget, and rating criteria.",
                catalog_version=self.catalog.catalog_version,
            )

        logger.info("Generated %d deterministic candidates before LLM ranking.", len(candidates))
        deterministic_recommendations = self._build_deterministic_recommendations(candidates, request)
        try:
            ranking = self.llm_adapter.rank_candidates(request, candidates)
        except (LLMAdapterError, TimeoutError, OSError, ValueError) as exc:
            logger.warning("LLM ranking failed; using deterministic fallback. Error: %s", exc)
            return RecommendationResponse(
                status="success",
                recommendations=deterministic_recommendations,
                summary=(
                    "The LLM ranking service was unavailable, so the strongest deterministic matches were "
                    "returned instead."
                ),
                catalog_version=self.catalog.catalog_version,
                error=str(exc),
                ai_ranked=False,
                fallback_used=True,
            )

        catalog_by_id = {candidate.id: candidate for candidate in candidates}
        ranked_recommendations: list[Recommendation] = []
        seen_ids: set[str] = set()
        for llm_item in ranking.recommendations[: self.settings.default_result_limit]:
            candidate = catalog_by_id.get(llm_item.restaurant_id)
            if candidate is None or candidate.id in seen_ids:
                continue
            seen_ids.add(candidate.id)
            ranked_recommendations.append(
                Recommendation(
                    restaurant_id=candidate.id,
                    rank=len(ranked_recommendations) + 1,
                    name=candidate.name,
                    location=candidate.location,
                    city=candidate.city,
                    cuisines=candidate.cuisines,
                    rating=candidate.rating,
                    estimated_cost=(
                        f"₹{candidate.cost:g} (dataset-derived estimate)"
                        if candidate.cost is not None
                        else "Unavailable"
                    ),
                    explanation=llm_item.explanation,
                )
            )

        if not ranked_recommendations:
            return RecommendationResponse(
                status="success",
                recommendations=deterministic_recommendations,
                summary="The model returned unusable recommendations, so deterministic results were shown instead.",
                catalog_version=self.catalog.catalog_version,
                ai_ranked=False,
                fallback_used=True,
            )

        return RecommendationResponse(
            status="success",
            recommendations=ranked_recommendations,
            summary=ranking.summary or (
                f"Found {len(ranked_recommendations)} ranked recommendations based on the supplied "
                f"preferences in {request.location}."
            ),
            catalog_version=self.catalog.catalog_version,
            ai_ranked=True,
            fallback_used=False,
        )
