"""
Authentication Routes for Flood Evacuation System
Handles login using the flood_evacuation_db.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import hashlib
from datetime import datetime
from db import _get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class UserResponse(BaseModel):
    username: str
    role: str
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""

class AuthResponse(BaseModel):
    success: bool
    user: Optional[UserResponse] = None
    message: str = ""

class DemoLoginRequest(BaseModel):
    role: str

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

# For Demo Users
DEMO_USERS = {
    "researcher": {
        "username": "researcher",
        "role": "researcher",
        "name": "Demo Researcher",
        "email": "researcher@floodsystem.com",
        "phone": "+911234567891",
    },
    "authority": {
        "username": "authority",
        "role": "authority",
        "name": "Demo Authority",
        "email": "authority@floodsystem.com",
        "phone": "+911234567893",
    }
}

@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")
    
    users_col = db["users"]
    user = users_col.find_one({"username": req.username})
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")      

    if user.get("password") != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")      

    return AuthResponse(
        success=True,
        user=UserResponse(
            username=user.get("username"),
            role=user.get("role", "researcher"),
            name=user.get("name", user.get("username")),
            email=user.get("email", ""),
            phone=user.get("phone", ""),
        ),
        message="Login successful",
    )

@router.post("/demo-login", response_model=AuthResponse)
async def demo_login(req: DemoLoginRequest):
    if req.role in DEMO_USERS:
        return AuthResponse(
            success=True,
            user=UserResponse(**DEMO_USERS[req.role]),
            message=f"Demo {req.role} login successful",
        )
    raise HTTPException(status_code=400, detail="Invalid demo role")

@router.get("/users")
async def list_authorities():
    db = _get_db()
    authorities = []
    if db is not None:
        try:
            authorities = list(db["users"].find({"role": "authority"}, {"_id": 0, "password": 0}))
        except Exception:
            pass
    if not authorities:
        # Fallback if empty database
        authorities = [
            DEMO_USERS["authority"]
        ]
    return {"authorities": authorities}