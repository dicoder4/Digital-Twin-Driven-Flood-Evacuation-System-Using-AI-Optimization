"""
Authentication Routes for Flood Evacuation System
Handles login, registration, and user info.
Supports both MongoDB auth and local fallback for demo/guest access.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import hashlib
from datetime import datetime

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ---------- Pydantic Models ----------

class LoginRequest(BaseModel):
    username: str
    password: str

class RegisterRequest(BaseModel):
    username: str
    password: str
    role: str = "researcher"
    name: str
    email: str
    phone: str = ""

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
    role: str  # "researcher", "authority", or "guest"


# ---------- Helpers ----------

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# Default users (same as Streamlit app.py / auth_components.py)
DEFAULT_USERS = {
    "admin": {
        "username": "admin",
        "password": hash_password("admin123"),
        "role": "researcher",
        "name": "System Administrator",
        "email": "admin@floodsystem.com",
        "phone": "+911234567890",
    },
    "researcher": {
        "username": "researcher",
        "password": hash_password("research123"),
        "role": "researcher",
        "name": "Emergency Researcher",
        "email": "researcher@floodsystem.com",
        "phone": "+911234567891",
    },
    "authority": {
        "username": "authority",
        "password": hash_password("authority123"),
        "role": "authority",
        "name": "Disaster Response Authority",
        "email": "authority@floodsystem.com",
        "phone": "+911234567893",
    },
}


# Try MongoDB, fall back to in-memory
_mongo_available = False
_users_collection = None

try:
    from db_utils import get_users_collection, save_user
    _users_collection = get_users_collection()
    _users_collection.count_documents({})  # test connection
    _mongo_available = True

    # Seed default users if empty
    if _users_collection.count_documents({}) == 0:
        for u in DEFAULT_USERS.values():
            save_user({**u, "created_at": datetime.utcnow().isoformat()})
    print("[OK] Auth: MongoDB connected")
except Exception as e:
    print(f"[WARN] Auth: MongoDB unavailable ({e}), using local fallback")
    _mongo_available = False


def _find_user(username: str):
    """Look up user in MongoDB first, then fall back to defaults."""
    if _mongo_available:
        try:
            user = _users_collection.find_one({"username": username})
            if user:
                return user
        except Exception:
            pass
    return DEFAULT_USERS.get(username)


def _save_user_safe(user_doc):
    if _mongo_available:
        try:
            save_user(user_doc)
            return True
        except Exception:
            pass
    return False


# ---------- Routes ----------

@router.post("/login", response_model=AuthResponse)
async def login(req: LoginRequest):
    user = _find_user(req.username)

    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if user.get("password") != hash_password(req.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    return AuthResponse(
        success=True,
        user=UserResponse(
            username=user["username"],
            role=user.get("role", "researcher"),
            name=user.get("name", user["username"]),
            email=user.get("email", ""),
            phone=user.get("phone", ""),
        ),
        message="Login successful",
    )


@router.post("/demo-login", response_model=AuthResponse)
async def demo_login(req: DemoLoginRequest):
    """Quick demo/guest login without password — matches Streamlit Demo Access tab."""
    if req.role == "guest":
        return AuthResponse(
            success=True,
            user=UserResponse(
                username="guest",
                role="citizen",
                name="Guest User",
                email="guest@example.com",
                phone="+911234567890",
            ),
            message="Guest login successful",
        )
    elif req.role == "researcher":
        return AuthResponse(
            success=True,
            user=UserResponse(
                username="researcher",
                role="researcher",
                name="Demo Researcher",
                email="researcher@floodsystem.com",
                phone="+911234567891",
            ),
            message="Demo researcher login successful",
        )
    elif req.role == "authority":
        return AuthResponse(
            success=True,
            user=UserResponse(
                username="authority",
                role="authority",
                name="Demo Authority",
                email="authority@floodsystem.com",
                phone="+911234567893",
            ),
            message="Demo authority login successful",
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid demo role")


@router.post("/register", response_model=AuthResponse)
async def register(req: RegisterRequest):
    existing = _find_user(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already exists")

    new_user = {
        "username": req.username,
        "password": hash_password(req.password),
        "role": req.role,
        "name": req.name,
        "email": req.email,
        "phone": req.phone,
        "created_at": datetime.utcnow().isoformat(),
    }

    saved = _save_user_safe(new_user)
    if not saved:
        # Store in local defaults so it works for this session
        DEFAULT_USERS[req.username] = new_user

    return AuthResponse(
        success=True,
        user=UserResponse(
            username=req.username,
            role=req.role,
            name=req.name,
            email=req.email,
            phone=req.phone,
        ),
        message="Registration successful",
    )


@router.get("/users")
async def list_authorities():
    """Return all authority-role users."""
    authorities = []
    if _mongo_available:
        try:
            authorities = list(_users_collection.find({"role": "authority"}, {"_id": 0, "password": 0}))
        except Exception:
            pass
    if not authorities:
        authorities = [
            {"username": u["username"], "role": u["role"], "name": u["name"], "email": u["email"]}
            for u in DEFAULT_USERS.values() if u["role"] == "authority"
        ]
    return {"authorities": authorities}
