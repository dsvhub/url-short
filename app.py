import qrcode
from io import BytesIO
import base64
import string
import random
from datetime import datetime
from flask import Flask, render_template, redirect, url_for, flash, Response
from flask_login import LoginManager, login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash
from app.forms import ShortenURLForm
from models import db, User, URL
import csv
from io import StringIO
from flask import session, request
from app.forms import RegistrationForm, LoginForm
from flask_login import current_user, login_required
from app.forms import ProfileForm
from io import TextIOWrapper

from app.routes import main  # Adjust the import path if necessary




def generate_qr_code(data):
    img = qrcode.make(data)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode('utf-8')





app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_secret_key_here'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///site.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.register_blueprint(main, url_prefix='/main')


db.init_app(app)

with app.app_context():
    db.create_all()


login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def generate_short_id(num_chars=6):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=num_chars))

def generate_unique_short_id(num_chars=6):
    while True:
        short_id = generate_short_id(num_chars)
        if not URL.query.filter_by(short_id=short_id).first():
            return short_id

@app.route('/')
def home():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        hashed_pw = generate_password_hash(form.password.data)
        user = User(username=form.username.data, email=form.email.data, password=hashed_pw)
        db.session.add(user)
        db.session.commit()
        flash('Account created!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and check_password_hash(user.password, form.password.data):
            login_user(user, remember=form.remember.data)
            return redirect(url_for('dashboard'))
        else:
            flash('Login failed.', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    # Get per_page from request OR fallback to session OR default to 5
    per_page = request.args.get('per_page', type=int)
    if per_page:
        session['per_page'] = per_page
    else:
        per_page = session.get('per_page', 5)

    page = request.args.get('page', 1, type=int)

    form = ShortenURLForm()

    # 🔧 Add this block to process the form submission
    if form.validate_on_submit():
        original_url = form.original_url.data

        # Optional: Check if URL was already shortened by this user
        existing = URL.query.filter_by(original_url=original_url, owner=current_user).first()
        if not existing:
            short_id = generate_short_id()
            new_url = URL(original_url=original_url, short_id=short_id, owner=current_user)
            db.session.add(new_url)
            db.session.commit()
            flash('Shortened URL created!', 'success')
        else:
            flash('URL was already shortened.', 'info')

        return redirect(url_for('dashboard', per_page=per_page))

    # Paginate URLs after processing form
    urls_paginated = URL.query.filter_by(owner=current_user)\
                        .paginate(page=page, per_page=per_page, error_out=False)

    qr_codes = [(url, generate_qr_code(request.host_url + url.short_id)) for url in urls_paginated.items]

    return render_template("dashboard.html",
                           urls=qr_codes,
                           form=form,
                           pagination=urls_paginated,
                           per_page=per_page)

@app.route('/bulk-upload', methods=['POST'])
@login_required
def bulk_upload():
    file = request.files.get('csv_file')

    if not file or not file.filename.endswith('.csv'):
        flash('Please upload a valid CSV file.', 'danger')
        return redirect(url_for('dashboard'))

    csv_file = TextIOWrapper(file, encoding='utf-8')
    reader = csv.reader(csv_file)
    created_count = 0

    for row in reader:
        if not row:
            continue
        original_url = row[0].strip()
        if not original_url:
            continue

        # Avoid duplicates
        existing = URL.query.filter_by(original_url=original_url, owner=current_user).first()
        if existing:
            continue

        new_url = URL(original_url=original_url, owner=current_user)
        db.session.add(new_url)
        created_count += 1

    db.session.commit()
    flash(f'{created_count} URLs shortened successfully.', 'success')
    return redirect(url_for('dashboard'))

@app.route('/<short_id>')
def redirect_short_url(short_id):
    url = URL.query.filter_by(short_id=short_id).first_or_404()
    if url.expiration_date and url.expiration_date < datetime.utcnow():
        flash('This link has expired.', 'warning')
        return redirect(url_for('home'))
    url.clicks += 1
    db.session.commit()
    return redirect(url.original_url)

@app.route('/edit/<short_id>', methods=['GET', 'POST'])
@login_required
def edit_url(short_id):
    url_entry = URL.query.filter_by(short_id=short_id, user_id=current_user.id).first_or_404()
    if request.method == 'POST':
        new_url = request.form.get('original_url')
        if new_url:
            url_entry.original_url = new_url
            db.session.commit()
            flash('URL updated.', 'success')
            return redirect(url_for('dashboard'))
    return render_template('edit_url.html', url_entry=url_entry)

@app.route('/delete/<short_id>', methods=['GET'])
@login_required
def delete_url(short_id):
    url_entry = URL.query.filter_by(short_id=short_id, user_id=current_user.id).first_or_404()
    db.session.delete(url_entry)
    db.session.commit()
    flash('URL deleted.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/download_csv')
@login_required
def download_csv():
    user_urls = URL.query.filter_by(user_id=current_user.id).all()

    si = StringIO()
    cw = csv.writer(si)
    cw.writerow(["Short URL", "Original URL", "Clicks"])
    for url in user_urls:
        short_url = request.host_url + url.short_id
        cw.writerow([short_url, url.original_url, url.clicks])

    output = si.getvalue()
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=shortened_links.csv"}
    )

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)

    if form.validate_on_submit():
        # Update username and email
        current_user.username = form.username.data
        current_user.email = form.email.data

        # If changing password
        if form.current_password.data and form.new_password.data:
            if check_password_hash(current_user.password, form.current_password.data):
                current_user.password = generate_password_hash(form.new_password.data)
                flash('Password updated successfully.', 'success')
            else:
                flash('Current password is incorrect.', 'danger')
                return render_template('profile.html', form=form)

        db.session.commit()
        flash('Profile updated.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('profile.html', form=form)



if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)


