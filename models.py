from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Enum, Date, Boolean, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
try:
    from .database import Base
except ImportError:
    from database import Base

# Define an Enum for the user roles, just like in your app
class UserRole(str, enum.Enum):
    PATIENT = "Patient"
    DOCTOR = "Doctor"


class User(Base):
    """
    This model represents BOTH Patients and Doctors, distinguished by the 'role' field.
    This replaces the static 'SignUpActivity.User' class.
    """
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False) # NEVER store plaintext
    full_name = Column(String)
    role = Column(Enum(UserRole), nullable=False)

    # --- Doctor-Specific Fields ---
    # The unique code a doctor shares with patients
    doctor_id_code = Column(String, unique=True, index=True, nullable=True)

    # --- Patient-Specific Fields ---
    # Personal details from PersonalDetailsActivity
    age = Column(Integer, nullable=True)
    gender = Column(String, nullable=True)
    # Optional date of birth field (stored as string to handle various formats from Android)
    date_of_birth = Column(String, nullable=True)
    father_name = Column(String, nullable=True)
    mother_name = Column(String, nullable=True)
    address = Column(String, nullable=True)

    # This links a patient to their doctor.
    linked_doctor_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # --- Relationships ---
    # If this user is a doctor, 'patients' is a list of their linked patients
    patients = relationship("User",
                            foreign_keys=[linked_doctor_id],
                            backref="linked_doctor",
                            remote_side=[id]
                           )
    
    # If this user is a patient, 'game_sessions' is a list of all their games
    game_sessions = relationship("GameSession", back_populates="patient")
    
    # Direct messaging relationships
    sent_messages = relationship("DirectMessage", 
                                foreign_keys="DirectMessage.sender_id",
                                back_populates="sender")
    received_messages = relationship("DirectMessage", 
                                    foreign_keys="DirectMessage.recipient_id",
                                    back_populates="recipient")


class GameSession(Base):
    """
    This model stores the results of each game a patient plays.
    This will provide the real data for the ProgressActivity screen.
    """
    __tablename__ = "game_sessions"

    id = Column(Integer, primary_key=True, index=True)
    game_name = Column(String, index=True)
    # Level: Low / Medium / High
    level = Column(String, nullable=True, index=True)
    score = Column(Integer)
    accuracy = Column(Float) # Use Float for percentage (e.g., 74.5)
    duration_seconds = Column(Integer)
    date_played = Column(DateTime(timezone=True), server_default=func.now())
    status = Column(String, default="completed")  # New field for game completion status
    # Foreign key to link this session to a patient
    patient_id = Column(Integer, ForeignKey("users.id"))
    # Relationship to the User model
    patient = relationship("User", back_populates="game_sessions")


class AiChatSession(Base):
    """
    A lightweight chat session for AI interactions per patient.
    Each patient should have exactly one AiChatSession row.
    """
    __tablename__ = "ai_chat_sessions"

    id = Column(Integer, primary_key=True, index=True)
    patient_id = Column(Integer, ForeignKey("users.id"), unique=True)
    patient_name = Column(String, nullable=True)  # Store patient's name for personalization
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    patient = relationship("User")
    messages = relationship("AiChatMessage", back_populates="session")


class AiChatMessage(Base):
    __tablename__ = "ai_chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("ai_chat_sessions.id"))
    sender = Column(String)  # 'patient' or 'ai'
    content = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    session = relationship("AiChatSession", back_populates="messages")


class DirectMessage(Base):
    """
    This model represents direct messages between patients and doctors.
    Similar to WhatsApp - direct messaging without query threads.
    """
    __tablename__ = "direct_messages"

    id = Column(Integer, primary_key=True, index=True)
    message_text = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    # Foreign key for the user who sent the message
    sender_id = Column(Integer, ForeignKey("users.id"))
    # Foreign key for the user who receives the message
    recipient_id = Column(Integer, ForeignKey("users.id"))

    # --- Deletion Fields ---
    # If True, message is deleted for everyone (permanently invisible)
    is_deleted = Column(Boolean, default=False, index=True)

    # JSON string of user IDs who deleted this message for themselves
    # Format: '{"deleted_for_user_ids": [1, 2, 3]}'
    # This allows selective hiding per user
    deleted_for_user_ids = Column(Text, default='{"deleted_for_user_ids": []}')

    # Timestamp when deleted (for delete for everyone)
    deleted_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    sender = relationship("User", foreign_keys=[sender_id], back_populates="sent_messages")
    recipient = relationship("User", foreign_keys=[recipient_id], back_populates="received_messages")