import os
import markdown
import json 
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from openai import OpenAI
from sqlalchemy.exc import IntegrityError
from datetime import datetime, time, date

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
login_manager.login_view = 'landing' 
login_manager.login_message = 'Please log in or sign up to access the app.'
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
    appointments = db.relationship('Appointment', backref='patient', lazy=True, cascade="all, delete-orphan")

class ChatHistory(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.String(10), nullable=False) # 'user' or 'assistant'
    content = db.Column(db.Text, nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class Article(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    category = db.Column(db.String(50), nullable=False)
    content_md = db.Column(db.Text, nullable=False)
    
    @property
    def content_html(self):
        return markdown.markdown(self.content_md)

class Reminder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    medicine_name = db.Column(db.String(100), nullable=False)
    dosage = db.Column(db.String(50), nullable=True)
    reminder_time = db.Column(db.Time, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    def to_dict(self):
        return {
            'id': self.id,
            'medicine_name': self.medicine_name,
            'dosage': self.dosage,
            'reminder_time': self.reminder_time.strftime('%I:%M %p')
        }

class Doctor(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    specialty = db.Column(db.String(150), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    appointments = db.relationship('Appointment', backref='doctor', lazy=True)
    
    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'specialty': self.specialty,
            'address': self.address,
            'phone': self.phone,
            'lat': self.latitude,
            'lng': self.longitude
        }

class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    appointment_datetime = db.Column(db.DateTime, nullable=False)
    reason = db.Column(db.String(300), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)


# --- Database Initialization Functions (RE-ORDERED FOR FIX) ---

def _init_db():
    """Internal function to create tables and add data. This is what we will call from our secret route."""
    db.drop_all()
    db.create_all()
    
    # --- THIS IS THE FIX: Full Article Content Added ---
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

**Disclaimer:** Seek immediate medical attention if you experience severe dehydration symptoms, such as dizziness, confusion, fainting, or inability to keep fluids down.
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
    
    # --- Add ALL 9 Sample Doctors ---
    doctors = [
        Doctor(name="Jai Hind Clinic", specialty="Medical Clinic", 
               address="Nawabganj, durga mandir road, unnao Uttar Pradesh 209859", 
               phone="09169457354", latitude=26.6187, longitude=80.6712),
        Doctor(name="SHASHWAT Dental Hospital Clinic", specialty="Dental Clinic", 
               address="block (kshtera panchayat, Nawabganj, Kanpur Rd, Unnao, Uttar Pradesh 209859", 
               phone="08090310358", latitude=26.6166, longitude=80.6725),
        Doctor(name="Dr.Vineet Tiwari", specialty="General Physician", 
               address="Lucknow, Kanpur - Lucknow Rd, near shiv mandir, Mawaiyya, Lucknow, Uttar Pradesh 209859", 
               phone="09415518286", latitude=26.8143, longitude=80.8924),
        Doctor(name="Shri Ram Murti Smarak Hospital", specialty="Hospital", 
               address="JJPGH+XG8, Allahabad Highway, Kanpur, Unnao, Ashakhera, Uttar Pradesh 209859", 
               phone="05143278408", latitude=26.6249, longitude=80.5788),
        Doctor(name="Sanjay Gandhi Post Graduate Institute (SGPGI)", specialty="Multi-Specialty Institute",
               address="Raebareli Road, Haibat Mau Mawaiya, Pushpendra Nagar, Lucknow, Uttar Pradesh, 226014",
               phone="0522-2494000", latitude=26.7588, longitude=80.9488),
        Doctor(name="Medanta Super Speciality Hospital", specialty="Multi-Specialty Hospital",
               address="Sector - A, Pocket - 1, Amar Shaheed Path, Golf City, Lucknow, Uttar Pradesh, 226030",
               phone="+91 522 450 5050", latitude=26.7766, longitude=80.9885),
        Doctor(name="Saraswati Medical College and Hospital", specialty="Medical College & Hospital",
               address="LIDA, Madhu Vihar, P.O. Asha Khera, NH-27, Lucknow-Kanpur Highway, Unnao (UP), 209859",
               phone="0515-3510001", latitude=26.5866, longitude=80.6053),
        Doctor(name="Shine Multispeciality Hospital", specialty="Multi-Specialty Hospital",
               address="Behind Utsav Bhog Dhaba, Kanpur Road, Junab Ganj, Lucknow, Uttar Pradesh, 226401",
               phone="N/A", latitude=26.6852, longitude=80.7936),
        Doctor(name="Surya Hospital & Trauma Center", specialty="Hospital & Trauma Care",
               address="Sector - I, L.D.A. Colony, Near Khazana Market, Kanpur Road Scheme (Aashiana), Lucknow, 226012",
               phone="0522-4074044", latitude=26.7934, longitude=80.9080)
    ]
    db.session.bulk_save_objects(doctors)
    
    db.session.commit()

@app.cli.command('init-db')
def init_db_command():
    """Clears existing data and creates new tables, adding sample articles and doctors."""
    with app.app_context():
        _init_db()
        print('Initialized the database, added 10 sample articles, and 9 sample doctors.')

# --- User Loader for Flask-Login ---

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# --- Main App Routes ---

@app.route('/')
def landing():
    """Our new public-facing 3D landing page."""
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form_to_show = request.args.get('form', None) 
    return render_template('landing.html', title='Welcome to Medullose', form_to_show=form_to_show)

@app.route('/dashboard')
@login_required
def dashboard():
    """This is the new 'homepage' after logging in."""
    return redirect(url_for('find_doctors')) # Go to the visual map page

@app.route('/chat')
@login_required
def chat():
    """The main chat interface."""
    return render_template('index.html', title='Chat - Medullose')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        password = request.form.get('password')
        
        if not name or not email or not password:
            flash('All fields are required.', 'danger')
            return redirect(url_for('landing', form='signup'))
        
        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('That email is already taken. Please log in.', 'warning')
            return redirect(url_for('landing', form='login'))
        
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
        new_user = User(name=name, email=email, password_hash=hashed_password)
        
        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Your account has been created! You can now log in.', 'success')
            return redirect(url_for('landing', form='login'))
        except IntegrityError:
            db.session.rollback()
            flash('An error occurred. Please try again.', 'danger')
            return redirect(url_for('landing', form='signup'))
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error during signup: {e}")
            flash('A server error occurred. Please try again later.', 'danger')
            return redirect(url_for('landing', form='signup'))

    return redirect(url_for('landing', form='signup'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        user = User.query.filter_by(email=email).first()
        
        if user and bcrypt.check_password_hash(user.password_hash, password):
            login_user(user, remember=True)
            next_page = request.args.get('next')
            return redirect(next_page or url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check your email and password.', 'danger')
            return redirect(url_for('landing', form='login'))
            
    return redirect(url_for('landing', form='login'))

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('landing')) 

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

    user_message = ChatHistory(role='user', content=user_message_content, author=current_user)
    db.session.add(user_message)
    
    system_prompt = {
        "role": "system",
        "content": (
            "You have two tasks. First, be a helpful medical AI. Second, be a reminder assistant."
            "\n\n**TASK 1: Medical AI**"
            "\n- **YOUR MOST IMPORTANT RULE:** You MUST refuse to answer any questions that are not related to health, medicine, wellness, or symptoms. "
            "If the user asks about anything else, you must politely decline."
            "\n- Your persona: You are 'Medullose AI'. You are NOT a doctor and must NEVER provide a diagnosis. "
            "Always end your (health-related) response with a clear, friendly disclaimer: 'Please remember, I am an AI, not a medical professional. It's always best to consult a doctor for a proper diagnosis.'"
            
            "\n\n**TASK 2: Reminder Assistant**"
            "\n- If the user asks to set a medicine reminder, your goal is to collect three pieces of information: `medicine_name`, `dosage` (optional), and `time` (in 24-hour HH:MM format)."
            "\n- Ask for any missing information."
            "\n- Once you have the required info, you **MUST** respond *only* with a special JSON-like string and nothing else."
            "\n- **JSON Format:** `{\"action\": \"create_reminder\", \"medicine\": \"...\", \"dosage\": \"...\", \"time\": \"HH:MM\"}`"
        )
    }
    
    recent_history = ChatHistory.query.filter_by(user_id=current_user.id).order_by(ChatHistory.timestamp.desc()).limit(10).all()
    recent_history.reverse() 
    
    messages = [system_prompt] + [{"role": msg.role, "content": msg.content} for msg in recent_history]
    messages.append({"role": "user", "content": user_message_content})

    ai_response_content = get_openrouter_response(messages)
    
    try:
        data = json.loads(ai_response_content)
        
        if data.get('action') == 'create_reminder':
            med_name = data.get('medicine')
            dosage = data.get('dosage')
            time_str = data.get('time')

            if dosage == "None":
                dosage = None 
            
            if not med_name or not time_str:
                ai_response_content = "I'm sorry, I missed some of those details. Could you please provide the medicine name and time again?"
            else:
                try:
                    reminder_time_obj = time.fromisoformat(time_str)
                    
                    new_reminder = Reminder(
                        medicine_name=med_name,
                        dosage=dosage,
                        reminder_time=reminder_time_obj,
                        author=current_user
                    )
                    db.session.add(new_reminder)
                    
                    time_friendly = reminder_time_obj.strftime('%I:%M %p') 
                    dosage_text = f" ({dosage})" if dosage else ""
                    ai_response_content = f"OK, I've set a reminder for {med_name}{dosage_text} at {time_friendly}. You can see all your reminders on the 'Reminders' page."

                except ValueError:
                    ai_response_content = f"I'm sorry, I couldn't understand the time '{time_str}'. Please provide it in 24-hour HH:MM format (e.g., 08:00 for 8 AM or 20:00 for 8 PM)."
                except Exception as e:
                    db.session.rollback()
                    app.logger.error(f"Error creating reminder from AI: {e}")
                    ai_response_content = "I'm sorry, I had trouble saving that reminder. Please try again or use the manual form on the 'Reminders' page."

    except (json.JSONDecodeError, TypeError):
        pass
    
    ai_message = ChatHistory(role='assistant', content=ai_response_content, author=current_user)
    
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
    return render_template('reminders.html', title='Medicine Reminders')

@app.route('/api/get_reminders', methods=['GET'])
@login_required
def get_reminders():
    reminders = Reminder.query.filter_by(user_id=current_user.id).order_by(Reminder.reminder_time).all()
    return jsonify([r.to_dict() for r in reminders])

@app.route('/api/add_reminder', methods=['POST'])
@login_required
def add_reminder():
    data = request.json
    try:
        med_name = data.get('medicine_name')
        dosage = data.get('dosage')
        time_str = data.get('reminder_time') 

        if not med_name or not time_str:
            return jsonify({"error": "Medicine name and time are required."}), 400
        
        reminder_time_obj = time.fromisoformat(time_str)
        
        new_reminder = Reminder(
            medicine_name=med_name,
            dosage=dosage,
            reminder_time=reminder_time_obj,
            author=current_user
        )
        db.session.add(new_reminder)
        db.session.commit()
        
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
        
        if reminder.user_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403
            
        db.session.delete(reminder)
        db.session.commit()
        return jsonify({"status": "success", "message": "Reminder deleted."})
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error deleting reminder: {e}")
        return jsonify({"error": "An internal error occurred."}), 500

# --- Doctor & Appointment Routes ---

@app.route('/find_doctors')
@login_required
def find_doctors():
    return render_template('find_doctors.html', title="Find a Doctor")

@app.route('/api/get_doctors', methods=['GET'])
@login_required
def get_doctors():
    doctors = Doctor.query.all()
    return jsonify([d.to_dict() for d in doctors])

@app.route('/book/<int:doctor_id>', methods=['GET', 'POST'])
@login_required
def book_appointment(doctor_id):
    doctor = db.session.get(Doctor, doctor_id)
    if not doctor:
        flash('Doctor not found.', 'danger')
        return redirect(url_for('find_doctors'))
    
    if request.method == 'POST':
        date_str = request.form.get('appointment_date')
        time_str = request.form.get('appointment_time')
        reason = request.form.get('reason')
        
        if not date_str or not time_str:
            flash('Please select a valid date and time.', 'danger')
            return redirect(url_for('book_appointment', doctor_id=doctor_id))

        try:
            appointment_dt_str = f"{date_str} {time_str}"
            appointment_datetime = datetime.strptime(appointment_dt_str, '%Y-%m-%d %H:%M')

            if appointment_datetime < datetime.now():
                flash('You cannot book an appointment in the past.', 'danger')
                return redirect(url_for('book_appointment', doctor_id=doctor_id))

            new_appointment = Appointment(
                appointment_datetime=appointment_datetime,
                reason=reason,
                patient=current_user,
                doctor=doctor
            )
            
            db.session.add(new_appointment)
            db.session.commit()
            
            flash('Your appointment has been successfully booked!', 'success')
            return redirect(url_for('my_appointments'))

        except ValueError:
            flash('Invalid date or time format.', 'danger')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Error booking appointment: {e}")
            flash('An error occurred while booking. Please try again.', 'danger')

    min_date = date.today().isoformat()
    return render_template('book_appointment.html', title=f"Book with {doctor.name}", doctor=doctor, min_date=min_date)


@app.route('/my_appointments')
@login_required
def my_appointments():
    appointments = Appointment.query.filter_by(user_id=current_user.id).order_by(Appointment.appointment_datetime.asc()).all()
    return render_template('my_appointments.html', title="My Appointments", appointments=appointments)

@app.route('/cancel_appointment/<int:appointment_id>', methods=['POST'])
@login_required
def cancel_appointment(appointment_id):
    try:
        appointment = Appointment.query.get_or_404(appointment_id)
        
        if appointment.user_id != current_user.id:
            flash('You are not authorized to cancel this appointment.', 'danger')
            return redirect(url_for('my_appointments'))
        
        if appointment.appointment_datetime < datetime.now():
            flash('You cannot cancel an appointment that has already passed.', 'warning')
            return redirect(url_for('my_appointments'))
            
        db.session.delete(appointment)
        db.session.commit()
        flash('Your appointment has been cancelled.', 'success')
        
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"Error cancelling appointment: {e}")
        flash('An error occurred while cancelling the appointment.', 'danger')
        
    return redirect(url_for('my_appointments'))

# --- NEW: Secret route to initialize the database on Render ---
@app.route('/admin/super-secret-init-db')
def secret_init_db():
    # This is a simple security measure. 
    # For a real app, you'd want a better password system.
    secret_key = request.args.get('key')
    if secret_key == 'medullose-admin-12345': # Key updated to 'medullose'
        try:
            with app.app_context():
                _init_db()
            return "DATABASE INITIALIZED SUCCESSFULLY."
        except Exception as e:
            return f"An error occurred: {e}"
    else:
        return "Not authorized.", 403

# --- Main Run ---
if __name__ == '__main__':
    app.run(debug=True)