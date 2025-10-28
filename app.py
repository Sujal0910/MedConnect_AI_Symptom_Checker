import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_bcrypt import Bcrypt
from openai import OpenAI
import click

# --- App Initialization ---
load_dotenv()
app = Flask(__name__)

# --- Configuration ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_very_strong_default_secret_key_123')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///medconnect.db'
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
MODEL_NAME = "openrouter/andromeda-alpha" # Or any other model

# --- Extensions ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'danger' # For styling flash messages

# --- Database Models ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False) # FIXED: Was 'username'
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(150), nullable=False)
    chats = db.relationship('ChatHistory', backref='author', lazy=True)

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(10), nullable=False) # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

# --- Flask-Login User Loader ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Database Initialization Command ---
@app.cli.command('init-db')
def init_db_command():
    """Clears existing data and creates new tables."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        click.echo('Initialized the database.')

# --- AI Chat Function ---
def get_openrouter_response(chat_history):
    try:
        client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
        )
        
        system_prompt = {
            'role': 'system',
            'content': (
                "You are 'MedConnect AI', a helpful symptom checker. "
                "Your goal is to provide preliminary information based on user-described symptoms. "
                "You must be caring, clear, and safe. "
                "IMPORTANT: You are an AI, not a doctor. You MUST end every single response with a clear disclaimer "
                "advising the user to consult a qualified medical professional for a real diagnosis."
            )
        }
        
        messages_to_send = [system_prompt] + chat_history

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages_to_send,
            max_tokens=1024,
        )
        
        if response.choices and response.choices[0].message.content:
            return response.choices[0].message.content.strip()
        else:
            return "Sorry, I couldn't get a response. Please try again."

    except Exception as e:
        print(f"An error occurred while contacting OpenRouter: {e}")
        return "Sorry, I'm having trouble connecting to my brain right now. Please try again later."

# --- Main Routes ---

@app.route('/')
@login_required
def index():
    # Main chat page
    return render_template('index.html')

# --- Authentication Routes ---

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')

        # Check if user already exists
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('An account with this email already exists. Please login.', 'danger')
            return redirect(url_for('login')) # FIXED: This line had the wrong indentation
        
        # Create new user
        new_user = User(
            email=email,
            name=name, # FIXED: Was 'username=name'
            password_hash=bcrypt.generate_password_hash(password).decode('utf-8')
        )
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Account created successfully! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error creating account: {e}', 'danger')
            return render_template('signup.html')

    return render_template('signup.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        user = User.query.filter_by(email=email).first()

        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Login unsuccessful. Please check email and password.', 'danger')

    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

# --- Chat API Routes ---

@app.route('/api/get_history')
@login_required
def get_history():
    history = ChatHistory.query.filter_by(user_id=current_user.id).all()
    history_list = [{'role': chat.role, 'content': chat.content} for chat in history]
    return jsonify(history_list)

@app.route('/api/ask', methods=['POST'])
@login_required
def ask():
    data = request.json
    user_message = data.get('message')

    if not user_message:
        return jsonify({'error': 'No message provided'}), 400

    # Add user message to DB
    db.session.add(ChatHistory(role='user', content=user_message, user_id=current_user.id))
    db.session.commit()

    # Get full chat history for context
    history = ChatHistory.query.filter_by(user_id=current_user.id).all()
    history_list = [{'role': chat.role, 'content': chat.content} for chat in history]

    # Get AI response
    ai_answer = get_openrouter_response(history_list)

    # Add AI response to DB
    db.session.add(ChatHistory(role='assistant', content=ai_answer, user_id=current_user.id))
    db.session.commit()

    return jsonify({'answer': ai_answer})

# --- Main execution ---
if __name__ == '__main__':
    app.run(debug=True)

