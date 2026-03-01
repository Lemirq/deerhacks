from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import instagram_routes

app = FastAPI(title="Deerhacks API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(instagram_routes.router, prefix="/api/instagram", tags=["instagram"])
