from fastapi import FastAPI, HTTPException, status, Depends, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import List
from bson import ObjectId
import os
import uvicorn

from db import connect_to_mongo, close_mongo_connection, get_database
from models import *
from auth import verify_google_token, create_access_token, get_current_user_id
from tmbackend.run_tailor import b64_to_bytes, run_tailor_pipeline

ACCESS_TOKEN_EXPIRE_HOURS = 24
ENV = os.getenv("ENVIRONMENT", "dev")
IS_PROD = ENV == "prod"

app = FastAPI(title="Resume Builder API", version="1.0.0")

origins = [
    "http://localhost:5173",           # local dev
    "https://tailormake.vercel.app",   # prod frontend on Vercel
]


# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Add your frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection events
@app.on_event("startup")
async def startup_db_client():
    await connect_to_mongo()

@app.on_event("shutdown")
async def shutdown_db_client():
    await close_mongo_connection()

# ====== AUTHENTICATION ROUTES ======

@app.post("/auth/google")
async def google_login(google_token: dict, response: Response):
    """
    Authenticate user with Google ID token
    """
    db = get_database()
    
    # Verify Google token
    user_info = await verify_google_token(google_token["token"])
    
    current_time = datetime.utcnow()
    
    # Check if user exists
    existing_user = await db.users_collection.find_one({
        "google_sub": user_info["google_sub"]
    })
    
    if existing_user:
        # Update last login
        await db.users_collection.update_one(
            {"google_sub": user_info["google_sub"]},
            {"$set": {"last_login_at": current_time}}
        )
        user_id = str(existing_user["_id"])
    else:
        # Create new user
        new_user = {
            "google_sub": user_info["google_sub"],
            "email": user_info["email"],
            "created_at": current_time,
            "last_login_at": current_time
        }
        
        result = await db.users_collection.insert_one(new_user)
        user_id = str(result.inserted_id)
    
    # Create JWT token
    access_token = create_access_token({"sub": user_id})

    # 🔐 Set JWT as HttpOnly cookie so frontend never has to store it
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=IS_PROD,          # ⬅️ use True in production (HTTPS)
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_HOURS * 3600,
    )
    
    # We no longer need to return the token
    return {
        "user": {
            "id": user_id,
            "email": user_info["email"]
        }
    }

