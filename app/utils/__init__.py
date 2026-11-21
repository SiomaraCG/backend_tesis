"""Utilidades transversales del Backend (Respuestas estandarizadas con `cod_ok`)."""
from app.utils.response import (
    ApiResponse,
    COD_ERROR,
    COD_OK,
    register_standard_responses,
    response_error,
    response_ok,
)

__all__ = [
    "ApiResponse",
    "COD_OK",
    "COD_ERROR",
    "response_ok",
    "response_error",
    "register_standard_responses",
]

