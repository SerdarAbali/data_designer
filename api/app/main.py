from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from app.architecture.baseline import router as architecture_baseline_router
from app.architecture.enterprise import router as architecture_enterprise_router
from app.architecture.evidence import router as architecture_evidence_router
from app.architecture.information import router as architecture_information_router
from app.architecture.objects import router as architecture_objects_router
from app.architecture.routes import router as architecture_router
from app.architecture.solution import router as architecture_solution_router
from app.architecture.solution_integration import (
    router as architecture_solution_integration_router,
)
from app.architecture.solution_landscape import (
    router as architecture_solution_landscape_router,
)
from app.architecture.traceability import router as architecture_traceability_router
from app.assistant.routes import internal_router as assistant_internal_router
from app.assistant.routes import router as assistant_router
from app.assistant.routes import workspace_router as assistant_workspace_router
from app.auth.routes import router as auth_router
from app.catalog.routes import router as catalog_router
from app.db import check_database
from app.helper_actions.routes import router as helper_actions_router
from app.imports.routes import router as imports_router
from app.integrations.contract_workbook import router as contract_workbook_router
from app.integrations.integration_design import router as integration_design_router
from app.integrations.routes import router as integrations_router
from app.scenarios.routes import router as scenarios_router
from app.workspaces.routes import router as workspaces_router

app = FastAPI(title="Data Designer API", version="0.2.0-alpha")


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
app.include_router(workspaces_router)
app.include_router(architecture_router)
app.include_router(architecture_baseline_router)
app.include_router(architecture_objects_router)
app.include_router(architecture_information_router)
app.include_router(architecture_solution_router)
app.include_router(architecture_solution_integration_router)
app.include_router(architecture_solution_landscape_router)
app.include_router(architecture_enterprise_router)
app.include_router(architecture_traceability_router)
app.include_router(architecture_evidence_router)
app.include_router(integration_design_router)
app.include_router(contract_workbook_router)
app.include_router(imports_router)
app.include_router(helper_actions_router)
app.include_router(assistant_router)
app.include_router(assistant_workspace_router)
app.include_router(assistant_internal_router)


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
