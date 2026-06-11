from pydantic import BaseModel, EmailStr, field_validator, ConfigDict
import uuid
from datetime import datetime

class SignupRequest(BaseModel):
    name: str
    email: str
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v
    
class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UploadResponse(BaseModel):
    document_id: str
    file_name: str
    message: str

class ChatRequest(BaseModel):
    session_id: uuid.UUID
    query: str

class ChatResponse(BaseModel):
    session_id: str
    answer: str

class ChatHistoryItem(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)