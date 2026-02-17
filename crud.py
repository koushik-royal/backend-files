import secrets
import string
from sqlalchemy.orm import Session
try:
    from . import models
    from . import schemas
    from . import security
except ImportError:
    import models
    import schemas
    import security
from typing import List

def get_user_by_email(db: Session, email: str):
    """
    Queries the database to find a user by their email address.
    
    Returns:
        The 'models.User' object if found, otherwise None.
    """
    return db.query(models.User).filter(models.User.email == email).first()


def _generate_unique_doctor_code(db: Session, length: int = 6):
    """Generates a unique alphanumeric code for doctors."""
    while True:
        # Generate a random 6-character code (e.g., '1a45cba')
        code = "".join(secrets.choice(string.ascii_lowercase + string.digits) for _ in range(length))
        # Check if it's already in use
        if not get_user_by_doctor_code(db, code):
            return code

def get_user_by_doctor_code(db: Session, code: str):
    """Finds a doctor by their unique shareable code."""
    return db.query(models.User).filter(models.User.doctor_id_code == code).first()


def create_user(db: Session, user: schemas.UserCreate):
    """
    Creates a new user in the database.

    MODIFIED: If the role is 'Doctor', this will also generate
    a unique 'doctor_id_code'.
    """
    hashed_password = security.get_password_hash(user.password)

    db_user = models.User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password,
        role=user.role
    )

    # Store optional profile fields if provided
    if getattr(user, "age", None) is not None:
        db_user.age = user.age
    if getattr(user, "gender", None) is not None:
        db_user.gender = user.gender
    if getattr(user, "date_of_birth", None) is not None:
        db_user.date_of_birth = user.date_of_birth
    if getattr(user, "fatherName", None) is not None:
        db_user.father_name = user.fatherName
    if getattr(user, "motherName", None) is not None:
        db_user.mother_name = user.motherName
    if getattr(user, "address", None) is not None:
        db_user.address = user.address

    # --- NEW LOGIC ---
    if user.role == models.UserRole.DOCTOR:
        # Generate a unique code if the user is a doctor
        db_user.doctor_id_code = _generate_unique_doctor_code(db)
    # --- END NEW LOGIC ---

    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    # If a patient was created, also create an empty AI chat session for them
    if db_user.role == models.UserRole.PATIENT:
        try:
            # Avoid duplicate session if it already exists
            existing = db.query(models.AiChatSession).filter(models.AiChatSession.patient_id == db_user.id).first()
            if not existing:
                ai_session = models.AiChatSession(patient_id=db_user.id)
                db.add(ai_session)
                db.commit()
                db.refresh(ai_session)
        except Exception:
            db.rollback()

    return db_user


def create_user_game_session(
    db: Session, 
    game_session: schemas.GameSessionCreate, 
    user_id: int):
    """
    Creates a new game session in the database, linked to a specific user.
    """
    # Validate game_name - do not accept placeholder or unknown names
    payload = game_session.model_dump()
    gname = (payload.get("game_name") or "").strip()
    if not gname or gname.lower() == "unknown game":
        raise ValueError("Invalid game_name")

    # Create the database model object, passing in the user_id
    db_game_session = models.GameSession(
        game_name = gname,
        level = payload.get("level"),
        score = int(payload.get("score")),
        accuracy = float(payload.get("accuracy")),
        duration_seconds = int(payload.get("duration_seconds")),
        status = payload.get("status", "completed"),
        patient_id = user_id
    )

    db.add(db_game_session)
    db.commit()
    db.refresh(db_game_session)

    return db_game_session


def create_ai_chat_message(db: Session, patient_id: int, sender: str, content: str, patient_name: str = None):
    """Append a message to a patient's AI chat session."""
    session = db.query(models.AiChatSession).filter(models.AiChatSession.patient_id == patient_id).first()
    if not session:
        # create session if missing
        session = models.AiChatSession(patient_id=patient_id, patient_name=patient_name)
        db.add(session)
        db.commit()
        db.refresh(session)
    elif patient_name and not session.patient_name:
        # Update patient name if provided and not already set
        session.patient_name = patient_name
        db.commit()
        db.refresh(session)

    msg = models.AiChatMessage(session_id=session.id, sender=sender, content=content)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    return msg


def get_ai_chat_for_user(db: Session, patient_id: int):
    session = db.query(models.AiChatSession).filter(models.AiChatSession.patient_id == patient_id).first()
    if not session:
        return None
    # return messages ordered by timestamp
    msgs = db.query(models.AiChatMessage).filter(models.AiChatMessage.session_id == session.id).order_by(models.AiChatMessage.timestamp.asc()).all()
    return {"session": session, "messages": msgs}


def get_last_n_game_sessions(db: Session, patient_id: int, n: int = 5):
    return db.query(models.GameSession).filter(models.GameSession.patient_id == patient_id).order_by(models.GameSession.date_played.desc()).limit(n).all()

