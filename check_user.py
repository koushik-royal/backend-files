import sqlite3
import os

db_path = 'eyenova.db'
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

email = 'poolavenkatkoushik@gmail.com'
cursor.execute('SELECT id, email, full_name, role FROM users WHERE email=?', (email,))
user = cursor.fetchone()

if user:
    print(f"User found: {user}")
else:
    print("User not found in database.")

# Also list all users for reference
cursor.execute('SELECT email FROM users')
all_users = cursor.fetchall()
print(f"All users in DB: {all_users}")

conn.close()
