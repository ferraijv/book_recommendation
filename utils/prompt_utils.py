import json
import logging
import re
def set_obscurity(obscurity_level):
    # Adjust the prompt based on obscurity_level
    if obscurity_level <= 3:
        prompt_obscurity_modifier = "The user wants highly popular books "
    elif obscurity_level >= 8:
        prompt_obscurity_modifier = "The user wants rare or obscure books "
    else:
        prompt_obscurity_modifier = ""

    return prompt_obscurity_modifier

def create_prompt(obscurity_level, user_input):
    prompt = f"""
    "Obscurity_level": {obscurity_level},
    "Preferences: {user_input} 
    """

    return prompt

def get_book_recommendations(user_profile, client):
    # Call ChatGPT for book recommendations
    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a helpful assistant providing book recommendations. "
                    "Always return the response in the following JSON format:\n\n"
                    "[\n"
                    "  {\n"
                    "    \"title\": \"<book title>\",\n"
                    "    \"author\": \"<author name>\",\n"
                    "    \"description\": \"<short description of the book>\",\n"
                    "    \"reason\": \"<why this book was recommended>\"\n"
                    "  },\n"
                    "  ... (5 total recommendations)\n"
                    "]\n\n"
                    "Ensure the JSON is valid and parseable."
                )
            },
            {
                "role": "user",
                "content": f"User profile: {user_profile}"
            }
        ]
    )
    # Parse the response into a Python object
    recommendations = json.loads(response.choices[0].message.content.strip())
    return recommendations



def create_reader_profile_prompt(reader_profile_details: dict):
    # Prepare the ChatGPT prompt
    prompt = f"""
    Analyze the following reading preferences and habits, and create a fun, sharable "Reader Personality" profile:
    - Favorite Genres: {reader_profile_details.get("genres")}
    - Favorite Books: {reader_profile_details.get("favorite_books")}
    - Reading Frequency: {reader_profile_details.get("reading_frequency")}
    - Preferred Format: {reader_profile_details.get("format")}
    - Reading Goals: {reader_profile_details.get("reading_goals")}
    - Themes to avoid {reader_profile_details.get("themes_to_avoid") if reader_profile_details.get("themes_to_avoid") else "None"}
    - MBTI: {reader_profile_details.get("mbti") if reader_profile_details.get("mbti") else "Not provided"}

    Categorize the user's "Reader Personality" (e.g., "The Book Adventurer", "The Cozy Reader", etc.), describe their traits, and suggest books or themes that align with their profile.
    """

    return prompt


def get_reader_profile_recommendations(reader_profile_details, client):
        
        prompt = create_reader_profile_prompt(reader_profile_details)
            # Call the ChatGPT API
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[
                {"role": "system", "content": """You are an assistant generating personalized reader profiles based on user inputs. Analyze the given responses and create a **reader personality type** tailored to the user. Return the results in the following structured JSON format:
                                                {
                                                "personality_type": "<Name of the reader personality type (e.g., 'The Analytical Explorer')>",
                                                "description": "<A brief description of this reader personality type, focusing on their reading habits, preferences, and motivations.>",
                                                "traits": [
                                                    "<Trait 1 (e.g., Analytical)>",
                                                    "<Trait 2 (e.g., Curious)>",
                                                    "<Trait 3 (e.g., Reflective)>",
                                                    "<Trait 4 (e.g., Adventurous)>",
                                                    "<Trait 5 (e.g., Thoughtful)>"
                                                ],
                                                "suggested_books": [
                                                    {
                                                    "title": "<Book Title 1>",
                                                    "author": "<Author Name 1>",
                                                    "description": "<Why this book is recommended for this reader personality type.>",
                                                    "reason": "<Why this book is recommended for this reader personality type.>"
                                                    },
                                                    {
                                                    "title": "<Book Title 2>",
                                                    "author": "<Author Name 2>",
                                                    "description": "<Why this book is recommended for this reader personality type.>",
                                                    "reason": "<Why this book is recommended for this reader personality type.>"
                                                    },
                                                    {
                                                    "title": "<Book Title 3>",
                                                    "author": "<Author Name 3>",
                                                    "description": "<Why this book is recommended for this reader personality type.>",
                                                    "reason": "<Why this book is recommended for this reader personality type.>"
                                                    },
                                                    {
                                                    "title": "<Book Title 4>",
                                                    "author": "<Author Name 4>",
                                                    "description": "<Why this book is recommended for this reader personality type.>",
                                                    "reason": "<Why this book is recommended for this reader personality type.>"
                                                    },
                                                    {
                                                    "title": "<Book Title 5>",
                                                    "author": "<Author Name 5>",
                                                    "description": "<Why this book is recommended for this reader personality type.>",
                                                    "reason": "<Why this book is recommended for this reader personality type.>"
                                                    },
                                                    {
                                                    "title": "<Book Title 6>",
                                                    "author": "<Author Name 6>",
                                                    "description": "<Why this book is recommended for this reader personality type.>",
                                                    "reason": "<Why this book is recommended for this reader personality type.>"
                                                    }
                                                ]
                                                }"""},
                {"role": "user", "content": prompt}
            ]
        )
        logging.warning(response)
        analysis = response.choices[0].message.content.strip()

        clean_response = re.sub(r"```(?:json)?", "", analysis).strip()

        logging.warning(f"Analysis: {clean_response}")

        return clean_response

def get_reader_profile_suggestions(reader_profile, client):
             # Prepare API request payload
    prompt = f"""
    Based on the following reader profile, recommend 5 books that align with the reader's personality and preferences. Format your response as a **valid JSON array** with the following structure:
    [
        {{
            "title": "Title of the book",
            "author": "Author of the book",
            "description": "A brief description of the book",
            "reason": "Why this book is recommended for the user"
        }},
        {{
            "title": "Title of the book",
            "author": "Author of the book",
            "description": "A brief description of the book",
            "reason": "Why this book is recommended for the user"
        }},
        ... 3 more books
    ]

    ### Reader Profile:
    - **Personality Type**: {reader_profile.personality_type}
    - **Description**: {reader_profile.description}
    - **Traits**: {', '.join(reader_profile.traits)}

    ### Guidelines for the Response:
    1. Ensure the JSON is strictly valid and free of syntax errors.
    2. Double-check that each field is populated with meaningful and relevant information.
    3. Avoid trailing commas or any invalid JSON formatting.
    4. Do not include extra text outside of the JSON array.

    Return only the JSON array in the response.
    """
    
    try:
        response = client.chat.completions.create(
            model="gpt-5-nano",
            messages=[{"role": "user", "content": prompt}],
        )
        recommendations = response.choices[0].message.content.strip()
        clean_response = re.sub(r"```(?:json)?", "", recommendations).strip()
        logging.warning(f"Recommendations: {clean_response}")
        recommended_books = json.loads(clean_response)  # Parse JSON response
    except Exception as e:
        logging.error(f"Error fetching recommendations: {str(e)}")

    return recommended_books
