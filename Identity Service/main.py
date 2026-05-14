import os
import httpx
from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
from database import engine, get_db

# Import your local modules
import models
import schemas
import auth_utils

# Create the database tables on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Identity Service")

# Internal URL for the Order Service (Shadow User Sync)
# 'order_service' matches the service name in docker-compose.yml
# ORDER_SERVICE_SYNC_URL = "http://order-service:8000/api/users/sync/"

# MUST include /orders/ in the path now
ORDER_SERVICE_SYNC_URL = "http://order-service:8000/api/orders/users/sync/"

@app.get("/")
async def read_root():
    return {"message": "Identity Service is online"}

@app.get("/db-test")
def test_db_connection(db: Session = Depends(get_db)):
    return {"status": "connected", "database": "ecom_db"}

@app.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Registers a user locally and syncs a 'Shadow User' to the Order Service.
    """
    # 1. Check if user already exists in FastAPI DB
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Email already registered"
        )
    
    # 2. Hash password and save to local Identity DB
    hashed_pwd = auth_utils.hash_password(user_data.password)
    new_user = models.User(email=user_data.email, hashed_password=hashed_pwd)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 3. --- SHADOW USER SYNC (Service-to-Service) ---
    async with httpx.AsyncClient() as client:
        try:
            # We send the request to Django's internal sync endpoint
            sync_response = await client.post(
                ORDER_SERVICE_SYNC_URL,
                json={"email": user_data.email},
                headers={"X-Internal-Secret": os.getenv("JWT_SECRET")},
                timeout=5.0
            )
            
            # Log failure if sync isn't successful (don't block the user)
            if sync_response.status_code not in [200, 201]:
                print(f"⚠️ Shadow User sync failed. Status: {sync_response.status_code}")
                print(f"Details: {sync_response.text}")
        
        except Exception as e:
            print(f"❌ Connection to Order Service failed: {e}")

    return new_user


@app.post("/login")
def login(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    """
    Authenticates user and returns a JWT access token.
    """
    # 1. Find the user
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    
    # 2. Verify existence and password
    if not user or not auth_utils.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # 3. Create the token
    # Identity Service signs this with SHARED_JWT_SECRET
    access_token = auth_utils.create_access_token(
        data={"sub": user.email, "user_id": user.id}
    )
    
    return {"access_token": access_token, "token_type": "bearer"}