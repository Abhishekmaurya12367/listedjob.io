from fastapi import FastAPI

from app.api.routes import router as api_router

app = FastAPI(title="listedjob.io API")
app.include_router(api_router)
