from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes_jobs import router as jobs_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(jobs_router)

@app.get("/health")
def health_check():
    return {"status": "ok"}
