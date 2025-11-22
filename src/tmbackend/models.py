from datetime import datetime
from typing import Optional, Dict, Any, Any as AnyType

from bson import ObjectId
from pydantic import BaseModel, Field, ConfigDict, GetCoreSchemaHandler
from pydantic_core import core_schema


class PyObjectId(ObjectId):
    """
    Custom ObjectId type for Pydantic v2 that:
    - Validates strings as Mongo ObjectIds
    - Serializes to string in responses
    """

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type: AnyType, handler: GetCoreSchemaHandler):
        # Use a string schema, then validate & coerce to ObjectId
        return core_schema.no_info_after_validator_function(
            cls.validate,
            core_schema.str_schema(),
            serialization=core_schema.to_string_ser_schema(),
        )

    @classmethod
    def validate(cls, v: AnyType) -> "PyObjectId":
        if isinstance(v, ObjectId):
            return cls(v)
        if isinstance(v, str) and ObjectId.is_valid(v):
            return cls(v)
        raise ValueError("Invalid ObjectId")

    @classmethod
    def __get_pydantic_json_schema__(cls, schema: core_schema.CoreSchema, handler):
        # Make OpenAPI / JSON schema show this as a string
        json_schema = handler(schema)
        json_schema.update(type="string")
        return json_schema


# =======================
# User Models
# =======================

class UserCreate(BaseModel):
    google_sub: str
    email: str


class UserInDB(BaseModel):
    id: PyObjectId = Field(default_factory=PyObjectId, alias="_id")
    google_sub: str
    email: str
    created_at: datetime
    last_login_at: datetime

    # Pydantic v2 config
    model_config = ConfigDict(
        populate_by_name=True,          # replaces allow_population_by_field_name
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


class UserResponse(BaseModel):
    id: str
    email: str
    created_at: datetime
    last_login_at: datetime


# =======================
# Resume Models
# =======================

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

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={ObjectId: str},
    )


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
