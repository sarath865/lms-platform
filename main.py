from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import List, Optional
import sqlite3
import json
import os

app = FastAPI(title="LMS User Panel API", version="1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database path
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "admin_panel", "db.sqlite3")

def get_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    except Exception as e:
        print(f"Database error: {e}")
        return None

# Pydantic Models
class UserCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    role: str = "student"

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ProgressUpdate(BaseModel):
    completed_lessons: List[int]
    progress_percent: int

@app.get("/")
def read_root():
    return {"message": "Welcome to LMS User Panel API", "version": "1.0"}

@app.get("/courses")
def list_courses():
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, description, instructor_id, status 
            FROM core_course 
            WHERE status = 'published'
        """)
        courses = cursor.fetchall()
        conn.close()
        
        return [dict(course) for course in courses]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/courses/{course_id}")
def get_course(course_id: int):
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, title, description, instructor_id, status 
            FROM core_course 
            WHERE id = ?
        """, (course_id,))
        course = cursor.fetchone()
        
        if not course:
            conn.close()
            raise HTTPException(status_code=404, detail="Course not found")
        
        cursor.execute("""
            SELECT id, title, content, video_url, order_num 
            FROM core_lesson 
            WHERE course_id = ?
            ORDER BY order_num
        """, (course_id,))
        lessons = cursor.fetchall()
        
        conn.close()
        
        result = dict(course)
        result["lessons"] = [dict(lesson) for lesson in lessons]
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/register")
def register(user: UserCreate):
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM core_user WHERE email = ?", (user.email,))
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Email already registered")
        
        username = user.email.split('@')[0]
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO core_user (username, email, password, role, first_name, last_name, is_active, date_joined)
            VALUES (?, ?, ?, ?, ?, ?, 1, ?)
        """, (username, user.email, user.password, user.role, user.name, "", now))
        
        conn.commit()
        conn.close()
        
        return {"message": "User created successfully", "email": user.email}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/login")
def login(user: UserLogin):
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, email, role, username FROM core_user 
            WHERE email = ? AND password = ?
        """, (user.email, user.password))
        
        db_user = cursor.fetchone()
        conn.close()
        
        if not db_user:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        
        return {
            "access_token": f"fake-jwt-token-{db_user['id']}",
            "token_type": "bearer",
            "user_id": db_user['id'],
            "email": db_user['email'],
            "role": db_user['role'],
            "username": db_user['username']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/enroll/{course_id}")
def enroll_course(course_id: int, user_id: int = 1):
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        cursor.execute("SELECT id FROM core_course WHERE id = ?", (course_id,))
        if not cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=404, detail="Course not found")
        
        cursor.execute("""
            SELECT id FROM core_enrollment 
            WHERE user_id = ? AND course_id = ?
        """, (user_id, course_id))
        
        if cursor.fetchone():
            conn.close()
            raise HTTPException(status_code=400, detail="Already enrolled in this course")
        
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            INSERT INTO core_enrollment (user_id, course_id, enrolled_on)
            VALUES (?, ?, ?)
        """, (user_id, course_id, now))
        
        enrollment_id = cursor.lastrowid
        
        cursor.execute("""
            INSERT INTO core_progress (enrollment_id, completed_lessons, progress_percent, updated_at)
            VALUES (?, '[]', 0, ?)
        """, (enrollment_id, now))
        
        conn.commit()
        conn.close()
        
        return {"message": "Successfully enrolled in course"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/my-courses")
def my_courses(user_id: int = 1):
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT e.id, e.course_id, c.title as course_title, e.enrolled_on, 
                   COALESCE(p.progress_percent, 0) as progress_percent
            FROM core_enrollment e
            JOIN core_course c ON e.course_id = c.id
            LEFT JOIN core_progress p ON e.id = p.enrollment_id
            WHERE e.user_id = ?
        """, (user_id,))
        
        enrollments = cursor.fetchall()
        conn.close()
        
        return [dict(enrollment) for enrollment in enrollments]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/progress/update/{course_id}")
def update_progress(course_id: int, progress: ProgressUpdate, user_id: int = 1):
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id FROM core_enrollment 
            WHERE user_id = ? AND course_id = ?
        """, (user_id, course_id))
        
        enrollment = cursor.fetchone()
        if not enrollment:
            conn.close()
            raise HTTPException(status_code=404, detail="Not enrolled in this course")
        
        import datetime
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        cursor.execute("""
            UPDATE core_progress 
            SET completed_lessons = ?, progress_percent = ?, updated_at = ?
            WHERE enrollment_id = ?
        """, (json.dumps(progress.completed_lessons), progress.progress_percent, now, enrollment['id']))
        
        conn.commit()
        conn.close()
        
        return {"message": "Progress updated successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/progress/view/{course_id}")
def view_progress(course_id: int, user_id: int = 1):
    try:
        conn = get_db()
        if conn is None:
            raise HTTPException(status_code=500, detail="Database connection failed")
        
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT p.id, p.completed_lessons, p.progress_percent, p.updated_at
            FROM core_enrollment e
            JOIN core_progress p ON e.id = p.enrollment_id
            WHERE e.user_id = ? AND e.course_id = ?
        """, (user_id, course_id))
        
        progress = cursor.fetchone()
        conn.close()
        
        if not progress:
            return {
                "enrollment_id": None,
                "completed_lessons": [],
                "progress_percent": 0,
                "updated_at": None
            }
        
        return {
            "enrollment_id": progress['id'],
            "completed_lessons": json.loads(progress['completed_lessons']) if progress['completed_lessons'] else [],
            "progress_percent": progress['progress_percent'],
            "updated_at": progress['updated_at']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
