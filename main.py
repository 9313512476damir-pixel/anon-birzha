import random
import sqlite3
import smtplib
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from email.mime.text import MIMEText
from email.header import Header
from fastapi.responses import FileResponse

app = FastAPI(
    title="Платформа анонимных заданий",
    description="Бэкенд-система с полноценными аккаунтами"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_NAME = "database.db"

# НАСТРОЙКА НАСТОЯЩЕЙ ПОЧТЫ MAIL.RU
SMTP_SERVER = "smtp.mail.ru"
SMTP_PORT = 465
SENDER_EMAIL = "anon.birzha@mail.ru"
SENDER_PASSWORD = "lr6HlpEd8tBQmDbAbgYt"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            login TEXT UNIQUE,
            password TEXT,
            email TEXT UNIQUE,
            username TEXT,
            balance REAL,
            reset_code TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            student_name TEXT,
            title TEXT,
            description TEXT,
            full_price REAL,
            commission REAL,
            worker_earnings REAL,
            worker_id INTEGER,
            status TEXT
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            sender_id INTEGER,
            text TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS site_earnings (
            id INTEGER PRIMARY KEY,
            amount REAL
        )
    ''')
    cursor.execute("SELECT amount FROM site_earnings WHERE id = 1")
    if not cursor.fetchone():
        cursor.execute("INSERT INTO site_earnings (id, amount) VALUES (1, 0.0)")
    conn.commit()
    conn.close()

init_db()

class UserRegister(BaseModel):
    login: str = Field(..., min_length=3)
    password: str = Field(..., min_length=4)
    email: str

class UserLogin(BaseModel):
    login: str
    password: str

class ForgotPassword(BaseModel):
    login: str
    email: str

class ResetPassword(BaseModel):
    email: str
    code: str
    new_password: str = Field(..., min_length=4)

class TaskCreate(BaseModel):
    student_id: int
    title: str
    description: str
    price: float = Field(ge=50.0)

class MessageSend(BaseModel):
    sender_id: int
    text: str = Field(..., min_length=1)

# РАЗДАЧА ФАЙЛА ИНТЕРФЕЙСА САЙТА ДЛЯ ИНТЕРНЕТА
@app.get("/")
def read_root_index():
    return FileResponse("index.html")

@app.get("/index.html")
def read_root_index_html():
    return FileResponse("index.html")


@app.post("/api/register", tags=["Пользователи"])
def register_user(auth_data: UserRegister):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE login = ?", (auth_data.login,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Этот логин уже занят!")
    cursor.execute("SELECT id FROM users WHERE email = ?", (auth_data.email,))
    if cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="Пользователь с такой почтой уже есть!")
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    user_id = 100000 + count + 1
    anonymous_name = f"Школьник #{random.randint(100000, 999999)}"
    cursor.execute(
        "INSERT INTO users (id, login, password, email, username, balance, reset_code) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, auth_data.login, auth_data.password, auth_data.email, anonymous_name, 0.0, None)
    )
    conn.commit()
    conn.close()
    return {"message": "Регистрация успешна! Ваш баланс: 0 руб.", "user": {"id": user_id, "username": anonymous_name, "balance": 0.0}}

@app.post("/api/login", tags=["Пользователи"])
def login_user(auth_data: UserLogin):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, username, balance FROM users WHERE login = ? AND password = ?", (auth_data.login, auth_data.password))
    user = cursor.fetchone()
    conn.close()
    if not user:
        raise HTTPException(status_code=400, detail="Неверный логин или пароль!")
    user_id, username, balance = user
    return {"message": "Вход выполнен успешно!", "user": {"id": user_id, "username": username, "balance": balance}}

@app.post("/api/forgot-password", tags=["Пользователи"])
def forgot_password(data: ForgotPassword):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT username FROM users WHERE login = ? AND email = ?", (data.login, data.email))
    user = cursor.fetchone()
    if not user:
        conn.close()
        return {"message": "If valid, the recovery code has been sent!"}
    student_username = user[0]
    secret_code = str(random.randint(100000, 999999))
    cursor.execute("UPDATE users SET reset_code = ? WHERE login = ? AND email = ?", (secret_code, data.login, data.email))
    conn.commit()
    conn.close()
    subject = "🥷 Восстановление доступа | Анонимная Биржа"
    body = f"Привет, {student_username}!\nТвой код подтверждения: {secret_code}"
    msg = MIMEText(body, 'plain', 'utf-8')
    msg['Subject'] = Header(subject, 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = data.email
    try:
        with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT) as server:
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, [data.email], msg.as_string())
    except Exception as e:
        print(f"SMTP error: {e}")
    return {"message": "Код восстановления отправлен на вашу почту!"}

@app.post("/api/reset-password", tags=["Пользователи"])
def reset_password(data: ResetPassword):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ? AND reset_code = ?", (data.email, data.code))
    user = cursor.fetchone()
    if not user:
        conn.close()
        raise HTTPException(status_code=400, detail="Неверный код или почта!")
    cursor.execute("UPDATE users SET password = ?, reset_code = NULL WHERE id = ?", (data.new_password, user[0]))
    conn.commit()
    conn.close()
    return {"message": "Пароль успешно изменен! Теперь вы можете войти."}


@app.post("/api/tasks", tags=["Задания"])
def create_task(task_data: TaskCreate):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT username, balance FROM users WHERE id = ?", (task_data.student_id,))
    student = cursor.fetchone()
    if not student:
        conn.close()
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    student_name, student_balance = student
    if student_balance < task_data.price:
        conn.close()
        raise HTTPException(status_code=400, detail="Недостаточно денег на балансе")
    commission = round(task_data.price * 0.10, 2)
    worker_earnings = round(task_data.price - commission, 2)
    new_balance = student_balance - task_data.price
    cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, task_data.student_id))
    cursor.execute('''
        INSERT INTO tasks (student_id, student_name, title, description, full_price, commission, worker_earnings, status)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'открыто')
    ''', (task_data.student_id, student_name, task_data.title, task_data.description, task_data.price, commission, worker_earnings))
    conn.commit()
    conn.close()
    return {"message": "Задание создано!"}

@app.get("/api/tasks")
def get_tasks():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE status = 'открыто'")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.post("/api/tasks/{task_id}/take")
def take_task(task_id: int, worker_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE id = ?", (worker_id,))
    if not cursor.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Исполнитель не найден")
    cursor.execute("SELECT student_id, status FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    if not task or task[1] != "открыто":
        conn.close()
        raise HTTPException(status_code=400, detail="Задание недоступно")
    if task[0] == worker_id:
        conn.close()
        raise HTTPException(status_code=400, detail="Вы не можете взять свое задание")
    cursor.execute("UPDATE tasks SET worker_id = ?, status = 'в работе' WHERE id = ?", (worker_id, task_id))
    conn.commit()
    conn.close()
    return {"message": "Вы успешно взяли задание в работу!"}

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, student_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, worker_id, commission, worker_earnings, status FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    if not task or task[0] != student_id or task[4] != "в работе":
        conn.close()
        raise HTTPException(status_code=400, detail="Ошибка завершения задания")
    cursor.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (task[3], task[1]))
    cursor.execute("UPDATE site_earnings SET amount = amount + ? WHERE id = 1", (task[2],))
    cursor.execute("UPDATE tasks SET status = 'выполнено' WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return {"message": "Задание успешно завершено!"}

@app.post("/api/tasks/{task_id}/messages")
def send_message(task_id: int, msg: MessageSend):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO messages (task_id, sender_id, text) VALUES (?, ?, ?)", (task_id, msg.sender_id, msg.text))
    conn.commit()
    conn.close()
    return {"status": "Сообщение отправлено"}

@app.get("/api/tasks/{task_id}/messages")
def get_messages(task_id: int, user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, worker_id FROM tasks WHERE id = ?", (task_id,))
    task = cursor.fetchone()
    cursor.execute("SELECT sender_id, text, timestamp FROM messages WHERE task_id = ? ORDER BY id ASC", (task_id,))
    rows = cursor.fetchall()
    conn.close()
    chat_history = []
    for row in rows:
        role = "🥷 Заказчик" if row[0] == task[0] else "🛠️ Исполнитель"
        chat_history.append({"role": role, "text": row[1], "time": row[2]})
    return chat_history

@app.get("/api/tasks/my-created/{user_id}")
def get_my_created_tasks(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE student_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/tasks/my-jobs/{user_id}")
def get_my_jobs(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE worker_id = ?", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]

@app.get("/api/users/{user_id}/balance")
def get_user_balance(user_id: int):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
    res = cursor.fetchone()
    conn.close()
    return {"balance": res[0] if res else 0, "admin_earnings": 0}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)



