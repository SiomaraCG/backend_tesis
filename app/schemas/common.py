"""Schemas comunes reutilizables (Coordenadas GPS y Estado Activo/Inactivo)."""
from typing import Any
from pydantic import BaseModel, Field, model_validator
from app.models.geo_utils import parse_point


class CoordenadaSchema(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitud en grados decimales (WGS84)")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitud en grados decimales (WGS84)")

    @model_validator(mode="before")
    @classmethod
    def _coerce_wkt_or_point(cls, value: Any) -> Any:
        if isinstance(value, cls):
            return value
        if isinstance(value, (str, bytes, tuple, list)):
            parsed = parse_point(value)
            if parsed is not None:
                return parsed
        return value


class EstadoActivoPatch(BaseModel):
    activo: int = Field(..., ge=0, le=1, description="1 = Activo, 0 = Desactivado")


