"""Controlador de Pagos Mensuales y Procesamiento de Comprobantes con OCR (RF-12, RF-13, RF-14, RF-15)."""
from datetime import datetime
from pathlib import Path
from typing import List, Optional
import uuid
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_user_roles, require_role
from app.models import (
    AsignacionEstudianteRuta,
    Comprobante,
    Estudiante,
    Notificacion,
    Pago,
    Ruta,
    TarifaEstudiante,
    Usuario,
)
from app.schemas.pagos_ocr import (
    ComprobanteResponse,
    ConfirmarDatosOcrRequest,
    GenerarPagosMesRequest,
    PagoResponse,
    RevisarComprobanteRequest,
)
from app.services.ocr_service import procesar_comprobante_ocr

router = APIRouter(prefix="/pagos", tags=["Pagos y Comprobantes OCR (RF-12, RF-13, RF-14)"])

UPLOADS_DIR = Path("uploads/comprobantes")
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)


def _serialize_comprobante(c: Comprobante, resultado_ocr=None) -> ComprobanteResponse:
    return ComprobanteResponse(
        id=c.id,
        pago_id=c.pago_id,
        canal=c.canal,
        archivo_url=c.archivo_url,
        banco=c.banco,
        monto_extraido=c.monto_extraido,
        fecha_transferencia=c.fecha_transferencia,
        referencia_extraida=c.referencia_extraida,
        ocr_confianza=c.ocr_confianza,
        estado=c.estado,
        created_at=c.created_at,
        resultado_ocr_detalle=resultado_ocr,
    )


def _serialize_pago(p: Pago) -> PagoResponse:
    est = p.estudiante
    rep = est.representante if est else None
    ruta_id = None
    ruta_nombre = None
    if est and est.asignaciones:
        activas = [a for a in est.asignaciones if a.activa == 1]
        if activas and activas[0].ruta:
            ruta_id = activas[0].ruta.id
            ruta_nombre = activas[0].ruta.nombre

    return PagoResponse(
        id=p.id,
        estudiante_id=p.estudiante_id,
        estudiante_nombre=f"{est.nombre} {est.apellido}" if est else None,
        estudiante_cedula=est.cedula if est else None,
        representante_nombre=f"{rep.nombre} {rep.apellido}" if rep else None,
        representante_telefono=rep.telefono if rep else None,
        ruta_id=ruta_id,
        ruta_nombre=ruta_nombre,
        tarifa_id=p.tarifa_id,
        monto=p.monto,
        mes=p.mes,
        anio=p.anio,
        estado=p.estado,
        created_at=p.created_at,
        updated_at=p.updated_at,
        comprobantes=[_serialize_comprobante(c) for c in (p.comprobantes or [])],
    )


# ============================================================================
# GENERACIÓN Y CONSULTA DE ESTADO DE PAGOS (RF-14, RF-15)
# ============================================================================

