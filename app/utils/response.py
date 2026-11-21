"""
Módulo de estandarización de respuestas HTTP con `COD` (app/utils/response.py).
Todas las respuestas JSON de la API siguen el contrato uniforme:
{
    "COD": "COD_OK" | "COD_ERROR",
    "codigo": 200,
    "mensaje": "Descripción del resultado",
    "data": { ... } | [ ... ] | null
}
"""
from typing import Any, Generic, Optional, TypeVar
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware
import json

T = TypeVar("T")

COD_OK: str = "COD_OK"
COD_ERROR: str = "COD_ERROR"


class ApiResponse(BaseModel, Generic[T]):
    """Esquema genérico estandarizado de respuesta con `COD: COD_OK | COD_ERROR`."""

    COD: str = COD_OK
    codigo: int = status.HTTP_200_OK
    mensaje: str = "Operación realizada exitosamente"
    data: Optional[T] = None


def response_ok(
    data: Any = None,
    mensaje: str = "Operación realizada exitosamente",
    codigo: int = status.HTTP_200_OK,
) -> dict:
    """
    Construye una respuesta exitosa estandarizada con `"COD": "COD_OK"`.
    Puede retornarse directamente en cualquier controlador de FastAPI.
    """
    return {
        "COD": COD_OK,
        "codigo": codigo,
        "mensaje": mensaje,
        "data": jsonable_encoder(data),
    }


def response_error(
    mensaje: str = "Error al procesar la solicitud",
    codigo: int = status.HTTP_400_BAD_REQUEST,
    data: Any = None,
) -> JSONResponse:
    """
    Construye un JSONResponse de error estandarizado con `"COD": "COD_ERROR"`.
    """
    return JSONResponse(
        status_code=codigo,
        content={
            "COD": COD_ERROR,
            "codigo": codigo,
            "mensaje": mensaje,
            "data": jsonable_encoder(data),
        },
    )


class StandardCodOkMiddleware(BaseHTTPMiddleware):
    """
    Middleware que garantiza que cualquier respuesta JSON de los endpoints `/api/...`
    quede envuelta en el formato estándar `{cod_ok, codigo, mensaje, data}`, respetando:
      - Descargas de archivos binarios (PDF, Excel, imágenes).
      - Documentación OpenAPI (`/docs`, `/redoc`, `/openapi.json`).
      - Endpoint OAuth2 `/api/auth/token` (mantiene `access_token` en raíz + `cod_ok`).
    """

    EXCLUDED_PATHS = {"/docs", "/redoc", "/openapi.json"}

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        if path in self.EXCLUDED_PATHS or path.startswith("/uploads"):
            return response

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            return response

        body_chunks = [chunk async for chunk in response.body_iterator]
        raw_body = b"".join(body_chunks)
        if not raw_body:
            return response

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            return ResponseFromBytes(raw_body, response)

        # Si el endpoint ya devolvió `cod_ok`, no volver a envolver
        if isinstance(payload, dict) and "COD" in payload:
            return ResponseFromBytes(raw_body, response)

        # Compatibilidad con el botón Authorize OAuth2 de Swagger UI (/api/auth/token)
        if path.endswith("/auth/token") and isinstance(payload, dict) and "access_token" in payload:
            payload["COD"] = COD_OK
            payload["codigo"] = response.status_code
            nuevo_raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return ResponseFromBytes(nuevo_raw, response)

        es_exito = 200 <= response.status_code < 400
        mensaje_default = (
            payload.get("mensaje")
            if (isinstance(payload, dict) and isinstance(payload.get("mensaje"), str) and len(payload) == 1)
            else ("Operación realizada exitosamente" if es_exito else "Error en la solicitud")
        )

        estandarizado = {
            "COD": COD_OK if es_exito else COD_ERROR,
            "codigo": response.status_code,
            "mensaje": mensaje_default,
            "data": payload,
        }
        nuevo_raw = json.dumps(estandarizado, ensure_ascii=False).encode("utf-8")
        return ResponseFromBytes(nuevo_raw, response)


def ResponseFromBytes(raw_bytes: bytes, original_response) -> JSONResponse:
    headers = dict(original_response.headers)
    headers.pop("content-length", None)
    return JSONResponse(
        content=json.loads(raw_bytes.decode("utf-8")),
        status_code=original_response.status_code,
        headers=headers,
    )


def register_standard_responses(app: FastAPI) -> None:
    """
    Registra el middleware `StandardCodOkMiddleware` y los manejadores globales
    de excepciones en la instancia principal de FastAPI (`app/main.py`).
    """
    app.add_middleware(StandardCodOkMiddleware)

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return response_error(
            mensaje=str(exc.detail),
            codigo=exc.status_code,
            data=None,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        return response_error(
            mensaje="Error de validación en los datos enviados",
            codigo=status.HTTP_422_UNPROCESSABLE_ENTITY,
            data=exc.errors(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        return response_error(
            mensaje=f"Error interno del servidor: {str(exc)}",
            codigo=status.HTTP_500_INTERNAL_SERVER_ERROR,
            data=None,
        )