@app.get("/auth/me")
async def get_current_user(user_id: str = Depends(get_current_user_id)):
    """
    Get current user information
    """
    db = get_database()
    
    user = await db.users_collection.find_one({"_id": ObjectId(user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        created_at=user["created_at"],
        last_login_at=user["last_login_at"]
    )


@app.post("/auth/logout")
def logout(response: Response):
    # Must match the key & settings you used in set_cookie
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=IS_PROD,   # same as when you set it
        samesite="lax",
    )
    return {"ok": True}

# ====== RESUME ROUTES ======

@app.post("/resumes", response_model=ResumeResponse)
async def create_resume(
    resume_data: ResumeCreate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Create a new resume for the authenticated user
    """
    db = get_database()
    
    current_time = datetime.utcnow()
    
    new_resume = {
        "user_id": user_id,
        "target_role": resume_data.target_role,
        "content": resume_data.content,
        "date_uploaded": current_time,
        "updated_at": current_time,
        "is_deleted": False
    }
    
    result = await db.resumes_collection.insert_one(new_resume)
    
    return ResumeResponse(
        id=str(result.inserted_id),
        target_role=resume_data.target_role,
        content=resume_data.content,
        date_uploaded=current_time,
        updated_at=current_time
    )

@app.get("/resumes", response_model=List[ResumeListItem])
async def list_resumes(user_id: str = Depends(get_current_user_id)):
    """
    Get all resumes for the authenticated user
    """
    db = get_database()
    
    cursor = db.resumes_collection.find(
        {
            "user_id": user_id,
            "is_deleted": False
        }
    ).sort("updated_at", -1)
    
    resumes = []
    async for resume in cursor:
        resumes.append(ResumeListItem(
            id=str(resume["_id"]),
            target_role=resume["target_role"],
            date_uploaded=resume["date_uploaded"],
            updated_at=resume["updated_at"]
        ))
    
    return resumes

@app.get("/resumes/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Get a specific resume by ID
    """
    db = get_database()
    
    if not ObjectId.is_valid(resume_id):
        raise HTTPException(status_code=400, detail="Invalid resume ID")
    
    resume = await db.resumes_collection.find_one({
        "_id": ObjectId(resume_id),
        "user_id": user_id,
        "is_deleted": False
    })
    
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    return ResumeResponse(
        id=str(resume["_id"]),
        target_role=resume["target_role"],
        content=resume["content"],
        date_uploaded=resume["date_uploaded"],
        updated_at=resume["updated_at"]
    )

@app.put("/resumes/{resume_id}", response_model=ResumeResponse)
async def update_resume(
    resume_id: str,
    resume_update: ResumeUpdate,
    user_id: str = Depends(get_current_user_id)
):
    """
    Update a specific resume
    """
    db = get_database()
    
    if not ObjectId.is_valid(resume_id):
        raise HTTPException(status_code=400, detail="Invalid resume ID")
    
    # Check if resume exists and belongs to user
    existing_resume = await db.resumes_collection.find_one({
        "_id": ObjectId(resume_id),
        "user_id": user_id,
        "is_deleted": False
    })
    
    if not existing_resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    # Prepare update data
    update_data = {"updated_at": datetime.utcnow()}
    
    if resume_update.target_role is not None:
        update_data["target_role"] = resume_update.target_role
    
    if resume_update.content is not None:
        update_data["content"] = resume_update.content
    
    # Update the resume
    await db.resumes_collection.update_one(
        {"_id": ObjectId(resume_id)},
        {"$set": update_data}
    )
    
    # Return updated resume
    updated_resume = await db.resumes_collection.find_one({"_id": ObjectId(resume_id)})
    
    return ResumeResponse(
        id=str(updated_resume["_id"]),
        target_role=updated_resume["target_role"],
        content=updated_resume["content"],
        date_uploaded=updated_resume["date_uploaded"],
        updated_at=updated_resume["updated_at"]
    )

@app.delete("/resumes/{resume_id}")
async def delete_resume(
    resume_id: str,
    user_id: str = Depends(get_current_user_id)
):
    """
    Soft delete a resume
    """
    db = get_database()
    
    if not ObjectId.is_valid(resume_id):
        raise HTTPException(status_code=400, detail="Invalid resume ID")
    
    # Check if resume exists and belongs to user
    resume = await db.resumes_collection.find_one({
        "_id": ObjectId(resume_id),
        "user_id": user_id,
        "is_deleted": False
    })
    
    if not resume:
        raise HTTPException(status_code=404, detail="Resume not found")
    
    # Soft delete
    await db.resumes_collection.update_one(
        {"_id": ObjectId(resume_id)},
        {
            "$set": {
                "is_deleted": True,
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    return {"message": "Resume deleted successfully"}

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy"}

# ====== Tailor RESUME ROUTES ======
from bson import Binary
from fastapi import HTTPException
from fastapi.responses import JSONResponse

import base64

from pydantic import BaseModel
from typing import Optional

class ResumeUpload(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    base64: Optional[str] = None

class TailorPayload(BaseModel):
    topic: Optional[str] = None
    workExperience: Optional[str] = None
    jobLink: Optional[str] = None
    resume: Optional[ResumeUpload] = None
    submittedAt: Optional[str] = None


@app.post("/tailor")
async def tailor_endpoint(
    payload: TailorPayload,
    user_id: str = Depends(get_current_user_id)
    ):
    # Decode uploaded resume (ephemeral)
    resume_bytes = None
    resume_mime = None
    if payload.resume and payload.resume.base64:
        resume_bytes = b64_to_bytes(payload.resume.base64)
        resume_mime = payload.resume.type

    # Run CrewAI pipeline (sync)
    result = run_tailor_pipeline(
        topic=payload.jobLink or payload.topic or "",
        work_experience=payload.workExperience,
        resume_bytes=resume_bytes,
        resume_mime=resume_mime,
    )

    pdf_bytes = result["pdf_bytes"]
    filename = result["filename"]

    # Save PDF in Mongo if you want it on the home page
    db = get_database()
    doc = {
        "user_id": user_id,
        "filename": filename,
        "mime": "application/pdf",
        "pdfData": Binary(pdf_bytes),
        "jobLink": payload.jobLink,
        "createdAt": datetime.utcnow(),
    }
    inserted = await db.tailored_resumes_collection.insert_one(doc)

    # Base64 for instant preview
    pdf_base64 = base64.b64encode(pdf_bytes).decode("utf-8")

    return {
        "ok": True,
        "result": {
            "id": str(inserted.inserted_id),
            "filename": filename,
            "pdfBase64": pdf_base64,
            "pdfUrl": f"/resumes/{inserted.inserted_id}/pdf",  # if you add such a route
        },
    }

from typing import List

@app.get("/tailored-resumes")
async def list_tailored_resumes(
    user_id: str = Depends(get_current_user_id),
):
    db = get_database()

    cursor = db.tailored_resumes_collection.find(
        {"user_id": user_id}
    ).sort("createdAt", -1)

    items = []
    async for doc in cursor:
        items.append({
            "id": str(doc["_id"]),
            "filename": doc.get("filename", ""),
            "jobLink": doc.get("jobLink"),
            "createdAt": doc.get("createdAt"),
        })

    return items

import io
from fastapi.responses import StreamingResponse
from bson import ObjectId

@app.get("/tailored-resumes/{resume_id}/pdf")
async def get_tailored_resume_pdf(
    resume_id: str,
    user_id: str = Depends(get_current_user_id),
):
    if not ObjectId.is_valid(resume_id):
        raise HTTPException(status_code=400, detail="Invalid resume ID")

    db = get_database()
    doc = await db.tailored_resumes_collection.find_one({
        "_id": ObjectId(resume_id),
        "user_id": user_id,   # 🔒 only allow owner
    })

    if not doc:
        raise HTTPException(status_code=404, detail="Tailored resume not found")

    pdf_bytes = bytes(doc["pdfData"])
    filename = doc.get("filename", "tailored_resume.pdf")

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )












if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


