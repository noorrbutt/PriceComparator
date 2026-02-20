from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# This creates your FastAPI application instance
# Think of it as the "engine" of your backend
app = FastAPI(
    title="Price Comparator API",
    description="Compares prices from Daraz and OLX",
    version="1.0.0"
)

# CORS middleware so your frontend can talk to this backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:8000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Basic health check route
@app.get("/")
def root():
    return {"status": "running", "message": "Price Comparator API is live"}