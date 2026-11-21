"""Schemas Pydantic (DTOs) para Pagos y Procesamiento de Comprobantes con OCR (RF-12, RF-13, RF-14)."""
from datetime import date, datetime
from decimal import Decimal
from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class GenerarPagosMesRequest(BaseModel):
    mes: int = Field(..., ge=1, le=12, description="Mes del periodo (1 a 12)")
    anio: int = Field(..., ge=2024, le=2035, description="Año del periodo, ej. 2026")


class ResultadoOcrSchema(BaseModel):
    banco: Optional[str] = None
    monto_extraido: Optional[Decimal] = None
    fecha_transferencia: Optional[date] = None
    referencia_extraida: Optional[str] = None
    ocr_confianza: Decimal
    coincide_monto_esperado: bool = False
    motor_utilizado: str
    texto_detectado: str


class ComprobanteResponse(BaseModel):
    id: int
    pago_id: int
    canal: str
    archivo_url: str
    banco: Optional[str] = None
    monto_extraido: Optional[Decimal] = None
    fecha_transferencia: Optional[date] = None
    referencia_extraida: Optional[str] = None
    ocr_confianza: Optional[Decimal] = None
    estado: str
    created_at: datetime
    resultado_ocr_detalle: Optional[ResultadoOcrSchema] = None

    model_config = {"from_attributes": True}


class ConfirmarDatosOcrRequest(BaseModel):
    banco: str = Field(..., max_length=100)
    monto_extraido: Decimal = Field(..., gt=0)
    fecha_transferencia: date
    referencia_extraida: str = Field(..., max_length=100)


class RevisarComprobanteRequest(BaseModel):
    estado: Literal["VALIDADO", "OBSERVADO", "RECHAZADO"]
    observacion: Optional[str] = Field(None, max_length=300)


class PagoResponse(BaseModel):
    id: int
    estudiante_id: int
    estudiante_nombre: Optional[str] = None
    estudiante_cedula: Optional[str] = None
    representante_nombre: Optional[str] = None
    representante_telefono: Optional[str] = None
    ruta_id: Optional[int] = None
    ruta_nombre: Optional[str] = None
    tarifa_id: int
    monto: Decimal
    mes: int
    anio: int
    estado: str
    created_at: datetime
    updated_at: datetime
    comprobantes: List[ComprobanteResponse] = []

    model_config = {"from_attributes": True}

