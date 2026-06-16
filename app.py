# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, request, redirect, url_for, session, send_from_directory, flash, jsonify, send_file
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from contextlib import contextmanager
import os, random, string, secrets, math, io, json, shutil
from fpdf import FPDF

# ---------- config ----------
class Config:
    SECRET_KEY = secrets.token_hex(32)
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
    MESSAGE_UPLOADS = os.path.join(UPLOAD_FOLDER, 'messages')
    BACKUP_FOLDER = os.path.join(BASE_DIR, 'backups')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024
    DEPARTMENTS = ['Cell_Molecular', 'Serology', 'Microbiology', 'Cell Culture', 'Production', 'all']
    DATABASE = os.path.join(BASE_DIR, 'data', 'labflow.db')
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'bmp', 'webp', 'pdf', 'doc', 'docx', 'xls', 'xlsx', 'mp3', 'wav', 'ogg'}

app = Flask(__name__)
app.config.from_object(Config)

DATABASE = app.config['DATABASE']
os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MESSAGE_UPLOADS'], exist_ok=True)
os.makedirs(app.config['BACKUP_FOLDER'], exist_ok=True)
DEPARTMENTS = Config.DEPARTMENTS

# ---------- Context Manager ----------
@contextmanager
def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    try:
        yield conn
    finally:
        conn.close()

# ---------- توابع کمکی ----------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def backup_database():
    if os.path.exists(DATABASE):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = os.path.join(app.config['BACKUP_FOLDER'], f'labflow_backup_{timestamp}.db')
        shutil.copy2(DATABASE, backup_path)
        backups = sorted([f for f in os.listdir(app.config['BACKUP_FOLDER']) if f.startswith('labflow_backup_')])
        while len(backups) > 5:
            os.remove(os.path.join(app.config['BACKUP_FOLDER'], backups[0]))
            backups.pop(0)

# ---------- دیتابیس ----------
def init_db():
    backup_database()
    with get_db() as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA synchronous=NORMAL")

        c.execute('''CREATE TABLE IF NOT EXISTS users
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT UNIQUE NOT NULL,
                      password TEXT NOT NULL,
                      role TEXT NOT NULL DEFAULT 'user',
                      department TEXT,
                      full_name TEXT,
                      failed_attempts INTEGER DEFAULT 0,
                      locked INTEGER DEFAULT 0)''')
        for col in ['failed_attempts', 'locked']:
            if not column_exists(c, 'users', col):
                c.execute(f"ALTER TABLE users ADD COLUMN {col} INTEGER DEFAULT 0")

        c.execute('''CREATE TABLE IF NOT EXISTS samples
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sample_id TEXT UNIQUE NOT NULL,
                      type TEXT,
                      source TEXT,
                      description TEXT,
                      confidential INTEGER DEFAULT 0,
                      status TEXT DEFAULT 'Awaiting Receipt',
                      submitted_by TEXT,
                      received_by TEXT,
                      receiving_department TEXT,
                      created_date TEXT,
                      additional_info TEXT,
                      confidential_info TEXT)''')
        for col in ['additional_info', 'confidential_info']:
            if not column_exists(c, 'samples', col):
                c.execute(f"ALTER TABLE samples ADD COLUMN {col} TEXT")

        # جدول جدید: ارتباط چند به چند بین نمونه و دپارتمان
        c.execute('''CREATE TABLE IF NOT EXISTS sample_departments
                     (sample_id TEXT NOT NULL,
                      department TEXT NOT NULL,
                      receiver TEXT,
                      status TEXT DEFAULT 'Awaiting Receipt',
                      PRIMARY KEY (sample_id, department))''')

        c.execute('''CREATE TABLE IF NOT EXISTS sample_tests
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sample_id TEXT NOT NULL,
                      test_type TEXT,
                      department TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS test_results
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sample_id TEXT NOT NULL,
                      test_type TEXT,
                      replicate INTEGER DEFAULT 1,
                      parameters TEXT,
                      performed_by TEXT,
                      test_date TEXT,
                      image TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS test_definitions
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      test_name TEXT NOT NULL,
                      department TEXT NOT NULL,
                      parameters TEXT)''')
        if not column_exists(c, 'test_definitions', 'parameters'):
            c.execute("ALTER TABLE test_definitions ADD COLUMN parameters TEXT")

        c.execute('''CREATE TABLE IF NOT EXISTS audit_log
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sample_id TEXT,
                      user TEXT,
                      action TEXT,
                      timestamp TEXT)''')

        c.execute('''CREATE TABLE IF NOT EXISTS password_change_requests
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL,
                      request_time TEXT NOT NULL,
                      status TEXT NOT NULL DEFAULT 'pending')''')

        c.execute('''CREATE TABLE IF NOT EXISTS messages
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      sender TEXT NOT NULL,
                      receiver TEXT NOT NULL,
                      subject TEXT,
                      body TEXT,
                      file_path TEXT,
                      send_time TEXT NOT NULL,
                      is_read INTEGER DEFAULT 0)''')
        if not column_exists(c, 'messages', 'read_at'):
            c.execute("ALTER TABLE messages ADD COLUMN read_at TEXT")

        c.execute('''CREATE TABLE IF NOT EXISTS notifications
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL,
                      message TEXT NOT NULL,
                      link TEXT,
                      is_read INTEGER DEFAULT 0,
                      created_time TEXT NOT NULL)''')

        c.execute('''CREATE TABLE IF NOT EXISTS reminders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL,
                      message TEXT,
                      remind_time TEXT NOT NULL,
                      is_sent INTEGER DEFAULT 0)''')

        c.execute('''CREATE TABLE IF NOT EXISTS private_notes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      username TEXT NOT NULL,
                      subject TEXT,
                      body TEXT,
                      file_path TEXT,
                      created_at TEXT NOT NULL)''')

        c.execute('''CREATE TABLE IF NOT EXISTS report_settings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      header_text TEXT,
                      footer_text TEXT,
                      logo_path TEXT)''')
        c.execute("SELECT COUNT(*) FROM report_settings")
        if c.fetchone()[0] == 0:
            c.execute("INSERT INTO report_settings (header_text, footer_text, logo_path) VALUES (?,?,?)",
                      ('', '', ''))

        try:
            c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                      ('admin', generate_password_hash('admin123'), 'admin', 'all', 'Admin User'))
            user_pw = generate_password_hash('user123')
            for uname, dept, full in [('cell_user','Cell_Molecular','Cell Lab Tech'),
                                      ('sero_user','Serology','Serology Tech'),
                                      ('micro_user','Microbiology','Micro Lab Tech')]:
                c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                          (uname, user_pw, 'user', dept, full))
        except:
            pass

        default_tests = [
            ('Cell Culture', 'Cell Culture', 'CPE;Viability'),
            ('PCR', 'Cell_Molecular', 'CT Value;Target Gene'),
            ('qPCR', 'Cell_Molecular', 'CT Value;Fold Change'),
            ('HA', 'Serology', 'Titer'),
            ('ELISA', 'Serology', 'OD Value;Concentration'),
            ('Bacterial Culture', 'Microbiology', 'Colony Count;Identification'),
            ('Gram Staining', 'Microbiology', 'Result'),
            ('Western Blot', 'Production', 'Band Size;Intensity'),
            ('SDS-PAGE', 'Production', 'Band Size;Purity'),
        ]
        for test_name, dept, params in default_tests:
            try:
                c.execute("INSERT INTO test_definitions (test_name, department, parameters) VALUES (?,?,?)",
                          (test_name, dept, params))
            except:
                pass

        conn.commit()

def column_exists(cursor, table, column):
    cursor.execute(f"PRAGMA table_info({table})")
    return column in [row[1] for row in cursor.fetchall()]

