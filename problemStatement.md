# Project Problem Statement

## Project

**Zomato AI-Powered Restaurant Recommender** is an application that helps
people find restaurants suited to their preferences. Instead of making users
manually compare restaurant listings, it combines restaurant data filtering
with an LLM to produce relevant, ranked recommendations and clear,
personalized explanations.

## Problem

Restaurant choices depend on several factors at once, including location,
budget, cuisine, and rating. A list of restaurants alone does not explain which
options best match a particular person's needs. The application should make
these choices easier by collecting preferences, finding suitable restaurants
from a real-world dataset, and presenting the strongest matches in an
understandable way.

## Objective

Build an application that:

- Collects a user's restaurant preferences, including location, budget,
  cuisine, minimum rating, and optional additional requirements.
- Uses real restaurant data from the Zomato restaurant recommendation dataset
  hosted on Hugging Face.
- Filters and prepares matching restaurant records before sending relevant,
  structured candidates to an LLM.
- Uses the LLM to rank candidates and explain, in natural language, why each
  recommendation fits the user's preferences.
- Presents the recommendations and their key details in a clear,
  user-friendly format.

## Data Source and Ingestion

Use the
[ManikaSaini Zomato restaurant recommendation dataset](https://huggingface.co/datasets/ManikaSaini/zomato-restaurant-recommendation).
Load and preprocess the dataset so restaurant records can be searched and
compared. Extract and normalize relevant fields where available, including:

- Restaurant name
- Location
- Cuisine
- Cost or price information
- Rating

The application should account for missing or inconsistent dataset values
rather than presenting unavailable information as fact.

## User Preferences

The application should let users provide:

- **Location:** for example, Bangalore
- **Budget:** low, medium, or high
- **Cuisine:** for example, Italian or Chinese
- **Minimum rating**
- **Additional preferences:** optional free-form requirements such as
  family-friendly dining or quick service

## Recommendation Workflow

1. Load and preprocess the restaurant dataset.
2. Collect the user's preferences.
3. Filter the dataset to find relevant restaurants, using the available
   location, cuisine, cost, and rating fields.
4. Prepare a bounded, structured set of candidate restaurants and the user's
   preferences for the LLM.
5. Ask the LLM to rank the candidates, explain how each matches the user's
   needs, and optionally summarize the options.
6. Display the results with factual restaurant details alongside the
   AI-generated explanations.

The LLM should base its recommendations on the supplied candidate data and
preferences. Restaurant names, ratings, cuisines, locations, and costs should
come from the dataset; explanations should not imply unsupported facts.

## Results

Each recommendation should show, when available:

- Restaurant name
- Cuisine
- Rating
- Estimated cost
- AI-generated explanation of why it fits

Show a useful set of top recommendations rather than an unfiltered dataset
dump. Clearly indicate when a detail is unavailable or when no suitable
matches are found.

## Intended Outcome

A user can enter their dining preferences and receive a relevant, ranked
selection of real restaurants, with enough factual detail and personalized
context to help them decide where to eat.
