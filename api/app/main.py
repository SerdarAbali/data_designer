from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.auth.routes import router as auth_router
from app.catalog.routes import router as catalog_router
from app.db import check_database
from app.integrations.routes import router as integrations_router
from app.scenarios.routes import router as scenarios_router

app = FastAPI(title="Data Designer API", version="0.1.0-alpha")


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault(
        "Permissions-Policy",
        "camera=(), microphone=(), geolocation=()",
    )
    return response


app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(integrations_router)
app.include_router(scenarios_router)


@app.get("/health", tags=["health"])
def health() -> JSONResponse:
    try:
        check_database()
    except SQLAlchemyError:
        return JSONResponse(
            status_code=503,
            content={"api": "ok", "database": "unavailable"},
        )
    return JSONResponse(
        status_code=200,
        content={"api": "ok", "database": "ok"},
    )
