from pydantic import BaseModel, EmailStr

# This is what we expect from the user when they sign up
class UserCreate(BaseModel):
    email: EmailStr
    password: str

# This is what we send BACK to the user (notice we don't send the password back!)
class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool

    class Config:
        from_attributes = True