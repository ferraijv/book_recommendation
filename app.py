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
from utils.db_utils import db, User, Book, UserBook
from contextlib import contextmanager
from utils.blog_utils import load_blog_posts
from utils.prompt_utils import set_obscurity, create_prompt
from utils.config_utils import get_secrets


from flask import Flask, render_template, request, abort


import logging


def add_or_update_book(data):
    """
    Adds a new book or updates an existing book in the database.

    Args:
        data (dict): A dictionary containing book details, including:
                     - isbn (required)
                     - title (required)
                     - author (required)
                     - description (optional)
                     - published_date (optional)
                     - page_count (optional)
                     - thumbnail (optional)

    Returns:
        Book: The added or updated Book object.
    """
    logging.warning("Starting add_or_update_book")
    isbn = data.get('isbn')
    if isbn and (not isbn.isdigit() or len(isbn) != 13):
        logging.error("ISBN must be a 13-digit number")
        return None
    if not isbn:
        logging.error("ISBN is required to add a book")
        return None
    if not data.get('title'):
        logging.error("Title is required to add a book")
        return None
    if not data.get('authors'):
        logging.error("Author is required to add a book")
        return None

    try:
        # Check if the book already exists
        book = Book.query.get(str(isbn))  # Ensure ISBN is passed as a string
        if not book:
            logging.info(f"Adding new book with ISBN: {isbn}")
            book = Book(isbn=isbn)
        else:
            logging.info(f"Updating existing book with ISBN: {isbn}")

        # Update book details
        book.title = data.get('title')
        book.author = data.get('authors')
        book.description = data.get('description', "No description available.")
        book.published_date = data.get('publishedDate')
        book.page_count = data.get('pageCount', 0)  # Default to 0 if not provided
        book.thumbnail = data.get('thumbnail', None)
        book.categories = data.get('categories', None)

        db.session.add(book)
        db.session.commit()
        return book
    except Exception as e:
        logging.error(f"Failed to add/update book with ISBN: {isbn}. Error: {str(e)}")
        raise


def get_book_metadata(title, author, google_books_api_key):
    """Fetch metadata for a book using Google Books API."""
    # First check if book exists in database by title and author
    book = Book.query.filter_by(title=title, author=author).first()
    if book:
        # Return existing book metadata
        return {
            "title": book.title,
            "authors": book.author,
            "description": book.description,
            "categories": book.categories,
            "publishedDate": book.published_date,
            "pageCount": book.page_count,
            "thumbnail": book.thumbnail,
            "isbn": book.isbn
        }

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
                add_or_update_book(metadata)
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
postgres_url = get_secrets("postgres_url")['postgres_url']
flask_secret_key = get_secrets("flask_secret_key")['flask_secret_key']

# Extract the OpenAI API key from the secret
openai_api_key = openai_api_key_raw['api_key']
google_books_api_key = google_books_api_key_raw['api_key']

client = OpenAI(
    # defaults to os.environ.get("OPENAI_API_KEY")
    api_key=openai_api_key,
)

# Initialize Flask app
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = postgres_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = flask_secret_key

db.init_app(app)

sitemap = Sitemap(app=app)
app.config['SITEMAP_URL_SCHEME'] = "https"

from flask_login import LoginManager

login_manager = LoginManager()
login_manager.login_view = 'login'  # Redirect unauthorized users to the login page

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))  # No explicit transaction management


login_manager.init_app(app)


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
                        {"role": "system",
                         "content": "You are a helpful assistant providing book recommendations. Return list book recommendations based on the user profiles. Return 5 book recommendations"},
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

                    book_details = get_book_metadata(title, author, google_books_api_key)
                    book_details["amazon_link"] = get_amazon_search_link(title, author)
                    if book_details.get("isbn"):
                        logging.warning(f"Adding book to all_book_metadata: {book_details}")
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

        book_details = get_book_metadata(title, author, google_books_api_key)
        book_details["amazon_link"] = get_amazon_search_link(title, author)
        book_details["ga_event"] = f"Outbound Link: {title}"
        if book_details.get("isbn"):
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

@app.route("/community")
def community():
    return render_template("community.html")

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(email=email).first():
            return "Email already registered!"
        
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))

    return render_template('register.html')

from flask_login import login_user

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        
        if user and user.check_password(password):
            login_user(user, remember=True)
            flash('Logged in successfully.')
            return redirect(url_for('index'))
        else:
            return "Invalid credentials!"
    
    return render_template('login.html')

from flask_login import logout_user

@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/my_account')
@login_required
def my_account():
    user_books = UserBook.query.filter_by(user_id=current_user.id).all()
    return render_template('my_account.html', user=current_user, user_books=user_books)

@app.route('/book/<string:isbn>')
def book_page(isbn):
    # Fetch the book from the database by ISBN
    book = Book.query.get_or_404(isbn)
    return render_template('book.html', book=book)


@app.route('/read_books', methods=['GET'])
@login_required
def read_books():
    # Fetch all UserBook entries for the current user
    user_books = UserBook.query.filter_by(user_id=current_user.id).all()
    return render_template('read_books.html', user_books=user_books)


@app.route('/under_construction')
def under_construction():
    return render_template('under_construction.html')


@app.route('/update_book_status/<string:isbn>', methods=['POST'])
@login_required
def update_book_status(isbn):
    # Get the book
    book = Book.query.get_or_404(isbn)

    # Get the selected status from the form
    status = request.form.get('status')

    # Find or create the UserBook entry
    user_book = UserBook.query.filter_by(user_id=current_user.id, book_isbn=isbn).first()
    if not user_book:
        user_book = UserBook(user_id=current_user.id, book_isbn=isbn)
        db.session.add(user_book)

    # Update the status
    user_book.status = status
    db.session.commit()

    flash(f'Status for "{book.title}" updated to "{status.replace("_", " ").title()}"!', 'success')
    return redirect(url_for('index'))  # Redirect back to the book list

@app.route('/search', methods=['GET', 'POST'])
def search():

    title = request.args.get("title", None)
    author = request.args.get("author", None)

    all_book_metadata = []  # Initialize an empty results list

    logging.warning(f"title: {title}, author: {author}")

    if title and author:  

        all_book_metadata = [get_book_metadata(title=title, author=author, google_books_api_key=google_books_api_key)]

    logging.warning(all_book_metadata)

    return render_template('search.html', title=title, author=author, all_book_metadata=all_book_metadata)


if __name__ == "__main__":
    app.run(debug=True)
