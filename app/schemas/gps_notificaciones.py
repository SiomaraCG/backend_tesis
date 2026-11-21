"""Schemas Pydantic (DTOs) para Monitoreo GPS en Tiempo Real, Geocercas y Notificaciones (RF-09, RF-10, RF-11)."""
from datetime import datetime
from decimal import Decimal
from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.common import CoordenadaSchema


class RegistrarPosicionGpsRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0, description="Latitud GPS actual de la unidad")
    lng: float = Field(..., ge=-180.0, le=180.0, description="Longitud GPS actual de la unidad")
    velocidad_kmh: Optional[Decimal] = Field(default=Decimal("0.00"), ge=0, le=200)
    heading: Optional[Decimal] = Field(default=Decimal("0.00"), ge=0, le=360)


class AlertaProximidadEmitidaSchema(BaseModel):
    parada_id: int
    parada_nombre: str
    distancia_m: float
    radio_configurado_m: int
    padres_notificados_ids: List[int]
    mensaje: str


class PosicionGpsResponse(BaseModel):
    id: int
    viaje_id: int
    ruta_id: int
    geom: CoordenadaSchema
    velocidad_kmh: Optional[Decimal] = None
    heading: Optional[Decimal] = None
    recorded_at: datetime
    parada_mas_cercana_id: Optional[int] = None
    parada_mas_cercana_nombre: Optional[str] = None
    distancia_parada_mas_cercana_m: Optional[float] = None
    alertas_disparadas: List[AlertaProximidadEmitidaSchema] = []

    model_config = {"from_attributes": True}


class DistanciaParadaResumenSchema(BaseModel):
    parada_id: int
    orden: int
    nombre: str
    geom: Optional[CoordenadaSchema] = None
    radio_metros: int
    distancia_actual_m: Optional[float] = None
    dentro_de_radio: bool = False
    visitada_en_viaje: bool = False


class MonitoreoRutaActualResponse(BaseModel):
    ruta_id: int
    ruta_nombre: str
    viaje_activo_id: Optional[int] = None
    estado_viaje: str
    bus_placa: Optional[str] = None
    conductor_nombre: Optional[str] = None
    conductor_telefono: Optional[str] = None
    ultima_posicion: Optional[CoordenadaSchema] = None
    velocidad_kmh: Optional[Decimal] = None
    heading: Optional[Decimal] = None
    ultima_actualizacion_at: Optional[datetime] = None
    paradas_estado: List[DistanciaParadaResumenSchema] = []
    historial_reciente: List[CoordenadaSchema] = []


class NotificacionResponse(BaseModel):
    id: int
    usuario_id: int
    titulo: str
    mensaje: str
    tipo: str
    leida: int
    created_at: datetime

    model_config = {"from_attributes": True}

