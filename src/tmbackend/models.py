from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from bson import ObjectId

class PyObjectId(ObjectId):
    @classmethod
    def __get_validators__(cls):
        yield cls.validate

    @classmethod
    def validate(cls, v):
        if not ObjectId.is_valid(v):
            raise ValueError("Invalid objectid")
        return ObjectId(v)

    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")

# User Models
class UserCreate(BaseModel):
    google_sub: str
    email: str

class UserInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    google_sub: str
    email: str
    created_at: datetime
    last_login_at: datetime

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime
    last_login_at: datetime

# Resume Models
class ResumeCreate(BaseModel):
    target_role: str
    content: Dict[str, Any]

class ResumeUpdate(BaseModel):
    target_role: Optional[str] = None
    content: Optional[Dict[str, Any]] = None

class ResumeInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    user_id: str
    target_role: str
    content: Dict[str, Any]
    date_uploaded: datetime
    updated_at: datetime
    is_deleted: bool = False

    class Config:
        allow_population_by_field_name = True
        arbitrary_types_allowed = True
        json_encoders = {ObjectId: str}

class ResumeResponse(BaseModel):
    id: str
    target_role: str
    content: Dict[str, Any]
    date_uploaded: datetime
    updated_at: datetime

class ResumeListItem(BaseModel):
    id: str
    target_role: str
    date_uploaded: datetime
    updated_at: datetime

