from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import json
import requests
from datetime import datetime
from dotenv import load_dotenv
import os

# Load the .env file
load_dotenv()

# Test it
api_key = os.getenv('OPENROUTER_API_KEY')
if api_key:
    print(f"✅ Success! Found key starting with: {api_key[:10]}...")
else:
    print("❌ Error: Could not find OPENROUTER_API_KEY. Check your .env file name!")

app = Flask(__name__)
app.secret_key = "iLikeCupCake"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'workRelatedStuff')
FEEDS_FILE = os.path.join(UPLOAD_FOLDER, 'feeds.json')

# Ensure directories exist
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# API Key setup - Check multiple possible env var names
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY') or os.getenv('OPENROUTE_API_KEY')

# Database Setup
app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{os.path.join(BASE_DIR, 'school_app.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='student')  # 'teacher', 'student', or 'admin'
    profile_picture = db.Column(db.String(255), nullable=True)  # Path to profile picture file
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # Profile setup fields
    full_name = db.Column(db.String(100), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    class_name = db.Column(db.String(50), nullable=True)  # For students
    roll_no = db.Column(db.String(20), nullable=True)  # For students
    section = db.Column(db.String(10), nullable=True)  # For students (A, B, C, D)
    student_council_post = db.Column(db.String(100), nullable=True)  # For students
    subject = db.Column(db.String(100), nullable=True)  # For teachers

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def moderate_content(text):
    """Check content for inappropriate language using OpenRoute API"""
    try:
        # You'll need to set your OpenRoute API key as an environment variable
        # You can get it from: https://openrouter.ai/keys
        # Set it as: export =your_key_here
        api_key = os.getenv('OPENROUTE_API_KEY') or os.getenv('OPENROUTER_API_KEY')
        if not api_key:
            # For development, return False (allow content) if no API key
            print("Warning: No OpenRoute API key found. Content moderation disabled.")
            return False
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        prompt = f"""Analyze the following text for inappropriate content, profanity, hate speech, or offensive language. 
        Return only 'INAPPROPRIATE' if the content contains any form of profanity, cussing, hate speech, or offensive language.
        Return only 'APPROPRIATE' if the content is clean and appropriate for a school environment.
        
        Text to analyze: "{text}"
        
        Response:"""
        
        data = {
            "model": "openai/gpt-3.5-turbo",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 10,
            "temperature": 0.1
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=10)
        response.raise_for_status()
        
        result = response.json()
        content = result['choices'][0]['message']['content'].strip().upper()
        
        return content == 'INAPPROPRIATE'
        
    except Exception as e:
        # If API fails, allow content to avoid blocking legitimate posts
        print(f"Content moderation error: {e}")
        return False



class Event(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    event_type = db.Column(db.String(50), nullable=False)  # 'exam', 'holiday', 'cultural'
    date = db.Column(db.Date, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    post_id = db.Column(db.String(50), nullable=False)  # Reference to post id
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    author = db.relationship('User', backref='comments')

def get_ai_response(message):
    """Generate AI response for academic doubts using OpenRoute API"""
    try:
        # 1. Use the variable defined at the top of your app.py
        api_key = OPENROUTER_API_KEY 

        if not api_key or "your-openrouter" in api_key:
            print("DEBUG: API Key is missing or still the placeholder!")
            return get_fallback_response(message)

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost:5000", # Required by OpenRouter
            "X-Title": "SchoolNet"                    # Required by OpenRouter
        }

        # Use a FREE model for testing to ensure it's not a credit issue
        data = {
            "model": "openai/gpt-3.5-turbo", 
            "messages": [
                {
                    "role": "system", 
                    "content": "You are a helpful school assistant. Answer academic questions clearly."
                },
                {"role": "user", "content": message}
            ]
        }

        response = requests.post(url, headers=headers, json=data, timeout=15)
        
        # This will print the error message in your terminal if it fails
        if response.status_code != 200:
            print(f"DEBUG API ERROR: {response.status_code} - {response.text}")
            return get_fallback_response(message)

        result = response.json()
        return result['choices'][0]['message']['content'].strip()

    except Exception as e:
        print(f"DEBUG PYTHON ERROR: {e}")
        return get_fallback_response(message)

@app.route('/add_announcement', methods=['POST'])
@login_required
def add_announcement():
    # Only allow Teacher or Admin
    if current_user.role not in ['teacher', 'admin']:
        flash('Only Teachers and Admins can create pinned announcements.', 'error')
        return redirect(url_for('home'))

    content = request.form.get('content', '').strip()
    if not content:
        flash('Announcement content cannot be empty.', 'warning')
        return redirect(url_for('home'))

    # Load existing posts
    posts_data = []
    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, 'r') as f:
            posts_data = json.load(f)

    # Unpin any existing pinned posts first (optional: if you only want ONE pinned post)
    for p in posts_data:
        p['pinned'] = False

    # Create new pinned post
    new_announcement = {
        'id': f"announcement_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        'description': content,
        'filename': '',
        'author': current_user.email,
        'pinned': True,  # This identifies it as pinned
        'type': 'announcement'
    }

    posts_data.insert(0, new_announcement)

    with open(FEEDS_FILE, 'w') as f:
        json.dump(posts_data, f, indent=2)

    flash('Announcement pinned successfully!', 'success')
    return redirect(url_for('home'))

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        if not current_user.is_authenticated:
            flash('Please log in to create posts.', 'error')
            return redirect(url_for('login'))
        
        content = request.form.get('content', '').strip()
        if not content:
            flash('Post content cannot be empty.', 'warning')
            return redirect(url_for('home'))
        
        # Handle image upload
        image_filename = None
        if 'image' in request.files:
            image_file = request.files['image']
            if image_file and image_file.filename:
                # Use secure filename and timestamp to prevent conflicts
                ext = os.path.splitext(image_file.filename)[1]
                image_filename = f"post_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
                image_file.save(os.path.join(UPLOAD_FOLDER, image_filename))
        
        new_post = {
            'id': datetime.now().isoformat(),
            'description': content,
            'filename': image_filename or '',
            'author': current_user.email
        }
        
        # Consistent file loading/saving
        posts_data = []
        if os.path.exists(FEEDS_FILE):
            with open(FEEDS_FILE, 'r') as f:
                posts_data = json.load(f)
        
        posts_data.insert(0, new_post)
        with open(FEEDS_FILE, 'w') as f:
            json.dump(posts_data, f, indent=2)
            
        flash('Post created successfully!', 'success')
        return redirect(url_for('home'))

    # Load and enrich posts for GET request
    posts_data = []
    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, 'r') as f:
            posts_data = json.load(f)
            
    for post in posts_data:
        post['author_user'] = User.query.filter_by(email=post.get('author')).first()
        
    return render_template('index.html', feed_posts=posts_data)

    #########################################################################################33

# Create database tables on startup
with app.app_context():
    db.create_all()


# --- feed storage setup ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'workRelatedStuff')

# Ensure upload folder exists. If a file exists at the path, rename it to avoid FileExistsError.
if os.path.exists(UPLOAD_FOLDER):
    if os.path.isfile(UPLOAD_FOLDER):
        # move the existing file out of the way by renaming with a timestamp suffix
        backup_name = UPLOAD_FOLDER + '.file_backup'
        idx = 1
        while os.path.exists(backup_name):
            backup_name = UPLOAD_FOLDER + f'.file_backup{idx}'
            idx += 1
        os.rename(UPLOAD_FOLDER, backup_name)
        print(f"Renamed existing file '{UPLOAD_FOLDER}' -> '{backup_name}' to create upload directory.")
        os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    else:
        # already a directory
        pass
else:
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

FEEDS_FILE = os.path.join(UPLOAD_FOLDER, 'feeds.json')

try:
    if os.path.exists(FEEDS_FILE):
        with open(FEEDS_FILE, 'r', encoding='utf-8') as f:
            posts = json.load(f)
    else:
        posts = []
except Exception:
    posts = []


@app.route('/profile')
@app.route('/profile/<int:user_id>')
def profile(user_id=None):
    if user_id:
        user = User.query.get_or_404(user_id)
        is_own_profile = (current_user.is_authenticated and current_user.id == user_id)
    else:
        if not current_user.is_authenticated:
            flash('Please log in to view profiles.')
            return redirect(url_for('login'))
        user = current_user
        is_own_profile = True
    
    return render_template('profile.html', user=user, is_own_profile=is_own_profile)


@app.route('/upload_profile_picture', methods=['POST'])
@login_required
def upload_profile_picture():
    if 'profile_picture' not in request.files:
        flash('No file selected.')
        return redirect(url_for('profile'))
    
    file = request.files['profile_picture']
    if file.filename == '':
        flash('No file selected.')
        return redirect(url_for('profile'))
    
    if file and file.filename:
        # Check if it's an image
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            flash('Only image files (PNG, JPG, JPEG, GIF, WEBP) are allowed.')
            return redirect(url_for('profile'))
        
        filename = secure_filename(f"profile_{current_user.id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.{file_ext}")
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)
        
        # Update user's profile picture
        current_user.profile_picture = filename
        db.session.commit()
        
        flash('Profile picture updated successfully.')
    
    return redirect(url_for('profile'))

@app.route('/setup_profile', methods=['POST'])
@login_required
def setup_profile():
    # Get form data
    full_name = request.form.get('full_name')
    date_of_birth_str = request.form.get('date_of_birth') # Get string from form
    
    # --- CONVERSION LOGIC ---
    dob_object = None
    if date_of_birth_str:
        try:
            # HTML date inputs use the 'YYYY-MM-DD' format
            dob_object = datetime.strptime(date_of_birth_str, '%Y-%m-%d').date()
        except ValueError:
            flash("Invalid date format.")
            return redirect(url_for('profile'))
    # -------------------------

    if current_user.role == 'student':
        class_name = request.form.get('class')
        roll_no = request.form.get('roll_no')
        section = request.form.get('section')
        student_council_post = request.form.get('student_council_post')
        
        current_user.full_name = full_name
        current_user.date_of_birth = dob_object # Use the object, not the string
        current_user.class_name = class_name
        current_user.roll_no = roll_no
        current_user.section = section
        current_user.student_council_post = student_council_post
        
    elif current_user.role == 'teacher':
        subject = request.form.get('subject')
        current_user.full_name = full_name
        current_user.date_of_birth = dob_object # Use the object
        current_user.subject = subject
        
    elif current_user.role == 'admin':
        current_user.full_name = full_name
        current_user.date_of_birth = dob_object # Use the object
    
    db.session.commit()
    flash('Profile setup completed successfully!')
    return redirect(url_for('profile'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        auth_type = request.form.get('auth_type', 'login')  # 'login' or 'signup'

        if auth_type == 'signup':
            # Registration flow
            email = request.form.get('email')
            password = request.form.get('password')
            username = request.form.get('username')
            
            if not email or not password or not username:
                flash('Username, email and password are required.')
                return render_template('login.html', title='login')
            
            # Check if user already exists
            existing_user = User.query.filter_by(email=email).first()
            if existing_user:
                flash('Email already registered. Please log in.')
                return render_template('login.html', title='login')
            
            existing_username = User.query.filter_by(username=username).first()
            if existing_username:
                flash('Username already taken. Please choose another.')
                return render_template('login.html', title='login')
            
            # Create new user
            role = request.form.get('role', 'student')
            new_user = User(email=email, username=username, role=role)
            new_user.set_password(password)
            db.session.add(new_user)
            try:
                db.session.commit()
                flash('Account created successfully! Please log in.')
                return redirect(url_for('login'))
            except Exception as e:
                db.session.rollback()
                flash(f'Error creating account: {str(e)}')
        else:
            # Login flow
            user = User.query.filter_by(email=email).first()
            if user and user.check_password(password):
                login_user(user)
                flash('Logged in successfully.')
                next_page = request.args.get('next')
                return redirect(next_page or url_for('home'))
            else:
                flash('Invalid email or password.')

    return render_template('login.html', title='login')


@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.')
    return redirect(url_for('home'))


@app.route('/dashboard')
@login_required
def dashboard():
    return f"Hello, {current_user.email}! This is a protected dashboard."


@app.route('/upload', methods=['POST'])
@login_required
def upload():
    title = request.form.get('title', '').strip()
    ptype = request.form.get('type', 'announcement')
    description = request.form.get('description', '').strip()
    file = request.files.get('file')
    
    # Content moderation
    content_to_check = f"{title} {description}".strip()
    if content_to_check and moderate_content(content_to_check):
        flash('Your post contains inappropriate content and cannot be published.')
        return redirect(url_for('home'))
    
    filename = ''
    if file and file.filename:
        # Check if it's an image
        allowed_extensions = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
        file_ext = file.filename.rsplit('.', 1)[1].lower() if '.' in file.filename else ''
        
        if file_ext not in allowed_extensions:
            flash('Only image files (PNG, JPG, JPEG, GIF, WEBP) are allowed.')
            return redirect(url_for('home'))
        
        filename = secure_filename(f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{file.filename}")
        file_path = os.path.join(UPLOAD_FOLDER, filename)
        file.save(file_path)

    post = {
        'id': datetime.utcnow().isoformat(),
        'title': title,
        'type': ptype,
        'description': description,
        'filename': filename,
        'author': current_user.email,
    }
    posts.insert(0, post)
    try:
        with open(FEEDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
    except Exception as e:
        flash('Could not save post metadata: ' + str(e))
        return redirect(url_for('home'))

    flash('Posted to school feed.')
    return redirect(url_for('home'))


@app.route('/something/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


@app.route('/uploads/<path:filename>')
def uploaded_image(filename):
    return send_from_directory(UPLOAD_FOLDER, filename)


@app.route('/add_comment', methods=['POST'])
@login_required
def add_comment():
    content = request.form.get('content', '').strip()
    post_id = request.form.get('post_id')
    
    if not content or not post_id:
        flash('Comment content and post ID are required.')
        return redirect(url_for('home'))
    
    # Content moderation for comments
    if moderate_content(content):
        flash('Your comment contains inappropriate content and cannot be posted.')
        return redirect(url_for('home'))
    
    new_comment = Comment(
        content=content,
        post_id=post_id,
        author_id=current_user.id
    )
    db.session.add(new_comment)
    db.session.commit()
    
    flash('Comment added successfully.')
    return redirect(url_for('home'))


@app.route('/api/comments/<post_id>')
@login_required
def get_comments(post_id):
    comments = Comment.query.filter_by(post_id=post_id).order_by(Comment.created_at).all()
    comments_list = []
    for comment in comments:
        comments_list.append({
            'id': comment.id,
            'content': comment.content,
            'author': comment.author.email,
            'author_user': {
                'id': comment.author.id,
                'username': comment.author.username,
                'profile_picture': comment.author.profile_picture
            },
            'created_at': comment.created_at.isoformat()
        })
    return {'comments': comments_list}


@app.route('/admin')
@login_required
def admin_dashboard():
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('home'))
    
    # Get all posts for moderation
    try:
        all_posts = []
        for post in posts:
            enriched_post = post.copy()
            # Find user by email
            user = User.query.filter_by(email=post.get('author')).first()
            if user:
                enriched_post['author_user'] = user
            else:
                enriched_post['author_user'] = None
            all_posts.append(enriched_post)
    except NameError:
        all_posts = []
    
    return render_template('admin.html', posts=all_posts, post_file_path_prefix='workRelatedStuff/')


@app.route('/admin/delete_post/<post_id>', methods=['POST'])
@login_required
def delete_post(post_id):
    if current_user.role != 'admin':
        flash('Access denied. Admin privileges required.')
        return redirect(url_for('home'))
    
    # Find and remove the post
    global posts
    try:
        posts = [post for post in posts if str(post.get('id', '')) != post_id]
        
        # Save updated posts to file
        with open(FEEDS_FILE, 'w', encoding='utf-8') as f:
            json.dump(posts, f, ensure_ascii=False, indent=2)
        
        # Also delete associated comments
        Comment.query.filter_by(post_id=post_id).delete()
        db.session.commit()
        
        flash('Post deleted successfully.')
    except Exception as e:
        flash(f'Error deleting post: {str(e)}')
    
    return redirect(url_for('admin_dashboard'))

# Calendar and Event Management
@app.route('/calendar')
@login_required
def calendar():
    return render_template('calander.html')

#landing page
app.route('/landing')
def landing():
    return render_template('landingpage.html')


@app.route('/api/events')
@login_required
def get_events():
    events = Event.query.all()
    event_list = []
    for event in events:
        event_list.append({
            'id': event.id,
            'title': event.title,
            'description': event.description,
            'type': event.event_type,
            'date': event.date.isoformat(),
            'created_by': event.created_by
        })
    return {'events': event_list}


@app.route('/add_event', methods=['POST'])
@login_required
def add_event():
    if current_user.role != 'teacher':
        flash('Only teachers can add events.')
        return redirect(url_for('calendar'))
    
    title = request.form.get('title')
    description = request.form.get('description')
    event_type = request.form.get('event_type')
    date_str = request.form.get('date')
    
    if not all([title, event_type, date_str]):
        flash('Title, type, and date are required.')
        return redirect(url_for('calendar'))
    
    try:
        date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        flash('Invalid date format.')
        return redirect(url_for('calendar'))
    
    new_event = Event(
        title=title,
        description=description,
        event_type=event_type,
        date=date,
        created_by=current_user.id
    )
    db.session.add(new_event)
    db.session.commit()
    flash('Event added successfully.')
    return redirect(url_for('calendar'))


#about us page
@app.route('/about-us')
def aboutUS():
    return render_template('aboutus.html')


def get_fallback_response(message):
    """Provide helpful fallback responses when AI API is unavailable"""
    lower_message = message.lower()

    # Academic help responses
    if any(word in lower_message for word in ['math', 'mathematics', 'algebra', 'geometry', 'calculus']):
        return "For mathematics, I recommend practicing regularly with problems. Break complex problems into smaller steps, and always check your work. Try using online resources like Khan Academy for additional practice!"

    if any(word in lower_message for word in ['science', 'physics', 'chemistry', 'biology']):
        return "Science is about understanding how things work! Focus on the 'why' behind concepts rather than just memorizing facts. Try relating scientific principles to real-world examples you see every day."

    if any(word in lower_message for word in ['study', 'exam', 'homework', 'learn', 'test']):
        return "Great question about studying! Try the Pomodoro technique: study for 25 minutes, then take a 5-minute break. Space out your study sessions over time rather than cramming. Get enough sleep and stay hydrated!"

    if any(word in lower_message for word in ['english', 'literature', 'writing', 'grammar']):
        return "For English and writing, practice regularly by reading different types of texts and writing daily. Focus on clear structure: introduction, body, and conclusion. Don't be afraid to revise your work multiple times!"

    if any(word in lower_message for word in ['history', 'social studies', 'geography']):
        return "History and social studies help us understand our world! Try connecting historical events to current events, and create timelines to visualize sequences of events. Understanding 'cause and effect' is key!"

    # General responses
    if any(word in lower_message for word in ['help', 'stuck', 'confused', 'understand']):
        return "I understand you're looking for help! When you're stuck on a subject, try explaining the concept in your own words, or break it down into smaller parts. Don't hesitate to ask your teacher or classmates for clarification."

    if 'hello' in lower_message or 'hi' in lower_message:
        return "Hello! I'm here to help with your academic questions. Whether it's math, science, English, history, or study tips, feel free to ask me anything!"

    # Default response
    return "That's a great question! I'm here to help with academic subjects. Try asking me about math, science, English, history, or study strategies. What specific subject would you like help with?"


@app.route('/api/chat', methods=['POST'])
@login_required
def chat():
    """API endpoint for AI chatbot"""
    try:
        data = request.get_json()
        message = data.get('message', '').strip()

        if not message:
            return {'error': 'Message cannot be empty'}, 400

        # Get AI response
        ai_response = get_ai_response(message)

        return {'response': ai_response}

    except Exception as e:
        print(f"Chat API error: {e}")
        return {'error': 'An error occurred while processing your request'}, 500


if __name__ == '__main__':
    app.run(debug=True)
