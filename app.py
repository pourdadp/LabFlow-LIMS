# -*- coding: utf-8 -*-
from flask import Flask, render_template_string, request, redirect, url_for, session, send_from_directory, flash
import sqlite3
import hashlib
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = 'labflow_secret_key_2024'

UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024

DEPARTMENTS = ['Cell_Molecular', 'Serology', 'Microbiology', 'Cell Culture', 'Production', 'all']

# ---------- دیتابیس ----------
def init_db():
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  username TEXT UNIQUE NOT NULL,
                  password TEXT NOT NULL,
                  role TEXT NOT NULL DEFAULT 'user',
                  department TEXT,
                  full_name TEXT)''')
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
                  created_date TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS sample_tests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sample_id TEXT NOT NULL,
                  test_type TEXT,
                  department TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tests
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sample_id TEXT NOT NULL,
                  test_type TEXT,
                  department TEXT,
                  result TEXT,
                  performed_by TEXT,
                  test_date TEXT,
                  image TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS audit_log
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  sample_id TEXT,
                  user TEXT,
                  action TEXT,
                  timestamp TEXT)''')
    # جدول جدید تعریف تست‌ها
    c.execute('''CREATE TABLE IF NOT EXISTS test_definitions
                 (id INTEGER PRIMARY KEY AUTOINCREMENT,
                  test_name TEXT NOT NULL,
                  department TEXT NOT NULL)''')
    # تست‌های پیش‌فرض برای هر بخش
    default_tests = [
        ('Cell Culture', 'Cell Culture'),
        ('PCR', 'Cell_Molecular'),
        ('qPCR', 'Cell_Molecular'),
        ('HA', 'Serology'),
        ('ELISA', 'Serology'),
        ('Bacterial Culture', 'Microbiology'),
        ('Gram Staining', 'Microbiology'),
        ('Western Blot', 'Production'),
        ('SDS-PAGE', 'Production'),
    ]
    for test_name, dept in default_tests:
        try:
            c.execute("INSERT INTO test_definitions (test_name, department) VALUES (?,?)", (test_name, dept))
        except:
            pass
    # کاربران پیش‌فرض
    try:
        admin_pw = hashlib.sha256('admin123'.encode()).hexdigest()
        c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                  ('admin', admin_pw, 'admin', 'all', 'Admin User'))
        user_pw = hashlib.sha256('user123'.encode()).hexdigest()
        c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                  ('cell_user', user_pw, 'user', 'Cell_Molecular', 'Cell Lab Tech'))
        c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                  ('sero_user', user_pw, 'user', 'Serology', 'Serology Tech'))
        c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                  ('micro_user', user_pw, 'user', 'Microbiology', 'Micro Lab Tech'))
    except:
        pass
    conn.commit()
    conn.close()

def log_action(sample_id, user, action):
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO audit_log (sample_id, user, action, timestamp) VALUES (?,?,?,?)",
              (sample_id, user, action, timestamp))
    conn.commit()
    conn.close()

def generate_sample_id():
    today = datetime.now().strftime("%Y%m%d")
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM samples WHERE created_date=?", (datetime.now().strftime("%Y-%m-%d"),))
    count = c.fetchone()[0] + 1
    conn.close()
    return f"SPL-{today}-{count:03d}"

def get_all_users():
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT username, full_name FROM users")
    users = c.fetchall()
    conn.close()
    return users

def get_users_by_dept(dept):
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT username, full_name FROM users WHERE department=?", (dept,))
    users = c.fetchall()
    conn.close()
    return users

def get_all_departments():
    return [d for d in DEPARTMENTS if d != 'all']

def get_test_map():
    """Return a dict mapping department -> list of test names."""
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT test_name, department FROM test_definitions ORDER BY department, test_name")
    rows = c.fetchall()
    conn.close()
    test_map = {}
    for name, dept in rows:
        test_map.setdefault(dept, []).append(name)
    return test_map

