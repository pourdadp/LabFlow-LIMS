# 🧪 LabFlow – Laboratory Information Management System

A complete **LIMS (Laboratory Information Management System)** built with **Python/Flask** and **SQLite**, featuring a **mobile-first responsive UI** with Bootstrap 5.

## 🔬 Key Features

| Feature | Description |
|:---|:---|
| **User Authentication** | Role-based access (Admin / Department Users) |
| **Sample Registration** | With department routing: Awaiting Receipt → Pending → In Progress → Completed / Rejected |
| **Multi-Department Support** | Cell & Molecular, Serology, Microbiology, Cell Culture, Production |
| **Dynamic Test Management** | Admin can add/edit/delete tests per department |
| **Smart Test Filtering** | When registering a sample, only tests for the selected receiving department appear |
| **Audit Trail** | Every action is logged with timestamp and username |
| **Confidential Sample Flag** | Restricts visibility to submitter, receiver, and admin |
| **Image Attachment** | Capture or upload images for test results (mobile camera support) |
| **Mobile-Optimized UI** | Floating action button with colorful vertical menu |

## 🚀 Live Demo (Source Code)

Because this is a Flask application, a live demo requires a server.  
You can browse the source code and run it locally:

👉 **[View Source Code](https://github.com/pourdadp/LabFlow-LIMS)**

*(A live PythonAnywhere deployment is planned.)*

## 🛠️ Tech Stack

- **Backend:** Python 3, Flask 2.0
- **Database:** SQLite
- **Frontend:** HTML5, CSS3, Bootstrap 5, JavaScript
- **Security:** Password hashing (SHA-256), session management

## 👨‍🔬 Author

Pourdad Panahi – Bioinformatics & Bioinformatics Developer
18+ years of wet-lab experience (cell culture, real-time PCR, virus cultivation, ELISA).
Building digital tools for the life sciences.

· Portfolio: pourdadp.github.io
· GitHub: github.com/pourdadp
· LinkedIn: linkedin.com/in/pourdad-panahi

---

📄 Powered By Pourdad Panahi

## 🏃 How to Run Locally

```bash
pip install flask
python app.py


Then open http://localhost:8501 in your browser.
Default admin login: admin / admin123