@router.post(
    "/generar-mes",
    response_model=List[PagoResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Generar registros de pago mensual para todos los estudiantes activos con tarifa vigente",
)
def generar_pagos_del_mes(
    payload: GenerarPagosMesRequest,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    estudiantes = (
        db.query(Estudiante)
        .join(Usuario, Estudiante.representante_usuario_id == Usuario.id)
        .filter(
            Usuario.cooperativa_id == current_user.cooperativa_id,
            Estudiante.activo == 1,
        )
        .all()
    )

    pagos_creados: List[Pago] = []
    for est in estudiantes:
        existente = (
            db.query(Pago)
            .filter(
                Pago.estudiante_id == est.id,
                Pago.mes == payload.mes,
                Pago.anio == payload.anio,
            )
            .first()
        )
        if existente:
            pagos_creados.append(existente)
            continue

        tarifa = (
            db.query(TarifaEstudiante)
            .filter(TarifaEstudiante.estudiante_id == est.id)
            .order_by(TarifaEstudiante.vigente_desde.desc())
            .first()
        )
        if not tarifa:
            continue

        nuevo_pago = Pago(
            estudiante_id=est.id,
            tarifa_id=tarifa.id,
            monto=tarifa.monto_mensual,
            mes=payload.mes,
            anio=payload.anio,
            estado="PENDIENTE",
        )
        db.add(nuevo_pago)
        db.flush()
        pagos_creados.append(nuevo_pago)

    db.commit()
    return [_serialize_pago(p) for p in pagos_creados]


@router.get(
    "",
    response_model=List[PagoResponse],
    summary="Consultar estado de pagos (PAGADO, PENDIENTE, EN_REVISION) según rol (RF-14, RF-15)",
)
def listar_pagos(
    mes: Optional[int] = Query(None, ge=1, le=12),
    anio: Optional[int] = Query(None, ge=2024, le=2035),
    estado: Optional[str] = Query(None, description="PENDIENTE | EN_REVISION | PAGADO | RECHAZADO"),
    ruta_id: Optional[int] = Query(None),
    estudiante_id: Optional[int] = Query(None),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cumple RF-14 y RF-15:
      - PADRE: consulta únicamente los pagos de sus hijos representados.
      - CONDUCTOR: consulta el estado de pagos de los estudiantes asignados a su ruta.
      - ADMIN: consulta todos los pagos con filtros por mes, año, ruta o estado.
    """
    roles = set(get_user_roles(current_user))
    query = (
        db.query(Pago)
        .join(Estudiante, Pago.estudiante_id == Estudiante.id)
        .join(Usuario, Estudiante.representante_usuario_id == Usuario.id)
        .filter(Usuario.cooperativa_id == current_user.cooperativa_id)
    )

    if mes is not None:
        query = query.filter(Pago.mes == mes)
    if anio is not None:
        query = query.filter(Pago.anio == anio)
    if estado is not None:
        query = query.filter(Pago.estado == estado.upper())
    if estudiante_id is not None:
        query = query.filter(Pago.estudiante_id == estudiante_id)
    if ruta_id is not None:
        subq_ruta = (
            db.query(AsignacionEstudianteRuta.estudiante_id)
            .filter(
                AsignacionEstudianteRuta.ruta_id == ruta_id,
                AsignacionEstudianteRuta.activa == 1,
            )
        )
        query = query.filter(Pago.estudiante_id.in_(subq_ruta))

    if "ADMIN" not in roles:
        if "PADRE" in roles:
            query = query.filter(Estudiante.representante_usuario_id == current_user.id)
        elif "CONDUCTOR" in roles and current_user.conductor:
            subq_cond = (
                db.query(AsignacionEstudianteRuta.estudiante_id)
                .join(Ruta, AsignacionEstudianteRuta.ruta_id == Ruta.id)
                .filter(
                    Ruta.conductor_id == current_user.conductor.id,
                    AsignacionEstudianteRuta.activa == 1,
                )
            )
            query = query.filter(Pago.estudiante_id.in_(subq_cond))
        else:
            return []

    pagos = query.order_by(Pago.anio.desc(), Pago.mes.desc(), Pago.id.desc()).all()
    return [_serialize_pago(p) for p in pagos]


# ============================================================================
# ENVÍO DE COMPROBANTES EN IMAGEN Y PROCESAMIENTO CON OCR (RF-12, RF-13)
# ============================================================================

@router.post(
    "/{pago_id}/comprobante",
    response_model=ComprobanteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subir imagen de comprobante de pago, procesarlo con OCR y exponer datos extraídos (RF-12, RF-13)",
)
async def subir_comprobante_y_procesar_ocr(
    pago_id: int,
    archivo: UploadFile = File(..., description="Imagen del comprobante (JPG, PNG, WEBP)"),
    canal: str = Form(default="APP_MOVIL"),
    banco_sugerido: Optional[str] = Form(default=None),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cumple RF-12 y RF-13:
      1. Permite al padre enviar el comprobante de pago en imagen.
      2. Almacena la imagen en `/uploads/comprobantes/`.
      3. Ejecuta el motor OCR (`procesar_comprobante_ocr`) extrayendo `banco`, `monto_extraido`,
         `fecha_transferencia`, `referencia_extraida` y `ocr_confianza`.
      4. Registra el comprobante en `comprobantes`, pasa el pago a `EN_REVISION` y devuelve
         el resultado expuesto para confirmación o revisión.
    """
    pago = db.query(Pago).filter(Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Registro de pago no encontrado")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        if not pago.estudiante or pago.estudiante.representante_usuario_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede enviar comprobantes de pago de sus propios representados (RF-15).",
            )

    contenido = await archivo.read()
    if not contenido:
        raise HTTPException(status_code=400, detail="El archivo de imagen está vacío")

    ext = Path(archivo.filename or "comprobante.png").suffix.lower() or ".png"
    nombre_unico = f"pago_{pago_id}_{uuid.uuid4().hex[:10]}{ext}"
    ruta_disco = UPLOADS_DIR / nombre_unico
    ruta_disco.write_bytes(contenido)
    archivo_url = f"/uploads/comprobantes/{nombre_unico}"

    # Ejecutar Motor OCR (RF-13)
    resultado_ocr = procesar_comprobante_ocr(
        image_bytes=contenido,
        filename=archivo.filename or nombre_unico,
        monto_esperado=pago.monto,
        banco_sugerido=banco_sugerido,
    )

    canal_valido = canal.upper() if canal.upper() in ("APP_MOVIL", "WEB", "WHATSAPP", "VENTANILLA") else "APP_MOVIL"

    nuevo_comp = Comprobante(
        pago_id=pago.id,
        canal=canal_valido,
        archivo_url=archivo_url,
        banco=resultado_ocr.banco,
        monto_extraido=resultado_ocr.monto_extraido,
        fecha_transferencia=resultado_ocr.fecha_transferencia,
        referencia_extraida=resultado_ocr.referencia_extraida,
        ocr_confianza=resultado_ocr.ocr_confianza,
        estado="PENDIENTE_REVISION",
    )
    db.add(nuevo_comp)

    pago.estado = "EN_REVISION"
    pago.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(nuevo_comp)
    return _serialize_comprobante(nuevo_comp, resultado_ocr=resultado_ocr)


@router.put(
    "/comprobantes/{comprobante_id}/confirmar-datos",
    response_model=ComprobanteResponse,
    summary="Confirmar o corregir los datos extraídos por el OCR del comprobante (RF-13)",
)
def confirmar_datos_extraidos_ocr(
    comprobante_id: int,
    payload: ConfirmarDatosOcrRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    comp = db.query(Comprobante).filter(Comprobante.id == comprobante_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        if not comp.pago or not comp.pago.estudiante or comp.pago.estudiante.representante_usuario_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede confirmar comprobantes de sus representados (RF-15).",
            )

    comp.banco = payload.banco.strip().upper()
    comp.monto_extraido = payload.monto_extraido
    comp.fecha_transferencia = payload.fecha_transferencia
    comp.referencia_extraida = payload.referencia_extraida.strip().upper()

    db.commit()
    db.refresh(comp)
    return _serialize_comprobante(comp)


@router.patch(
    "/comprobantes/{comprobante_id}/revisar",
    response_model=ComprobanteResponse,
    summary="Aprobar (VALIDADO) o rechazar (RECHAZADO) un comprobante y actualizar el estado del pago (RF-13, RF-14)",
)
def revisar_y_aprobar_comprobante(
    comprobante_id: int,
    payload: RevisarComprobanteRequest,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    comp = db.query(Comprobante).filter(Comprobante.id == comprobante_id).first()
    if not comp:
        raise HTTPException(status_code=404, detail="Comprobante no encontrado")

    comp.estado = payload.estado
    pago = comp.pago
    if pago:
        if payload.estado == "VALIDADO":
            pago.estado = "PAGADO"
        elif payload.estado == "RECHAZADO":
            pago.estado = "RECHAZADO"
        else:
            pago.estado = "EN_REVISION"
        pago.updated_at = datetime.utcnow()

        # Notificar automáticamente al padre sobre el resultado de la revisión
        if pago.estudiante:
            est = pago.estudiante
            db.add(
                Notificacion(
                    usuario_id=est.representante_usuario_id,
                    titulo=f"Comprobante de pago {payload.estado}",
                    mensaje=(
                        f"El comprobante del estudiante {est.nombre} {est.apellido} "
                        f"(mes {pago.mes}/{pago.anio}) fue marcado como {payload.estado}. "
                        f"{payload.observacion or ''}".strip()
                    ),
                    tipo="REVISION_PAGO",
                    leida=0,
                )
            )

    db.commit()
    db.refresh(comp)
    return _serialize_comprobante(comp)
