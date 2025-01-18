import json
import logging

def set_obscurity(obscurity_level):
    # Adjust the prompt based on obscurity_level
    if obscurity_level <= 3:
        prompt_obscurity_modifier = "The user wants highly popular books "
    elif obscurity_level >= 8:
        prompt_obscurity_modifier = "The user wants rare or obscure books "
    else:
        prompt_obscurity_modifier = ""

    return prompt_obscurity_modifier

def create_prompt(obscurity_level, user_input, mbti):
    prompt = f"""
    "MBTI": {mbti},
    "Obscurity_level": {obscurity_level},
    "Preferences: {user_input} 
    """

    return prompt

def get_book_recommendations(user_profile, client):
    # Call ChatGPT for book recommendations
    response = client.chat.completions.create(
        model="gpt-4o-mini",
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
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """Analyze the following reading preferences and habits, and create a "Reader Personality" profile. Don't include books they've already read in their suggestions. Return the output in structured Markdown format like this:

                                                **Reader Personality Profile**: <Personality Name>  
                                                **Description**: <Description of personality>  
                                                **Traits**: <Description of personality traits>  
                                                **Suggested Books/Themes**:  
                                                1. <Book 1>  
                                                2. <Book 2>  
                                                3. <Book 3>  
                                                4. <Book 4>
                                                5. <Book 5>
                                                """},
                {"role": "user", "content": prompt}
            ]
        )
        logging.warning(response)
        analysis = response.choices[0].message.content.strip()

        return analysis