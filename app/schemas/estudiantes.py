"""Schemas Pydantic (DTOs) para Representantes (Padres), Estudiantes, Tarifas y Asignaciones (RF-04, RF-05)."""
from datetime import date, time
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field
from app.schemas.common import CoordenadaSchema


# --- PADRES / REPRESENTANTES ---
class PadreCreate(BaseModel):
    email: EmailStr
    password: str = Field(default="padre123", min_length=6)
    nombre: str = Field(..., max_length=100)
    apellido: str = Field(..., max_length=100)
    cedula: str = Field(..., min_length=10, max_length=10)
    telefono: Optional[str] = Field(None, max_length=20)


class PadreResponse(BaseModel):
    id: int
    email: str
    nombre: str
    apellido: str
    cedula: str
    telefono: Optional[str] = None
    activo: int
    total_representados: int = 0

    model_config = {"from_attributes": True}


# --- TARIFAS ESTUDIANTE ---
class TarifaCreate(BaseModel):
    monto_mensual: Decimal = Field(..., gt=0)
    vigente_desde: date
    vigente_hasta: Optional[date] = None
    observacion: Optional[str] = Field(None, max_length=300)


class TarifaResponse(BaseModel):
    id: int
    estudiante_id: int
    monto_mensual: Decimal
    vigente_desde: date
    vigente_hasta: Optional[date] = None
    observacion: Optional[str] = None

    model_config = {"from_attributes": True}


# --- ASIGNACIONES ESTUDIANTE -> RUTA / PARADA ---
class AsignacionRutaCreate(BaseModel):
    estudiante_id: int
    ruta_id: int
    parada_id: int


class AsignacionRutaResponse(BaseModel):
    id: int
    estudiante_id: int
    estudiante_nombre_completo: Optional[str] = None
    estudiante_cedula: Optional[str] = None
    estudiante_grado: Optional[str] = None
    representante_nombre: Optional[str] = None
    representante_telefono: Optional[str] = None
    ruta_id: int
    ruta_nombre: Optional[str] = None
    parada_id: int
    parada_nombre: Optional[str] = None
    parada_orden: Optional[int] = None
    parada_geom: Optional[CoordenadaSchema] = None
    parada_eta: Optional[time] = None
    activa: int

    model_config = {"from_attributes": True}


# --- ESTUDIANTES ---
class EstudianteCreate(BaseModel):
    representante_usuario_id: int
    cedula: str = Field(..., min_length=10, max_length=10)
    nombre: str = Field(..., max_length=100)
    apellido: str = Field(..., max_length=100)
    grado: Optional[str] = Field(None, max_length=50)
    domicilio_geom: Optional[CoordenadaSchema] = None
    domicilio_direccion: Optional[str] = Field(None, max_length=300)
    monto_mensual_inicial: Optional[Decimal] = Field(
        default=None,
        gt=0,
        description="Si se envía, crea automáticamente la tarifa vigente del estudiante",
    )


class EstudianteUpdate(BaseModel):
    representante_usuario_id: Optional[int] = None
    cedula: Optional[str] = Field(None, min_length=10, max_length=10)
    nombre: Optional[str] = Field(None, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    grado: Optional[str] = Field(None, max_length=50)
    domicilio_geom: Optional[CoordenadaSchema] = None
    domicilio_direccion: Optional[str] = Field(None, max_length=300)
    activo: Optional[int] = Field(None, ge=0, le=1)


class EstudianteResponse(BaseModel):
    id: int
    representante_usuario_id: int
    representante_nombre: Optional[str] = None
    representante_cedula: Optional[str] = None
    representante_telefono: Optional[str] = None
    representante_email: Optional[str] = None
    cedula: str
    nombre: str
    apellido: str
    grado: Optional[str] = None
    activo: int
    domicilio_geom: Optional[CoordenadaSchema] = None
    domicilio_direccion: Optional[str] = None
    tarifa_actual: Optional[Decimal] = None
    asignaciones_activas: List[AsignacionRutaResponse] = []

    model_config = {"from_attributes": True}


# --- REGISTRO UNIFICADO PADRE + ESTUDIANTE POR PARTE DEL CONDUCTOR (RF-04) ---
class EstudianteDatosIn(BaseModel):
    cedula: str = Field(..., min_length=10, max_length=10)
    nombre: str = Field(..., max_length=100)
    apellido: str = Field(..., max_length=100)
    grado: Optional[str] = Field(None, max_length=50)
    domicilio_geom: Optional[CoordenadaSchema] = None
    domicilio_direccion: Optional[str] = Field(None, max_length=300)
    monto_mensual_inicial: Optional[Decimal] = Field(default=Decimal("45.00"), gt=0)


class RegistroPadreEstudianteCreate(BaseModel):
    padre: PadreCreate
    estudiante: EstudianteDatosIn
    ruta_id: Optional[int] = Field(
        default=None,
        description="Si el que registra es CONDUCTOR y no envía ruta_id, se asigna automáticamente a la ruta activa del conductor",
    )
    parada_id: Optional[int] = Field(
        default=None,
        description="Si no se envía parada_id y el estudiante tiene domicilio_geom, se crea automáticamente su parada en la ruta",
    )


class RegistroPadreEstudianteResponse(BaseModel):
    padre: PadreResponse
    estudiante: EstudianteResponse


