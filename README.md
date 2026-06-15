```markdown
# 🧪 LabFlow – Laboratory Information Management System

A complete **LIMS (Laboratory Information Management System)** built with **Python/Flask** and **SQLite**, featuring a **mobile‑first responsive UI** with Bootstrap 5.

## 🔬 Key Features

- **User Authentication** – Role‑based access (Admin / Department Users) with session persistence (5 hours)
- **Sample Registration** – Department routing: Awaiting Receipt → Pending → In Progress → Completed / Rejected
- **Multi‑Department Support** – Cell & Molecular, Serology, Microbiology, Cell Culture, Production
- **Dynamic Test Management** – Admin can add/edit/delete tests with custom parameters per department
- **Smart Test Filtering** – When registering a sample, only tests for the selected receiving department appear
- **Audit Trail** – Every action is logged with timestamp and username
- **Confidential Sample Flag** – Restricts visibility to submitter, receiver, and admin
- **Image Attachment** – Capture or upload images for test results (mobile camera support)
- **Replicates** – Record multiple replicates per test with automatic averaging
- **Chat System** – Real‑time messaging between users with read receipts and file attachments
- **Notifications** – In‑app notifications with floating badge and sound alerts
- **Dashboard Analytics** – Interactive charts (pie, bar, line) with Chart.js
- **Print & PDF** – Sample reports ready for printing or PDF download
- **User Management** – Create, unlock, delete users; password reset with 24‑hour expiry
- **Account Locking** – Automatic lock after 5 failed login attempts
- **Automatic Backups** – Database backup on every startup, keeping the last 5 copies
- **Tools Menu** – Quick access to TCID₅₀ and MOI calculators (hosted on GitHub Pages)
- **Mobile‑Optimized UI** – Floating action button with colorful vertical menu, floating notifications
- **Auto‑Discovery Launcher** – HTML file that scans the local network and redirects to the server

## 📁 Project Structure (Organized)

```

lims/
├── app.py                  # Main Flask application (all settings included)
├── Launcher.html           # Network auto‑discovery file for users
├── requirements.txt        # Python dependencies
├── data/                   # SQLite database
│   └── labflow.db
├── uploads/                # Uploaded files (images, chat attachments)
│   └── messages/
├── backups/                # Automatic database backups (last 5 kept)
└── README.md               # This file

```

> 💡 **No separate `config.py` needed** – all configuration is inside `app.py` for simplicity.

## 🚀 Live Demo (Source Code)

👉 **[View Source Code on GitHub](https://github.com/pourdadp/LabFlow-LIMS)**

## 🛠️ Tech Stack

- **Backend:** Python 3, Flask 2.0
- **Database:** SQLite (with auto‑backup)
- **Frontend:** HTML5, CSS3, Bootstrap 5, JavaScript, Chart.js
- **Security:** Password hashing (SHA‑256), CSRF protection, session management

## 🏃 How to Run Locally

```bash
pip install -r requirements.txt
python app.py
```

Then open http://localhost:8501 (or http://<server-IP>:8501 on other devices).
Default admin login: admin / admin123

📸 Screenshots

Dashboard Sample Detail Chat
Add screenshot Add screenshot Add screenshot

👨‍🔬 Author

Pourdad Panahi
Biotechnologist with 18+ years of wet‑lab experience (cell culture, real‑time PCR, virus cultivation, ELISA, serology).
Building digital tools for the life sciences.

· Portfolio: pourdadp.github.io
· GitHub: github.com/pourdadp
· LinkedIn: linkedin.com/in/pourdad-panahi

---

📄 Powered By Pourdad Panahi

```
