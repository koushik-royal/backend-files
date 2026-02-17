import sqlite3
import os

db_path = 'c:\\Users\\koush\\AndroidStudioProjects\\EyeNova AI\\EyeNova AI\\EyeNova\\EyeNova_backend\\eyenova.db'

def check_roles():
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('SELECT email, role FROM users')
    users = cursor.fetchall()
    print("Users in DB with roles:")
    for email, role in users:
        print(f"Email: {email}, Role value: {role}")
    conn.close()

if __name__ == "__main__":
    check_roles()
