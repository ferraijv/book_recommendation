import json
import logging
import re
from google.genai.types import GenerateContentConfig


def set_obscurity(obscurity_level):
    if obscurity_level <= 3:
        return "The user wants highly popular books."
    elif obscurity_level >= 8:
        return "The user wants rare or obscure books."
    return ""


def create_prompt(obscurity_level, user_input):
    return f"""
Obscurity level: {obscurity_level}
Preferences: {user_input}
"""


def get_book_recommendations(user_profile, client):
    prompt = f"""
You are a helpful assistant providing book recommendations.

Given this user profile:
{user_profile}

Return exactly 5 book recommendations in the following valid JSON format:

[
  {{
    "title": "<book title>",
    "author": "<author name>",
    "description": "<short description of the book>",
    "reason": "<why this book was recommended>"
  }},
  ...
]
"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[prompt],
        config=GenerateContentConfig(
            temperature=0.7
        )
    )

    raw = response.text.strip()
    try:
        clean_json = re.sub(r"```(?:json)?", "", raw).strip()
        return json.loads(clean_json)
    except Exception as e:
        logging.error(f"Failed to parse recommendations: {e}\nRaw response: {raw}")
        return []


def create_reader_profile_prompt(reader_profile_details: dict):
    return f"""
Analyze the following reading preferences and habits, and create a fun, sharable "Reader Personality" profile with 5 reader traits and 5 books recommendations:

- Favorite Genres: {reader_profile_details.get("genres")}
- Favorite Books: {reader_profile_details.get("favorite_books")}
- Favorite Authors: {reader_profile_details.get("favorite_authors")}
- Reading Goals: {reader_profile_details.get("reading_goals")}
- Themes to avoid: {reader_profile_details.get("themes_to_avoid", "None")}
- MBTI: {reader_profile_details.get("mbti", "Not provided")}

Return the result in this valid JSON format:

{{
  "personality_type": "<e.g., 'The Analytical Explorer'>",
  "description": "<Brief description of reading habits and motivations>",
  "traits": ["Trait 1", "Trait 2", "Trait 3", "Trait 4", "Trait 5"],
  "suggested_books": [
    {{
      "title": "<Book Title>",
      "author": "<Author Name>",
      "description": "<Why this book is recommended>",
      "reason": "<Why this book matches the personality>"
    }},
    ...
  ]
}}
"""


def get_reader_profile_recommendations(reader_profile_details, client):
    prompt = create_reader_profile_prompt(reader_profile_details)

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[prompt],
        config=GenerateContentConfig(
            temperature=0.7,
            max_output_tokens=20000
        )
    )

    raw = response.text.strip()
    logging.debug(f"Raw Gemini response:\n{raw}")

    try:
        clean_response = re.sub(r"```(?:json)?", "", raw).strip()
        return json.loads(clean_response)
    except Exception as e:
        logging.error(f"Failed to parse Gemini JSON: {e}\nRaw response: {raw}")
        return {}
