import importlib
import json
import os

from fastapi.testclient import TestClient


def _reload_app():
    os.environ.setdefault("DATASET_URL", "https://example.com/zomato.csv")
    os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
    os.environ.setdefault("GEMINI_MODEL", "gemini-2.5-flash")
    os.environ.setdefault("REQUEST_TIMEOUT_SECONDS", "30")
    os.environ.setdefault("DEFAULT_CANDIDATE_LIMIT", "20")
    os.environ.setdefault("DEFAULT_RESULT_LIMIT", "5")
    os.environ.setdefault("SERVER_HOST", "0.0.0.0")
    os.environ.setdefault("SERVER_PORT", "8000")

    import app.config
    app.config.get_settings.cache_clear()
    import app.main
    importlib.reload(app.main)
    return app.main.app


def test_health_endpoint():
    app = _reload_app()
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_home_page_renders_search_form():
    app = _reload_app()
    client = TestClient(app)

    response = client.get("/")
    stylesheet = client.get("/static/styles.css")
    script = client.get("/static/app.js")

    assert response.status_code == 200
    assert "Your next favorite" in response.text
    assert "id=\"location\"" in response.text
    assert "id=\"cuisine\"" in response.text
    assert "Cuisine <span class=\"optional\">(optional)</span>" in response.text
    assert "Low · ₹500 or less" in response.text
    assert "High · over ₹1,000" in response.text
    assert "id=\"budget\"" in response.text
    assert "id=\"min_rating\"" in response.text
    assert "Family friendly - no alcohol" in response.text
    assert "Family friendly - with Alcohol" in response.text
    assert "additional_preferences" in response.text
    assert stylesheet.status_code == 200
    assert "restaurant-card" in stylesheet.text
    assert script.status_code == 200
    assert 'fetch("/api/options")' in script.text
    assert 'fetch("/api/recommend"' in script.text
    assert "familyPreference" in script.text
    assert "additional_preferences: additionalPreferences || null" in script.text


