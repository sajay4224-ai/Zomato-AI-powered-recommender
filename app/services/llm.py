from __future__ import annotations

import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.config import Settings
from app.models import LLMRankingResponse, LLMRecommendation, RequestPreferences
from app.services.catalog import RestaurantCandidate


class LLMAdapterError(RuntimeError):
    """Raised when the provider cannot produce a usable structured ranking."""


class LLMAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.timeout_seconds = max(1, int(settings.request_timeout_seconds))
        self.api_key = settings.gemini_api_key.strip()
        self.model_name = settings.gemini_model.strip() or "gemini-3.5-flash-lite"

    def rank_candidates(
        self,
        request: RequestPreferences,
        candidates: list[RestaurantCandidate],
    ) -> LLMRankingResponse:
        if not candidates:
            raise LLMAdapterError("No candidates are available for LLM ranking.")
        if not self.api_key:
            raise LLMAdapterError("Gemini API credentials are missing.")

        payload = self._build_payload(request, candidates)
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model_name}:generateContent"
        )
        body = json.dumps(payload).encode("utf-8")
        http_request = Request(
            endpoint,
            data=body,
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
                "User-Agent": "ZomatoAIRecommender/1.0",
            },
            method="POST",
        )

        try:
            with urlopen(http_request, timeout=self.timeout_seconds) as response:
                raw_text = response.read().decode("utf-8")
        except HTTPError as exc:
            raise LLMAdapterError(
                f"Gemini returned HTTP {exc.code}; verify GEMINI_API_KEY and GEMINI_MODEL."
            ) from None
        except (URLError, TimeoutError, OSError) as exc:
            raise LLMAdapterError(
                f"Gemini request failed ({type(exc).__name__}); check connectivity and timeout."
            ) from None

        try:
            response_data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            raise LLMAdapterError("Gemini returned malformed JSON.") from exc

        text = self._extract_text(response_data)
        if not text:
            raise LLMAdapterError("Gemini returned an empty response body.")

        ranking = self._parse_ranking_payload(text)
        if not ranking.recommendations:
            raise LLMAdapterError("Gemini returned no usable recommendations.")
        return ranking

    def _build_payload(
        self,
        request: RequestPreferences,
        candidates: list[RestaurantCandidate],
    ) -> dict[str, object]:
        candidate_context = []
        for candidate in candidates:
            candidate_context.append(
                {
                    "restaurant_id": candidate.id,
                    "name": candidate.name,
                    "location": candidate.location,
                    "city": candidate.city,
                    "cuisines": candidate.cuisines,
                    "rating": candidate.rating,
                    "estimated_cost": candidate.cost,
                    "cost_display": candidate.cost_display,
                }
            )

        prompt = (
            "You are ranking eligible restaurants for a user.",
            " Rank only candidate IDs supplied in the JSON payload.",
            " Use the user's preferences to prioritize options.",
            " Explain each recommendation using only the restaurant facts supplied in the payload.",
            " Do not invent attributes like parking, family-friendly status, or opening hours.",
            " Treat extra free-form preferences as soft wishes rather than confirmed facts.",
            " Return valid JSON only with keys 'recommendations' and optional 'summary'.",
            " Each recommendation must include 'restaurant_id', 'rank', and 'explanation'.",
            f" User preferences: {request.model_dump(exclude_none=True)}",
            f" Candidate records: {json.dumps(candidate_context, ensure_ascii=False)}",
        )

        return {
            "contents": [{"parts": [{"text": "\n".join(prompt)}]}],
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "recommendations": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "restaurant_id": {"type": "STRING"},
                                    "rank": {"type": "INTEGER"},
                                    "explanation": {"type": "STRING"},
                                },
                                "required": ["restaurant_id", "rank", "explanation"],
                            },
                        },
                        "summary": {"type": "STRING"},
                    },
                    "required": ["recommendations"],
                },
            },
        }

    @staticmethod
    def _extract_text(response_data: object) -> str | None:
        if not isinstance(response_data, dict):
            return None
        candidates = response_data.get("candidates")
        if not isinstance(candidates, list):
            return None
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str) and text.strip():
                        return text.strip()
        return None

    @staticmethod
    def _clean_json_text(text: str) -> str:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s*```$", "", cleaned)
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return cleaned[start : end + 1]
        return cleaned

    def _parse_ranking_payload(self, raw_text: str) -> LLMRankingResponse:
        cleaned = self._clean_json_text(raw_text)
        try:
            payload = json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LLMAdapterError("Gemini returned a non-JSON ranking payload.") from exc

        if not isinstance(payload, dict):
            raise LLMAdapterError("Gemini returned an unexpected ranking structure.")

        recommendations = payload.get("recommendations", [])
        if not isinstance(recommendations, list):
            raise LLMAdapterError("Gemini recommendations were not returned as a list.")

        parsed_recommendations: list[LLMRecommendation] = []
        seen_ids: set[str] = set()
        for item in recommendations:
            if not isinstance(item, dict):
                raise LLMAdapterError("Each recommendation must be an object.")

            restaurant_id = str(item.get("restaurant_id", "")).strip()
            if not restaurant_id:
                raise LLMAdapterError("A recommendation is missing a restaurant_id.")
            if restaurant_id in seen_ids:
                raise LLMAdapterError(f"Duplicate restaurant_id in model output: {restaurant_id}")
            seen_ids.add(restaurant_id)

            rank_raw = item.get("rank")
            try:
                rank = int(rank_raw)
            except (TypeError, ValueError) as exc:
                raise LLMAdapterError(f"Recommendation rank is invalid for {restaurant_id}.") from exc
            if rank < 1:
                raise LLMAdapterError(f"Recommendation rank must be positive for {restaurant_id}.")

            explanation = item.get("explanation")
            if not isinstance(explanation, str) or not explanation.strip():
                raise LLMAdapterError(f"Recommendation explanation is missing for {restaurant_id}.")

            parsed_recommendations.append(
                LLMRecommendation(
                    restaurant_id=restaurant_id,
                    rank=rank,
                    explanation=explanation.strip()[:1500],
                )
            )

        parsed_recommendations.sort(key=lambda item: item.rank)
        return LLMRankingResponse(
            recommendations=parsed_recommendations,
            summary=payload.get("summary") if isinstance(payload.get("summary"), str) else None,
        )