def log_action(sample_id, user, action):
    with get_db() as conn:
        conn.execute("INSERT INTO audit_log (sample_id, user, action, timestamp) VALUES (?,?,?,?)",
                     (sample_id, user, action, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()

def add_notification(username, message, link=''):
    with get_db() as conn:
        conn.execute("INSERT INTO notifications (username, message, link, created_time) VALUES (?,?,?,?)",
                     (username, message, link, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()

def generate_sample_id():
    today = datetime.now().strftime("%Y%m%d")
    with get_db() as conn:
        c = conn.cursor()
        c.execute("BEGIN IMMEDIATE")
        c.execute("SELECT COUNT(*) FROM samples WHERE created_date=?", (datetime.now().strftime("%Y-%m-%d"),))
        count = c.fetchone()[0] + 1
        conn.commit()
    return f"SPL-{today}-{count:03d}"

def get_all_users():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT username, full_name FROM users")
        return c.fetchall()

def get_users_by_dept(dept):
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT username, full_name FROM users WHERE department=?", (dept,))
        return c.fetchall()

def get_all_departments():
    return [d for d in DEPARTMENTS if d != 'all']

def get_test_map():
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT test_name, department, parameters FROM test_definitions ORDER BY department, test_name")
        rows = c.fetchall()
        test_map = {}
        for row in rows:
            test_map.setdefault(row[1], []).append((row[0], row[2] or ''))
        return test_map

def generate_temp_password(length=8):
    return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

# ---------- CSRF ----------
def generate_csrf_token():
    if '_csrf_token' not in session:
        session['_csrf_token'] = secrets.token_hex(16)
    return session['_csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token

@app.before_request
def csrf_protect():
    if request.method == 'POST':
        exempt_routes = ['/request_password_change', '/forgot_password', '/delete_user', '/unlock_user']
        if request.path in exempt_routes:
            return None
        token = session.get('_csrf_token', None)
        if not token or token != request.form.get('_csrf_token', ''):
            return 'CSRF token missing or invalid', 400

# ---------- مسیرهای فایل ----------
@app.route('/ping')
def ping():
    return "pong", 200

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], secure_filename(filename))

# ---------- صفحه ورود ----------
@app.route('/', methods=['GET', 'POST'])
def login():
    error_msg = ''
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username=?", (username,))
            user = c.fetchone()
            if user and user[7] == 1:
                return render_template_string(LOGIN_HTML, error='Account is locked. Contact your administrator.')
            if user and check_password_hash(user[2], password):
                c.execute("UPDATE users SET failed_attempts=0 WHERE username=?", (username,))
                conn.commit()
                session['user'] = user[1]
                session['role'] = user[3]
                session['dept'] = user[4]
                session['full_name'] = user[5] if len(user) > 5 and user[5] else user[1]
                session.permanent = True
                app.permanent_session_lifetime = timedelta(hours=5)
                return redirect(url_for('dashboard'))
            else:
                if user:
                    new_fail = (user[6] or 0) + 1
                    c.execute("UPDATE users SET failed_attempts=? WHERE username=?", (new_fail, username))
                    if new_fail >= 5:
                        c.execute("UPDATE users SET locked=1 WHERE username=?", (username,))
                        log_action('LOGIN', username, 'Account locked after 5 failed attempts')
                    conn.commit()
                log_action('LOGIN', username, 'Failed login attempt')
                c.execute("SELECT timestamp FROM audit_log WHERE user=? AND action='Failed login attempt' ORDER BY timestamp DESC LIMIT 1", (username,))
                last_fail = c.fetchone()
                error_msg = f'Invalid credentials. Last failed login: {last_fail[0]}' if last_fail else 'Invalid credentials.'
    return render_template_string(LOGIN_HTML, error=error_msg)

# ... ادامه در بخش دوم ... (توابع unlock_user، delete_user، forgot_password، dashboard، register، receive_sample، my_samples و...)

# ---------- ثبت نمونه (با قابلیت چند دپارتمان) ----------
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user' not in session:
        return redirect(url_for('login'))
    if session['role'] == 'admin':
        submit_users = get_all_users()
        submit_depts = get_all_departments()
    else:
        submit_users = [(session['user'], session['full_name'])]
        submit_depts = []
    receive_depts = get_all_departments()
    dept_users = {dept: get_users_by_dept(dept) for dept in receive_depts}
    test_map = get_test_map()

    if request.method == 'POST':
        sample_id = generate_sample_id()
        today = datetime.now().strftime("%Y-%m-%d")
        with get_db() as conn:
            c = conn.cursor()
            # اطلاعات اصلی نمونه (بدون دپارتمان و گیرنده کلی)
            c.execute("INSERT INTO samples (sample_id, type, source, description, additional_info, confidential_info, confidential, status, submitted_by, created_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (sample_id, request.form['type'], request.form['source'], request.form['description'],
                       request.form.get('additional_info', ''), request.form.get('confidential_info', ''),
                       1 if 'confidential' in request.form else 0, 'Awaiting Receipt',
                       request.form['submitted_by'], today))
            # دپارتمان‌ها و گیرنده‌ها
            departments = request.form.getlist('departments[]')
            receivers = request.form.getlist('receivers[]')
            for dept, recv in zip(departments, receivers):
                if dept:
                    c.execute("INSERT INTO sample_departments (sample_id, department, receiver, status) VALUES (?,?,?,?)",
                              (sample_id, dept, recv if recv else None, 'Awaiting Receipt'))
            # تست‌های درخواستی برای هر دپارتمان (از روی تست‌های انتخاب‌شده)
            test_types = request.form.getlist('test_type[]')
            for tt in test_types:
                if tt:
                    # تست‌ها برای همه دپارتمان‌های انتخاب‌شده ثبت می‌شوند
                    for dept in departments:
                        c.execute("INSERT INTO sample_tests (sample_id, test_type, department) VALUES (?,?,?)",
                                  (sample_id, tt, dept))
            conn.commit()
        log_action(sample_id, session['user'], 'Sample registered with multiple departments')
        # اعلان به همه گیرنده‌ها
        for recv in receivers:
            if recv:
                add_notification(recv, f'New sample {sample_id} assigned to you.', f'/sample/{sample_id}')
        return redirect(url_for('dashboard'))

    return render_template_string(REGISTER_HTML, submit_users=submit_users, submit_depts=submit_depts,
                                  receive_depts=receive_depts, dept_users=dept_users, test_map=test_map)                                  
@app.route('/unlock_user/<username>', methods=['POST'])
def unlock_user(username):
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    with get_db() as conn:
        conn.execute("UPDATE users SET locked=0, failed_attempts=0 WHERE username=?", (username,))
        conn.commit()
    log_action('SYSTEM', session['user'], f'Unlocked user {username}')
    flash(f'User {username} unlocked.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/delete_user/<username>', methods=['POST'])
def delete_user(username):
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    if username == 'admin':
        flash('Cannot delete the main admin account.', 'danger')
        return redirect(url_for('manage_users'))
    with get_db() as conn:
        conn.execute("DELETE FROM users WHERE username=?", (username,))
        conn.commit()
    log_action('SYSTEM', session['user'], f'Deleted user {username}')
    flash(f'User {username} has been deleted.', 'success')
    return redirect(url_for('manage_users'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        username = request.form.get('username', '')
        if not username:
            flash('Please enter a username.', 'danger')
            return redirect(url_for('forgot_password'))
        now = datetime.now()
        cutoff = (now - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        try:
            with get_db() as conn:
                c = conn.cursor()
                c.execute("SELECT id FROM audit_log WHERE user=? AND action='Failed login attempt' AND timestamp >= ?",
                          (username, cutoff))
                if c.fetchone():
                    c.execute("UPDATE password_change_requests SET status='expired' WHERE username=? AND status='pending'",
                              (username,))
                    c.execute("INSERT INTO password_change_requests (username, request_time, status) VALUES (?,?,?)",
                              (username, now.strftime("%Y-%m-%d %H:%M:%S"), 'pending'))
                    conn.commit()
                    flash('Password reset request submitted. Your administrator will process it within 24 hours.', 'success')
                else:
                    flash('No failed login attempt found in the last 24 hours. Request denied.', 'danger')
        except Exception as e:
            flash(f'An error occurred: {str(e)}', 'danger')
        return redirect(url_for('forgot_password'))
    return render_template_string(FORGOT_PASSWORD_HTML)

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT status, COUNT(*) FROM samples GROUP BY status")
        stats = c.fetchall()
        c.execute("SELECT * FROM samples ORDER BY created_date DESC LIMIT 10")
        recent = c.fetchall()
        c.execute("SELECT COUNT(*) FROM messages WHERE receiver=? AND is_read=0", (session['user'],))
        unread = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM notifications WHERE username=? AND is_read=0", (session['user'],))
        notif_count = c.fetchone()[0]
        c.execute("SELECT department, COUNT(*) FROM sample_tests GROUP BY department")
        dept_test_counts = c.fetchall()
        c.execute("SELECT created_date, COUNT(*) FROM samples WHERE created_date >= date('now','-30 days') GROUP BY created_date ORDER BY created_date")
        daily_counts = c.fetchall()

        # چک کردن reminderهای تمام‌شده
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT id, message FROM reminders WHERE username=? AND remind_time <= ? AND is_sent=0",
                  (session['user'], now_str))
        for rem in c.fetchall():
            add_notification(session['user'], f'⏰ Reminder: {rem[1]}')
            c.execute("UPDATE reminders SET is_sent=1 WHERE id=?", (rem[0],))
        conn.commit()

    return render_template_string(DASHBOARD_HTML, stats=stats, recent=recent, unread=unread,
                                  notif_count=notif_count, dept_test_counts=dept_test_counts, daily_counts=daily_counts)

@app.route('/my_samples')
def my_samples():
    if 'user' not in session:
        return redirect(url_for('login'))
    search = request.args.get('search', '')
    status_filter = request.args.get('status', '')
    dept_filter = request.args.get('dept', '')
    date_from = request.args.get('date_from', '')
    date_to = request.args.get('date_to', '')

    # کوئری پیشرفته با در نظر گرفتن نمونه‌های چند دپارتمانی
    query = """SELECT DISTINCT s.* FROM samples s
               LEFT JOIN sample_departments sd ON s.sample_id = sd.sample_id
               WHERE 1=1"""
    params = []
    if session['role'] != 'admin':
        query += " AND (s.submitted_by=? OR sd.receiver=? OR s.confidential=0)"
        params.extend([session['user'], session['user']])
    if search:
        query += " AND (s.sample_id LIKE ? OR s.description LIKE ? OR s.source LIKE ?)"
        params.extend([f'%{search}%'] * 3)
    if status_filter:
        query += " AND (s.status=? OR sd.status=?)"
        params.extend([status_filter, status_filter])
    if dept_filter:
        query += " AND (s.receiving_department=? OR sd.department=?)"
        params.extend([dept_filter, dept_filter])
    if date_from:
        query += " AND s.created_date >= ?"
        params.append(date_from)
    if date_to:
        query += " AND s.created_date <= ?"
        params.append(date_to)
    query += " ORDER BY s.created_date DESC"

    with get_db() as conn:
        c = conn.cursor()
        c.execute(query, params)
        samples = c.fetchall()
    return render_template_string(SAMPLES_HTML, samples=samples, search=search, status_filter=status_filter,
                                  dept_filter=dept_filter, date_from=date_from, date_to=date_to)

@app.route('/sample/<sample_id>', methods=['GET', 'POST'])
def sample_detail(sample_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM samples WHERE sample_id=?", (sample_id,))
        sample = c.fetchone()
        if not sample or (sample[5] and session['role'] != 'admin' and session['user'] != sample[7] and
                          not c.execute("SELECT 1 FROM sample_departments WHERE sample_id=? AND receiver=?", (sample_id, session['user'])).fetchone()):
            return "Access denied", 403

        # دپارتمان‌های مرتبط
        c.execute("SELECT department, receiver, status FROM sample_departments WHERE sample_id=?", (sample_id,))
        departments = c.fetchall()

        # تست‌های درخواستی
        c.execute("SELECT * FROM sample_tests WHERE sample_id=?", (sample_id,))
        requested_tests = c.fetchall()

        # نتایج
        c.execute("SELECT * FROM test_results WHERE sample_id=? ORDER BY test_type, replicate", (sample_id,))
        results_raw = c.fetchall()

        if request.method == 'POST':
            test_type = request.form['test_type']
            replicate = int(request.form.get('replicate', 1))
            performed_by = session['user']
            test_date = datetime.now().strftime("%Y-%m-%d")
            param_dict = {}
            for key in request.form:
                if key.startswith('param_'):
                    param_dict[key[6:]] = request.form[key]
            image_filename = ''
            if 'image' in request.files:
                file = request.files['image']
                if file and file.filename and allowed_file(file.filename):
                    safe_fname = secure_filename(f"{sample_id}_{test_type}_rep{replicate}_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file.filename.rsplit('.', 1)[-1]}")
                    file.save(os.path.join(app.config['UPLOAD_FOLDER'], safe_fname))
                    image_filename = safe_fname
            c.execute("INSERT INTO test_results (sample_id, test_type, replicate, parameters, performed_by, test_date, image) VALUES (?,?,?,?,?,?,?)",
                      (sample_id, test_type, replicate, json.dumps(param_dict), performed_by, test_date, image_filename))
            # به‌روزرسانی وضعیت نمونه (کلی)
            c.execute("UPDATE samples SET status='In Progress' WHERE sample_id=? AND status='Pending'", (sample_id,))
            conn.commit()
            log_action(sample_id, performed_by, f"Test {test_type} rep{replicate} completed")
            add_notification(sample[7], f'Result added for {sample_id}: {test_type} rep{replicate}.', f'/sample/{sample_id}')
            return redirect(url_for('sample_detail', sample_id=sample_id))

    from collections import defaultdict
    grouped = defaultdict(list)
    for t in results_raw:
        try:
            params = json.loads(t[4]) if t[4] else {}
        except:
            params = {}
        grouped[t[1]].append({'replicate': t[2], 'parameters': params, 'performed_by': t[5], 'test_date': t[6], 'image': t[7]})
    test_map = get_test_map()
    dept_tests = test_map.get(session['dept'], [])
    return render_template_string(SAMPLE_DETAIL_HTML, sample=sample, departments=departments,
                                  requested_tests=requested_tests, grouped=grouped, dept_tests=dept_tests)

@app.route('/receive_sample/<sample_id>/<department>', methods=['POST'])
def receive_sample_department(sample_id, department):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM sample_departments WHERE sample_id=? AND department=? AND receiver=?",
                  (sample_id, department, session['user']))
        if not c.fetchone() and session['role'] != 'admin':
            return "Access denied", 403
        c.execute("UPDATE sample_departments SET status='Pending' WHERE sample_id=? AND department=?", (sample_id, department))
        # اگر همه دپارتمان‌ها تأیید شدند، وضعیت کلی نمونه را Pending کن
        c.execute("SELECT COUNT(*) FROM sample_departments WHERE sample_id=? AND status='Awaiting Receipt'", (sample_id,))
        if c.fetchone()[0] == 0:
            c.execute("UPDATE samples SET status='Pending' WHERE sample_id=?", (sample_id,))
        conn.commit()
    log_action(sample_id, session['user'], f'Received sample in {department}')
    return redirect(url_for('sample_detail', sample_id=sample_id))

@app.route('/print_sample/<sample_id>')
def print_sample(sample_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM samples WHERE sample_id=?", (sample_id,))
        sample = c.fetchone()
        if not sample or (sample[5] and session['role'] != 'admin' and session['user'] != sample[7]):
            return "Access denied", 403
        c.execute("SELECT * FROM sample_tests WHERE sample_id=?", (sample_id,))
        requested_tests = c.fetchall()
        c.execute("SELECT * FROM test_results WHERE sample_id=? ORDER BY test_type, replicate", (sample_id,))
        results_raw = c.fetchall()
        c.execute("SELECT * FROM report_settings WHERE id=1")
        settings = c.fetchone()
    return render_template_string(PRINT_SAMPLE_HTML, sample=sample, requested_tests=requested_tests,
                                  results_raw=results_raw, settings=settings)

@app.route('/download_sample_pdf/<sample_id>')
def download_sample_pdf(sample_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM samples WHERE sample_id=?", (sample_id,))
        sample = c.fetchone()
        if not sample or (sample[5] and session['role'] != 'admin' and session['user'] != sample[7]):
            return "Access denied", 403
        c.execute("SELECT * FROM test_results WHERE sample_id=? ORDER BY test_type, replicate", (sample_id,))
        results = c.fetchall()
        c.execute("SELECT * FROM report_settings WHERE id=1")
        settings = c.fetchone()

    pdf = FPDF()
    pdf.add_page()
    if settings and settings[3]:
        logo_path = os.path.join(app.config['UPLOAD_FOLDER'], settings[3])
        if os.path.exists(logo_path):
            pdf.image(logo_path, x=10, y=10, w=30)
    if settings and settings[1]:
        pdf.set_font('Helvetica', 'B', 14)
        pdf.cell(0, 10, settings[1], align='C')
        pdf.ln(10)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'LabFlow LIMS - Sample Report', align='C')
    pdf.ln(10)
    pdf.set_font('Helvetica', '', 11)
    for label, val in [('Sample ID', sample[1]), ('Type', sample[2]), ('Source', sample[3]), ('Description', sample[4]),
                       ('Status', sample[6]), ('Submitted by', sample[7]), ('Received by', sample[8]), ('Date', sample[10])]:
        pdf.cell(0, 8, f'{label}: {val}')
        pdf.ln(6)
    pdf.ln(5)
    pdf.set_font('Helvetica', 'B', 13)
    pdf.cell(0, 10, 'Test Results')
    pdf.ln(8)
    for r in results:
        pdf.set_font('Helvetica', '', 10)
        try:
            params = json.loads(r[4]) if r[4] else {}
        except:
            params = {}
        param_str = ', '.join(f'{k}: {v}' for k, v in params.items())
        pdf.cell(0, 7, f'{r[1]} (rep {r[2]}): {param_str} | By: {r[5]} on {r[6]}')
        pdf.ln(6)
    if settings and settings[2]:
        pdf.ln(10)
        pdf.set_font('Helvetica', 'I', 9)
        pdf.cell(0, 8, settings[2], align='C')
    buf = pdf.output()
    return send_file(io.BytesIO(buf), mimetype='application/pdf', as_attachment=True, download_name=f'{sample_id}_report.pdf')

@app.route('/update_status/<sample_id>', methods=['POST'])
def update_status(sample_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        conn.execute("UPDATE samples SET status=? WHERE sample_id=?", (request.form['status'], sample_id))
        conn.commit()
    log_action(sample_id, session['user'], f'Status changed to {request.form["status"]}')
    return redirect(url_for('sample_detail', sample_id=sample_id))

@app.route('/request_password_change', methods=['POST'])
def request_password_change():
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        conn.execute("UPDATE password_change_requests SET status='expired' WHERE username=? AND status='pending'", (session['user'],))
        conn.execute("INSERT INTO password_change_requests (username, request_time, status) VALUES (?,?,?)",
                     (session['user'], datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'pending'))
        conn.commit()
    flash('Password change request submitted.', 'info')
    return redirect(url_for('dashboard'))

@app.route('/manage_users', methods=['GET', 'POST'])
def manage_users():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'create':
                try:
                    c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                              (request.form['username'], generate_password_hash(request.form['password']),
                               request.form['role'], request.form['department'], request.form['full_name']))
                    conn.commit()
                    flash('User created.', 'success')
                except:
                    flash('Username already exists.', 'danger')
            elif action == 'reset_password':
                cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
                c.execute("SELECT id FROM password_change_requests WHERE username=? AND status='pending' AND request_time >= ?",
                          (request.form['username'], cutoff))
                if c.fetchone():
                    new_pass = generate_temp_password()
                    c.execute("UPDATE users SET password=?, locked=0, failed_attempts=0 WHERE username=?",
                              (generate_password_hash(new_pass), request.form['username']))
                    c.execute("UPDATE password_change_requests SET status='completed' WHERE username=? AND status='pending'",
                              (request.form['username'],))
                    conn.commit()
                    flash(f'Password reset to: {new_pass}', 'success')
                else:
                    flash('No valid pending request.', 'warning')
            return redirect(url_for('manage_users'))
        c.execute("SELECT username, full_name, role, department, locked FROM users ORDER BY username")
        users = c.fetchall()
        cutoff = (datetime.now() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
        c.execute("SELECT username, request_time FROM password_change_requests WHERE status='pending' AND request_time >= ?", (cutoff,))
        pending_requests = c.fetchall()
    return render_template_string(MANAGE_USERS_HTML, users=users, pending_requests=pending_requests, departments=get_all_departments())

@app.route('/manage_tests', methods=['GET', 'POST'])
def manage_tests():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        if request.method == 'POST':
            action = request.form.get('action')
            if action == 'add':
                c.execute("INSERT INTO test_definitions (test_name, department, parameters) VALUES (?,?,?)",
                          (request.form['test_name'], request.form['department'], request.form.get('parameters', '')))
                conn.commit()
                flash('Test added.', 'success')
            elif action == 'delete':
                c.execute("DELETE FROM test_definitions WHERE id=?", (request.form['test_id'],))
                conn.commit()
                flash('Test deleted.', 'success')
            return redirect(url_for('manage_tests'))
        c.execute("SELECT * FROM test_definitions ORDER BY department, test_name")
        tests = c.fetchall()
    return render_template_string(MANAGE_TESTS_HTML, tests=tests, departments=get_all_departments())

@app.route('/audit')
def audit():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 200")
        logs = c.fetchall()
    return render_template_string(AUDIT_HTML, logs=logs)

# ---------- یادداشت‌های خصوصی ----------
@app.route('/notes', methods=['GET', 'POST'])
def private_notes():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        subject = request.form.get('subject', 'Note')
        body = request.form.get('body', '')
        file_path = ''
        if 'attachment' in request.files:
            file = request.files['attachment']
            if file and file.filename and allowed_file(file.filename):
                safe_name = secure_filename(f"{session['user']}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], safe_name))
                file_path = safe_name
        with get_db() as conn:
            conn.execute("INSERT INTO private_notes (username, subject, body, file_path, created_at) VALUES (?,?,?,?,?)",
                         (session['user'], subject, body, file_path, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            conn.commit()
        flash('Note saved.', 'success')
        return redirect(url_for('private_notes'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM private_notes WHERE username=? ORDER BY created_at DESC", (session['user'],))
        notes = c.fetchall()
    return render_template_string(NOTES_HTML, notes=notes)

# ---------- Reminders ----------
@app.route('/reminders', methods=['GET', 'POST'])
def reminders():
    if 'user' not in session:
        return redirect(url_for('login'))
    if request.method == 'POST':
        message = request.form.get('message', 'Reminder')
        minutes = int(request.form.get('minutes', 5))
        remind_time = (datetime.now() + timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S")
        with get_db() as conn:
            conn.execute("INSERT INTO reminders (username, message, remind_time) VALUES (?,?,?)",
                         (session['user'], message, remind_time))
            conn.commit()
        flash('Reminder set successfully.', 'success')
        return redirect(url_for('dashboard'))
    return render_template_string(REMINDER_HTML)

# ---------- تنظیمات گزارش (مدیر) ----------
@app.route('/manage_settings', methods=['GET', 'POST'])
def manage_settings():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    if request.method == 'POST':
        header_text = request.form.get('header_text', '')
        footer_text = request.form.get('footer_text', '')
        logo_path = ''
        if 'logo' in request.files:
            file = request.files['logo']
            if file and file.filename and allowed_file(file.filename):
                safe_name = secure_filename(f"logo_{datetime.now().strftime('%Y%m%d%H%M%S')}.{file.filename.rsplit('.', 1)[-1]}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], safe_name))
                logo_path = safe_name
        with get_db() as conn:
            c = conn.cursor()
            if logo_path:
                c.execute("UPDATE report_settings SET header_text=?, footer_text=?, logo_path=? WHERE id=1",
                          (header_text, footer_text, logo_path))
            else:
                c.execute("UPDATE report_settings SET header_text=?, footer_text=? WHERE id=1",
                          (header_text, footer_text))
            conn.commit()
        flash('Settings updated.', 'success')
        return redirect(url_for('manage_settings'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM report_settings WHERE id=1")
        settings = c.fetchone()
    return render_template_string(MANAGE_SETTINGS_HTML, settings=settings)

# ---------- چت ----------
@app.route('/chat')
def chat():
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT other_user FROM (
                SELECT receiver AS other_user FROM messages WHERE sender=?
                UNION
                SELECT sender AS other_user FROM messages WHERE receiver=?
            )
        """, (session['user'], session['user']))
        chat_users = [row[0] for row in c.fetchall()]
        chat_list = []
        for username in chat_users:
            c.execute("SELECT body, send_time, is_read FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY send_time DESC LIMIT 1",
                      (session['user'], username, username, session['user']))
            last_msg = c.fetchone()
            c.execute("SELECT COUNT(*) FROM messages WHERE sender=? AND receiver=? AND is_read=0", (username, session['user']))
            unread = c.fetchone()[0]
            if last_msg:
                chat_list.append({
                    'username': username,
                    'last_msg': last_msg[0][:50] + ('...' if len(last_msg[0]) > 50 else ''),
                    'time': last_msg[1],
                    'unread': unread
                })
    return render_template_string(CHAT_LIST_HTML, chat_list=chat_list, all_users=get_all_users())

@app.route('/chat/<username>', methods=['GET', 'POST'])
def chat_with(username):
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        if request.method == 'POST':
            body = request.form['body']
            send_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            file_path = ''
            if 'attachment' in request.files:
                file = request.files['attachment']
                if file and file.filename and allowed_file(file.filename):
                    safe_name = secure_filename(f"{session['user']}_{username}_{datetime.now().strftime('%Y%m%d%H%M%S')}_{file.filename}")
                    file.save(os.path.join(app.config['MESSAGE_UPLOADS'], safe_name))
                    file_path = f'messages/{safe_name}'
            c.execute("INSERT INTO messages (sender, receiver, body, file_path, send_time) VALUES (?,?,?,?,?)",
                      (session['user'], username, body, file_path, send_time))
            conn.commit()
            add_notification(username, f'New message from {session["user"]}', f'/chat/{session["user"]}')
            return redirect(url_for('chat_with', username=username))
        c.execute("UPDATE messages SET is_read=1, read_at=? WHERE sender=? AND receiver=? AND is_read=0",
                  (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), username, session['user']))
        conn.commit()
        c.execute("SELECT * FROM messages WHERE (sender=? AND receiver=?) OR (sender=? AND receiver=?) ORDER BY send_time ASC",
                  (session['user'], username, username, session['user']))
        messages = c.fetchall()
    return render_template_string(CHAT_VIEW_HTML, username=username, messages=messages)

@app.route('/notifications')
def notifications():
    if 'user' not in session:
        return redirect(url_for('login'))
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM notifications WHERE username=? ORDER BY created_time DESC", (session['user'],))
        notifs = c.fetchall()
        c.execute("UPDATE notifications SET is_read=1 WHERE username=? AND is_read=0", (session['user'],))
        conn.commit()
    return render_template_string(NOTIFICATIONS_HTML, notifs=notifs)

@app.route('/notifications/unread_count')
def unread_count():
    if 'user' not in session:
        return jsonify({'count': 0})
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM notifications WHERE username=? AND is_read=0", (session['user'],))
        count = c.fetchone()[0]
    return jsonify({'count': count})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))# ========== قالب‌های HTML ==========
BASE_STYLE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
    *,*::before,*::after{box-sizing:border-box}
    body{margin:0;font-family:system-ui,-apple-system,'Segoe UI',Roboto,sans-serif;font-size:16px;line-height:1.5;color:#212529;background:#f5f7fa;padding-top:60px;padding-bottom:20px}
    .container{max-width:960px;margin:0 auto;padding:0 15px}
    .navbar{background:#2d6a4f;color:white;padding:10px 0;position:fixed;top:0;left:0;right:0;z-index:1000}
    .navbar .container{display:flex;justify-content:space-between;align-items:center}
    .navbar a{color:white;text-decoration:none;padding:8px 12px}
    .card{background:white;border-radius:8px;padding:20px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,0.1)}
    .btn{display:inline-block;padding:10px 20px;border:none;border-radius:6px;cursor:pointer;font-size:16px;text-decoration:none}
    .btn-success{background:#2d6a4f;color:white}
    .btn-info{background:#17a2b8;color:white}
    .btn-warning{background:#ffc107;color:#212529}
    .btn-danger{background:#dc3545;color:white}
    .btn-primary{background:#0d6efd;color:white}
    .btn-secondary{background:#6c757d;color:white}
    .btn-sm{padding:5px 10px;font-size:14px}
    table{width:100%;border-collapse:collapse}
    th,td{padding:10px;text-align:left;border-bottom:1px solid #ddd}
    .alert{padding:15px;border-radius:6px;margin-bottom:15px}
    .alert-info{background:#d1ecf1;color:#0c5460}
    .alert-danger{background:#f8d7da;color:#721c24}
    .alert-warning{background:#fff3cd;color:#856404}
    .alert-success{background:#d4edda;color:#155724}
    .form-control{width:100%;padding:10px;border:1px solid #ddd;border-radius:6px;font-size:16px}
    .form-select{width:100%;padding:10px;border:1px solid #ddd;border-radius:6px;font-size:16px;background:white}
    .form-check{margin:10px 0}
    .badge{display:inline-block;padding:4px 8px;border-radius:20px;font-size:12px;color:white}
    .bg-danger{background:#dc3545}
    .footer{margin-top:40px;font-size:0.9em;color:#666;text-align:center}
    .fab-menu{position:fixed;bottom:30px;right:30px;z-index:1050;width:60px;height:60px;border-radius:50%;background:#2d6a4f;color:white;border:none;font-size:28px;cursor:pointer}
    .offcanvas-menu{position:fixed;top:0;right:-320px;width:300px;height:100%;background:white;z-index:1060;transition:right 0.3s;box-shadow:-2px 0 10px rgba(0,0,0,0.3);padding:20px;overflow-y:auto}
    .offcanvas-menu.show{right:0}
    .offcanvas-menu .nav-btn{display:flex;align-items:center;gap:12px;padding:14px 16px;margin-bottom:12px;border-radius:10px;color:white;font-size:18px;font-weight:bold;text-decoration:none}
    .bg-primary{background:#0d6efd}
    .bg-success{background:#198754}
    .bg-warning{background:#ffc107}
    .bg-info{background:#17a2b8}
    .bg-secondary{background:#6c757d}
    .bg-dark{background:#212529}
    .text-dark{color:#212529}
    .text-muted{color:#6c757d}
    .dept-radio-label{flex:1;min-width:120px;background:#f0f0f0;border-radius:8px;padding:12px 8px;cursor:pointer;text-align:center;border:2px solid transparent}
    .dept-radio-label.selected{background:#2d6a4f;color:white}
    .floating-notif{position:fixed;top:10px;left:50%;transform:translateX(-50%);z-index:9999;background:#dc3545;color:white;padding:10px 20px;border-radius:20px;display:none;font-weight:bold;cursor:pointer}
    .dept-checkbox-group{display:flex;flex-wrap:wrap;gap:10px;margin:10px 0}
    .dept-checkbox-item{flex:1;min-width:200px;padding:10px;background:#f9f9f9;border-radius:8px;border:1px solid #ddd}
    @media(min-width:768px){
        .fab-menu{display:none}
        .desktop-nav{display:flex}
    }
    @media(max-width:767px){
        .desktop-nav{display:none!important}
    }
    @media print{body{padding-top:0}.navbar,.fab-menu,.btn,.footer,form{display:none!important}}
</style>
</head>
<body>
"""

LOGIN_HTML = BASE_STYLE + """
<div class="container mt-5" style="max-width:400px;">
    <h2 class="text-center mb-4">🧪 LabFlow Login</h2>
    {% if error %}<div class="alert alert-danger">{{ error }}</div>{% endif %}
    <form method="post">
        <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
        <div class="mb-3"><label>Username</label><input type="text" name="username" id="username" class="form-control" required></div>
        <div class="mb-3"><label>Password</label><input type="password" name="password" id="password" class="form-control" required></div>
        <div class="mb-3 form-check">
            <input type="checkbox" class="form-check-input" id="rememberMe">
            <label class="form-check-label" for="rememberMe">Remember Me</label>
        </div>
        <button type="submit" class="btn btn-success w-100">Login</button>
    </form>
    <div class="mt-3 text-center"><a href="/forgot_password" class="text-muted">Forgot Password?</a></div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</div>
<script>
(function() {
    const saved = localStorage.getItem('labflow_remember');
    if (saved) {
        try {
            const creds = JSON.parse(saved);
            document.getElementById('username').value = creds.username || '';
            document.getElementById('password').value = creds.password || '';
            document.getElementById('rememberMe').checked = true;
        } catch(e) {}
    }
    document.querySelector('form').addEventListener('submit', function() {
        const remember = document.getElementById('rememberMe').checked;
        if (remember) {
            const creds = {
                username: document.getElementById('username').value,
                password: document.getElementById('password').value
            };
            localStorage.setItem('labflow_remember', JSON.stringify(creds));
        } else {
            localStorage.removeItem('labflow_remember');
        }
    });
})();
</script>
</body></html>"""

FORGOT_PASSWORD_HTML = BASE_STYLE + """
<div class="container mt-5" style="max-width:400px;">
    <h2 class="text-center mb-4">🔑 Forgot Password</h2>
    <p class="text-muted">Enter your username to submit a password reset request.</p>
    {% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="alert alert-{{ category }}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}
    <form method="post">
        <div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div>
        <button type="submit" class="btn btn-warning w-100">Submit Request</button>
    </form>
    <div class="mt-3 text-center"><a href="/">← Back to Login</a></div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</div>
</body></html>"""

DESKTOP_NAV = """
<nav class="navbar desktop-nav" style="display:flex;"><div class="container">
<a class="navbar-brand" href="/dashboard">🧪 LabFlow</a>
<div style="display:flex;gap:10px;">
<a href="/dashboard">Dashboard</a>
<a href="/register">New Sample</a>
<a href="/my_samples">Samples</a>
<a href="/notifications" id="notifLink">🔔 Notifications <span id="notifBadge" class="badge bg-danger" style="display:none;">0</span></a>
<a href="/chat">💬 Chat</a>
<a href="/notes">📝 Notes</a>
<a href="/reminders">⏰ Reminders</a>
<a href="https://pourdadp.github.io/tcid50-calculato/main" target="_blank">🦠 TCID50</a>
<a href="https://pourdadp.github.io/MOI-Calculator/MOI_Calculator" target="_blank">🧫 MOI</a>
{% if session['role']=='admin' %}
<a href="/audit">Audit Log</a>
<a href="/manage_users">Users</a>
<a href="/manage_tests">Tests</a>
<a href="/manage_settings">Settings</a>
{% endif %}
<a href="#" onclick="event.preventDefault();document.getElementById('pwdForm').submit();">Change Password</a>
</div>
<div>
<span>{{ session['full_name'] }} ({{ session['role'] }})</span>
<a href="/logout">Logout</a>
</div>
</div></nav>
<form id="pwdForm" method="post" action="/request_password_change" style="display:none;"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"></form>
"""

MOBILE_MENU = """
<div id="floatingNotif" class="floating-notif" onclick="window.location.href='/notifications'"></div>
<button class="fab-menu" onclick="openMenu()">☰</button>
<div class="offcanvas-menu" id="sideMenu">
<button class="close-btn" onclick="closeMenu()" style="float:right;background:none;border:none;font-size:24px;cursor:pointer;">✕</button>
<h5>🧪 LabFlow Menu</h5>
<a href="/dashboard" class="nav-btn bg-primary">Dashboard</a>
<a href="/register" class="nav-btn bg-success">New Sample</a>
<a href="/my_samples" class="nav-btn bg-warning text-dark">Samples</a>
<a href="/notifications" class="nav-btn bg-info text-dark">🔔 Notifications</a>
<a href="/chat" class="nav-btn bg-info text-dark">💬 Chat</a>
<a href="/notes" class="nav-btn bg-secondary">📝 Notes</a>
<a href="/reminders" class="nav-btn bg-secondary">⏰ Reminders</a>
<a href="https://pourdadp.github.io/tcid50-calculato/main" target="_blank" class="nav-btn bg-secondary">🦠 TCID50</a>
<a href="https://pourdadp.github.io/MOI-Calculator/MOI_Calculator" target="_blank" class="nav-btn bg-secondary">🧫 MOI</a>
{% if session['role']=='admin' %}
<a href="/audit" class="nav-btn bg-info text-dark">Audit Log</a>
<a href="/manage_users" class="nav-btn bg-secondary">Manage Users</a>
<a href="/manage_tests" class="nav-btn bg-dark">Manage Tests</a>
<a href="/manage_settings" class="nav-btn bg-dark">Settings</a>
{% endif %}
<a href="#" class="nav-btn bg-warning text-dark" onclick="event.preventDefault();document.getElementById('pwdForm2').submit();">Change Password</a>
<hr>
<div class="text-muted">{{ session['full_name'] }} ({{ session['role'] }})</div>
<a href="/logout" class="nav-btn bg-danger">Logout</a>
</div>
<form id="pwdForm2" method="post" action="/request_password_change" style="display:none;"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"></form>
<script>
function openMenu(){document.getElementById('sideMenu').classList.add('show');}
function closeMenu(){document.getElementById('sideMenu').classList.remove('show');}
</script>
"""

NAVBAR = DESKTOP_NAV + MOBILE_MENU

DASHBOARD_HTML = BASE_STYLE + NAVBAR + """
<div class="container"><h2>Dashboard</h2>
<div class="row mt-4">{% for stat in stats %}<div class="col-md-3"><div class="card text-center p-3"><h5>{{ stat[0] }}</h5><p>{{ stat[1] }} samples</p></div></div>{% endfor %}</div>
<div class="row mt-4">
    <div class="col-md-4"><canvas id="statusChart"></canvas></div>
    <div class="col-md-4"><canvas id="deptChart"></canvas></div>
    <div class="col-md-8 mt-4"><canvas id="dailyChart"></canvas></div>
</div>
{% if unread > 0 %}<div class="alert alert-info mt-3">You have {{ unread }} unread chat(s). <a href="/chat">View Chat</a></div>{% endif %}
<h4 class="mt-4">Recent Samples</h4>
<table class="table"><thead><tr><th>ID</th><th>Type</th><th>Source</th><th>Status</th><th>Date</th></tr></thead>
<tbody>{% for s in recent %}<tr><td><a href="/sample/{{ s[1] }}">{{ s[1] }}</a></td><td>{{ s[2] }}</td><td>{{ s[3] }}</td><td>{{ s[6] }}</td><td>{{ s[10] }}</td></tr>{% endfor %}</tbody></table></div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const statusData = {{ stats|tojson }};
const deptData = {{ dept_test_counts|tojson }};
const dailyData = {{ daily_counts|tojson }};
new Chart(document.getElementById('statusChart'),{type:'pie',data:{labels:statusData.map(s=>s[0]),datasets:[{data:statusData.map(s=>s[1]),backgroundColor:['#2d6a4f','#4caf50','#ff9800','#f44336','#2196f3']}]}});
new Chart(document.getElementById('deptChart'),{type:'bar',data:{labels:deptData.map(d=>d[0]),datasets:[{label:'Tests',data:deptData.map(d=>d[1]),backgroundColor:'#2d6a4f'}]}});
new Chart(document.getElementById('dailyChart'),{type:'line',data:{labels:dailyData.map(d=>d[0]),datasets:[{label:'Samples per day',data:dailyData.map(d=>d[1]),borderColor:'#2d6a4f',fill:false}]}});
</script>
</body></html>"""

REGISTER_HTML = BASE_STYLE + NAVBAR + """
<div class="container" style="max-width:700px;"><h2>Register New Sample</h2>
<form method="post"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<div class="row"><div class="col-md-6 mb-3"><label>Type</label><select name="type" class="form-select"><option>Active</option><option>Inactive</option></select></div>
<div class="col-md-6 mb-3"><label>Source</label><input type="text" name="source" class="form-control" required></div></div>
<div class="mb-3"><label>Description</label><textarea name="description" class="form-control"></textarea></div>
<div class="mb-3"><label>Additional Info (Visible to All)</label><textarea name="additional_info" class="form-control"></textarea></div>
<div class="mb-3"><label>Confidential Info (Only Submitter & Admin)</label><textarea name="confidential_info" class="form-control"></textarea></div>
<div class="mb-3"><label>Submitted By</label>
{% if submit_users|length==1 and submit_depts|length==0 %}
<input type="text" class="form-control" value="{{ submit_users[0][1] }} ({{ submit_users[0][0] }})" readonly>
<input type="hidden" name="submitted_by" value="{{ submit_users[0][0] }}">
{% else %}
<select name="submitted_by" class="form-select" required><optgroup label="Users">{% for u in submit_users %}<option value="{{ u[0] }}">{{ u[1] }} ({{ u[0] }})</option>{% endfor %}</optgroup>{% if submit_depts %}<optgroup label="Departments">{% for d in submit_depts %}<option value="{{ d }}">{{ d }}</option>{% endfor %}</optgroup>{% endif %}</select>
{% endif %}</div>

<h5>Receiving Departments</h5>
<div class="dept-checkbox-group">
{% for d in receive_depts %}
<div class="dept-checkbox-item">
    <label class="form-check">
        <input type="checkbox" name="departments[]" value="{{ d }}" class="form-check-input dept-check" onchange="toggleReceiver('{{ d }}')"> {{ d }}
    </label>
    <select name="receivers[]" id="receiver_{{ d }}" class="form-select" disabled onchange="updateAllTests()">
        <option value="">-- Select Receiver --</option>
        {% for u in dept_users[d] %}
        <option value="{{ u[0] }}">{{ u[1] }} ({{ u[0] }})</option>
        {% endfor %}
    </select>
</div>
{% endfor %}
</div>

<div class="form-check mb-3"><input class="form-check-input" type="checkbox" name="confidential" id="conf"><label class="form-check-label" for="conf">Confidential Sample</label></div>

<h5>Requested Tests</h5>
<div id="testList">
    <div class="row mb-2 test-row">
        <div class="col-md-10">
            <select name="test_type[]" class="form-select test-type-select" onchange="updateAllTests()">
                <option value="">-- Select test --</option>
            </select>
        </div>
        <div class="col-md-2"><button type="button" class="btn btn-danger btn-sm" onclick="this.closest('.test-row').remove()">✕</button></div>
    </div>
</div>
<button type="button" class="btn btn-secondary btn-sm" onclick="addTestRow()">+ Add Test</button>
<hr>
<button type="submit" class="btn btn-success">Register Sample</button></form></div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
<script>
const deptUsers = {{ dept_users|tojson }};
const testMap = {{ test_map|tojson }};

function toggleReceiver(dept) {
    const sel = document.getElementById('receiver_' + dept);
    const cb = document.querySelector(`input[value="${dept}"]`);
    if (cb && cb.checked) {
        sel.disabled = false;
    } else {
        sel.disabled = true;
        sel.value = '';
    }
    updateAllTests();
}

function updateAllTests() {
    // جمع‌آوری دپارتمان‌های انتخاب‌شده
    const checked = document.querySelectorAll('.dept-check:checked');
    let allTests = [];
    checked.forEach(cb => {
        const dept = cb.value;
        if (testMap[dept]) {
            testMap[dept].forEach(t => {
                const name = typeof t === 'string' ? t : t[0];
                if (!allTests.includes(name)) allTests.push(name);
            });
        }
    });
    // به‌روزرسانی همه selectها
    document.querySelectorAll('.test-type-select').forEach(select => {
        const currentVal = select.value;
        select.innerHTML = '<option value="">-- Select test --</option>';
        allTests.forEach(name => {
            const opt = document.createElement('option');
            opt.value = name;
            opt.textContent = name;
            if (name === currentVal) opt.selected = true;
            select.appendChild(opt);
        });
    });
}

function addTestRow() {
    const row = document.querySelector('.test-row').cloneNode(true);
    row.querySelector('.test-type-select').innerHTML = document.querySelector('.test-type-select').innerHTML;
    document.getElementById('testList').appendChild(row);
}
</script>
</body></html>"""

SAMPLES_HTML = BASE_STYLE + NAVBAR + """
<div class="container"><h2>Samples</h2>
<form class="row mb-3"><div class="col-md-3"><input type="text" name="search" class="form-control" placeholder="Search..." value="{{ search }}"></div>
<div class="col-md-2"><select name="status" class="form-select"><option value="">All Status</option><option>Awaiting Receipt</option><option>Pending</option><option>In Progress</option><option>Completed</option><option>Rejected</option></select></div>
<div class="col-md-2"><select name="dept" class="form-select"><option value="">All Departments</option>{% for d in ['Cell_Molecular','Serology','Microbiology','Cell Culture','Production'] %}<option value="{{ d }}">{{ d }}</option>{% endfor %}</select></div>
<div class="col-md-2"><input type="date" name="date_from" class="form-control" value="{{ date_from }}"></div>
<div class="col-md-2"><input type="date" name="date_to" class="form-control" value="{{ date_to }}"></div>
<div class="col-md-1"><button type="submit" class="btn btn-primary">Filter</button></div></form>
<table class="table"><thead><tr><th>ID</th><th>Type</th><th>Source</th><th>Status</th><th>Confidential</th><th>Date</th></tr></thead>
<tbody>{% for s in samples %}<tr><td><a href="/sample/{{ s[1] }}">{{ s[1] }}</a></td><td>{{ s[2] }}</td><td>{{ s[3] }}</td><td>{{ s[6] }}</td><td>{{ 'Yes' if s[5] else 'No' }}</td><td>{{ s[10] }}</td></tr>{% endfor %}</tbody></table></div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

SAMPLE_DETAIL_HTML = BASE_STYLE + NAVBAR + """
<div class="container"><h2>Sample {{ sample[1] }}</h2>
<div class="card p-3"><p><strong>Type:</strong> {{ sample[2] }} | <strong>Source:</strong> {{ sample[3] }}</p>
<p><strong>Description:</strong> {{ sample[4] }}</p>
{% if sample[11] %}{% if not sample[5] or session['user'] in [sample[7],sample[8]] or session['role']=='admin' %}<div class="alert alert-info"><strong>Additional Info:</strong> {{ sample[11] }}</div>{% endif %}{% endif %}
{% if sample[12] and (session['user']==sample[7] or session['role']=='admin') %}<div class="alert alert-warning"><strong>Confidential Info:</strong> {{ sample[12] }}</div>{% endif %}
<p><strong>Status:</strong> {{ sample[6] }}</p><p><strong>Submitted by:</strong> {{ sample[7] }}</p>
<p><strong>Date:</strong> {{ sample[10] }}</p><p><strong>Confidential:</strong> {{ 'Yes' if sample[5] else 'No' }}</p></div>

<h4 class="mt-4">Departments</h4>
<table class="table">
    <thead><tr><th>Department</th><th>Receiver</th><th>Status</th><th>Action</th></tr></thead>
    <tbody>
    {% for dept in departments %}
    <tr>
        <td>{{ dept[0] }}</td>
        <td>{{ dept[1] }}</td>
        <td>{{ dept[2] }}</td>
        <td>
            {% if dept[2] == 'Awaiting Receipt' and (session['user'] == dept[1] or session['role'] == 'admin') %}
            <form method="post" action="/receive_sample/{{ sample[1] }}/{{ dept[0] }}" style="display:inline;">
                <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
                <button type="submit" class="btn btn-sm btn-info">Confirm Receipt</button>
            </form>
            {% endif %}
        </td>
    </tr>
    {% endfor %}
    </tbody>
</table>

<div class="mt-3"><a href="/print_sample/{{ sample[1] }}" class="btn btn-secondary" target="_blank">🖨️ Print Report</a>
<a href="/download_sample_pdf/{{ sample[1] }}" class="btn btn-outline-danger">📄 Download PDF</a></div>

<h4 class="mt-4">Requested Tests</h4>
<table class="table"><thead><tr><th>Test Type</th><th>Department</th></tr></thead>
<tbody>{% for t in requested_tests %}<tr><td>{{ t[2] }}</td><td>{{ t[3] }}</td></tr>{% endfor %}</tbody></table>

<h4 class="mt-4">Completed Tests</h4>
{% for test_name, reps in grouped.items() %}<div class="card p-3 mt-2"><p><strong>{{ test_name }}</strong></p>
{% for rep in reps %}<p>Replicate {{ rep.replicate }}: {% for k,v in rep.parameters.items() %}<strong>{{ k }}:</strong> {{ v }} {% endfor %}| By: {{ rep.performed_by }} on {{ rep.test_date }}{% if rep.image %}<br><img src="/uploads/{{ rep.image }}" style="max-height:100px;">{% endif %}</p>{% endfor %}</div>{% endfor %}

{% if sample[6]!='Awaiting Receipt' %}
<h4 class="mt-4">Add Test Result ({{ session['dept'] }})</h4>
{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="alert alert-{{ category }}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}
<form method="post" enctype="multipart/form-data"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<div class="row"><div class="col-md-6 mb-3"><label>Test Type</label><select name="test_type" id="testTypeSelect" class="form-select" onchange="updateParamFields()" required>{% for t,params in dept_tests %}<option value="{{ t }}" data-params="{{ params }}">{{ t }}</option>{% endfor %}</select></div>
<div class="col-md-6 mb-3"><label>Replicate #</label><input type="number" name="replicate" class="form-control" value="1" min="1"></div></div>
<div id="paramFields"></div>
<div class="mb-3"><label>Attach Image</label><input type="file" name="image" class="form-control" accept="image/*" capture="environment"></div>
<button type="submit" class="btn btn-primary">Submit Result</button></form>{% endif %}

<h4 class="mt-4">Update Status</h4>
<form method="post" action="/update_status/{{ sample[1] }}"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
<div class="row"><div class="col-md-4"><select name="status" class="form-select"><option>Awaiting Receipt</option><option>Pending</option><option>In Progress</option><option>Completed</option><option>Rejected</option></select></div><div class="col-md-2"><button type="submit" class="btn btn-warning">Update</button></div></div></form></div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
<script>
function updateParamFields(){const sel=document.getElementById('testTypeSelect');const opt=sel.options[sel.selectedIndex];const params=(opt.getAttribute('data-params')||'').split(';').filter(p=>p.trim());const div=document.getElementById('paramFields');div.innerHTML='';params.forEach(p=>{div.innerHTML+=`<div class="mb-3"><label>${p.trim()}</label><input type="text" name="param_${p.trim()}" class="form-control"></div>`;});}
updateParamFields();
</script>
</body></html>"""

PRINT_SAMPLE_HTML = BASE_STYLE + """
<div class="container" id="printArea">
{% if settings and settings[1] %}<div style="text-align:center; font-weight:bold; font-size:18px;">{{ settings[1] }}</div>{% endif %}
{% if settings and settings[3] %}<div style="text-align:center;"><img src="/uploads/{{ settings[3] }}" style="max-height:80px;"></div>{% endif %}
<h2>LabFlow LIMS - Sample Report</h2><hr>
<p><strong>Sample ID:</strong> {{ sample[1] }}</p><p><strong>Type:</strong> {{ sample[2] }} | <strong>Source:</strong> {{ sample[3] }}</p>
<p><strong>Description:</strong> {{ sample[4] }}</p>{% if sample[11] %}<p><strong>Additional Info:</strong> {{ sample[11] }}</p>{% endif %}
<p><strong>Status:</strong> {{ sample[6] }}</p><p><strong>Submitted by:</strong> {{ sample[7] }} | <strong>Received by:</strong> {{ sample[8] }}</p>
<p><strong>Receiving Department:</strong> {{ sample[9] }}</p><p><strong>Date:</strong> {{ sample[10] }}</p><p><strong>Confidential:</strong> {{ 'Yes' if sample[5] else 'No' }}</p><hr>
<h4>Requested Tests</h4><table class="table"><thead><tr><th>Test Type</th><th>Department</th></tr></thead><tbody>{% for t in requested_tests %}<tr><td>{{ t[2] }}</td><td>{{ t[3] }}</td></tr>{% endfor %}</tbody></table>
<h4>Test Results</h4>{% for r in results_raw %}<div class="card p-3 mt-2"><p><strong>{{ r[1] }}</strong> (rep {{ r[2] }}): {{ r[3] }} | By: {{ r[4] }} on {{ r[5] }}{% if r[6] %}<br><img src="/uploads/{{ r[6] }}" style="max-height:200px;">{% endif %}</p></div>{% endfor %}
<hr><p>Printed by: {{ session['full_name'] }} on {{ now }}</p>
{% if settings and settings[2] %}<div style="text-align:center; font-style:italic;">{{ settings[2] }}</div>{% endif %}
</div>
<script>window.print();</script>
</body></html>"""

MANAGE_USERS_HTML = BASE_STYLE + NAVBAR + """
<div class="container" style="max-width:700px;"><h2>Manage Users</h2>
{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="alert alert-{{ category }}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}
<h4>Pending Password Change Requests</h4>{% if pending_requests %}<ul class="list-group mb-3">{% for req in pending_requests %}<li class="list-group-item d-flex justify-content-between align-items-center">{{ req[0] }} (requested {{ req[1] }})<form method="post" style="display:inline;"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="action" value="reset_password"><input type="hidden" name="username" value="{{ req[0] }}"><button type="submit" class="btn btn-sm btn-warning">Reset Password</button></form></li>{% endfor %}</ul>{% else %}<p>No pending requests.</p>{% endif %}
<h4>Create New User</h4><form method="post"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="action" value="create">
<div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div>
<div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control" required></div>
<div class="mb-3"><label>Full Name</label><input type="text" name="full_name" class="form-control" required></div>
<div class="mb-3"><label>Role</label><select name="role" class="form-select"><option>user</option><option>admin</option></select></div>
<div class="mb-3"><label>Department</label><div style="display:flex;flex-wrap:wrap;gap:8px;">{% for d in departments %}<label class="dept-radio-label" onclick="selectDept(this,'{{ d }}')"><input type="radio" name="department" value="{{ d }}" required><span>{{ d }}</span></label>{% endfor %}</div></div>
<button type="submit" class="btn btn-success mt-2">Create User</button></form><hr>
<h4>Existing Users</h4><ul class="list-group">{% for u in users %}<li class="list-group-item d-flex justify-content-between align-items-center">{{ u[1] }} ({{ u[0] }}) - {{ u[2] }} / {{ u[3] }}<div>{% if u[4]==1 %}<span class="badge bg-danger me-2">Locked</span><form method="post" action="/unlock_user/{{ u[0] }}" style="display:inline;"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><button type="submit" class="btn btn-sm btn-outline-success">Unlock</button></form>{% endif %}{% if u[0] != session['user'] %}<form method="post" action="/delete_user/{{ u[0] }}" style="display:inline;" onsubmit="return confirm('Are you sure you want to delete user {{ u[0] }}?');"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><button type="submit" class="btn btn-sm btn-outline-danger ms-1">Delete</button></form>{% endif %}</div></li>{% endfor %}</ul></div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
<script>function selectDept(label,value){document.querySelectorAll('.dept-radio-label').forEach(l=>l.classList.remove('selected'));label.classList.add('selected');label.querySelector('input').checked=true;}</script>
</body></html>"""

MANAGE_TESTS_HTML = BASE_STYLE + NAVBAR + """
<div class="container" style="max-width:700px;"><h2>Manage Tests</h2>
{% with messages = get_flashed_messages(with_categories=true) %}{% if messages %}{% for category, message in messages %}<div class="alert alert-{{ category }}">{{ message }}</div>{% endfor %}{% endif %}{% endwith %}
<h4>Add New Test</h4><form method="post"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="action" value="add">
<div class="row"><div class="col-md-4 mb-3"><label>Test Name</label><input type="text" name="test_name" class="form-control" required></div>
<div class="col-md-4 mb-3"><label>Department</label><select name="department" class="form-select" required>{% for d in departments %}<option value="{{ d }}">{{ d }}</option>{% endfor %}</select></div>
<div class="col-md-4 mb-3"><label>Parameters (separated by ;)</label><input type="text" name="parameters" class="form-control" placeholder="e.g. CT Value;Target Gene"></div></div>
<button type="submit" class="btn btn-success">Add Test</button></form><hr>
<h4>Existing Tests</h4><table class="table"><thead><tr><th>Test Name</th><th>Department</th><th>Parameters</th><th>Actions</th></tr></thead>
<tbody>{% for t in tests %}<tr><td>{{ t[1] }}</td><td>{{ t[2] }}</td><td>{{ t[3] }}</td><td>
<form method="post" style="display:inline;"><input type="hidden" name="_csrf_token" value="{{ csrf_token() }}"><input type="hidden" name="action" value="delete"><input type="hidden" name="test_id" value="{{ t[0] }}"><button type="submit" class="btn btn-danger btn-sm">Delete</button></form></td></tr>{% endfor %}</tbody></table></div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

AUDIT_HTML = BASE_STYLE + NAVBAR + """
<div class="container"><h2>Audit Log</h2><table class="table"><thead><tr><th>Timestamp</th><th>User</th><th>Sample ID</th><th>Action</th></tr></thead>
<tbody>{% for log in logs %}<tr><td>{{ log[4] }}</td><td>{{ log[2] }}</td><td>{{ log[1] }}</td><td>{{ log[3] }}</td></tr>{% endfor %}</tbody></table></div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

NOTIFICATIONS_HTML = BASE_STYLE + NAVBAR + """
<div class="container"><h2>🔔 Notifications</h2>
{% if notifs %}<ul class="list-group">{% for n in notifs %}<li class="list-group-item d-flex justify-content-between align-items-center"><div>{% if n[3] %}<a href="{{ n[3] }}">{{ n[2] }}</a>{% else %}{{ n[2] }}{% endif %}<br><small class="text-muted">{{ n[5] }}</small></div>{% if n[4]==0 %}<span class="badge bg-primary">New</span>{% endif %}</li>{% endfor %}</ul>{% else %}<p>No notifications yet.</p>{% endif %}</div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

NOTES_HTML = BASE_STYLE + NAVBAR + """
<div class="container" style="max-width:700px;"><h2>📝 Private Notes</h2>
<form method="post" enctype="multipart/form-data">
    <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
    <div class="mb-3"><label>Subject</label><input type="text" name="subject" class="form-control" required></div>
    <div class="mb-3"><label>Body</label><textarea name="body" class="form-control" rows="4"></textarea></div>
    <div class="mb-3"><label>Attachment (optional)</label><input type="file" name="attachment" class="form-control"></div>
    <button type="submit" class="btn btn-success">Save Note</button>
</form>
<hr>
<h4>Your Notes</h4>
{% if notes %}
<ul class="list-group">
{% for note in notes %}
<li class="list-group-item">
    <strong>{{ note[2] }}</strong>
    <p>{{ note[3] }}</p>
    {% if note[4] %}<a href="/uploads/{{ note[4] }}" target="_blank">Download Attachment</a>{% endif %}
    <br><small class="text-muted">{{ note[5] }}</small>
</li>
{% endfor %}
</ul>
{% else %}
<p>No notes yet.</p>
{% endif %}
</div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

REMINDER_HTML = BASE_STYLE + NAVBAR + """
<div class="container" style="max-width:500px;"><h2>⏰ Set Reminder</h2>
<form method="post">
    <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
    <div class="mb-3"><label>Reminder Message</label><input type="text" name="message" class="form-control" required></div>
    <div class="mb-3"><label>Remind me in (minutes)</label><input type="number" name="minutes" class="form-control" value="5" min="1"></div>
    <button type="submit" class="btn btn-success">Set Reminder</button>
</form>
</div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

MANAGE_SETTINGS_HTML = BASE_STYLE + NAVBAR + """
<div class="container" style="max-width:600px;"><h2>⚙️ Report Settings</h2>
<form method="post" enctype="multipart/form-data">
    <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
    <div class="mb-3"><label>Header Text</label><input type="text" name="header_text" class="form-control" value="{{ settings[1] if settings else '' }}"></div>
    <div class="mb-3"><label>Footer Text</label><input type="text" name="footer_text" class="form-control" value="{{ settings[2] if settings else '' }}"></div>
    <div class="mb-3"><label>Logo (PNG, JPG)</label>
    {% if settings and settings[3] %}<p><img src="/uploads/{{ settings[3] }}" style="max-height:60px;"></p>{% endif %}
    <input type="file" name="logo" class="form-control"></div>
    <button type="submit" class="btn btn-success">Save Settings</button>
</form>
</div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

CHAT_LIST_HTML = BASE_STYLE + NAVBAR + """
<div class="container">
    <h2>💬 Chat</h2>
    {% if chat_list %}
        <div class="list-group mb-4">
            {% for chat in chat_list %}
            <a href="/chat/{{ chat.username }}" class="list-group-item list-group-item-action d-flex justify-content-between align-items-center">
                <div>
                    <strong>{{ chat.username }}</strong>
                    <p class="mb-0 text-muted small">{{ chat.last_msg }}</p>
                </div>
                <div>
                    <small class="text-muted">{{ chat.time }}</small>
                    {% if chat.unread > 0 %}
                    <span class="badge bg-danger rounded-pill">{{ chat.unread }}</span>
                    {% endif %}
                </div>
            </a>
            {% endfor %}
        </div>
    {% else %}
        <p class="text-muted">No messages yet.</p>
    {% endif %}

    <h4>Start New Conversation</h4>
    <div class="d-flex gap-2">
        <select id="usernameSelect" class="form-select">
            <option value="">-- Select User --</option>
            {% for u in all_users %}
            {% if u[0] != session['user'] %}
            <option value="{{ u[0] }}">{{ u[1] }} ({{ u[0] }})</option>
            {% endif %}
            {% endfor %}
        </select>
        <button onclick="const sel=document.getElementById('usernameSelect'); if(sel.value) window.location.href='/chat/'+sel.value;" class="btn btn-success">Chat</button>
    </div>
</div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

CHAT_VIEW_HTML = BASE_STYLE + """
<div class="container d-flex flex-column" style="height: 100vh; padding-top: 70px;">
    <div class="d-flex align-items-center mb-3">
        <a href="/chat" class="btn btn-sm btn-outline-secondary me-2">← Back</a>
        <h4 class="mb-0">{{ username }}</h4>
    </div>
    <div class="flex-grow-1 overflow-auto mb-3" style="background: #f5f5f5; border-radius: 10px; padding: 15px;" id="chatBox">
        {% for msg in messages %}
        <div class="d-flex mb-2 {% if msg[1] == session['user'] %}justify-content-end{% else %}justify-content-start{% endif %}">
            <div class="p-2 rounded {% if msg[1] == session['user'] %}bg-success text-white{% else %}bg-white{% endif %}" style="max-width: 75%;">
                <p class="mb-0">{{ msg[4] }}</p>
                {% if msg[5] %}
                <a href="/uploads/{{ msg[5] }}" class="text-decoration-underline text-white small" target="_blank">Attachment</a>
                {% endif %}
                <small class="d-block {% if msg[1] == session['user'] %}text-white-50{% else %}text-muted{% endif %}">
                    {{ msg[7] }}
                    {% if msg[1] == session['user'] and msg[6] == 1 %}
                        <span class="ms-1">✓✓ Seen</span>
                    {% elif msg[1] == session['user'] %}
                        <span class="ms-1">✓</span>
                    {% endif %}
                </small>
            </div>
        </div>
        {% endfor %}
    </div>
    <form method="post" enctype="multipart/form-data" class="d-flex gap-2">
        <input type="hidden" name="_csrf_token" value="{{ csrf_token() }}">
        <input type="text" name="body" class="form-control" placeholder="Type a message..." required>
        <input type="file" name="attachment" class="form-control" style="width: 50px;">
        <button type="submit" class="btn btn-success">Send</button>
    </form>
</div>
<div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
</body></html>"""

# ---------- Polling script ----------
POLLING_SCRIPT = """
<script>
let lastCount = 0;
function playBeep(){try{const ctx=new(window.AudioContext||window.webkitAudioContext)();const osc=ctx.createOscillator();const gain=ctx.createGain();osc.connect(gain);gain.connect(ctx.destination);osc.frequency.value=800;gain.gain.value=0.3;osc.start();osc.stop(ctx.currentTime+0.15);}catch(e){}}
function updateBadge(count){const badge=document.getElementById('notifBadge');if(badge){if(count>0){badge.textContent=count;badge.style.display='inline-block';}else{badge.style.display='none';}}}
function updateFloatingNotif(count){
    const fn = document.getElementById('floatingNotif');
    if(fn && count > 0){
        fn.textContent = count + ' new notification(s)';
        fn.style.display = 'block';
    } else if(fn) {
        fn.style.display = 'none';
    }
}
async function pollNotifications(){try{const resp=await fetch('/notifications/unread_count');const data=await resp.json();if(data.count>lastCount){playBeep();}lastCount=data.count;updateBadge(data.count);updateFloatingNotif(data.count);}catch(e){}}
setInterval(pollNotifications,30000);pollNotifications();
</script>
"""

for template_name in ['DASHBOARD_HTML', 'REGISTER_HTML', 'SAMPLES_HTML', 'SAMPLE_DETAIL_HTML',
                       'MANAGE_USERS_HTML', 'MANAGE_TESTS_HTML', 'AUDIT_HTML', 'NOTIFICATIONS_HTML',
                       'NOTES_HTML', 'REMINDER_HTML', 'MANAGE_SETTINGS_HTML',
                       'CHAT_LIST_HTML', 'CHAT_VIEW_HTML']:
    if template_name in locals():
        locals()[template_name] = locals()[template_name].replace('</body>', POLLING_SCRIPT + '</body>')

# ---------- راه‌اندازی ----------
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8501, debug=False)
