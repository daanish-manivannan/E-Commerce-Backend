from fastapi import FastAPI

app = FastAPI(title="Identity Service")

@app.get("/")
async def read_root():
    return {"message": "Identity Service is Up and Running on Port 8001"}