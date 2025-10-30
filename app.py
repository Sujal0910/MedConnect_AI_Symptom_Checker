import os
import markdown
import json # Import json for parsing AI responses
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from openai import OpenAI
from sqlalchemy.exc import IntegrityError
from datetime import datetime, time

# --- App Initialization ---
load_dotenv()
app = Flask(__name__)

# --- Configurations ---
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'a_very_strong_default_secret_key_12345')
# Use Flask's instance path for the database
instance_path = os.path.join(app.instance_path)
os.makedirs(instance_path, exist_ok=True)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(instance_path, 'medconnect.db')

# --- Extensions ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message_category = 'info'

# --- OpenRouter AI Client ---
OPENROUTER_API_KEY = os.environ.get('OPENROUTER_API_KEY')
client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)

# --- Database Models ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    chat_history = db.relationship('ChatHistory', backref='author', lazy=True, cascade="all, delete-orphan")
    reminders = db.relationship('Reminder', backref='author', lazy=True, cascade="all, delete-orphan")

    def __repr__(self):
        return f"User('{self.name}', '{self.email}')"

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(10), nullable=False) # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def __repr__(self):
        return f"ChatHistory('{self.role}', '{self.content[:20]}...')"

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    content_md = db.Column(db.Text, nullable=False)
    
    @property
    def content_html(self):
        return markdown.markdown(self.content_md)

    def __repr__(self):
        return f"Article('{self.title}', '{self.category}')"

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50), nullable=True)
    reminder_time = db.Column(db.Time, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def __repr__(self):
        return f"Reminder('{self.medicine_name}', '{self.reminder_time}')"
    
    def to_dict(self):
        return {
            'id': self.id,
            'medicine_name': self.medicine_name,
            'dosage': self.dosage,
            # Convert time to string in HH:MM AM/PM format
            'reminder_time': self.reminder_time.strftime('%I:%M %p')
        }


# --- Database Initialization Command ---

@app.cli.command('init-db')
def init_db_command():
    """Clears existing data and creates new tables, adding sample articles."""
    with app.app_context():
        db.drop_all()
        db.create_all()
        
        # Add sample articles
        articles = [
            Article(title="Understanding the Common Cold", category="Common Illness", content_md="""
**What is a common cold?**
The common cold is a viral infection of your nose and throat (upper respiratory tract). It's usually harmless, although it might not feel that way.

**Symptoms**
- Runny or stuffy nose
- Sore throat
- Cough
- Congestion
- Slight body aches or a mild headache
- Sneezing
- Low-grade fever

**What to do**
- **Rest:** Your body needs rest to heal.
- **Hydration:** Drink plenty of fluids like water, juice, and clear broth to prevent dehydration.
- **Symptom Relief:** Over-the-counter pain-relievers, decongestants, and cough syrups can help manage symptoms.

**Disclaimer:** This is for informational purposes only. Always consult a medical professional for diagnosis and treatment.
            """),
            Article(title="First Aid for Minor Burns", category="First Aid", content_md="""
**What is a minor burn?**
A minor burn (first-degree or mild second-degree) is one that is small (less than 3 inches), superficial, and does not cover a major joint or sensitive area like the face.

**Immediate Steps**
1.  **Cool Water:** Immediately run cool (not cold) tap water over the burn for 10-15 minutes or until the pain subsides.
2.  **Remove Jewelry:** Gently remove rings or other tight items from the burned area before it swells.
3.  **Cover:** Loosely cover the burn with a sterile gauze bandage.
4.  **Pain Relief:** Take an over-the-counter pain reliever like ibuprofen or acetaminophen if needed.

**What NOT to do**
- **Do NOT** use ice, as it can cause more skin damage.
- **Do NOT** apply butter, oils, or toothpaste to the burn.
- **Do NOT** break any blisters that form, as this can lead to infection.

**Disclaimer:** Seek immediate medical attention for any burns that are large, deep, on the face/hands/feet/genitals, or caused by chemicals or electricity.
            """),
            Article(title="What is a Fever?", category="Symptoms", content_md="""
**What is a fever?**
A fever is a temporary increase in your body temperature, often due to an illness. A fever is a sign that something out of the ordinary is going on in your body. For an adult, a fever may be uncomfortable, but it usually isn't a cause for concern unless it reaches 103 F (39.4 C) or higher.

**Common Causes**
- Viral infections (like the flu or a cold)
- Bacterial infections
- Some inflammatory conditions
- A reaction to a vaccine

**What to do**
- **Rest:** Get plenty of rest.
- **Hydration:** Drink lots of fluids to stay hydrated.
- **Medication:** Over-the-counter medications like acetaminophen or ibuprofen can help reduce a fever.

**Disclaimer:** While most fevers are harmless, you should consult a doctor if your fever is unusually high, lasts for more than a few days, or is accompanied by severe symptoms like a stiff neck, confusion, or difficulty breathing.
            """),
            Article(title="The Importance of Handwashing", category="Wellness", content_md="""
**Why is handwashing important?**
Handwashing is one of the easiest and most effective ways to prevent the spread of germs and stay healthy. Your hands touch many surfaces and can pick up germs, which can then be transferred to your eyes, nose, or mouth.

**When to Wash Your Hands**
- Before, during, and after preparing food
- Before eating
- After using the toilet
- After blowing your nose, coughing, or sneezing
- After touching garbage
- After touching an animal or animal waste

**How to Wash Your Hands**
1.  **Wet:** Wet your hands with clean, running water.
2.  **Lather:** Apply soap and lather your hands well. Be sure to get the backs of your hands, between your fingers, and under your nails.
3.  **Scrub:** Scrub your hands for at least **20 seconds**. (A good timer is humming the "Happy Birthday" song twice.)
4.  **Rinse:** Rinse your hands well under clean, running water.
5.  **Dry:** Dry your hands using a clean towel or air dryer.

**Disclaimer:** This is general health advice. Handwashing is a key part of hygiene but does not replace other medical advice.
            """),
            Article(title="Understanding Mild Sprains", category="First Aid", content_md="""
**What is a sprain?**
A sprain is a stretching or tearing of ligaments — the tough bands of fibrous tissue that connect two bones in your joints. The most common location for a sprain is in your ankle.

**Symptoms of a Mild Sprain**
- Pain
- Swelling
- Bruising
- Limited ability to move the joint

**The R.I.C.E. Method**
For the first 24-48 hours, the best treatment for a mild sprain is the R.I.C.E. approach:
- **Rest:** Avoid activities that cause pain.
- **Ice:** Apply an ice pack (wrapped in a thin towel) to the area for 15-20 minutes every 2-3 hours.
- **Compression:** Use an elastic compression bandage to help reduce swelling.
- **Elevation:** Elevate the injured joint above the level of your heart, especially at night.

**Disclaimer:** Seek medical advice if you cannot put weight on the joint or if the pain and swelling are severe or do not improve after 2-3 days.
            """),
            Article(title="Tips for a Healthy Diet", category="Wellness", content_md="""
**What is a healthy diet?**
A healthy diet is one that helps to maintain or improve overall health. It provides the body with essential nutrition: fluid, macronutrients, micronutrients, and adequate calories.

**Key Principles**
1.  **Eat a Variety of Foods:** Include fruits, vegetables, whole grains, lean proteins, and healthy fats in your meals.
2.  **Control Portion Sizes:** Avoid eating too much of any one food.
3.  **Limit Processed Foods:** Reduce your intake of foods high in added sugar, salt (sodium), and unhealthy fats (trans and saturated fats).
4.  **Stay Hydrated:** Drink plenty of water throughout the day.
5.  **Listen to Your Body:** Eat when you're hungry and stop when you're full.

**Disclaimer:** This is general dietary advice. For specific nutritional needs, allergies, or health conditions, please consult a registered dietitian or medical professional.
            """),
            Article(title="The Benefits of Regular Exercise", category="Wellness", content_md="""
**Why exercise?**
Regular physical activity is one of the most important things you can do for your health. It can help:
- Control your weight
- Reduce your risk of heart diseases
- Improve your mental health and mood
- Strengthen your bones and muscles
- Improve your ability to do daily activities and prevent falls
- Increase your chances of living longer

**How much exercise?**
Aim for at least 150 minutes of moderate-intensity aerobic activity (like brisk walking or swimming) or 75 minutes of vigorous-intensity activity (like running) each week, spread throughout the week. Also, include muscle-strengthening activities on 2 or more days a week.

**Disclaimer:** Before starting any new exercise program, it's important to consult with your doctor, especially if you have any pre-existing health conditions.
            """),
            Article(title="Managing Stress", category="Wellness", content_md="""
**What is stress?**
Stress is your body's reaction to a challenge or demand. In short bursts, stress can be positive, such as when it helps you avoid danger. But when stress lasts for a long time, it may harm your health.

**Techniques for Stress Management**
- **Identify Stressors:** Figure out what is causing stress in your life.
- **Physical Activity:** Exercise is a powerful stress reliever.
- **Relaxation Techniques:** Try deep breathing, meditation, yoga, or mindfulness.
- **Time Management:** Plan your day and prioritize tasks to avoid feeling overwhelmed.
- **Social Support:** Talk to friends, family, or a mental health professional.
- **Healthy Habits:** Eat a balanced diet, get enough sleep, and limit alcohol and caffeine.

**Disclaimer:** If you are feeling overwhelmed by stress or it is impacting your daily life, please seek help from a qualified mental health professional.
            """),
            Article(title="Understanding Dehydration", category="Symptoms", content_md="""
**What is dehydration?**
Dehydration occurs when you lose more fluid than you take in, and your body doesn't have enough water and other fluids to carry out its normal functions.

**Symptoms of Mild to Moderate Dehydration**
- Thirst
- Dry or sticky mouth
- Not peeing very much
- Dark yellow pee
- Dry, cool skin
- Headache
- Muscle cramps

**What to do**
- **Drink Fluids:** The best treatment is to replace lost fluids by drinking water.
- **Electrolytes:** For more significant fluid loss (e.g., from vomiting or diarrhea), an oral rehydration solution (like Pedialyte) or sports drinks can help replace lost electrolytes.

**Disclaimer:** Seek medical attention if you experience severe dehydration symptoms, such as dizziness, confusion, fainting, or inability to keep fluids down.
            """),
            Article(title="When to See a Doctor for a Cough", category="Symptoms", content_md="""
**Most coughs are not serious.**
A cough is a common reflex action that clears your throat of mucus or foreign irritants. Most coughs are caused by the common cold or flu and will go away on their own.

**When to Consult a Doctor**
You should see a medical professional if your cough:
- Lasts for more than three weeks
- Is very severe or getting worse
- Is accompanied by a high fever, shortness of breath, or chest pain
- Causes you to cough up blood or thick, discolored phlegm
- Is accompanied by unexplained weight loss

**Disclaimer:** This is not an exhaustive list. If you are ever concerned about a cough or any other symptom, it is always best to consult a medical professional for an accurate diagnosis and treatment.
            """)
        ]
        
        db.session.bulk_save_objects(articles)
        db.session.commit()
        print('Initialized the database and added 10 sample articles.')

# --- User Loader for Flask-Login ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Main App Routes ---

@app.route('/')
@login_required
def index():
    return render_template('index.html', title='Chat - MedConnect AI')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('signup'))
        
        # Check for existing user
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('That email is already taken. Please log in.', 'warning')
            return redirect(url_for('login'))
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(name=name, email=email, password_hash=hashed_password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Your account has been created! You can now log in.', 'success')
            return redirect(url_for('login'))
        except IntegrityError:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error during signup: {e}")
            flash('A server error occurred. Please try again later.', 'danger')

    return render_template('signup.html', title='Sign Up')

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
            flash('Login unsuccessful. Please check your email and password.', 'danger')
            
    return render_template('login.html', title='Login')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))