def get_game_stats_for_patient_game(db: Session, patient_id: int, game_name: str, level: str = None):
    q = db.query(models.GameSession).filter(models.GameSession.patient_id == patient_id, models.GameSession.game_name == game_name)
    if level:
        q = q.filter(models.GameSession.level == level)
    sessions = q.all()
    if not sessions:
        return None
    best = max(s.score for s in sessions)
    avg_time = sum(s.duration_seconds for s in sessions) / len(sessions)
    avg_accuracy = sum(s.accuracy for s in sessions) / len(sessions)
    return {"best_score": best, "avg_time": avg_time, "avg_accuracy": avg_accuracy, "count": len(sessions)}


def get_game_sessions_by_user(db: Session, user_id: int) -> List[models.GameSession]:
    """
    Queries the database for all game sessions belonging to a specific user.
    Orders them by date, with the newest first.
    """
    return (
        db.query(models.GameSession)
        .filter(models.GameSession.patient_id == user_id)
        .order_by(models.GameSession.date_played.desc())
        .all()
    )


def create_direct_message(
    db: Session,
    message_data: schemas.DirectMessageCreate,
    sender: models.User) -> models.DirectMessage:
    """
    Creates a new direct message between two users.
    """
    # Create the DirectMessage object
    db_message = models.DirectMessage(
        message_text=message_data.message_text,
        sender_id=sender.id,
        recipient_id=message_data.recipient_id
    )

    db.add(db_message)
    db.commit()
    db.refresh(db_message)
    return db_message


def get_direct_messages_between_users(
    db: Session,
    user1_id: int,
    user2_id: int) -> List[models.DirectMessage]:
    """
    Gets all direct messages between two specific users.
    Orders them by timestamp, with the oldest first (for chat flow).
    """
    return (
        db.query(models.DirectMessage)
        .filter(
            ((models.DirectMessage.sender_id == user1_id) & (models.DirectMessage.recipient_id == user2_id)) |
            ((models.DirectMessage.sender_id == user2_id) & (models.DirectMessage.recipient_id == user1_id))
        )
        .order_by(models.DirectMessage.timestamp.asc())
        .all()
    )


def get_direct_messages_for_user(
    db: Session,
    user_id: int) -> List[models.DirectMessage]:
    """
    Gets all direct messages where the user is either sender or recipient.
    Excludes messages that are deleted for this user.
    This is used to show conversation threads for a user.
    """
    import json

    # Get all messages involving this user
    all_messages = (
        db.query(models.DirectMessage)
        .filter(
            (models.DirectMessage.sender_id == user_id) |
            (models.DirectMessage.recipient_id == user_id)
        )
        .order_by(models.DirectMessage.timestamp.desc())
        .all()
    )

    # Filter out messages deleted for this user
    visible_messages = []
    for msg in all_messages:
        # Skip if deleted for everyone
        if msg.is_deleted:
            continue

        # Skip if deleted for this specific user
        if msg.deleted_for_user_ids:
            try:
                deleted_ids = json.loads(msg.deleted_for_user_ids).get('deleted_for_user_ids', [])
                if user_id in deleted_ids:
                    continue
            except (json.JSONDecodeError, KeyError):
                pass  # If parsing fails, show the message

        visible_messages.append(msg)

    return visible_messages


def get_conversation_partners_for_user(
    db: Session,
    user_id: int) -> List[models.User]:
    """
    Gets all users that the given user has direct message conversations with.
    Also includes linked doctors/patients even if no messages have been exchanged.
    Returns unique users (no duplicates).
    """
    # Get all messages where user is involved
    messages = get_direct_messages_for_user(db, user_id)

    # Extract unique partner IDs from messages
    partner_ids = set()
    for msg in messages:
        if msg.sender_id == user_id:
            partner_ids.add(msg.recipient_id)
        else:
            partner_ids.add(msg.sender_id)

    # Get the user to check for linked relationships
    user = get_user_by_id(db, user_id)
    if user:
        # For patients, include their linked doctor
        if user.role == models.UserRole.PATIENT and user.linked_doctor_id:
            partner_ids.add(user.linked_doctor_id)
        # For doctors, include all their linked patients
        elif user.role == models.UserRole.DOCTOR:
            patients = db.query(models.User).filter(models.User.linked_doctor_id == user_id).all()
            for patient in patients:
                partner_ids.add(patient.id)

    # Get user objects for these IDs
    if partner_ids:
        return db.query(models.User).filter(models.User.id.in_(partner_ids)).all()
    return []


def get_direct_message_by_id(db: Session, message_id: int) -> models.DirectMessage:
    """
    Gets a single direct message by its ID.
    """
    return db.query(models.DirectMessage).filter(models.DirectMessage.id == message_id).first()


def get_patients_for_doctor(db: Session, doctor_id: int) -> List[models.User]:
    """
    Queries the database for all patients linked to a specific doctor.
    """
    return (
        db.query(models.User)
        .filter(models.User.linked_doctor_id == doctor_id)
        .order_by(models.User.full_name)
        .all()
    )


# (This should be at the end of your crud.py file)
def get_user_by_id(db: Session, user_id: int):
    """
    Queries the database to find a user by their ID.
    """
    return db.query(models.User).filter(models.User.id == user_id).first()


