from flask import Flask, request, render_template, redirect, url_for
import openai
import os
import boto3
import json
from openai import OpenAI
import logging
import requests
from markdown2 import markdown, Markdown
import yaml

def get_secrets(secret_name) -> dict:
    """Retrieves secrets based on the environment."""
    try:
        if "RENDER" in os.environ:  # Check if running on Render
            logging.info("Running on Render, using secret files")
            secrets_path = f"/etc/secrets/{secret_name}.json"
            try:
                with open(secrets_path, "r") as f:
                    secrets = json.load(f)
                    return secrets
            except (FileNotFoundError, json.JSONDecodeError) as e:
                logging.error(f"Error reading Render secrets: {e}")
                return None
        else:  # Running locally
            logging.info("Running locally, using AWS Secrets Manager")
            region_name = os.environ.get("AWS_REGION", "us-east-1") # get region from env if available otherwise default
            try:
                session = boto3.session.Session()
                client = session.client(
                    service_name='secretsmanager',
                    region_name=region_name
                )
                get_secret_value_response = client.get_secret_value(SecretId=secret_name)
                secret = get_secret_value_response['SecretString']
                return json.loads(secret)
            except Exception as e:
                logging.error(f"Error retrieving AWS secret: {e}")
                return None
    except Exception as e:
        logging.exception("A top level exception occurred")
        return None
from flask import Flask, render_template, request, abort

BLOG_DIR = "blog/posts"
def load_blog_posts():
    posts = []
    for filename in os.listdir(BLOG_DIR):
        if filename.endswith(".md"):
            with open(os.path.join(BLOG_DIR, filename), "r") as file:
                content = file.read()
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    metadata = yaml.safe_load(parts[1])
                    html_content = markdown(parts[2].strip())
                    posts.append({"metadata": metadata, "content": html_content})

    logging.warning(posts)
    return sorted(posts, key=lambda x: x["metadata"]["date"], reverse=True)
def get_book_metadata(title, author):
    """Fetch metadata for a book using Google Books API."""
    api_key = os.getenv("GOOGLE_BOOKS_API_KEY")  # Fetch API key from environment variables
    base_url = "https://www.googleapis.com/books/v1/volumes"

    # Construct query for title and author
    query = f"intitle:{title}+inauthor:{author}"
    params = {
        "q": query,
        "key": api_key,
        "maxResults": 1
    }

    try:
        response = requests.get(base_url, params=params)
        if response.status_code == 200:
            data = response.json()
            if 'items' in data:
                book = data['items'][0]['volumeInfo']
                metadata = {
                    "title": book.get("title"),
                    "authors": book.get("authors"),
                    "description": book.get("description"),
                    "categories": book.get("categories"),
                    "publishedDate": book.get("publishedDate"),
                    "pageCount": book.get("pageCount"),
                    "thumbnail": book.get("imageLinks", {}).get("thumbnail")
                }
                return metadata
        return {"error": "No book data found"}
    except Exception as e:
        return {"error": str(e)}

def get_amazon_search_link(title, author):
    """Generate a basic Amazon search link using the book title and author."""
    base_url = "https://www.amazon.com/s"
    query = f"{title} {author}".replace(" ", "+")
    return f"{base_url}?k={query}&tag=bookrecom0e1f-20"  # TODO parameterize the tag


# Example usage (in your main app code):
openai_api_key_raw = get_secrets("openai_api_key")
google_books_api_key_raw = get_secrets("google_books_api")

# Extract the OpenAI API key from the secret
openai_api_key = openai_api_key_raw['api_key']
google_books_api_key = google_books_api_key_raw['api_key']

client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=openai_api_key,
)

# Initialize Flask app
app = Flask(__name__)

def create_prompt(obscurity_level, user_input, mbti):
    prompt = f"""
    "MBTI": {mbti},
    "Obscurity_level": {obscurity_level},
    "Preferences: {user_input} 
    """

    return prompt

def set_obscurity(obscurity_level):
    # Adjust the prompt based on obscurity_level
    if obscurity_level <= 3:
        prompt_obscurity_modifier = "The user wants highly popular books "
    elif obscurity_level >= 8:
        prompt_obscurity_modifier = "The user wants rare or obscure books "
    else:
        prompt_obscurity_modifier = ""
        
    return prompt_obscurity_modifier