# --- Verified Health Library Routes ---

@app.route('/library')
@login_required
def library():
    articles = Article.query.all()
    return render_template('library.html', title='Health Library', articles=articles)

@app.route('/article/<int:article_id>')
@login_required
def article_detail(article_id):
    article = db.session.get(Article, article_id)
    if not article:
        flash('Article not found.', 'danger')
        return redirect(url_for('library'))
    
    return render_template('article_detail.html', title=article.title, article=article)

# --- Chat API Routes ---

def get_openrouter_response(messages):
    """Gets a response from the OpenRouter API."""
    try:
        completion = client.chat.completions.create(
            model="openai/gpt-oss-20b:free", 
            messages=messages,
            max_tokens=1024,
        )
        return completion.choices[0].message.content
    except Exception as e:
        app.logger.error(f"Error contacting OpenRouter: {e}")
        return "I'm sorry, I'm having trouble connecting to my brain right now. Please try again in a moment."

@app.route('/get_history')
@login_required
def get_history():
    history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp).all()
    history_list = [{"role": msg.role, "content": msg.content} for msg in history]
    return jsonify(history_list)

@app.route('/ask', methods=['POST'])
@login_required
def ask():
    user_message_content = request.json.get('message')
    if not user_message_content:
        return jsonify({"error": "No message provided"}), 400

    # Save user message
    user_message = ChatHistory(role='user', content=user_message_content, author=current_user)
    db.session.add(user_message)
    
    # --- NEW: System Prompt with Function Calling ---
    system_prompt = {
        "role": "system",
        "content": (
            "You have two tasks. First, be a helpful medical AI. Second, be a reminder assistant."
            "\n\n**TASK 1: Medical AI**"
            "\n- **YOUR MOST IMPORTANT RULE:** You MUST refuse to answer any questions that are not related to health, medicine, wellness, or symptoms. "
            "If the user asks about anything else (like sports, history, movies, or general knowledge), you must politely decline with a message like: "
            "'I'm sorry, I'm a medical assistant and can only answer questions about your health and wellness. How are you feeling today?'"
            "\n- Your persona: You are 'MedConnect AI'. You are NOT a doctor and must NEVER provide a diagnosis. "
            "Always end your (health-related) response with a clear, friendly disclaimer: 'Please remember, I am an AI, not a medical professional. It's always best to consult a doctor for a proper diagnosis.You must consult a qualified healthcare professional ,such as a doctor or pharmacist ,before taking any medications'"
            "\n\n**TASK 2: Reminder Assistant**"
            "\n- If the user asks to set a medicine reminder, your goal is to collect three pieces of information: `medicine_name`, `dosage` (optional), and `time` (in 24-hour HH:MM format)."
            "\n- Ask for any missing information. If the user just says 'remind me to take my pill at 8', you must ask 'What is the medicine's name?' and 'Is that 8 AM or 8 PM? Please provide the time in 24-hour HH:MM format, like 08:00 or 20:00.'"
            "\n- Once you have the required info, you **MUST** respond *only* with a special JSON-like string and nothing else."
            "\n- **JSON Format:** `{\"action\": \"create_reminder\", \"medicine\": \"...\", \"dosage\": \"...\", \"time\": \"HH:MM\"}`"
            "\n- If `dosage` is not specified, set its value to `None` (as a string: \"None\")."
            "\n- **Example 1:** `{\"action\": \"create_reminder\", \"medicine\": \"Paracetamol\", \"dosage\": \"500mg\", \"time\": \"08:00\"}`"
            "\n- **Example 2:** `{\"action\": \"create_reminder\", \"medicine\": \"Aspirin\", \"dosage\": \"None\", \"time\": \"14:30\"}`"
            "\n- Only respond with this JSON string. The system will handle the confirmation."
        )
    }
    
    # Fetch recent history
    recent_history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.desc()).limit(10).all()
    recent_history.reverse() # Put in chronological order
    
    messages = [system_prompt] + [{"role": msg.role, "content": msg.content} for msg in recent_history]

    # Get AI response
    ai_response_content = get_openrouter_response(messages)
    
    # --- NEW: Check for Function Call ---
    try:
        # Check if the response is our special JSON string
        data = json.loads(ai_response_content)
        
        if data.get('action') == 'create_reminder':
            # It's a reminder! Let's process it.
            med_name = data.get('medicine')
            dosage = data.get('dosage')
            time_str = data.get('time')

            if dosage == "None":
                dosage = None # Convert string "None" to Python's None
            
            if not med_name or not time_str:
                # The AI failed to extract data, send a normal error
                ai_response_content = "I'm sorry, I missed some of those details. Could you please provide the medicine name and time again?"
            else:
                try:
                    # Convert "HH:MM" string to a Python time object
                    reminder_time_obj = time.fromisoformat(time_str)
                    
                    new_reminder = Reminder(
                        medicine_name=med_name,
                        dosage=dosage,
                        reminder_time=reminder_time_obj,
                        author=current_user
                    )
                    db.session.add(new_reminder)
                    
                    # Craft our *own* friendly confirmation message
                    time_friendly = reminder_time_obj.strftime('%I:%M %p') # e.g., "08:00 AM"
                    dosage_text = f" ({dosage})" if dosage else ""
                    ai_response_content = f"OK, I've set a reminder for {med_name}{dosage_text} at {time_friendly}. You can see all your reminders on the 'Reminders' page."

                except ValueError:
                    ai_response_content = f"I'm sorry, I couldn't understand the time '{time_str}'. Please provide it in 24-hour HH:MM format (e.g., 08:00 for 8 AM or 20:00 for 8 PM)."
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"Error creating reminder from AI: {e}")
                    ai_response_content = "I'm sorry, I had trouble saving that reminder. Please try again or use the manual form on the 'Reminders' page."

    except (json.JSONDecodeError, TypeError):
        # It's a normal chat message, not a JSON object.
        # We don't need to do anything, just let it proceed.
        pass
    
    # --- End of New Logic ---

    # Save AI response (either the original one or our new confirmation message)
    ai_message = ChatHistory(role='assistant', content=ai_response_content, author=current_user)
    db.session.add(ai_message)
    
    # Commit user message + AI message
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error saving chat history: {e}")
        return jsonify({"error": "Could not save chat history"}), 500

    return jsonify({"answer": ai_response_content})

