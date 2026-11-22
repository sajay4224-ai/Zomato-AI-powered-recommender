const API_BASE_URL = (window.API_BASE_URL || "").replace(/\/+$/, "");

const form = document.getElementById("recommendation-form");
const submitButton = document.getElementById("submit-button");
const statusBox = document.getElementById("status-box");
const results = document.getElementById("results");
const locationSelect = document.getElementById("location");
const cuisineSelect = document.getElementById("cuisine");

function addOption(select, label, value = "") {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  select.append(option);
}

async function loadOptions() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/options`);
    const data = await response.json();
    if (!response.ok) {
      throw new Error(data.detail || "Restaurant options could not be loaded.");
    }

    locationSelect.replaceChildren();
    addOption(locationSelect, "Choose a location...", "");
    for (const location of data.locations) {
      addOption(locationSelect, location, location);
    }
    locationSelect.disabled = data.locations.length === 0;

    cuisineSelect.replaceChildren();
    addOption(cuisineSelect, "Any cuisine · optional", "");
    for (const cuisine of data.cuisines) {
      addOption(cuisineSelect, cuisine, cuisine);
    }
    cuisineSelect.disabled = false;
    submitButton.disabled = data.locations.length === 0;

    if (data.locations.length === 0) {
      showStatus("error", "The catalog has no locations available for searching.");
    }
  } catch (error) {
    locationSelect.replaceChildren();
    addOption(locationSelect, "Locations unavailable", "");
    cuisineSelect.replaceChildren();
    addOption(cuisineSelect, "Cuisines unavailable", "");
    showStatus(
      "error",
      error instanceof Error ? error.message : "Restaurant options could not be loaded.",
    );
  }
}

function showStatus(type, message) {
  statusBox.className = `status-box ${type}`;
  statusBox.textContent = message;
  statusBox.hidden = false;
}

function clearStatus() {
  statusBox.className = "status-box";
  statusBox.textContent = "";
  statusBox.hidden = true;
}

function renderEmptyState(title, message) {
  const state = document.createElement("div");
  state.className = "empty-state";

  const heading = document.createElement("h3");
  heading.textContent = title;
  const description = document.createElement("p");
  description.textContent = message;
  state.append(heading, description);
  results.replaceChildren(state);
}

function appendDetail(container, label, value) {
  const chip = document.createElement("span");
  chip.className = "detail-chip";
  chip.textContent = `${label}: ${value || "Unavailable"}`;
  container.append(chip);
}

function createRestaurantCard(restaurant, index, aiRanked) {
  const card = document.createElement("article");
  card.className = "restaurant-card";

  const top = document.createElement("div");
  top.className = "card-top";
  const titleGroup = document.createElement("div");
  const rank = document.createElement("span");
  rank.className = "card-rank";
  rank.textContent = `${aiRanked ? "✦ AI PICK" : "✦ TOP MATCH"} · #${restaurant.rank || index + 1}`;
  const title = document.createElement("h3");
  title.className = "card-title";
  title.textContent = restaurant.name || "Restaurant";
  titleGroup.append(rank, title);

  const rating = document.createElement("span");
  rating.className = `rating-pill${restaurant.rating == null ? " no-rating" : ""}`;
  rating.textContent = restaurant.rating == null
    ? "Rating unavailable"
    : `★ ${Number(restaurant.rating).toFixed(1)}`;
  top.append(titleGroup, rating);

  const details = document.createElement("div");
  details.className = "card-details";
  appendDetail(details, "Location", restaurant.location || restaurant.city);
  appendDetail(
    details,
    "Cuisine",
    Array.isArray(restaurant.cuisines) && restaurant.cuisines.length
      ? restaurant.cuisines.join(", ")
      : null,
  );
  appendDetail(details, "Cost for two", restaurant.estimated_cost);

  const explanation = document.createElement("p");
  explanation.className = "card-explanation";
  explanation.textContent = restaurant.explanation || "No explanation was provided.";
  card.append(top, details, explanation);
  return card;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const familyPreference = document.getElementById("family_preference").value;
  const freeFormPreference = document.getElementById("additional_preferences").value.trim();
  const preferenceParts = [familyPreference, freeFormPreference].filter(Boolean);
  const additionalPreferences = preferenceParts.join("; ");
  if (additionalPreferences.length > 500) {
    showStatus(
      "error",
      "Please shorten the natural-language preference to fit the 500-character limit with this family preference.",
    );
    return;
  }

  clearStatus();
  submitButton.disabled = true;
  submitButton.querySelector("span").textContent = "Finding your matches...";
  results.setAttribute("aria-busy", "true");
  renderEmptyState("Finding your next favorite...", "Looking through the restaurant catalog for a match.");

  const rating = document.getElementById("min_rating").value;
  const cuisine = cuisineSelect.value;
  const payload = {
    location: locationSelect.value,
    budget: document.getElementById("budget").value,
    cuisine: cuisine ? [cuisine] : [],
    min_rating: rating ? Number(rating) : null,
    additional_preferences: additionalPreferences || null,
  };

  try {
    const response = await fetch(`${API_BASE_URL}/api/recommend`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.detail || "The recommendation request failed.");
    }

    if (data.status === "success" && Array.isArray(data.recommendations) && data.recommendations.length) {
      results.replaceChildren(
        ...data.recommendations.map((restaurant, index) =>
          createRestaurantCard(restaurant, index, data.ai_ranked !== false),
        ),
      );
      showStatus(
        data.fallback_used ? "info" : "success",
        data.summary || "Here are the restaurants that best fit your preferences.",
      );
    } else if (data.status === "no_results") {
      renderEmptyState("No matches this time.", "Try a nearby location or broaden your cuisine, budget, or rating preferences.");
      showStatus("info", data.error || "No restaurants matched those filters.");
    } else if (data.status === "invalid_request") {
      renderEmptyState("Let's try that again.", "Check your preferences and submit the search once more.");
      showStatus("error", data.error || "Please check your search details.");
    } else {
      renderEmptyState("We couldn't find your picks.", "The recommendation service is temporarily unavailable. Please try again.");
      showStatus("error", data.error || "The recommendation service could not complete this request.");
    }
  } catch (error) {
    renderEmptyState("We couldn't reach the kitchen.", "Check your connection and try your search again.");
    showStatus(
      "error",
      error instanceof Error ? error.message : "The recommendation service encountered a network or server error.",
    );
  } finally {
    submitButton.disabled = false;
    submitButton.querySelector("span").textContent = "Find my restaurants";
    results.setAttribute("aria-busy", "false");
  }
});

loadOptions();
