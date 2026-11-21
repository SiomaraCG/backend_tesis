"""Schemas Pydantic (DTOs) para Socios, Conductores y Buses (RF-02)."""
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field


# --- SOCIOS ---
class SocioCreate(BaseModel):
    # Permite crear el usuario simultáneamente o vincular un usuario_id existente
    usuario_id: Optional[int] = Field(None, description="ID de usuario existente (opcional si se envían datos de usuario)")
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default="socio123", min_length=6)
    nombre: Optional[str] = Field(None, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    cedula: Optional[str] = Field(None, min_length=10, max_length=10)
    telefono: Optional[str] = Field(None, max_length=20)
    nombre_razon_social: str = Field(..., max_length=200)


class SocioUpdate(BaseModel):
    nombre_razon_social: Optional[str] = Field(None, max_length=200)
    nombre: Optional[str] = Field(None, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    activo: Optional[int] = Field(None, ge=0, le=1)


class SocioResponse(BaseModel):
    id: int
    cooperativa_id: int
    usuario_id: int
    nombre_razon_social: str
    activo: int
    usuario_nombre: Optional[str] = None
    usuario_apellido: Optional[str] = None
    usuario_cedula: Optional[str] = None
    usuario_email: Optional[str] = None
    usuario_telefono: Optional[str] = None
    total_buses: int = 0

    model_config = {"from_attributes": True}


# --- CONDUCTORES ---
class ConductorCreate(BaseModel):
    usuario_id: Optional[int] = Field(None, description="ID de usuario existente (opcional)")
    email: Optional[EmailStr] = None
    password: Optional[str] = Field(default="conductor123", min_length=6)
    nombre: Optional[str] = Field(None, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    cedula: Optional[str] = Field(None, min_length=10, max_length=10)
    telefono: Optional[str] = Field(None, max_length=20)
    licencia: str = Field(..., max_length=20, description="Número o código de licencia profesional única")


class ConductorUpdate(BaseModel):
    licencia: Optional[str] = Field(None, max_length=20)
    nombre: Optional[str] = Field(None, max_length=100)
    apellido: Optional[str] = Field(None, max_length=100)
    telefono: Optional[str] = Field(None, max_length=20)
    email: Optional[EmailStr] = None
    activo: Optional[int] = Field(None, ge=0, le=1)


class ConductorResponse(BaseModel):
    id: int
    usuario_id: int
    licencia: str
    activo: int
    nombre: Optional[str] = None
    apellido: Optional[str] = None
    cedula: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None

    model_config = {"from_attributes": True}


# --- BUSES ---
class BusCreate(BaseModel):
    socio_id: int
    placa: str = Field(..., max_length=15, description="Placa única de la unidad, ej. PAA-1024")
    capacidad: int = Field(..., gt=0, le=100, description="Capacidad máxima de estudiantes")


class BusUpdate(BaseModel):
    socio_id: Optional[int] = None
    placa: Optional[str] = Field(None, max_length=15)
    capacidad: Optional[int] = Field(None, gt=0, le=100)
    activo: Optional[int] = Field(None, ge=0, le=1)


class BusResponse(BaseModel):
    id: int
    socio_id: int
    socio_nombre: Optional[str] = None
    placa: str
    capacidad: int
    activo: int

    model_config = {"from_attributes": True}