def test_ready_endpoint_reports_catalog_status(monkeypatch, tmp_path):
    csv_path = tmp_path / "zomato.csv"
    csv_path.write_text(
        """name,location,listed_in(city),cuisines,rate,approx_cost(for two people),address
Alpha,Indiranagar,Bangalore,"Italian, Pizza",4.8/5,600,1st Main Rd
"""
    )
    monkeypatch.setenv("DATASET_URL", str(csv_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    import app.config
    import app.main

    app.config.get_settings.cache_clear()
    importlib.reload(app.main)

    client = TestClient(app.main.app)
    ready = client.get("/ready")
    options = client.get("/api/options")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["catalog_loaded"] is True
    assert options.status_code == 200
    assert options.json() == {
        "locations": ["Bangalore", "Indiranagar"],
        "cuisines": ["Italian", "Pizza"],
    }

    monkeypatch.setenv("DATASET_URL", "/tmp/does-not-exist.csv")
    app.config.get_settings.cache_clear()
    importlib.reload(app.main)

    not_ready = TestClient(app.main.app).get("/ready")
    unavailable_options = TestClient(app.main.app).get("/api/options")
    assert not_ready.json()["status"] == "not_ready"
    assert not_ready.json()["catalog_loaded"] is False
    assert unavailable_options.status_code == 503
    assert "catalog" in unavailable_options.json()["detail"].lower()


def test_recommend_endpoint_requires_location():
    app = _reload_app()
    client = TestClient(app)

    response = client.post(
        "/api/recommend",
        json={
            "location": "",
            "budget": "medium",
            "cuisine": ["Italian"],
            "min_rating": 4.0,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "invalid_request"
    assert "Location is required" in response.json()["error"]


def test_settings_fail_when_required_vars_are_missing(monkeypatch):
    monkeypatch.delenv("DATASET_URL", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    monkeypatch.chdir("/tmp")

    import app.config

    app.config.get_settings.cache_clear()
    try:
        app.config.Settings()
    except Exception as exc:  # pragma: no cover - pydantic validation error is the expected outcome
        assert "required and cannot be blank" in str(exc).lower() or "dataset_url" in str(exc).lower() or "gemini_api_key" in str(exc).lower()
    else:
        raise AssertionError("Settings should fail when required env vars are missing.")


def test_catalog_loader_normalizes_dataset_rows():
    from app.services.catalog import RestaurantCatalog

    csv_text = """name,location,listed_in(city),cuisines,rate,approx_cost(for two people),address
Blue Bowl,Indiranagar,Bangalore,"Italian, Pizza",4.4/5,800,1st Main Rd
,Indiranagar,Bangalore,"Italian",-, ,2nd Main Rd
"""

    catalog = RestaurantCatalog.from_csv_text(csv_text)

    assert len(catalog.restaurants) == 1
    restaurant = catalog.restaurants[0]
    assert restaurant.name == "Blue Bowl"
    assert restaurant.city == "Bangalore"
    assert restaurant.location == "Indiranagar"
    assert restaurant.cuisines == ["Italian", "Pizza"]
    assert restaurant.rating == 4.4
    assert restaurant.cost == 800.0
    assert restaurant.cost_display == "800"
    assert restaurant.id.startswith("restaurant-")


def test_recommend_returns_service_error_when_catalog_fails(monkeypatch):
    monkeypatch.setenv("DATASET_URL", "/tmp/definitely-missing-zomato.csv")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    import app.config
    import app.main

    app.config.get_settings.cache_clear()
    importlib.reload(app.main)

    client = TestClient(app.main.app)
    response = client.post(
        "/api/recommend",
        json={
            "location": "Bangalore",
            "budget": "medium",
            "cuisine": ["Italian"],
            "min_rating": 4.0,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "service_error"
    assert "catalog" in response.json()["error"].lower()


def test_filter_service_returns_deterministic_matches_for_valid_preferences():
    from app.models import RequestPreferences
    from app.services.catalog import RestaurantCatalog
    from app.services.filtering import PreferenceFilterService

    csv_text = """name,location,listed_in(city),cuisines,rate,approx_cost(for two people),address
Alpha,Indiranagar,Bangalore,"Italian, Pizza",4.8/5,600,1st Main Rd
Beta,Indiranagar,Bangalore,"Italian",4.5/5,900,2nd Main Rd
Gamma,Indiranagar,Bangalore,"Chinese",4.7/5,400,3rd Main Rd
Delta,HSR Layout,Bangalore,"Italian",,900,4th Main Rd
"""
    catalog = RestaurantCatalog.from_csv_text(csv_text)
    request = RequestPreferences(
        location="Bangalore",
        budget="medium",
        cuisine=["Italian"],
        min_rating=4.5,
        additional_preferences="family friendly",
    )

    candidates = PreferenceFilterService(5).filter_candidates(catalog, request)

    assert [candidate.name for candidate in candidates] == ["Alpha", "Beta"]
    assert candidates[0].rating == 4.8
    assert candidates[1].rating == 4.5


def test_recommend_response_includes_catalog_details_for_results(monkeypatch, tmp_path):
    csv_path = tmp_path / "zomato.csv"
    csv_path.write_text(
        """name,location,listed_in(city),cuisines,rate,approx_cost(for two people),address
Alpha,Indiranagar,Bangalore,"Italian, Pizza",4.8/5,600,1st Main Rd
"""
    )
    monkeypatch.setenv("DATASET_URL", str(csv_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    import app.config
    import app.main

    app.config.get_settings.cache_clear()
    importlib.reload(app.main)

    client = TestClient(app.main.app)
    response = client.post(
        "/api/recommend",
        json={
            "location": "Bangalore",
            "budget": "medium",
            "cuisine": ["Italian"],
            "min_rating": 4.0,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    first = payload["recommendations"][0]
    assert first["name"] == "Alpha"
    assert first["rating"] == 4.8
    assert "₹600" in first["estimated_cost"]
    assert "Italian" in first["cuisines"]


def test_llm_adapter_parses_ranking_response():
    from app.models import RequestPreferences
    from app.services.catalog import RestaurantCatalog
    from app.services.llm import LLMAdapter

    csv_text = """name,location,listed_in(city),cuisines,rate,approx_cost(for two people),address
Alpha,Indiranagar,Bangalore,"Italian, Pizza",4.8/5,600,1st Main Rd
Beta,Indiranagar,Bangalore,"Italian",4.5/5,900,2nd Main Rd
"""
    catalog = RestaurantCatalog.from_csv_text(csv_text)
    request = RequestPreferences(
        location="Bangalore",
        budget="medium",
        cuisine=["Italian"],
        min_rating=4.0,
    )

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return False

        def read(self):
            return json.dumps(
                {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {
                                        "text": '{"recommendations":[{"restaurant_id":"' + catalog.restaurants[1].id + '","rank":1,"explanation":"Matches your cuisine and rating."}],"summary":"Top match."}'
                                    }
                                ]
                            }
                        }
                    ]
                }
            ).encode("utf-8")

    import app.services.llm as llm_module

    monkeypatch = __import__("pytest").MonkeyPatch()
    monkeypatch.setattr(llm_module, "urlopen", lambda *args, **kwargs: FakeResponse())
    try:
        adapter = LLMAdapter(type("Settings", (), {"request_timeout_seconds": 30, "gemini_api_key": "fake-key", "gemini_model": "gemini-2.5-flash"})())
        ranking = adapter.rank_candidates(request, catalog.restaurants[:2])
        assert ranking.recommendations[0].restaurant_id == catalog.restaurants[1].id
        assert ranking.summary == "Top match."
    finally:
        monkeypatch.undo()


def test_recommend_uses_deterministic_fallback_when_llm_fails(monkeypatch):
    from app.models import RequestPreferences
    from app.services.catalog import RestaurantCatalog
    from app.services.llm import LLMAdapterError

    csv_text = """name,location,listed_in(city),cuisines,rate,approx_cost(for two people),address
Alpha,Indiranagar,Bangalore,"Italian, Pizza",4.8/5,600,1st Main Rd
Beta,Indiranagar,Bangalore,"Italian",4.5/5,900,2nd Main Rd
"""
    catalog = RestaurantCatalog.from_csv_text(csv_text)
    request = RequestPreferences(
        location="Bangalore",
        budget="medium",
        cuisine=["Italian"],
        min_rating=4.0,
    )

    from app.services.orchestration import RecommendationService

    service = RecommendationService(type("Settings", (), {"default_candidate_limit": 5, "default_result_limit": 5, "dataset_url": "https://example.com/zomato.csv", "gemini_api_key": "fake-key", "gemini_model": "gemini-2.5-flash", "request_timeout_seconds": 30})())
    service.catalog = catalog
    service.catalog_error = None
    service.llm_adapter.rank_candidates = lambda *args, **kwargs: (_ for _ in ()).throw(LLMAdapterError("provider unavailable"))

    response = service.generate(request)

    assert response.status == "success"
    assert response.fallback_used is True
    assert response.ai_ranked is False
    assert len(response.recommendations) == 2


def test_recommend_returns_no_results_when_filters_exclude_everything(monkeypatch, tmp_path):
    csv_path = tmp_path / "zomato.csv"
    csv_path.write_text(
        """name,location,listed_in(city),cuisines,rate,approx_cost(for two people),address
Only,Indiranagar,Bangalore,"Italian",3.9/5,1400,1st Main Rd
"""
    )
    monkeypatch.setenv("DATASET_URL", str(csv_path))
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")

    import app.config
    import app.main

    app.config.get_settings.cache_clear()
    importlib.reload(app.main)

    client = TestClient(app.main.app)
    response = client.post(
        "/api/recommend",
        json={
            "location": "Bangalore",
            "budget": "medium",
            "cuisine": ["Italian"],
            "min_rating": 4.5,
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "no_results"
    assert "No restaurants matched" in response.json()["error"]