def identify_books(text):
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": """
            You are a helpful assistant providing book recommendations. For each recommendation, Provide the book recommendations in the following JSON format:
            [
              {"title": "<book title>", "author": "<author name>"},
              {"title": "<book title>", "author": "<author name>"},
              ...
            ]"""},
            {"role": "user", "content": f"Identify the books mentioned below and return results: {text}"}
        ]
    )
    logging.warning(response)
    response_content = response.choices[0].message.content
    books = json.loads(response_content.strip("```json").strip())

    return books

@app.route("/", methods=["GET", "POST"])
def index():
    recommendations = ""
    books = None
    book_details = None
    all_book_metadata = []
    if request.method == "POST":
        user_input = request.form.get("preferences")
        mbti = request.form.get("MBTI")
        obscurity_level = int(request.form.get("obscurity", 5))  # Get obscurity, default to 5
        if user_input:
            user_input = user_input[:500]  # Limit input to avoid large charges
            user_profile = create_prompt(obscurity_level, user_input, mbti)

            try:
                # Call ChatGPT for book recommendations
                response = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=[
                        {"role": "system", "content": "You are a helpful assistant providing book recommendations. Return list book recommendations based on the user profiles. Return 5 book recommendations"},
                        {"role": "user", "content": f"User profile: {user_profile}"}
                    ]
                )
                logging.warning(response)
                recommendations = response.choices[0].message.content.strip()

                books = identify_books(recommendations)

                logging.warning(books)

                for book in books:
                    logging.warning(book)
                    title = book["title"]
                    author = book["author"]

                    book_details = get_book_metadata(title, author)
                    book_details["amazon_link"] = get_amazon_search_link(title, author)
                    if book_details:
                        all_book_metadata.append(book_details)
                    logging.warning(book_details)

            except Exception as e:
                recommendations = f"Error: {e}"

    return render_template("index.html", all_book_metadata=all_book_metadata, recommendations=recommendations)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/reader-profile", methods=["GET"])
def reader_profile_form():
    return render_template("reader_profile_input.html")

@app.route("/generate-reader-profile", methods=["POST"])
def generate_reader_profile():
    # Get user input from the form
    genres = request.form.get("genres")[:500]
    favorite_books = request.form.get("favorite_books")[:500]
    reading_frequency = request.form.get("reading_frequency")[:500]
    format = request.form.get("format")[:500]
    reading_goals = request.form.get("reading_goals")[:500]
    themes_to_avoid = request.form.get("themes_to_avoid")[:500]
    mbti = request.form.get("mbti")  # Optional field

    # Prepare the ChatGPT prompt
    prompt = f"""
    Analyze the following reading preferences and habits, and create a fun, sharable "Reader Personality" profile:
    - Favorite Genres: {genres}
    - Favorite Books: {favorite_books}
    - Reading Frequency: {reading_frequency}
    - Preferred Format: {format}
    - Reading Goals: {reading_goals}
    - Themes to avoid {themes_to_avoid if themes_to_avoid else "None"}
    - MBTI: {mbti if mbti else "Not provided"}

    Categorize the user's "Reader Personality" (e.g., "The Book Adventurer", "The Cozy Reader", etc.), describe their traits, and suggest books or themes that align with their profile.
    """
    logging.warning(prompt)
    all_book_metadata = []
    try:
        # Call the ChatGPT API
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": """Analyze the following reading preferences and habits, and create a "Reader Personality" profile. Don't include books they've already read in their suggestions. Return the output in structured Markdown format like this:

                                                **Reader Personality Profile**: <Personality Name>  
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
        analysis = response.choices[0].message.content.strip()
        logging.warning(analysis)
        analysis_html = markdown(analysis)  # Converts Markdown to HTML
        logging.warning(analysis_html)
    except Exception as e:
        analysis = f"Error generating profile: {str(e)}"
        analysis_html = None

    books = identify_books(analysis)

    shareable_text = analysis

    for book in books:
        logging.warning(book)
        title = book["title"]
        author = book["author"]

        book_details = get_book_metadata(title, author)
        book_details["amazon_link"] = get_amazon_search_link(title, author)
        book_details["ga_event"] = f"Outbound Link: {title}"
        if book_details.get("title"):
            all_book_metadata.append(book_details)
        logging.warning(book_details)

    # Render the output page with the analysis
    return render_template(
        "reader_profile_output.html",
        analysis_html=analysis_html,
        shareable_text=shareable_text,
        all_book_metadata=all_book_metadata
    )

@app.route("/blog")
def blog_index():
    posts = load_blog_posts()
    return render_template("blog_index.html", posts=posts)

@app.route("/blog/<post_title>")
def blog_post(post_title):
    posts = load_blog_posts()
    post = next((p for p in posts if p["metadata"]["title"].replace(" ", "-").lower() == post_title.lower()), None)
    if not post:
        abort(404)
    return render_template("blog_post.html", post=post)

if __name__ == "__main__":
    app.run(debug=True)
