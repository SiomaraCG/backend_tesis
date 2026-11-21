"""Schemas Pydantic (DTOs) para Viajes, Asistencia, Ausencias y Optimización OR-Tools (RF-07, RF-08)."""
from datetime import date, datetime, time
from typing import List, Literal, Optional
from pydantic import BaseModel, Field
from app.schemas.common import CoordenadaSchema


# --- VIAJES E INICIO/FIN DE RECORRIDO (RF-07) ---
class IniciarViajeRequest(BaseModel):
    ruta_id: int
    fecha: Optional[date] = None


class ViajeResponse(BaseModel):
    id: int
    ruta_id: int
    ruta_nombre: Optional[str] = None
    turno: Optional[str] = None
    conductor_id: int
    conductor_nombre: Optional[str] = None
    bus_id: int
    bus_placa: Optional[str] = None
    fecha: date
    estado: str
    inicio_at: Optional[datetime] = None
    fin_at: Optional[datetime] = None
    total_estudiantes_ruta: int = 0
    total_ausencias_hoy: int = 0
    total_recogidos_hoy: int = 0

    model_config = {"from_attributes": True}


# --- AUSENCIAS Y ASISTENCIA DEL DÍA (RF-07) ---
class ReportarAusenciaRequest(BaseModel):
    estudiante_id: int
    motivo_padre: str = Field(..., max_length=500, description="Motivo por el que el estudiante no asistirá al recorrido")


class RegistrarAsistenciaRequest(BaseModel):
    estudiante_id: int
    estado_asistencia: Literal["RECOGIDO", "NO_ASISTIO", "PRESENTE", "NO_SALIO"] = Field(
        ...,
        description="RECOGIDO (o PRESENTE) cuando sube al bus; NO_ASISTIO (o NO_SALIO) cuando no salió a la parada",
    )
    observacion: Optional[str] = Field(None, max_length=300)
    ubicacion: Optional[CoordenadaSchema] = None


class EstudianteHojaRutaResponse(BaseModel):
    estudiante_id: int
    estudiante_nombre_completo: str
    cedula: str
    grado: Optional[str] = None
    representante_nombre: Optional[str] = None
    representante_telefono: Optional[str] = None
    parada_id: int
    parada_nombre: str
    parada_orden: int
    parada_geom: Optional[CoordenadaSchema] = None
    parada_eta: Optional[time] = None
    estado_hoy: str = Field(
        ...,
        description="PENDIENTE | RECOGIDO | AUSENCIA_PREVIA | NO_ASISTIO",
    )
    motivo_ausencia: Optional[str] = None


# --- NOVEDADES / INCIDENTES DE VIAJE ---
class NovedadViajeCreate(BaseModel):
    tipo: Literal["ASISTENCIA", "RETRASO", "AVERIA", "TRAFICO", "INCIDENTE", "OTRO"]
    descripcion: str = Field(..., max_length=1000)
    ubicacion: Optional[CoordenadaSchema] = None


class NovedadViajeResponse(BaseModel):
    id: int
    viaje_id: int
    reportado_por_usuario_id: int
    tipo: str
    descripcion: Optional[str] = None
    estado: str
    ocurrido_at: datetime
    ubicacion: Optional[CoordenadaSchema] = None

    model_config = {"from_attributes": True}


# --- OPTIMIZACIÓN DE RUTAS CON GOOGLE OR-TOOLS (RF-08) ---
class OptimizarRutaRequest(BaseModel):
    viaje_id: Optional[int] = Field(
        None,
        description="Si se envía, excluye paradas donde todos los estudiantes reportaron ausencia en este viaje",
    )
    velocidad_promedio_kmh: float = Field(default=25.0, gt=5.0, le=90.0)


class ParadaOptimizadaItem(BaseModel):
    parada_id: int
    nombre: str
    orden_anterior: int
    orden_optimizado: int
    geom: CoordenadaSchema
    eta_estimado: Optional[time] = None
    estudiantes_activos: int
    distancia_desde_anterior_m: float


class RutaOptimizacionResponse(BaseModel):
    ruta_id: int
    ruta_nombre: str
    turno: str
    algoritmo: str = "Google OR-Tools Routing Solver (GUIDED_LOCAL_SEARCH / PATH_CHEAPEST_ARC)"
    distancia_total_km: float
    tiempo_total_estimado_min: float
    paradas_activas_optimizadas: List[ParadaOptimizadaItem]
    paradas_omitidas_por_ausencia: List[str] = []
    polilinea_coordenadas: List[CoordenadaSchema] = []

