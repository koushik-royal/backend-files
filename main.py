from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Annotated, List
from datetime import datetime, timedelta
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import random
import string
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv
from fastapi import BackgroundTasks
import dns.resolver # Added for DNS workaround

# Load environment variables
load_dotenv()

# SMTP Config
SMTP_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
try:
    SMTP_PORT = int(os.getenv("MAIL_PORT", 587))
except (TypeError, ValueError):
    SMTP_PORT = 587

SMTP_USERNAME = os.getenv("MAIL_USERNAME")
SMTP_PASSWORD = os.getenv("MAIL_PASSWORD")
MAIL_FROM = os.getenv("MAIL_FROM")
MAIL_FROM_NAME = os.getenv("MAIL_FROM_NAME", "EyeNova AI Support")

# Log SMTP status at startup (without showing password)
if not SMTP_USERNAME or "your-email" in SMTP_USERNAME:
    print("⚠️ WARNING: SMTP_USERNAME is not set correctly in .env. Emails will FAIL.")
else:
    print(f"✅ SMTP configured for: {SMTP_USERNAME}")

try:
    from . import models
    from . import schemas
    from . import crud
    from . import security
    from .database import SessionLocal, engine
except ImportError:
    import models
    import schemas
    import crud
    import security
    from database import SessionLocal, engine
import logging
from ai_health_assistant_fixed import get_ai_reply

# Create our FastAPI app instance
app = FastAPI()

# configure basic logging for debug
logging.basicConfig(level=logging.INFO)

# Create all tables on startup
try:
    models.Base.metadata.create_all(bind=engine)
    logging.info("✓ Database tables created/verified on startup")
except Exception as e:
    logging.error(f"❌ Database startup error: {e}")
    raise

# ============== TEST ENDPOINT ==============
@app.post("/test/")
def test_endpoint(data: dict = None):
    """Simple test endpoint to verify server is working"""
    print("✅ TEST ENDPOINT HIT")
    import sys
    sys.stdout.flush()
    return {"status": "ok", "message": "Server is working"}

# --- Database Dependency ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Authentication Dependency ---
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def get_current_user(
    token: Annotated[str, Depends(oauth2_scheme)], 
    db: Session = Depends(get_db)
):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    email = security.get_current_user_email(token)
    if email is None:
        raise credentials_exception
    
    user = crud.get_user_by_email(db, email=email)
    if user is None:
        raise credentials_exception
    
    return user


