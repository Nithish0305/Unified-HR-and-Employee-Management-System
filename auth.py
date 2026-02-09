from fastapi import APIRouter, Depends, HTTPException, Form
from database import users_collection
from security import verify_password, hash_password, create_access_token
from dependencies import get_current_user, require_role
from bson import ObjectId
from datetime import datetime, timedelta
from security import (
    verify_password,
    hash_password,
    create_access_token,
    create_refresh_token,
    REFRESH_TOKEN_EXPIRE_DAYS
)
router = APIRouter()

# LOGIN
@router.post("/login")
async def login(username: str = Form(...), password: str = Form(...)):
    user = await users_collection.find_one({"username": username})

    if not user or not verify_password(password, user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(str(user["_id"]))
    refresh_token = create_refresh_token()

    refresh_expiry = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "refresh_token": refresh_token,
                "refresh_token_expiry": refresh_expiry
            }
        }
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer"
    }

# ADMIN CREATES USER
@router.post("/admin/create-user")
async def create_user(
    username: str = Form(...),
    password: str = Form(...),
    role: str = Form(...),
    admin=Depends(require_role("admin"))
):
    if role not in ["admin", "hr", "manager", "employee"]:
        raise HTTPException(status_code=400, detail="Invalid role")

    hashed = hash_password(password)
    await users_collection.insert_one({
        "username": username,
        "password": hashed,
        "role": role
    })
    return {"message": "User created successfully"}

@router.post("/refresh")
async def refresh_token(refresh_token: str = Form(...)):
    user = await users_collection.find_one({"refresh_token": refresh_token})

    if not user:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    if user.get("refresh_token_expiry") < datetime.utcnow():
        raise HTTPException(status_code=401, detail="Refresh token expired")

    new_access_token = create_access_token(str(user["_id"]))

    return {
        "access_token": new_access_token,
        "token_type": "bearer"
    }

@router.post("/logout")
async def logout(user=Depends(get_current_user)):
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$unset": {
                "refresh_token": "",
                "refresh_token_expiry": ""
            }
        }
    )

    return {"message": "Logged out successfully"}