# ---------- مسیر فایل‌های آپلود شده ----------
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# ---------- صفحه ورود ----------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        conn = sqlite3.connect('labflow.db')
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
        user = c.fetchone()
        conn.close()
        if user:
            session['user'] = user[1]
            session['role'] = user[3]
            session['dept'] = user[4]
            session['full_name'] = user[5] if len(user) > 5 and user[5] else user[1]
            return redirect(url_for('dashboard'))
        else:
            return render_template_string(LOGIN_HTML, error='Invalid credentials')
    return render_template_string(LOGIN_HTML, error='')

# ---------- داشبورد ----------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT status, COUNT(*) FROM samples GROUP BY status")
    stats = c.fetchall()
    c.execute("SELECT * FROM samples ORDER BY created_date DESC LIMIT 10")
    recent = c.fetchall()
    conn.close()
    return render_template_string(DASHBOARD_HTML, stats=stats, recent=recent)

# ---------- ثبت نمونه ----------
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
    test_map = get_test_map()   # نگاشت دپارتمان → لیست تست‌ها

    if request.method == 'POST':
        sample_type = request.form['type']
        source = request.form['source']
        description = request.form['description']
        confidential = 1 if 'confidential' in request.form else 0
        submitted_by = request.form['submitted_by']
        received_by = request.form['received_by']
        receiving_department = request.form['receiving_department']
        sample_id = generate_sample_id()
        today = datetime.now().strftime("%Y-%m-%d")
        conn = sqlite3.connect('labflow.db')
        c = conn.cursor()
        c.execute("INSERT INTO samples (sample_id, type, source, description, confidential, status, submitted_by, received_by, receiving_department, created_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
                  (sample_id, sample_type, source, description, confidential, 'Awaiting Receipt', submitted_by, received_by, receiving_department, today))
        # تست‌های درخواستی – فقط test_type ارسال می‌شود، department = receiving_department
        test_types = request.form.getlist('test_type[]')
        for tt in test_types:
            if tt:
                c.execute("INSERT INTO sample_tests (sample_id, test_type, department) VALUES (?,?,?)",
                          (sample_id, tt, receiving_department))
        conn.commit()
        conn.close()
        log_action(sample_id, session['user'], 'Sample registered, awaiting receipt')
        return redirect(url_for('dashboard'))

    return render_template_string(REGISTER_HTML,
                                  submit_users=submit_users,
                                  submit_depts=submit_depts,
                                  receive_depts=receive_depts,
                                  dept_users=dept_users,
                                  test_map=test_map)

