"""Schemas Pydantic (DTOs) para Instituciones Educativas, Rutas y Paradas (RF-03, RF-08)."""
from datetime import time
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from app.schemas.common import CoordenadaSchema


# --- INSTITUCIONES EDUCATIVAS ---
class InstitucionCreate(BaseModel):
    nombre: str = Field(..., max_length=200)
    direccion: Optional[str] = Field(None, max_length=300)
    tipo: Optional[str] = Field(default="PARTICULAR", max_length=50)
    geom: Optional[CoordenadaSchema] = None


class InstitucionUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    direccion: Optional[str] = Field(None, max_length=300)
    tipo: Optional[str] = Field(None, max_length=50)
    geom: Optional[CoordenadaSchema] = None
    activa: Optional[int] = Field(None, ge=0, le=1)


class InstitucionResponse(BaseModel):
    id: int
    cooperativa_id: int
    nombre: str
    direccion: Optional[str] = None
    tipo: Optional[str] = None
    geom: Optional[CoordenadaSchema] = None
    activa: int

    model_config = {"from_attributes": True}


# --- PARADAS ---
class ParadaCreate(BaseModel):
    nombre: str = Field(..., max_length=200)
    orden: int = Field(default=1, ge=1)
    geom: CoordenadaSchema
    radio_metros: int = Field(default=150, ge=20, le=2000)
    eta_estimado: Optional[time] = None


class ParadaUpdate(BaseModel):
    nombre: Optional[str] = Field(None, max_length=200)
    orden: Optional[int] = Field(None, ge=1)
    geom: Optional[CoordenadaSchema] = None
    radio_metros: Optional[int] = Field(None, ge=20, le=2000)
    eta_estimado: Optional[time] = None


class ParadaResponse(BaseModel):
    id: int
    ruta_id: int
    orden: int
    nombre: str
    geom: Optional[CoordenadaSchema] = None
    radio_metros: int
    eta_estimado: Optional[time] = None
    total_estudiantes_asignados: int = 0

    model_config = {"from_attributes": True}


# --- RUTAS ---
class RutaCreate(BaseModel):
    conductor_id: int
    bus_id: int
    institucion_id: int
    nombre: str = Field(..., max_length=100)
    sector: Optional[str] = Field(None, max_length=120)
    turno: Literal["AM", "PM"]
    hora_campana: Optional[time] = None


class RutaUpdate(BaseModel):
    conductor_id: Optional[int] = None
    bus_id: Optional[int] = None
    institucion_id: Optional[int] = None
    nombre: Optional[str] = Field(None, max_length=100)
    sector: Optional[str] = Field(None, max_length=120)
    turno: Optional[Literal["AM", "PM"]] = None
    hora_campana: Optional[time] = None
    activa: Optional[int] = Field(None, ge=0, le=1)


class RutaResponse(BaseModel):
    id: int
    cooperativa_id: int
    conductor_id: int
    conductor_nombre: Optional[str] = None
    bus_id: int
    bus_placa: Optional[str] = None
    bus_capacidad: Optional[int] = None
    institucion_id: int
    institucion_nombre: Optional[str] = None
    nombre: str
    sector: Optional[str] = None
    turno: str
    hora_campana: Optional[time] = None
    activa: int
    total_paradas: int = 0
    total_estudiantes: int = 0
    paradas: List[ParadaResponse] = []

    model_config = {"from_attributes": True}

