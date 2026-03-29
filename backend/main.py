from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import generate, media, publish
from app.core.db import init_db 

init_db()

app = FastAPI(title="Social Auto Engine API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register both routers
app.include_router(generate.router, prefix="/api")
app.include_router(media.router, prefix="/api/media") 
app.include_router(publish.router, prefix="/api/publish")

@app.get("/")
def read_root():
    return {"message": "Social Auto Engine Backend is running!"}