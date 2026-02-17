from __future__ import annotations
from pydantic import BaseModel, EmailStr
from datetime import datetime, date
from typing import List, Optional

# Import the Enums we defined in models.py
try:
    from . import models
except ImportError:
    import models

# --- GameSession Schemas ---

class GameSessionBase(BaseModel):
    """Base schema for a game session, used for creation."""
    game_name: str
    level: Optional[str] = None
    score: int
    accuracy: float
    duration_seconds: int
    status: str = "completed"  # New field for game completion status

class GameSessionCreate(GameSessionBase):
    """Schema used when the app uploads a new game session."""
    pass

class GameSession(GameSessionBase):
    """
    Schema used when returning game session data from the API.
    It includes the fields from the database.
    """
    id: int
    patient_id: int
    date_played: datetime
    model_config = {"from_attributes": True}


class AiChatMessageBase(BaseModel):
    sender: str
    content: str


class AiChatMessageCreate(AiChatMessageBase):
    pass


class AiChatMessage(AiChatMessageBase):
    id: int
    timestamp: datetime
    model_config = {"from_attributes": True}


class AiChatSession(BaseModel):
    id: int
    patient_id: int
    patient_name: Optional[str] = None
    messages: List[AiChatMessage] = []
    model_config = {"from_attributes": True}


# --- Direct Message Schemas ---

class DirectMessageBase(BaseModel):
    message_text: str

class DirectMessageCreate(DirectMessageBase):
    """Schema for creating a new direct message."""
    recipient_id: int

class DirectMessage(DirectMessageBase):
    """Schema for returning a direct message from the API."""
    id: int
    timestamp: datetime
    sender_id: int
    recipient_id: int
    is_deleted: bool = False
    deleted_for_user_ids: str = '{"deleted_for_user_ids": []}'
    deleted_at: Optional[datetime] = None
    model_config = {"from_attributes": True}


# --- User Schemas ---

class UserBase(BaseModel):
    """Base schema for a user."""
    email: EmailStr  # Pydantic will automatically validate this is an email
    full_name: str

class UserCreate(UserBase):
    """
    Schema used for creating a new user (registration).
    This is what the app will send to the /register endpoint.
    """
    password: str  # The app sends the plain-text password...
    role: models.UserRole
    # Optional profile fields collected during signup
    age: Optional[int] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    fatherName: Optional[str] = None
    motherName: Optional[str] = None
    address: Optional[str] = None

class User(UserBase):
    """
    Schema used when returning user data from the API.
    Notice: NO 'password' or 'hashed_password' field. This is for security.
    """
    id: int
    role: models.UserRole
    doctor_id_code: Optional[str] = None  # Optional, for doctors
    linked_doctor_id: Optional[int] = None # Optional, for patients

    # --- NEWLY ADDED ---
    age: Optional[int] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    address: Optional[str] = None
    profile_image_url: Optional[str] = None
    # --- END OF ADD ---

    model_config = {"from_attributes": True}


# --- Token Schemas ---

class TokenRequest(BaseModel):
    """
    Schema for the /login endpoint.
    FastAPI's OAuth2 utility requires this to be in a form
    with 'username' and 'password' fields.
    """
    username: EmailStr  # We will use the email as the username
    password: str

class Token(BaseModel):
    """Schema for the response from the /login endpoint."""
    access_token: str
    token_type: str

class TokenData(BaseModel):
    """Schema to define the data we hide inside the token."""
    email: Optional[str] = None


# --- Doctor Linking Schemas ---

class DoctorLink(BaseModel):
    """Schema for a patient to link to a doctor."""
    doctor_code: str


# (This should be at the end of your schemas.py file)

class PatientInfo(UserBase):
    """
    A simple schema to return basic patient information
    for the doctor's patient list.
    Inherits email and full_name from UserBase.
    """
    id: int
    age: Optional[int] = None
    gender: Optional[str] = None
    profile_image_url: Optional[str] = None
    model_config = {"from_attributes": True}


# --- Health Chat Schemas ---

class HealthChatMessageCreate(BaseModel):
    """Schema for creating a health chat message."""
    user_message: str


class HealthChatMessageResponse(BaseModel):
    """Schema for health chat response."""
    user_message: str
    ai_response: str
    timestamp: Optional[datetime] = None


# --- ML-Based AI Chat Schemas ---

class AIChatMLRequest(BaseModel):
    """Schema for ML-based AI chat request."""
    user_message: str


class AIChatMLResponse(BaseModel):
    """Schema for ML-based AI chat response with intent classification."""
    user_message: str
    ai_response: str
    intent: str  # one of: eye_health, eye_movement, eye_food, vision_check, not_related, greeting
    confidence: float  # confidence score of intent prediction (0.0 to 1.0)
    timestamp: Optional[str] = None

# --- OTP Schemas ---
class OTPRequest(BaseModel):
    email: EmailStr
    intent: str  # "signup" or "reset"

class OTPVerifyRequest(BaseModel):
    email: EmailStr
    otp: str

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    age: Optional[int] = None
    gender: Optional[str] = None
    date_of_birth: Optional[str] = None
    father_name: Optional[str] = None
    mother_name: Optional[str] = None
    address: Optional[str] = None
    profile_image_url: Optional[str] = None