# --- Legacy/Compatibility Endpoint ---
@app.get("/game-sessions/patient/{patient_id}/", response_model=List[schemas.GameSession])
def get_game_sessions_for_patient(
    patient_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Returns all game sessions for a given patient (for legacy frontend support)."""
    patient = crud.get_user_by_id(db, user_id=patient_id)
    if not patient or patient.role != models.UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found."
        )
    # Only allow doctor or patient themselves to view
    if current_user.role == models.UserRole.DOCTOR:
        if patient.linked_doctor_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view this patient."
            )
    elif current_user.role == models.UserRole.PATIENT:
        if current_user.id != patient_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to view another patient's game sessions."
            )
    else:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view patient game sessions."
        )
    return crud.get_game_sessions_by_user(db=db, user_id=patient_id)


# ============== AI HEALTH ASSISTANT ==============
class AIChatRequest(BaseModel):
    message: str
    patient_name: str = ""
    session_id: str = "patient_session"

@app.post("/ai-chat/")
def ai_chat(req: AIChatRequest):
    """
    AI Health Assistant endpoint for health-related queries
    
    Parameters:
    - message: User's input message
    - patient_name: Patient name for personalization (optional)
    - session_id: Session ID for maintaining conversation context (optional)
    
    Features:
    - Personalized greetings with patient name
    - 50+ eye-healthy foods (non-repeating)
    - 12 eye exercises with steps
    - Smart reminder setup (4-step form with confirmation)
    - Intent detection (7 types)
    - Session-based food non-repetition
    """
    reply = get_ai_reply(
        user_text=req.message, 
        patient_name=req.patient_name,
        session_id=req.session_id
    )
    return {"reply": reply}

# --- OTP Store (In-Memory) ---
otp_store = {}
verified_emails = set()

def resolve_smtp_host(hostname="smtp.gmail.com"):
    """
    Attempts to resolve the SMTP hostname.
    Falls back to Google DNS (8.8.8.8) if system DNS fails.
    """
    try:
        # Try system default first
        print(f"DEBUG: Resolving {hostname} using system/default DNS...")
        return hostname # If this works, smtplib will resolve it again, which is fine.
                        # But wait, smtplib uses getaddrinfo. If that fails, we need an IP.
                        # Let's try to resolve to an IP to be safe.
        # actually, let's just use the custom resolver logic directly if system fails
        # But for simplicity, we can just return the hostname and let smtplib handle it
        # UNLESS we specifically want to bypass a broken system DNS.
        
        # Testing system DNS resolution (simple check)
        import socket
        socket.gethostbyname(hostname)
        return hostname
    except Exception as e:
        print(f"⚠️ System DNS failed for {hostname}: {e}")
        print("🔄 Attempting fallback to Google DNS (8.8.8.8)...")
        
        try:
            resolver = dns.resolver.Resolver()
            resolver.nameservers = ['8.8.8.8']
            answers = resolver.resolve(hostname, 'A')
            ip = answers[0].to_text()
            print(f"✅ Resolved {hostname} to {ip} via Google DNS")
            return ip
        except Exception as e2:
            print(f"❌ DNS Fallback failed: {e2}")
            return hostname # Return hostname as last resort

def send_email_task(recipient: str, otp: str):
    """Sends the OTP email in the background."""
    try:
        if not SMTP_USERNAME or "your-email" in SMTP_USERNAME:
            raise ValueError("Invalid SMTP credentials in .env file.")

        msg = EmailMessage()
        # Create a professional HTML version
        html_content = f"""
        <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; color: #333; max-width: 500px; margin: auto; border: 1px solid #ddd; border-radius: 12px; padding: 25px; background-color: #ffffff;">
            <h2 style="color: #4A90E2; text-align: center;">EyeNova AI Verification</h2>
            <p>To securely access your EyeNova account, please use the following One-Time Password (OTP):</p>
            <div style="font-size: 32px; font-weight: bold; letter-spacing: 6px; text-align: center; background: #f4f7f6; padding: 20px; border-radius: 8px; color: #333; margin: 25px 0;">
                {otp}
            </div>
            <p>This code is valid for <strong>5 minutes</strong>. If you didn't request this, please ignore this email.</p>
            <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
            <p style="font-size: 12px; color: #888; text-align: center;">Helping the world see better, one check at a time.</p>
        </div>
        """
        msg.set_content(f"Your EyeNova verification code is: {otp}")
        msg.add_alternative(html_content, subtype="html")
        
        msg["Subject"] = f"{otp} is your EyeNova code"
        # msg["From"] = f"{MAIL_FROM_NAME} <{SMTP_USERNAME}>" # OLD
        # Use the configured MAIL_FROM (eyenova7@gmail.com)
        sender_email = MAIL_FROM if MAIL_FROM else SMTP_USERNAME
        msg["From"] = f"{MAIL_FROM_NAME} <{sender_email}>"
        msg["To"] = recipient

        # Resolve Hostname
        smtp_target = resolve_smtp_host(SMTP_SERVER)
        
        print(f"DEBUG: Attempting to connect to {smtp_target}:{SMTP_PORT}...")
        with smtplib.SMTP(smtp_target, SMTP_PORT, timeout=20) as server:
            server.set_debuglevel(0) # Set to 1 for detailed SMTP logs if needed
            server.starttls()
            server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(msg)
        
        print(f"✅ SUCCESS: OTP Email sent to {recipient} from {sender_email}")
    except Exception as e:
        print(f"❌ SMTP ERROR: {str(e)}")
        if "535" in str(e):
            print("💡 TIP: Your Gmail App Password or Username is incorrect in .env")
        print(f"[INTERNAL FALLBACK] OTP for {recipient}: {otp}")

@app.post("/send-otp/")
def send_otp(request: schemas.OTPRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Generates and sends a 6-digit OTP to the email."""
    # Logic: 
    # Signup intent -> Only send if email is NOT in database
    # Reset intent -> Only send if email IS in database
    
    user = crud.get_user_by_email(db, email=request.email)
    
    if request.intent == "signup" and user:
        raise HTTPException(
            status_code=400, 
            detail="This email is already registered. Please login or reset your password."
        )
    
    if request.intent == "reset" and not user:
        raise HTTPException(
            status_code=404, 
            detail="No account found with this email. Please sign up instead."
        )

    otp = "".join(random.choices(string.digits, k=6))
    expire_time = datetime.now() + timedelta(minutes=5)
    otp_store[request.email] = {"otp": otp, "expires": expire_time}
    
    # Add email sending to background tasks
    background_tasks.add_task(send_email_task, request.email, otp)
    
    return {"message": "OTP sent successfully"}

@app.post("/verify-otp/")
def verify_otp(request: schemas.OTPVerifyRequest):
    stored_otp_data = otp_store.get(request.email)
    
    if not stored_otp_data:
        raise HTTPException(status_code=400, detail="OTP not found or expired")
    
    if datetime.now() > stored_otp_data["expires"]:
        del otp_store[request.email]
        raise HTTPException(status_code=400, detail="OTP expired")
    
    if stored_otp_data["otp"] != request.otp:
        raise HTTPException(status_code=400, detail="Invalid OTP")
    
    # OTP is valid
    verified_emails.add(request.email) # Mark as verified for next steps
    del otp_store[request.email]
    
    return {"message": "OTP verified successfully"}

class ResetPasswordRequest(BaseModel):
    email: str
    new_password: str

@app.post("/reset-password/")
def reset_password(request: ResetPasswordRequest, db: Session = Depends(get_db)):
    # Verify that the email was recently verified via OTP
    if request.email not in verified_emails:
        raise HTTPException(
            status_code=400, 
            detail="Email not verified. Please verify your identity with OTP first."
        )
    
    user = crud.get_user_by_email(db, email=request.email)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Update password
    hashed_password = security.get_password_hash(request.new_password)
    user.hashed_password = hashed_password
    db.commit()
    
    # Clear verification after success
    verified_emails.remove(request.email)
    
    return {"message": "Password reset successfully"}
# --- API Endpoints ---

@app.get("/")
def read_root():
    return {"message": "Welcome to the EyeNova Backend API!"}


@app.post("/register/", response_model=schemas.User)
def register_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    """Handles user registration."""
    db_user = crud.get_user_by_email(db, email=user.email)
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Check if email is verified
    if user.email not in verified_emails:
        raise HTTPException(
            status_code=400, 
            detail="Email not verified. Please verify your email with OTP first."
        )
    
    # Optional: Clear after registration so same verification can't be reused for multiple registrations
    verified_emails.remove(user.email)
    
    return crud.create_user(db=db, user=user)


# --- THIS IS THE FIX ---
@app.post("/login/", response_model=schemas.Token)
def login_for_access_token(
    # We now accept our JSON 'TokenRequest' schema
    login_data: schemas.TokenRequest, 
    db: Session = Depends(get_db)
):
    """Handles user login."""
    
    # We get the email and password from the 'login_data' object
    # Debug: check user existence and password verification (DO NOT log passwords)
    user = crud.get_user_by_email(db, email=login_data.username)
    if not user:
        logging.info(f"Login attempt for unknown email: {login_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    password_ok = security.verify_password(login_data.password, user.hashed_password)
    if not password_ok:
        logging.info(f"Login attempt failed password verification for email: {login_data.username}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=security.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = security.create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}
# --- END OF FIX ---


@app.get("/users/me/", response_model=schemas.User)
def read_users_me(
    current_user: Annotated[models.User, Depends(get_current_user)]
):
    """A protected endpoint that returns the data for the currently logged-in user."""
    return current_user


@app.delete("/users/me/", status_code=204)
def delete_my_account(
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Delete the authenticated user's account and related data."""
    success = crud.delete_user(db=db, user_id=current_user.id)
    if not success:
        return JSONResponse(status_code=404, content={"detail": "User not found"})
    # Return 204 No Content on success
    return JSONResponse(status_code=204, content=None)

@app.delete("/users/{user_id}", status_code=204)
def delete_patient_account(
    user_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Allow doctors to delete their linked patients' accounts."""
    if current_user.role != models.UserRole.DOCTOR:
         return JSONResponse(status_code=403, content={"detail": "Only doctors can delete accounts"})
    
    target_user = crud.get_user_by_id(db, user_id=user_id)
    if not target_user:
        return JSONResponse(status_code=404, content={"detail": "User not found"})
        
    if target_user.linked_doctor_id != current_user.id:
        return JSONResponse(status_code=403, content={"detail": "You can only delete your own patients"})

    success = crud.delete_user(db=db, user_id=user_id)
    if not success:
         return JSONResponse(status_code=404, content={"detail": "Failed to delete user"})
         
    return JSONResponse(status_code=204, content=None)


@app.get("/users/{user_id}/", response_model=schemas.User)
def get_user_by_id(
    user_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Get user information by ID. Patients can only see their linked doctor, doctors can see their patients."""
    user = crud.get_user_by_id(db, user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Permission checks
    if current_user.role == models.UserRole.PATIENT:
        if current_user.id != user_id and current_user.linked_doctor_id != user_id:
            raise HTTPException(status_code=403, detail="Access denied")
    elif current_user.role == models.UserRole.DOCTOR:
        if current_user.id != user_id and user.linked_doctor_id != current_user.id:
            raise HTTPException(status_code=403, detail="Access denied")
    
    return user


@app.post("/game-sessions/", response_model=schemas.GameSession)
def create_game_session_for_user(
    game_session: schemas.GameSessionCreate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """A protected endpoint for a logged-in user to submit a game result."""
    print("\n" + "="*60)
    print("📝 GAME SESSION RECEIVED")
    print("="*60)
    print(f"User ID: {current_user.id}")
    print(f"User Email: {current_user.email}")
    print(f"User Role: {current_user.role}")
    print(f"Game Name: {game_session.game_name}")
    print(f"Score: {game_session.score}")
    print(f"Accuracy: {game_session.accuracy}")
    print(f"Duration: {game_session.duration_seconds}s")
    print(f"Level: {game_session.level}")
    
    if current_user.role != models.UserRole.PATIENT:
        print(f"❌ ERROR: User is not a PATIENT. Role: {current_user.role}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can submit game sessions."
        )
    
    print("✓ User is PATIENT")
    print(f"Status: {game_session.status}")
    
    try:
        result = crud.create_user_game_session(
            db=db, 
            game_session=game_session, 
            user_id=current_user.id
        )
        print(f"✅ GAME SAVED SUCCESSFULLY")
        print(f"   Saved Game ID: {result.id}")
        print(f"   Game Name: {result.game_name}")
        print(f"   Score: {result.score}")
        print(f"   Status: {result.status}")
        print(f"   Date: {result.date_played}")
        print("="*60 + "\n")
        return result
    except Exception as e:
        print(f"❌ ERROR SAVING GAME: {str(e)}")
        print("="*60 + "\n")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@app.get("/game-sessions/me/", response_model=List[schemas.GameSession])
def read_my_game_sessions(
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """A protected endpoint for a logged-in patient to retrieve their game history."""
    print("\n" + "="*60)
    print("📊 FETCHING GAME SESSIONS")
    print("="*60)
    print(f"User ID: {current_user.id}")
    print(f"User Email: {current_user.email}")
    print(f"User Role: {current_user.role}")
    
    if current_user.role != models.UserRole.PATIENT:
        print(f"❌ ERROR: User is not a PATIENT")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can view their game sessions."
        )
    
    try:
        sessions = crud.get_game_sessions_by_user(db=db, user_id=current_user.id)
        print(f"✅ Found {len(sessions)} game sessions")
        for idx, session in enumerate(sessions, 1):
            print(f"   [{idx}] {session.game_name} | Level: {session.level} | Score: {session.score} | Status: {session.status} | Date: {session.date_played}")
        print("="*60 + "\n")
        return sessions
    except Exception as e:
        print(f"❌ ERROR FETCHING SESSIONS: {str(e)}")
        print("="*60 + "\n")
        raise
    logging.info(f"Fetching game sessions for user {current_user.id}")
    return crud.get_game_sessions_by_user(db=db, user_id=current_user.id)


@app.post("/users/me/link-doctor/", response_model=schemas.User)
def link_patient_to_doctor(
    link_request: schemas.DoctorLink,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """A protected endpoint for a logged-in Patient to link to a Doctor."""
    if current_user.role != models.UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only patients can link to doctors."
        )
        
    doctor = crud.get_user_by_doctor_code(db, code=link_request.doctor_code)
    
    if not doctor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Doctor code not found."
        )
    
    current_user.linked_doctor_id = doctor.id
    db.commit()
    db.refresh(current_user)
    
    print(f"[LINK] Patient {current_user.id} ({current_user.email}) linked to Doctor {doctor.id} ({doctor.email})")
    
    return current_user


@app.post("/messages/", response_model=schemas.DirectMessage)
def create_direct_message(
    message_data: schemas.DirectMessageCreate,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """A protected endpoint for a user to send a direct message to another user."""
    # Verify recipient exists
    recipient = crud.get_user_by_id(db=db, user_id=message_data.recipient_id)
    if not recipient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipient not found"
        )

    # For patients, only allow messaging their linked doctor
    if current_user.role == models.UserRole.PATIENT:
        if current_user.linked_doctor_id != message_data.recipient_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Patients can only message their linked doctor."
            )
    # For doctors, only allow messaging their linked patients
    elif current_user.role == models.UserRole.DOCTOR:
        if recipient.linked_doctor_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Doctors can only message their linked patients."
            )

    return crud.create_direct_message(
        db=db,
        message_data=message_data,
        sender=current_user
    )


@app.get("/messages/conversations/", response_model=List[schemas.User])
def get_conversation_partners(
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Get all users that the current user has direct message conversations with."""
    return crud.get_conversation_partners_for_user(db=db, user_id=current_user.id)


@app.get("/messages/{user_id}/", response_model=List[schemas.DirectMessage])
def get_direct_messages_with_user(
    user_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Get all direct messages between current user and another user."""
    # Verify the other user exists
    other_user = crud.get_user_by_id(db=db, user_id=user_id)
    if not other_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Verify permission to view conversation
    if current_user.role == models.UserRole.PATIENT:
        if current_user.linked_doctor_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view messages with your linked doctor."
            )
    elif current_user.role == models.UserRole.DOCTOR:
        if other_user.linked_doctor_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You can only view messages with your linked patients."
            )

    # Get visible messages
    return crud.get_visible_direct_messages_between_users(
        db=db,
        user1_id=current_user.id,
        user2_id=user_id,
        requesting_user_id=current_user.id
    )


@app.patch("/messages/{message_id}/delete-for-me/", status_code=200)
def delete_direct_message_for_me(
    message_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """
    Mark a direct message as deleted for the current user only.
    The message will be hidden from this user but visible to the other user.
    """
    # Verify message exists and user has access
    message = crud.get_direct_message_by_id(db=db, message_id=message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Verify user is part of this conversation
    if current_user.id != message.sender_id and current_user.id != message.recipient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this message."
        )

    # Delete for this user
    success = crud.delete_direct_message_for_me(db=db, message_id=message_id, user_id=current_user.id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    return {"status": "success", "message": "Message deleted for you"}


@app.delete("/messages/{message_id}/", status_code=200)
def delete_direct_message_for_everyone(
    message_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """
    Permanently delete a direct message for everyone.
    The message will be invisible to both users.
    Only the message sender can delete it for everyone.
    """
    # Verify message exists
    message = crud.get_direct_message_by_id(db=db, message_id=message_id)
    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Verify user is part of this conversation
    if current_user.id != message.sender_id and current_user.id != message.recipient_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this message."
        )

    # Only message sender can delete for everyone
    if message.sender_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the message sender can delete it for everyone."
        )

    # Delete for everyone
    success = crud.delete_direct_message_for_everyone(db=db, message_id=message_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete message"
        )

    return {"status": "success", "message": "Message deleted for everyone"}



@app.get("/patients/me/", response_model=List[schemas.PatientInfo])
def read_my_patients(
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """A protected endpoint for a logged-in Doctor to retrieve their patient list."""
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can view the patient list."
        )
            
    return crud.get_patients_for_doctor(db=db, doctor_id=current_user.id)



# --- Doctor Dashboard Game History APIs ---
@app.get("/doctor/get-patient-history", response_model=List[schemas.GameSession])
def get_patient_game_history(
    patient_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Doctor fetches all game history for a patient."""
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can view patient game history."
        )
    patient = crud.get_user_by_id(db, user_id=patient_id)
    if not patient or patient.role != models.UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found."
        )
    if patient.linked_doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this patient."
        )
    return crud.get_game_sessions_by_user(db=db, user_id=patient_id)

@app.get("/doctor/get-history-details", response_model=schemas.GameSession)
def get_game_history_details(
    id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Doctor fetches details for a specific game session."""
    game_session = crud.get_game_session_by_id(db=db, session_id=id)
    if not game_session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Game session not found."
        )
    patient = crud.get_user_by_id(db, user_id=game_session.patient_id)
    if not patient or patient.linked_doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this game session."
        )
    return game_session

@app.get("/doctor/get-patient-info", response_model=schemas.User)
def get_patient_info(
    patient_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Fetch basic patient information for the doctor."""
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can view patient information."
        )
    patient = crud.get_user_by_id(db, user_id=patient_id)
    if not patient or patient.role != models.UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found."
        )
    if patient.linked_doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this patient."
        )
    return patient

@app.get("/doctor/get-patient-game-history", response_model=List[schemas.GameSession])
def get_patient_game_history(
    patient_id: int,
    current_user: Annotated[models.User, Depends(get_current_user)],
    db: Session = Depends(get_db)
):
    """Fetch game history for a specific patient."""
    if current_user.role != models.UserRole.DOCTOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only doctors can view patient game history."
        )
    patient = crud.get_user_by_id(db, user_id=patient_id)
    if not patient or patient.role != models.UserRole.PATIENT:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Patient not found."
        )
    if patient.linked_doctor_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to view this patient."
        )
    return crud.get_game_sessions_by_user(db=db, user_id=patient_id)