# ---------- تأیید دریافت نمونه ----------
@app.route('/receive_sample/<sample_id>', methods=['POST'])
def receive_sample(sample_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT * FROM samples WHERE sample_id=? AND status='Awaiting Receipt'", (sample_id,))
    sample = c.fetchone()
    if not sample:
        conn.close()
        return "Sample not found or not awaiting receipt", 404
    if session['role'] != 'admin' and session['user'] != sample[8]:
        conn.close()
        return "Access denied", 403
    c.execute("UPDATE samples SET status='Pending' WHERE sample_id=?", (sample_id,))
    conn.commit()
    conn.close()
    log_action(sample_id, session['user'], 'Sample received, status changed to Pending')
    return redirect(url_for('sample_detail', sample_id=sample_id))

# ---------- نمونه‌های من ----------
@app.route('/my_samples')
def my_samples():
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    if session['role'] == 'admin':
        c.execute("SELECT * FROM samples ORDER BY created_date DESC")
    else:
        c.execute("SELECT * FROM samples WHERE submitted_by=? OR received_by=? OR confidential=0 ORDER BY created_date DESC", (session['user'], session['user']))
    samples = c.fetchall()
    conn.close()
    return render_template_string(SAMPLES_HTML, samples=samples)

# ---------- جزئیات نمونه + ثبت جواب ----------
@app.route('/sample/<sample_id>', methods=['GET', 'POST'])
def sample_detail(sample_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT * FROM samples WHERE sample_id=?", (sample_id,))
    sample = c.fetchone()
    if not sample:
        conn.close()
        return "Sample not found", 404
    if sample[5] and session['role'] != 'admin' and session['user'] not in [sample[7], sample[8]]:
        conn.close()
        return "Access denied (confidential sample)", 403
    c.execute("SELECT * FROM sample_tests WHERE sample_id=?", (sample_id,))
    requested_tests = c.fetchall()
    c.execute("SELECT * FROM tests WHERE sample_id=?", (sample_id,))
    completed_tests = c.fetchall()

    if request.method == 'POST':
        test_type = request.form['test_type']
        department = session['dept']
        result = request.form['result']
        performed_by = session['user']
        test_date = datetime.now().strftime("%Y-%m-%d")
        image_filename = ''

        if 'image' in request.files:
            file = request.files['image']
            if file and file.filename:
                allowed_ext = {'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'}
                ext = file.filename.rsplit('.', 1)[-1].lower()
                if ext not in allowed_ext:
                    flash('Only image files (jpg, png, gif) are allowed.', 'danger')
                else:
                    timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
                    image_filename = f"{sample_id}_{test_type}_{timestamp}.{ext}"
                    save_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
                    file.save(save_path)
                    flash('Image uploaded successfully.', 'success')
            else:
                flash('No file selected.', 'warning')
        else:
            flash('No image file received.', 'warning')

        c.execute("INSERT INTO tests (sample_id, test_type, department, result, performed_by, test_date, image) VALUES (?,?,?,?,?,?,?)",
                  (sample_id, test_type, department, result, performed_by, test_date, image_filename))
        c.execute("UPDATE samples SET status='In Progress' WHERE sample_id=? AND status='Pending'", (sample_id,))
        conn.commit()
        log_action(sample_id, performed_by, f"Test {test_type} completed: {result}")
        conn.close()
        return redirect(url_for('sample_detail', sample_id=sample_id))
    conn.close()
    # برای dropdown تست‌ها در صفحه جزئیات (فقط تست‌های مربوط به دپارتمان کاربر)
    test_map = get_test_map()
    dept_tests = test_map.get(session['dept'], [])
    return render_template_string(SAMPLE_DETAIL_HTML, sample=sample, requested_tests=requested_tests,
                                  completed_tests=completed_tests, dept_tests=dept_tests)

# ---------- تغییر وضعیت نمونه ----------
@app.route('/update_status/<sample_id>', methods=['POST'])
def update_status(sample_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    new_status = request.form['status']
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("UPDATE samples SET status=? WHERE sample_id=?", (new_status, sample_id))
    conn.commit()
    conn.close()
    log_action(sample_id, session['user'], f"Status changed to {new_status}")
    return redirect(url_for('sample_detail', sample_id=sample_id))

# ---------- مدیریت تست‌ها (فقط ادمین) ----------
@app.route('/manage_tests', methods=['GET', 'POST'])
def manage_tests():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add':
            test_name = request.form['test_name']
            department = request.form['department']
            try:
                c.execute("INSERT INTO test_definitions (test_name, department) VALUES (?,?)", (test_name, department))
                conn.commit()
                flash('Test added.', 'success')
            except:
                flash('Error adding test.', 'danger')
        elif action == 'delete':
            test_id = request.form['test_id']
            c.execute("DELETE FROM test_definitions WHERE id=?", (test_id,))
            conn.commit()
            flash('Test deleted.', 'success')
        elif action == 'edit':
            test_id = request.form['test_id']
            new_name = request.form['new_name']
            new_dept = request.form['new_department']
            c.execute("UPDATE test_definitions SET test_name=?, department=? WHERE id=?", (new_name, new_dept, test_id))
            conn.commit()
            flash('Test updated.', 'success')
        return redirect(url_for('manage_tests'))
    c.execute("SELECT * FROM test_definitions ORDER BY department, test_name")
    tests = c.fetchall()
    conn.close()
    return render_template_string(MANAGE_TESTS_HTML, tests=tests, departments=get_all_departments())

# ---------- مدیریت کاربران (فقط ادمین) ----------
@app.route('/manage_users', methods=['GET', 'POST'])
def manage_users():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    if request.method == 'POST':
        new_username = request.form['username']
        new_password = hashlib.sha256(request.form['password'].encode()).hexdigest()
        full_name = request.form['full_name']
        role = request.form['role']
        department = request.form['department']
        try:
            conn = sqlite3.connect('labflow.db')
            c = conn.cursor()
            c.execute("INSERT INTO users (username, password, role, department, full_name) VALUES (?,?,?,?,?)",
                      (new_username, new_password, role, department, full_name))
            conn.commit()
            conn.close()
            log_action('SYSTEM', session['user'], f"Created user {new_username}")
        except:
            return render_template_string(MANAGE_USERS_HTML, error='Username already exists!',
                                          users=get_all_users(), departments=get_all_departments())
        return redirect(url_for('manage_users'))
    return render_template_string(MANAGE_USERS_HTML, error='', users=get_all_users(),
                                  departments=get_all_departments())

# ---------- تاریخچه ----------
@app.route('/audit')
def audit():
    if 'user' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = sqlite3.connect('labflow.db')
    c = conn.cursor()
    c.execute("SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 100")
    logs = c.fetchall()
    conn.close()
    return render_template_string(AUDIT_HTML, logs=logs)

# ---------- خروج ----------
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ========== قالب‌های HTML ==========
BASE_STYLE = """
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.css" rel="stylesheet">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<style>
    body { padding-top: 60px; padding-bottom: 20px; }
    .footer { margin-top: 40px; font-size: 0.9em; color: #666; text-align: center; }
    .navbar { margin-bottom: 0; }
    .card { margin-bottom: 20px; }
    .fab-menu {
        position: fixed; bottom: 30px; right: 30px; z-index: 1050;
        width: 60px; height: 60px; border-radius: 50%;
        background: #2d6a4f; color: white; border: none;
        box-shadow: 0 4px 10px rgba(0,0,0,0.3); font-size: 28px;
        display: flex; align-items: center; justify-content: center;
        cursor: pointer; transition: transform 0.2s;
    }
    .fab-menu:hover { transform: scale(1.1); background: #1b4d3a; }
    .offcanvas-menu {
        position: fixed; top: 0; right: -320px; width: 300px; height: 100%;
        background: white; z-index: 1060; transition: right 0.3s;
        box-shadow: -2px 0 10px rgba(0,0,0,0.3); padding: 20px;
        overflow-y: auto;
    }
    .offcanvas-menu.show { right: 0; }
    .offcanvas-menu .close-btn {
        position: absolute; top: 15px; right: 15px; font-size: 24px;
        background: none; border: none; cursor: pointer; color: #666;
    }
    .offcanvas-menu h5 { margin-top: 30px; margin-bottom: 20px; }
    .offcanvas-menu .nav-btn {
        display: flex; align-items: center; gap: 12px;
        padding: 14px 16px; margin-bottom: 12px; border-radius: 10px;
        color: white; font-size: 18px; font-weight: bold;
        text-decoration: none; transition: opacity 0.2s;
    }
    .offcanvas-menu .nav-btn:hover { opacity: 0.9; }
    .offcanvas-menu .nav-btn i { font-size: 24px; }
    .offcanvas-backdrop {
        position: fixed; top:0; left:0; right:0; bottom:0;
        background: rgba(0,0,0,0.5); z-index: 1050; display: none;
    }
    .offcanvas-backdrop.show { display: block; }
    @media (min-width: 768px) {
        .fab-menu { display: none; }
    }
    .dept-radio-label {
        flex: 1; min-width: 120px; background: #f0f0f0; border-radius: 8px;
        padding: 12px 8px; cursor: pointer; text-align: center;
        border: 2px solid transparent; transition: 0.2s;
    }
    .dept-radio-label.selected {
        background: #2d6a4f; color: white; border-color: #1b4d3a;
    }
    .dept-radio-label input { display: none; }
</style>
"""

LOGIN_HTML = (
    BASE_STYLE +
    """
    <div class="container mt-5" style="max-width: 400px;">
        <h2 class="text-center mb-4">🧪 LabFlow Login</h2>
        {% if error %}
        <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        <form method="post">
            <div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div>
            <div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control" required></div>
            <button type="submit" class="btn btn-success w-100">Login</button>
        </form>
        <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    </div>
    """
)

DESKTOP_NAV = """
<nav class="navbar navbar-expand-lg navbar-dark bg-success desktop-nav fixed-top">
    <div class="container">
        <a class="navbar-brand" href="/dashboard">🧪 LabFlow</a>
        <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#desktopNav">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="desktopNav">
            <ul class="navbar-nav">
                <li class="nav-item"><a class="nav-link" href="/dashboard">Dashboard</a></li>
                <li class="nav-item"><a class="nav-link" href="/register">New Sample</a></li>
                <li class="nav-item"><a class="nav-link" href="/my_samples">Samples</a></li>
                {% if session['role'] == 'admin' %}
                <li class="nav-item"><a class="nav-link" href="/audit">Audit Log</a></li>
                <li class="nav-item"><a class="nav-link" href="/manage_users">Users</a></li>
                <li class="nav-item"><a class="nav-link" href="/manage_tests">Tests</a></li>
                {% endif %}
            </ul>
            <ul class="navbar-nav ms-auto">
                <li class="nav-item"><span class="nav-link">{{ session['full_name'] }} ({{ session['role'] }})</span></li>
                <li class="nav-item"><a class="nav-link" href="/logout">Logout</a></li>
            </ul>
        </div>
    </div>
</nav>
"""

MOBILE_MENU = """
<button class="fab-menu" onclick="openMenu()" title="Menu">
    <i class="bi bi-list"></i>
</button>

<div class="offcanvas-backdrop" id="backdrop" onclick="closeMenu()"></div>
<div class="offcanvas-menu" id="sideMenu">
    <button class="close-btn" onclick="closeMenu()">✕</button>
    <h5>🧪 LabFlow Menu</h5>
    <a href="/dashboard" class="nav-btn bg-primary"><i class="bi bi-speedometer2"></i> Dashboard</a>
    <a href="/register" class="nav-btn bg-success"><i class="bi bi-plus-square"></i> New Sample</a>
    <a href="/my_samples" class="nav-btn bg-warning text-dark"><i class="bi bi-collection"></i> Samples</a>
    {% if session['role'] == 'admin' %}
    <a href="/audit" class="nav-btn bg-info text-dark"><i class="bi bi-journal-text"></i> Audit Log</a>
    <a href="/manage_users" class="nav-btn bg-secondary"><i class="bi bi-people"></i> Manage Users</a>
    <a href="/manage_tests" class="nav-btn bg-dark"><i class="bi bi-clipboard-check"></i> Manage Tests</a>
    {% endif %}
    <hr>
    <div class="px-2 text-muted">{{ session['full_name'] }} ({{ session['role'] }})</div>
    <a href="/logout" class="nav-btn bg-danger"><i class="bi bi-box-arrow-right"></i> Logout</a>
</div>

<script>
    function openMenu() {
        document.getElementById('sideMenu').classList.add('show');
        document.getElementById('backdrop').classList.add('show');
    }
    function closeMenu() {
        document.getElementById('sideMenu').classList.remove('show');
        document.getElementById('backdrop').classList.remove('show');
    }
</script>
"""

NAVBAR = DESKTOP_NAV + MOBILE_MENU

DASHBOARD_HTML = (
    BASE_STYLE + NAVBAR +
    """
    <div class="container">
        <h2>Dashboard</h2>
        <div class="row mt-4">
            {% for stat in stats %}
            <div class="col-md-3"><div class="card text-center p-3"><h5>{{ stat[0] }}</h5><p>{{ stat[1] }} samples</p></div></div>
            {% endfor %}
        </div>
        <h4 class="mt-4">Recent Samples</h4>
        <table class="table table-striped">
            <thead><tr><th>ID</th><th>Type</th><th>Source</th><th>Status</th><th>Date</th></tr></thead>
            <tbody>
                {% for s in recent %}
                <tr><td><a href="/sample/{{ s[1] }}">{{ s[1] }}</a></td><td>{{ s[2] }}</td><td>{{ s[3] }}</td><td>{{ s[6] }}</td><td>{{ s[9] }}</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """
)

REGISTER_HTML = (
    BASE_STYLE + NAVBAR +
    """
    <div class="container" style="max-width: 700px;">
        <h2>Register New Sample</h2>
        <form method="post">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label>Type</label>
                    <select name="type" class="form-select"><option>Active</option><option>Inactive</option></select>
                </div>
                <div class="col-md-6 mb-3">
                    <label>Source</label>
                    <input type="text" name="source" class="form-control" required>
                </div>
            </div>
            <div class="mb-3">
                <label>Description</label>
                <textarea name="description" class="form-control"></textarea>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label>Submitted By</label>
                    {% if submit_users|length == 1 and submit_depts|length == 0 %}
                        <input type="text" class="form-control" value="{{ submit_users[0][1] }} ({{ submit_users[0][0] }})" readonly>
                        <input type="hidden" name="submitted_by" value="{{ submit_users[0][0] }}">
                    {% else %}
                        <select name="submitted_by" class="form-select" required>
                            <optgroup label="Users">
                            {% for u in submit_users %}
                            <option value="{{ u[0] }}">{{ u[1] }} ({{ u[0] }})</option>
                            {% endfor %}
                            </optgroup>
                            {% if submit_depts %}
                            <optgroup label="Departments">
                            {% for d in submit_depts %}
                            <option value="{{ d }}">{{ d }}</option>
                            {% endfor %}
                            </optgroup>
                            {% endif %}
                        </select>
                    {% endif %}
                </div>
                <div class="col-md-6 mb-3">
                    <label>Receiving Department</label>
                    <select name="receiving_department" id="receiving_department" class="form-select" required onchange="updateReceivers(); updateTestTypes();">
                        <option value="">-- Select --</option>
                        {% for d in receive_depts %}
                        <option value="{{ d }}">{{ d }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>
            <div class="mb-3">
                <label>Receiver (person)</label>
                <select name="received_by" id="received_by" class="form-select" required disabled>
                    <option value="">-- First select department --</option>
                </select>
            </div>
            <div class="form-check mb-3">
                <input class="form-check-input" type="checkbox" name="confidential" id="conf">
                <label class="form-check-label" for="conf">Confidential Sample</label>
            </div>
            <h5>Requested Tests</h5>
            <div id="testList">
                <div class="row mb-2 test-row">
                    <div class="col-md-10">
                        <select name="test_type[]" class="form-select test-type-select">
                            <option value="">-- Select test --</option>
                        </select>
                    </div>
                    <div class="col-md-2"><button type="button" class="btn btn-danger btn-sm" onclick="this.closest('.test-row').remove()">✕</button></div>
                </div>
            </div>
            <button type="button" class="btn btn-secondary btn-sm" onclick="addTestRow()">+ Add Test</button>
            <hr>
            <button type="submit" class="btn btn-success">Register Sample</button>
        </form>
    </div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    <script>
        const deptUsers = {{ dept_users|tojson }};
        const testMap = {{ test_map|tojson }};
        function updateReceivers() {
            const dept = document.getElementById('receiving_department').value;
            const receiverSelect = document.getElementById('received_by');
            receiverSelect.innerHTML = '';
            if (dept && deptUsers[dept]) {
                receiverSelect.disabled = false;
                deptUsers[dept].forEach(u => {
                    const opt = document.createElement('option');
                    opt.value = u[0];
                    opt.textContent = u[1] + ' (' + u[0] + ')';
                    receiverSelect.appendChild(opt);
                });
            } else {
                receiverSelect.disabled = true;
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = '-- First select department --';
                receiverSelect.appendChild(opt);
            }
        }
        function updateTestTypes() {
            const dept = document.getElementById('receiving_department').value;
            const tests = testMap[dept] || [];
            document.querySelectorAll('.test-type-select').forEach(select => {
                select.innerHTML = '<option value="">-- Select test --</option>';
                tests.forEach(t => {
                    const opt = document.createElement('option');
                    opt.value = t;
                    opt.textContent = t;
                    select.appendChild(opt);
                });
            });
        }
        function addTestRow() {
            const row = document.querySelector('.test-row').cloneNode(true);
            row.querySelector('.test-type-select').innerHTML = document.querySelector('.test-type-select').innerHTML;
            document.getElementById('testList').appendChild(row);
        }
        document.getElementById('receiving_department').addEventListener('change', updateTestTypes);
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """
)

SAMPLES_HTML = (
    BASE_STYLE + NAVBAR +
    """
    <div class="container">
        <h2>Samples</h2>
        <table class="table table-striped">
            <thead><tr><th>ID</th><th>Type</th><th>Source</th><th>Status</th><th>Confidential</th><th>Date</th></tr></thead>
            <tbody>
                {% for s in samples %}
                <tr><td><a href="/sample/{{ s[1] }}">{{ s[1] }}</a></td><td>{{ s[2] }}</td><td>{{ s[3] }}</td><td>{{ s[6] }}</td><td>{{ 'Yes' if s[5] else 'No' }}</td><td>{{ s[9] }}</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """
)

SAMPLE_DETAIL_HTML = (
    BASE_STYLE + NAVBAR +
    """
    <div class="container">
        <h2>Sample {{ sample[1] }}</h2>
        <div class="card p-3">
            <p><strong>Type:</strong> {{ sample[2] }} | <strong>Source:</strong> {{ sample[3] }}</p>
            <p><strong>Description:</strong> {{ sample[4] }}</p>
            <p><strong>Status:</strong> {{ sample[6] }}</p>
            <p><strong>Submitted by:</strong> {{ sample[7] }} | <strong>Received by:</strong> {{ sample[8] }}</p>
            <p><strong>Receiving Department:</strong> {{ sample[9] }}</p>
            <p><strong>Date:</strong> {{ sample[10] }}</p>
            <p><strong>Confidential:</strong> {{ 'Yes' if sample[5] else 'No' }}</p>
        </div>

        {% if sample[6] == 'Awaiting Receipt' and (session['user'] == sample[8] or session['role'] == 'admin') %}
        <div class="mt-3">
            <form method="post" action="/receive_sample/{{ sample[1] }}">
                <button type="submit" class="btn btn-info">Confirm Receipt</button>
            </form>
        </div>
        {% endif %}

        <h4 class="mt-4">Requested Tests</h4>
        <table class="table table-bordered">
            <thead><tr><th>Test Type</th><th>Department</th></tr></thead>
            <tbody>
                {% for t in requested_tests %}
                <tr><td>{{ t[2] }}</td><td>{{ t[3] }}</td></tr>
                {% endfor %}
            </tbody>
        </table>

        <h4 class="mt-4">Completed Tests</h4>
        {% for t in completed_tests %}
        <div class="card p-3 mt-2">
            <p><strong>Test:</strong> {{ t[2] }} | <strong>Department:</strong> {{ t[3] }}</p>
            <p><strong>Result:</strong> {{ t[4] }}</p>
            <p><strong>By:</strong> {{ t[5] }} on {{ t[6] }}</p>
            {% if t[7] %}
            <p><strong>Image:</strong> <a href="/uploads/{{ t[7] }}" target="_blank"><img src="/uploads/{{ t[7] }}" style="max-height:200px;" class="img-fluid"></a></p>
            {% endif %}
        </div>
        {% endfor %}

        {% if sample[6] != 'Awaiting Receipt' %}
        <h4 class="mt-4">Add Test Result ({{ session['dept'] }})</h4>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
                        {{ message }}
                        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                    </div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        <form method="post" enctype="multipart/form-data">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label>Test Type</label>
                    <select name="test_type" class="form-select" required>
                        {% for t in dept_tests %}
                        <option value="{{ t }}">{{ t }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div class="col-md-6 mb-3">
                    <label>Result</label>
                    <input type="text" name="result" class="form-control" required>
                </div>
            </div>
            <div class="mb-3">
                <label>Attach Image (camera or gallery)</label>
                <input type="file" name="image" class="form-control" accept="image/*" capture="environment">
                <small class="text-muted">Max size: 16 MB. Allowed formats: jpg, png, gif, webp.</small>
            </div>
            <button type="submit" class="btn btn-primary">Submit Result</button>
        </form>
        {% endif %}

        <h4 class="mt-4">Update Status</h4>
        <form method="post" action="/update_status/{{ sample[1] }}">
            <div class="row">
                <div class="col-md-4">
                    <select name="status" class="form-select">
                        <option>Awaiting Receipt</option>
                        <option>Pending</option><option>In Progress</option><option>Completed</option><option>Rejected</option>
                    </select>
                </div>
                <div class="col-md-2"><button type="submit" class="btn btn-warning">Update</button></div>
            </div>
        </form>
    </div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """
)

MANAGE_TESTS_HTML = (
    BASE_STYLE + NAVBAR +
    """
    <div class="container" style="max-width: 700px;">
        <h2>Manage Tests</h2>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for category, message in messages %}
                    <div class="alert alert-{{ category }}">{{ message }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}

        <h4>Add New Test</h4>
        <form method="post">
            <input type="hidden" name="action" value="add">
            <div class="row">
                <div class="col-md-6 mb-3">
                    <label>Test Name</label>
                    <input type="text" name="test_name" class="form-control" required>
                </div>
                <div class="col-md-6 mb-3">
                    <label>Department</label>
                    <select name="department" class="form-select" required>
                        {% for d in departments %}
                        <option value="{{ d }}">{{ d }}</option>
                        {% endfor %}
                    </select>
                </div>
            </div>
            <button type="submit" class="btn btn-success">Add Test</button>
        </form>

        <hr>
        <h4>Existing Tests</h4>
        <table class="table table-striped">
            <thead><tr><th>Test Name</th><th>Department</th><th>Actions</th></tr></thead>
            <tbody>
                {% for t in tests %}
                <tr>
                    <td>{{ t[1] }}</td>
                    <td>{{ t[2] }}</td>
                    <td>
                        <form method="post" style="display:inline;">
                            <input type="hidden" name="action" value="delete">
                            <input type="hidden" name="test_id" value="{{ t[0] }}">
                            <button type="submit" class="btn btn-danger btn-sm">Delete</button>
                        </form>
                        <!-- Edit can be a small form, but for simplicity delete only, we'll add edit later if needed -->
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """
)

MANAGE_USERS_HTML = (
    BASE_STYLE + NAVBAR +
    """
    <div class="container" style="max-width: 600px;">
        <h2>Manage Users</h2>
        {% if error %}
        <div class="alert alert-danger">{{ error }}</div>
        {% endif %}
        <h4>Create New User</h4>
        <form method="post">
            <div class="mb-3"><label>Username</label><input type="text" name="username" class="form-control" required></div>
            <div class="mb-3"><label>Password</label><input type="password" name="password" class="form-control" required></div>
            <div class="mb-3"><label>Full Name</label><input type="text" name="full_name" class="form-control" required></div>
            <div class="mb-3"><label>Role</label>
                <select name="role" class="form-select"><option>user</option><option>admin</option></select>
            </div>
            <div class="mb-3"><label>Department</label>
                <div style="display:flex; flex-wrap:wrap; gap:8px;" id="deptContainer">
                    {% for d in departments %}
                    <label class="dept-radio-label" onclick="selectDept(this, '{{ d }}')">
                        <input type="radio" name="department" value="{{ d }}" required>
                        <span>{{ d }}</span>
                    </label>
                    {% endfor %}
                </div>
            </div>
            <button type="submit" class="btn btn-success mt-2">Create User</button>
        </form>
        <hr>
        <h4>Existing Users</h4>
        <ul class="list-group">
            {% for u in users %}
            <li class="list-group-item">{{ u[1] }} ({{ u[0] }})</li>
            {% endfor %}
        </ul>
    </div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    <script>
        function selectDept(label, value) {
            document.querySelectorAll('.dept-radio-label').forEach(l => l.classList.remove('selected'));
            label.classList.add('selected');
            label.querySelector('input').checked = true;
        }
    </script>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """
)

AUDIT_HTML = (
    BASE_STYLE + NAVBAR +
    """
    <div class="container">
        <h2>Audit Log</h2>
        <table class="table table-striped">
            <thead><tr><th>Timestamp</th><th>User</th><th>Sample ID</th><th>Action</th></tr></thead>
            <tbody>
                {% for log in logs %}
                <tr><td>{{ log[4] }}</td><td>{{ log[2] }}</td><td>{{ log[1] }}</td><td>{{ log[3] }}</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    <div class="footer">Powered by <strong>Pourdad Panahi</strong></div>
    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    """
)

# ---------- راه‌اندازی ----------
if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=8501, debug=True)