@app.route('/clear_chat', methods=['POST'])
@login_required
def clear_chat():
    try:
        ChatHistory.query.filter_by(user_id=current_user.id).delete()
        db.session.commit()
        return jsonify({"status": "success", "message": "Chat history cleared."})
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error clearing chat history: {e}")
        return jsonify({"error": "Could not clear chat history"}), 500


# --- Medicine Reminder Routes (API-driven) ---

@app.route('/reminders')
@login_required
def reminders():
    # The page itself is simple, all data is loaded via API
    return render_template('reminders.html', title='Medicine Reminders')

@app.route('/api/get_reminders', methods=['GET'])
@login_required
def get_reminders():
    reminders = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.reminder_time).all()
    # Convert list of Reminder objects to list of dictionaries
    return jsonify([r.to_dict() for r in reminders])

@app.route('/api/add_reminder', methods=['POST'])
@login_required
def add_reminder():
    data = request.json
    try:
        med_name = data.get('medicine_name')
        dosage = data.get('dosage')
        time_str = data.get('reminder_time') # Expected format: "HH:MM" (24-hour)

        if not med_name or not time_str:
            return jsonify({"error": "Medicine name and time are required."}), 400
        
        # Convert "HH:MM" string to a Python time object
        reminder_time_obj = time.fromisoformat(time_str)
        
        new_reminder = Reminder(
            medicine_name=med_name,
            dosage=dosage,
            reminder_time=reminder_time_obj,
            author=current_user
        )
        db.session.add(new_reminder)
        db.session.commit()
        
        # Return the newly created reminder so the frontend can add it to the list
        return jsonify(new_reminder.to_dict()), 201
        
    except ValueError:
        return jsonify({"error": "Invalid time format. Please use HH:MM (24-hour)."}), 400
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error adding reminder: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

@app.route('/api/delete_reminder/<int:reminder_id>', methods=['DELETE'])
@login_required
def delete_reminder(reminder_id):
    try:
        reminder = Reminder.query.get_or_404(reminder_id)
        
        # Security check: make sure the reminder belongs to the logged-in user
        if reminder.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
            
        db.session.delete(reminder)
        db.session.commit()
        return jsonify({"status": "success", "message": "Reminder deleted."})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting reminder: {e}")
        return jsonify({"error": "An internal error occurred."}), 500


# --- Main Run ---
if __name__ == '__main__':
    app.run(debug=True)