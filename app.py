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
from utils.prompt_utils import set_obscurity, create_prompt, get_book_recommendations, get_reader_profile_recommendations
from utils.config_utils import get_secrets
from sqlalchemy.sql.expression import func
from werkzeug.utils import secure_filename
import csv


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
    book = Book.query.filter(
        Book.title.ilike(f"%{title}%"),
        Book.author.ilike(f"%{author}%")  # Case-insensitive partial match
    ).first()
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
    recommendations_html = ""
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
                    if book_details.get("isbn"):
                        logging.warning(f"Adding book to all_book_metadata: {book_details}")
                        all_book_metadata.append(book_details)


            except Exception as e:
                recommendations = f"Error: {e}"

    popular_books = (
    db.session.query(Book, func.count(UserBook.book_isbn).label('book_count'))
    .join(UserBook, Book.isbn == UserBook.book_isbn)
    .group_by(Book)
    .order_by(func.count(UserBook.book_isbn).desc())
    .limit(5)
    .all())

    return render_template("index.html", all_book_metadata=all_book_metadata, popular_books=popular_books)


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

    all_book_metadata = []
    try:
        reader_profile_details = {
            "genres": genres,
            "favorite_books": favorite_books,
            "reading_frequency": reading_frequency,
            "format": format,
            "reading_goals": reading_goals,
            "themes_to_avoid": themes_to_avoid,
            "mbti": mbti
        }
        analysis = get_reader_profile_recommendations(reader_profile_details, client)
        logging.info(analysis)
        analysis_html = markdown(analysis)  # Converts Markdown to HTML
        logging.info(analysis_html)
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
        shareable_text=analysis,
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
    read_books = [user_book for user_book in user_books if user_book.status == 'read' and user_book.rating is not None]
    average_rating = sum(user_book.rating for user_book in read_books) / len(read_books) if read_books else 0
    return render_template('my_account.html', user=current_user, user_books=user_books, book_count=len(user_books), average_rating=average_rating)

@app.route('/book/<string:isbn>')
def book_page(isbn):
    # Get main book
    book = Book.query.get_or_404(isbn)
    
    # Get similar books based on categories
    similar_books = []
    if book.categories:
        # Use the first category from the array
        main_category = book.categories[0]
        similar_books = Book.query.filter(
            Book.categories.op('&&')([main_category]),  # Check if the array overlaps with the main category
            Book.isbn != isbn  # Exclude current book
        ).order_by(func.random()).limit(5).all()
    
    
    return render_template('book.html', book=book, similar_books=similar_books)

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

    title = request.form.get("title", None)
    author = request.form.get("author", None)

    all_book_metadata = []  # Initialize an empty results list

    logging.warning(f"title: {title}, author: {author}")

    if title and author:  

        all_book_metadata = [get_book_metadata(title=title, author=author, google_books_api_key=google_books_api_key)]
        logging.warning(all_book_metadata)

    logging.warning(all_book_metadata)

    return render_template('search.html', title=title, author=author, all_book_metadata=all_book_metadata)

# Directory to store uploaded files (temporary)
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Ensure the upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def add_book_to_user(title, author, status, isbn, rating):
    logging.info(f"Adding book: {title}, {author}, {status}, {isbn}, {rating}")

    user_book = UserBook.query.filter_by(user_id=current_user.id, book_isbn=isbn).first()
    book = Book.query.get(str(isbn))

    if not book:
        # Add book to database
        book_details = get_book_metadata(title=title, author=author, google_books_api_key=google_books_api_key)

    if not user_book and book:  # We have book metadata but no user book
        user_book = UserBook(user_id=current_user.id, book_isbn=isbn, status=status, rating=rating)
        db.session.add(user_book)
        db.session.commit()  # Save the book to the databas

    logging.info(f"Adding book: {title}, {author}, {status}, {isbn}, {rating}")


def map_goodreads_rating_to_text(goodreads_rating, custom_map=None):
    # Default mapping
    default_map = {
        1: "Hated it",
        2: "Didn't like it",
        3: "It was OK",
        4: "Liked it",
        5: "Loved it"
    }

    # Use the custom map if provided
    rating_map = custom_map or default_map

    # Return the corresponding text
    return rating_map.get(goodreads_rating, "No rating")


@app.route('/upload_csv', methods=['POST'])
def upload_csv():
    logging.info("Processing CSV upload")
    if 'goodreads_csv' not in request.files:
        flash('No file part')
        return redirect(url_for('my_account'))

    file = request.files['goodreads_csv']

    if file.filename == '':
        flash('No selected file')
        return redirect(url_for('my_account'))


    if file and allowed_file(file.filename):
        logging.info("File is valid")
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)

        # Process the CSV file
        books_to_add = []
        user_books_to_add = []
        try:
            with open(filepath, newline='', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)

                for row in reader:
                    logging.warning(f"Processing row: {row}")
                    title = row.get('Title')
                    author = row.get('Author')
                    goodreads_status = row.get('Exclusive Shelf')
                    status = 'read' if goodreads_status == 'read' else 'want_to_read' if goodreads_status == 'to-read' else None
                    isbn = str(row.get('ISBN13').replace('=', '').replace('"', '').strip())
                    rating = int(row.get('My Rating'))
                    rating = map_goodreads_rating_to_text(goodreads_rating=rating)

                    # Check if book exists in database
                    book = Book.query.get(str(isbn))
                    if not book:
                        book_details = get_book_metadata(title=title, author=author, google_books_api_key=google_books_api_key)
                        book = Book(
                            isbn=isbn,
                            title=book_details.get('title', title),
                            author=book_details.get('authors', author),
                            description=book_details.get('description', None),
                            published_date=book_details.get('publishedDate', None),
                            page_count=book_details.get('pageCount', 0),
                            thumbnail=book_details.get('thumbnail', None),
                            categories=book_details.get('categories', [])
                        )
                        books_to_add.append(book)

                    user_book = UserBook.query.filter_by(user_id=current_user.id, book_isbn=isbn).first()
                    if not user_book:
                        user_books_to_add.append(UserBook(
                            user_id=current_user.id,
                            book_isbn=isbn,
                            status=status,
                            rating=rating
                        ))

                            # Batch insert
                if books_to_add:
                    db.session.bulk_save_objects(books_to_add)
                    logging.info(f"Added {len(books_to_add)} new books to the database.")

                if user_books_to_add:
                    db.session.bulk_save_objects(user_books_to_add)
                    logging.info(f"Added {len(user_books_to_add)} new user-book relationships.")

                db.session.commit()
                flash(f"Books successfully imported! {len(user_books_to_add)} books added to your library.", 'success')
        except Exception as e:
            db.session.rollback()
            logging.error(f"Error processing CSV file: {str(e)}")
            flash(f"Error processing CSV file: {str(e)}", 'error')
        finally:
            # Clean up the temporary file
            if os.path.exists(filepath):
                os.remove(filepath)
            return redirect(url_for('my_account'))


if __name__ == "__main__":
    app.run(debug=True)
