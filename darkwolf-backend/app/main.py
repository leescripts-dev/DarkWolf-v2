from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.db.mongodb import check_database_connection
from app.api.dashboard import router as dashboard_router
from app.api.routes.victims import router as victims_router
from app.api.routes.changes import router as changes_router
from app.api.routes.evidence import router as evidence_router
from app.api.routes.scrape import router as scrape_router
from app.api.routes.sources import router as sources_router



app = FastAPI(
    title="DarkWolf Backend",
    version="0.1.0",
)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(dashboard_router)
app.include_router(victims_router)
app.include_router(changes_router)
app.include_router(evidence_router)
app.include_router(scrape_router)
app.include_router(sources_router)


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "darkwolf-backend",
    }


@app.get("/health/database")
def database_health():
    connected = check_database_connection()

    return {
        "status": "ok" if connected else "error",
        "database": "mongodb",
        "connected": connected,
    }