def update_user(db: Session, user_id: int, user_update: schemas.UserUpdate):
    """
    Updates a user's profile information.
    """
    db_user = get_user_by_id(db, user_id)
    if not db_user:
        return None
    
    update_data = user_update.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(db_user, key, value)
    
    db.commit()
    db.refresh(db_user)
    return db_user


def delete_user(db: Session, user_id: int):
    """
    Deletes a user and related data from the database.
    This performs a best-effort cleanup of associated game sessions, queries and messages.
    Returns True on success.
    """
    user = get_user_by_id(db, user_id=user_id)
    if not user:
        return False

    # If user is a doctor, unlink their patients
    if user.role == models.UserRole.DOCTOR:
        patients = db.query(models.User).filter(models.User.linked_doctor_id == user.id).all()
        for p in patients:
            p.linked_doctor_id = None

    # Delete game sessions (for patients)
    try:
        db.query(models.GameSession).filter(models.GameSession.patient_id == user.id).delete()
    except Exception:
        pass

    # Delete AI Chat sessions and messages (for patients)
    try:
        session = db.query(models.AiChatSession).filter(models.AiChatSession.patient_id == user.id).first()
        if session:
            db.query(models.AiChatMessage).filter(models.AiChatMessage.session_id == session.id).delete()
            db.query(models.AiChatSession).filter(models.AiChatSession.id == session.id).delete()
    except Exception:
        pass

    # Delete direct messages where user is sender or recipient
    try:
        db.query(models.DirectMessage).filter(
            (models.DirectMessage.sender_id == user.id) |
            (models.DirectMessage.recipient_id == user.id)
        ).delete(synchronize_session=False)
    except Exception:
        pass

    # Finally delete the user row
    db.query(models.User).filter(models.User.id == user.id).delete()
    db.commit()
    return True

def disconnect_patient(db: Session, patient_id: int, doctor_id: int):
    """
    Disconnects a patient from a doctor by setting linked_doctor_id to None.
    Does NOT delete the user account.
    """
    patient = get_user_by_id(db, user_id=patient_id)
    if not patient:
        return False
    
    if patient.linked_doctor_id != doctor_id:
        return False
        
    patient.linked_doctor_id = None
    db.commit()
    return True

# --- Doctor Game History Helpers ---
def get_game_sessions_by_user(db: Session, user_id: int):
    """
    Returns all game sessions for a given patient/user.
    """
    return db.query(models.GameSession).filter(models.GameSession.patient_id == user_id).order_by(models.GameSession.date_played.desc()).all()

def get_game_session_by_id(db: Session, session_id: int):
    """
    Returns a single game session by its id.
    """
    return db.query(models.GameSession).filter(models.GameSession.id == session_id).first()





def delete_direct_message_for_me(db: Session, message_id: int, user_id: int) -> bool:
    """
    Mark a direct message as deleted for a specific user only.
    The message remains visible to the other user in the conversation.

    Returns True if successful, False if message not found.
    """
    import json

    message = db.query(models.DirectMessage).filter(models.DirectMessage.id == message_id).first()
    if not message:
        return False

    # Parse the deleted_for_user_ids JSON
    try:
        deletion_data = json.loads(message.deleted_for_user_ids or '{"deleted_for_user_ids": []}')
    except json.JSONDecodeError:
        deletion_data = {"deleted_for_user_ids": []}

    # Add user_id if not already present
    if user_id not in deletion_data["deleted_for_user_ids"]:
        deletion_data["deleted_for_user_ids"].append(user_id)

    # Update the message
    message.deleted_for_user_ids = json.dumps(deletion_data)
    db.commit()
    return True


def delete_direct_message_for_everyone(db: Session, message_id: int) -> bool:
    """
    Permanently delete a direct message (delete for everyone).
    The message will be invisible to both users.

    Returns True if successful, False if message not found.
    """
    from datetime import datetime

    message = db.query(models.DirectMessage).filter(models.DirectMessage.id == message_id).first()
    if not message:
        return False

    # Mark as deleted and record timestamp
    message.is_deleted = True
    message.deleted_at = datetime.utcnow()
    db.commit()
    return True


def get_visible_direct_messages_between_users(
    db: Session,
    user1_id: int,
    user2_id: int,
    requesting_user_id: int) -> List[models.DirectMessage]:
    """
    Retrieve all non-deleted direct messages between two users that are visible to the requesting user.
    Excludes:
    - Messages marked as is_deleted == True (deleted for everyone)
    - Messages in the user's deleted_for_user_ids list (deleted for me)

    Returns list of DirectMessage objects that should be visible to the requesting user.
    """
    import json

    messages = get_direct_messages_between_users(db, user1_id, user2_id)

    visible_messages = []
    for msg in messages:
        # Skip if deleted for everyone
        if msg.is_deleted:
            continue

        # Check if deleted for this specific user
        try:
            deletion_data = json.loads(msg.deleted_for_user_ids or '{"deleted_for_user_ids": []}')
            if requesting_user_id in deletion_data.get("deleted_for_user_ids", []):
                continue
        except json.JSONDecodeError:
            pass

        visible_messages.append(msg)

    return visible_messages