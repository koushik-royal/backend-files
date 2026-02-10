# EyeNova Backend Setup Instructions (January 2026)

## Quick Start for Progress & History Testing

### Step 1: Start the Backend Server

#### Option A: Windows Batch File (Easiest)
```bash
cd EyeNova_backend
start_server.bat
```
The server will run for 5 minutes. You'll see it listening on `http://127.0.0.1:8000`

#### Option B: PowerShell Command (Manual)
```powershell
cd EyeNova_backend
timeout /t 300 /nobreak & .\venv\Scripts\python.exe test_server.py
```

### Step 2: Update Android App for Your Network

The app needs to know where your backend server is running.

#### For Android Emulator:
```java
// In RetrofitClient.java line 37
private static String baseUrl = "http://10.0.2.2:8000/";  // Host machine localhost
```

#### For Physical Device on Same Wi-Fi:
First, find your host machine's Wi-Fi IP:
```powershell
ipconfig | findstr "Wi-Fi adapter" -A 2
```
Look for "IPv4 Address" under Wi-Fi adapter (example: 192.168.1.100)

Then update RetrofitClient.java:
```java
// In RetrofitClient.java line 37
private static String baseUrl = "http://192.168.1.100:8000/";  // Your actual Wi-Fi IP
```

Or override at runtime in your Activity:
```java
RetrofitClient.setBaseUrl("http://192.168.1.100:8000/");
```

### Step 3: Test the Connection

#### From Command Line:
```powershell
# Test health endpoint
curl http://127.0.0.1:8000/health

# Test game sessions endpoint  
curl http://127.0.0.1:8000/game-sessions/me/
```

#### From Android App:
1. Build and run the app
2. Login with any credentials (test_server.py doesn't check auth)
3. Play a game
4. Go to Progress or History
5. Check Logcat with filter "ProgressActivity" to see API calls

### Step 4: Troubleshooting

If Progress/History still show no data:

1. **Check Logcat** (Android Studio → Logcat):
   - Filter for "ProgressActivity"
   - Look for "API Response received" messages
   - Check for network errors

2. **Verify Server is Running**:
   - Keep the terminal window visible
   - You should see request logs when app makes API calls

3. **Check IP Address**:
   - Make sure both host and device are on the same Wi-Fi network
   - Try ping from command line: `ping 192.168.1.100`

4. **Test Backend Directly**:
   ```powershell
   curl http://127.0.0.1:8000/game-sessions/me/
   # Should return sample game session data
   ```

### Important Notes

- The `test_server.py` provides sample game session data
- The server automatically shuts down after the timeout period
- For production use, switch to the full `main.py` with authentication
- The database file is `eyenova.db` in the backend directory

---

## For Full Backend with Authentication

To use the complete FastAPI backend with user authentication:

```powershell
cd EyeNova_backend
timeout /t 300 /nobreak & .\venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
```

Note: This requires valid user login and returns real game sessions from the database.
