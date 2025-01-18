from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'user'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    read_books = db.relationship('UserBook', back_populates='user')  # Define the relationship


    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password, method='pbkdf2:sha256')

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class Book(db.Model):
    __tablename__ = 'book'
    isbn = db.Column(db.String(13), primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    author = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text, nullable=True)
    published_date = db.Column(db.String(50), nullable=True)
    page_count = db.Column(db.Integer, nullable=True)
    thumbnail = db.Column(db.String(300), nullable=True)
    categories = db.Column(db.String(200), nullable=True)
    read_by_users = db.relationship('UserBook', back_populates='book')  # Define the relationship


    def __repr__(self):
        return f"<Book ISBN={self.isbn}, Title={self.title}>"

class UserBook(db.Model):
    __tablename__ = 'user_books'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    book_isbn = db.Column(db.String(13), db.ForeignKey('book.isbn'), nullable=False)
    rating = db.Column(db.String(13), nullable=True)
    status = db.Column(db.String(20), nullable=False, default="want_to_read")
    timestamp = db.Column(db.DateTime, default=db.func.current_timestamp())
    user = db.relationship('User', back_populates='read_books')
    book = db.relationship('Book', back_populates='read_by_users')