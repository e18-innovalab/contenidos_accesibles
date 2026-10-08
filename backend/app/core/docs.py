from fastapi import Depends, FastAPI
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse

from app.core.security import get_docs_user


def setup_protected_docs(app: FastAPI, openapi_url: str) -> None:
    """
    Registra /docs, /redoc y openapi.json detrás de HTTP Basic Auth.

    Se usa en staging/production, donde la app se crea con docs_url, redoc_url
    y openapi_url en None para que FastAPI no exponga sus rutas públicas.
    Las tres rutas comparten realm, así el navegador reenvía las credenciales
    cuando Swagger/ReDoc piden el esquema y no vuelve a pedir login.
    """
    auth = [Depends(get_docs_user)]

    @app.get(openapi_url, include_in_schema=False, dependencies=auth)
    def openapi_json() -> JSONResponse:
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False, dependencies=auth)
    def swagger_ui() -> HTMLResponse:
        return get_swagger_ui_html(openapi_url=openapi_url, title=f"{app.title} - Swagger UI")

    @app.get("/redoc", include_in_schema=False, dependencies=auth)
    def redoc() -> HTMLResponse:
        return get_redoc_html(openapi_url=openapi_url, title=f"{app.title} - ReDoc")
