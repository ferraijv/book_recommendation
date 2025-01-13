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
