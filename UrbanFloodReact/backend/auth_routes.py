"""
Authentication Routes for Flood Evacuation System
Handles login using the flood_evacuation_db.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import hashlib
import re
from datetime import datetime
from db import _get_db

router = APIRouter(prefix="/auth", tags=["Authentication"])

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    name: str
    role: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""

class UserResponse(BaseModel):
    username: str
    role: str
    name: str
    email: Optional[str] = ""
    phone: Optional[str] = ""
    address: Optional[str] = ""

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
    },
    "citizen": {
        "username": "citizen",
        "role": "citizen",
        "name": "Demo Citizen",
        "email": "citizen@floodsystem.com",
        "phone": "+910000000000",
    },
    "simulate": {
        "username": "simulate",
        "role": "simulate",
        "name": "Demo Simulate",
        "email": "simulate@floodsystem.com",
        "phone": "+910000000000",
    }
}

@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")
        
    # Check password strength
    if len(req.password) < 8 or not re.search(r"[A-Z]", req.password) or not re.search(r"\d", req.password) or not re.search(r"[!@#$%^&*(),.?\":{}|<>]", req.password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters, with 1 uppercase, 1 number, and 1 special character.")
    
    users_col = db["users"]
    
    # Check if username already exists
    if users_col.find_one({"username": req.username}) is not None:
        raise HTTPException(status_code=400, detail="Username already exists")
        
    new_user = {
        "username": req.username,
        "password": hash_password(req.password),
        "name": req.name,
        "role": req.role,
        "email": req.email,
        "phone": req.phone,
        "address": req.address,
        "created_at": datetime.utcnow()
    }
    
    users_col.insert_one(new_user)
    
    return AuthResponse(
        success=True,
        user=UserResponse(
            username=new_user["username"],
            role=new_user["role"],
            name=new_user["name"],
            email=new_user.get("email", ""),
            phone=new_user.get("phone", ""),
            address=new_user.get("address", ""),
        ),
        message="Registration successful",
    )

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
            address=user.get("address", ""),
        ),
        message="Login successful",
    )

@router.post("/demo-login", response_model=AuthResponse)
async def demo_login(req: DemoLoginRequest):
    db = _get_db()
    if db is None:
        raise HTTPException(status_code=500, detail="Database connection unavailable")
        
    users_col = db["users"]
    demo_username = f"demo_{req.role}"
    
    user = users_col.find_one({"username": demo_username})
    
    if not user:
        # Create demo user in MongoDB if it doesn't exist
        demo_names = {
            "researcher": "Demo Researcher",
            "authority": "Demo Authority",
            "citizen": "Demo Citizen",
            "simulate": "Demo Simulate"
        }
        user = {
            "username": demo_username,
            "password": hash_password("DemoPassword1!"), 
            "name": demo_names.get(req.role, f"Demo {req.role.capitalize()}"),
            "role": req.role,
            "email": f"{req.role}@floodsystem.com",
            "phone": "+910000000000",
            "address": "Digital Twin Command Center, New Delhi",
            "created_at": datetime.utcnow()
        }
        users_col.insert_one(user)
        
    return AuthResponse(
        success=True,
        user=UserResponse(
            username=user.get("username"),
            role=user.get("role", "researcher"),
            name=user.get("name", user.get("username")),
            email=user.get("email", ""),
            phone=user.get("phone", ""),
            address=user.get("address", ""),
        ),
        message=f"Demo {req.role} login successful",
    )

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