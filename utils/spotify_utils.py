import requests
from base64 import b64encode
import logging
from difflib import SequenceMatcher

# Function to get Spotify token
def get_spotify_token(client_id, client_secret):
    url = "https://accounts.spotify.com/api/token"
    headers = {
        "Authorization": f"Basic {b64encode(f'{client_id}:{client_secret}'.encode()).decode()}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    data = {"grant_type": "client_credentials"}
    response = requests.post(url, headers=headers, data=data)
    if response.status_code == 200:
        return response.json().get("access_token")
    else:
        logging.error(f"Failed to get token: {response.status_code} - {response.text}")
        return None


def filter_by_language(results, language="en"):
    """
    Filter results to include only those in the specified language.
    Args:
        results (list): List of audiobook results from Spotify API.
        language (str): Desired language code (default is "en").
    Returns:
        list: Filtered results in the specified language.
    """
    logging.warning([result.get("languages") for result in results])
    return [result for result in results if language in result.get("language")]


def search_spotify_audiobooks(title, author=None, access_token=None):
    url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {access_token}"}
    query = f'"{title}"'  # Wrap title in quotes for exact match
    if author:
        query += f" {author}"
    params = {
        "q": query,
        "type": "audiobook",
        "limit": 10,  # Fetch more results to filter later
        "market": "US"  # Restrict to a specific market for language consistency
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        return response.json().get("audiobooks", {}).get("items", [])
    else:
        return []

# Utility function to check similarity
def is_match(query, result, threshold=0.4):
    if query in result:
        return True
    else:
        return SequenceMatcher(None, query.lower(), result.lower()).ratio() >= threshold

# Function to filter results by language, title, and author
def filter_audiobooks(results, book_title, book_author, language="en"):
    for result in results:
        # Check for language match
        if language not in result.get("languages", []):
            continue

        # Check for title match
        title_match = is_match(book_title, result["name"])

        # Check for author match
        author_match = any(is_match(book_author, author["name"]) for author in result.get("authors", []))

        if title_match and author_match:
            return result  # Return the first matching result
    return None

# Main function to get audiobook details
def get_audiobook_details(spotify_client_id, spotify_client_secret, book_title, book_author):
    logging.warning(f"Searching for audibook title: {book_title} author: {book_author}")
    try:
        token = get_spotify_token(spotify_client_id, spotify_client_secret)
        audiobooks = search_spotify_audiobooks(book_title, book_author, token)
        logging.warning(f"Audibooks before filtering: {audiobooks}")
        return filter_audiobooks(audiobooks, book_title, book_author, language="en")
    except Exception as e:
        print(f"Error fetching Spotify audiobook: {e}")
        return None


def search_spotify_podcasts(title, author, spotify_client_id, spotify_client_secret, language="en", limit=3):
    """
    Search Spotify for podcast episodes related to a given title.
    Args:
        title (str): The book title to search for.
        access_token (str): Spotify API access token.
        language (str): Language filter (default is "en").
        limit (int): Number of episodes to retrieve (default is 5).
    Returns:
        list: A list of relevant podcast episodes.
    """
    token = get_spotify_token(spotify_client_id, spotify_client_secret)
    url = "https://api.spotify.com/v1/search"
    headers = {"Authorization": f"Bearer {token}"}
    query = title + f" {author}"
    params = {
        "q": query,  # Use the book title as the query
        "type": "episode",
        "limit": limit,
        "market": "US",  # Restrict results to the US market for English content
    }
    response = requests.get(url, headers=headers, params=params)
    if response.status_code == 200:
        episodes = response.json().get("episodes", {}).get("items", [])
        # Filter episodes by language if applicable
        if language:
            episodes = [ep for ep in episodes if language in ep.get("languages", ["en"])]
        return episodes
    else:
        logging.error(f"Failed to fetch podcasts: {response.status_code} - {response.text}")
        return []
