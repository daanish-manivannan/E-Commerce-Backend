from fastapi import FastAPI, Depends, HTTPException, status
from sqlalchemy.orm import Session
import models, schemas, auth_utils  # These imports will work now!
from database import engine, get_db

# Create the tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="Identity Service")

@app.get("/")
async def read_root():
    return {"message": "Identity Service is online"}

@app.get("/db-test")
def test_db_connection(db: Session = Depends(get_db)):
    return {"status": "connected", "database": "ecom_db"}

@app.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
def register_user(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    # Check if user exists
    db_user = db.query(models.User).filter(models.User.email == user_data.email).first()
    if db_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Hash password and save
    hashed_pwd = auth_utils.hash_password(user_data.password)
    new_user = models.User(email=user_data.email, hashed_password=hashed_pwd)
    
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


@app.post("/login")
def login(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    # 1. Find the user
    user = db.query(models.User).filter(models.User.email == user_data.email).first()
    
    # 2. Verify existence and password
    if not user or not auth_utils.verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )
    
    # 3. Create the token
    access_token = auth_utils.create_access_token(data={"sub": user.email, "user_id": user.id})
    
    return {"access_token": access_token, "token_type": "bearer"}