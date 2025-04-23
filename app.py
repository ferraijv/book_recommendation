from flask import Flask, request, render_template, redirect, url_for, flash, abort
import openai
import os
import boto3
import json
from openai import OpenAI
import logging
import requests
from markdown2 import markdown, Markdown
import yaml
import time
from flask_sitemap import Sitemap
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin, current_user, login_required
from utils.db_utils import db, User, Book, UserBook, ReaderProfile
from contextlib import contextmanager
from utils.blog_utils import load_blog_posts
from utils.gemini_utils import set_obscurity, create_prompt, get_book_recommendations, get_reader_profile_recommendations
from utils.config_utils import get_secrets
from utils.spotify_utils import get_audiobook_details, search_spotify_podcasts
from sqlalchemy.sql.expression import func
from werkzeug.utils import secure_filename
import csv
from flask import request, jsonify, send_from_directory
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import re
from google import genai


from flask import Flask, render_template, request, abort


import logging


def get_book_metadata(title, author, google_books_api_key):
    """Fetch metadata for a book using Google Books API."""

    # If not found in DB, fetch from Google Books API
    api_key = google_books_api_key
    base_url = "https://www.googleapis.com/books/v1/volumes"
    query = f"intitle:{title}+inauthor:{author}"

    params = {
        "q": query,
        "key": api_key,
        "maxResults": 1
    }

    try:
        response = requests.get(base_url, params=params)
        logging.warning(response.status_code)
        if response.status_code == 200:
            logging.warning("Response is 200")
            data = response.json()
            logging.warning(data)
            if 'items' in data:
                book = data['items'][0]['volumeInfo']
                metadata = {
                    "title": book.get("title"),
                    "authors": book.get("authors"),
                    "description": book.get("description"),
                    "categories": book.get("categories"),
                    "publishedDate": book.get("publishedDate"),
                    "pageCount": book.get("pageCount"),
                    "thumbnail": book.get("imageLinks", {}).get("thumbnail"),
                    "isbn": str(next((identifier.get("identifier") for identifier in book.get("industryIdentifiers", []) if identifier.get("type") == "ISBN_13"), ""))
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
gemini_api_key_raw = get_secrets("gemini_api_key")
google_books_api_key_raw = get_secrets("google_books_api")
postgres_url = get_secrets("postgres_url")['postgres_url']
flask_secret_key = get_secrets("flask_secret_key")['flask_secret_key']
spotify_credentials = get_secrets("spotify_credentials")

# Extract the OpenAI API key from the secret
openai_api_key = openai_api_key_raw['api_key']
google_books_api_key = google_books_api_key_raw['api_key']

"""
client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=openai_api_key,
)
"""

client = genai.Client(api_key=gemini_api_key_raw['gemini_api_key'])

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = postgres_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = flask_secret_key

db.init_app(app)

sitemap = Sitemap(app=app)
app.config['SITEMAP_URL_SCHEME'] = "https"

def generate_slug(title):
    """Generate a slug from the book title"""
    return re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-')

app.jinja_env.filters['generate_slug'] = generate_slug


@app.route("/", methods=["GET", "POST"])
def index():
    recommendations = ""
    recommendations_html = ""
    books = None
    book_details = None
    all_book_metadata = []
    if request.method == "POST":
        user_input = request.form.get("preferences")
        obscurity_level = int(request.form.get("obscurity", 5))  # Get obscurity, default to 5
        if user_input:
            user_input = user_input[:500]  # Limit input to avoid large charges
            user_profile = create_prompt(obscurity_level, user_input)

            try:

                recommendations = get_book_recommendations(user_profile, client)

                logging.warning(recommendations)

                for book in recommendations:
                    logging.warning(book)
                    title = book["title"]
                    author = book["author"]
                    description = book["description"]
                    reason = book["reason"]

                    book_details = get_book_metadata(title, author, google_books_api_key)
                    book_details["amazon_link"] = get_amazon_search_link(title, author)
                    book_details["reason"] = reason
                    if book_details.get("title"):
                        logging.warning(f"Adding book to all_book_metadata: {book_details}")
                        all_book_metadata.append(book_details)


            except Exception as e:
                recommendations = f"Error: {e}"

    return render_template("index.html", all_book_metadata=all_book_metadata)


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/reader-profile", methods=["GET"])
def reader_profile_form():
    return render_template("reader_profile_input.html")


@app.route("/generate-reader-profile", methods=["POST"])
def generate_reader_profile():
    # Get user input from the form
    genres = request.form.get("genres", "")[:500]
    favorite_books = request.form.get("favorite_books", "")[:500]
    favorite_authors = request.form.get("favorite_authors", "")[:500]
    reading_goals = request.form.get("reading_goals", "")[:500]
    themes_to_avoid = request.form.get("themes_to_avoid", "")[:500]
    mbti = request.form.get("mbti", "")[:500]

    all_book_metadata = []

    try:
        # Prepare input data for the API
        reader_profile_details = {
            "genres": genres,
            "favorite_books": favorite_books,
            "favorite_authors": favorite_authors,
            "reading_goals": reading_goals,
            "themes_to_avoid": themes_to_avoid,
            "mbti": mbti
        }
        
        # Call the ChatGPT API with the input data
        analysis = get_reader_profile_recommendations(reader_profile_details, client)
        logging.warning(f"Raw API Response: {analysis}")
        
        # Parse the structured JSON response
        reader_profile = analysis
        
        # Extract components for rendering
        personality_type = reader_profile.get("personality_type", "Unknown")
        description = reader_profile.get("description", "No description provided.")
        traits = reader_profile.get("traits", [])
        suggested_books = reader_profile.get("suggested_books", [])

        # Fetch metadata for each suggested book
        for book in suggested_books:
            try:
                title = book.get("title", "Unknown Title")
                author = book.get("author", "Unknown Author")
                reason = book.get("reason", "No reason provided")

                book_details = get_book_metadata(title, author, google_books_api_key)
                book_details["amazon_link"] = get_amazon_search_link(title, author)
                book_details["reason"] = reason
                if book_details.get("title"):
                    all_book_metadata.append(book_details)
            except Exception as e:
                logging.error(f"Error fetching metadata for book '{title}': {str(e)}")

        logging.warning(f"All Metadata: {all_book_metadata}")
        # Render the template with the parsed data
        return render_template(
            "reader_profile_output.html",
            personality_type=personality_type,
            description=description,
            traits=traits,
            all_book_metadata=all_book_metadata,
        )
    except Exception as e:
        raise Exception(f"Error generating reader profile: {str(e)}")



@app.route("/blog")
def blog_index():
    posts = load_blog_posts()
    return render_template("blog_index.html", posts=posts)

@sitemap.register_generator
def blog_post_generator():
    posts = load_blog_posts()
    for post in posts:
        yield 'blog_post', {'post_title': post["metadata"]["title"].replace(" ", "-").lower()}


@sitemap.register_generator
def static_page_generator():
    routes = [
        ('index', {}),  # Root route ("/")
        ('blog_index', {}),
        ('about', {}),
        ('reader_profile_form', {}),
        ('community', {}),
    ]
    for route in routes:
        print(f"Adding static route to sitemap: {route}")
        yield route

@app.route("/blog/<post_title>")
def blog_post(post_title):
    posts = load_blog_posts()
    post = next((p for p in posts if p["metadata"]["title"].replace(" ", "-").lower() == post_title.lower()), None)
    if not post:
        abort(404)
    return render_template("blog_post.html", post=post)



@app.route('/book/<string:title_slug>-<string:isbn>')
def book_page(title_slug, isbn):
    return render_template('404.html'), 404

@app.route('/book/<string:isbn>')
def old_book_page(isbn):
    return render_template('404.html'), 404

@app.route('/under_construction')
def under_construction():
    return render_template('under_construction.html')

@app.route('/search', methods=['GET', 'POST'])
def search():
    return render_template('404.html'), 404

@app.route('/community', methods=['GET', 'POST'])
def community():
    return render_template('404.html'), 404

# Directory to store uploaded files (temporary)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route('/autocomplete', methods=['GET'])
def autocomplete():
    query = request.args.get('query', '').strip().lower()
    if not query:
        return jsonify([])

    results = (
        Book.query
        .filter(Book.search_data.op('@@')(func.plainto_tsquery('english', query)))
        .limit(10)
        .all()
    )

    return jsonify([
        {"title": book.title, "author": book.author, "isbn": book.isbn}
        for book in results
    ])

@app.route("/robots.txt")
def robots_txt():
    return send_from_directory(os.path.abspath(os.path.dirname(__file__)), "robots.txt", mimetype="text/plain")


if __name__ == "__main__":
    app.run(debug=True)
