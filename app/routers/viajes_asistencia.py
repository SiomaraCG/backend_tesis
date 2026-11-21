"""Controlador de Viajes Diarios, Hoja de Ruta del Conductor, Asistencia y Ausencias (RF-07, RF-15)."""
from datetime import date, datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    get_current_conductor,
    get_current_user,
    get_user_roles,
    require_role,
)
from app.models import (
    AsignacionEstudianteRuta,
    AusenciaEstudiante,
    Conductor,
    Estudiante,
    NovedadViaje,
    Parada,
    Ruta,
    Usuario,
    Viaje,
)
from app.schemas.viajes_optimizacion import (
    EstudianteHojaRutaResponse,
    IniciarViajeRequest,
    NovedadViajeCreate,
    NovedadViajeResponse,
    RegistrarAsistenciaRequest,
    ReportarAusenciaRequest,
    ViajeResponse,
)

router = APIRouter(prefix="/viajes", tags=["Viajes y Asistencia (RF-07)"])


def _serialize_viaje(v: Viaje) -> ViajeResponse:
    ruta = v.ruta
    cond_user = v.conductor.usuario if v.conductor else None
    cond_nombre = f"{cond_user.nombre} {cond_user.apellido}" if cond_user else None

    total_est = 0
    if ruta and ruta.asignaciones:
        total_est = len([a for a in ruta.asignaciones if a.activa == 1])

    ausencias = [
        a
        for a in (v.ausencias or [])
        if a.estado in ("REPORTADA", "CONFIRMADA")
    ]
    recogidos = [
        a for a in (v.ausencias or []) if a.estado == "RECOGIDO"
    ]

    return ViajeResponse(
        id=v.id,
        ruta_id=v.ruta_id,
        ruta_nombre=ruta.nombre if ruta else None,
        turno=ruta.turno if ruta else None,
        conductor_id=v.conductor_id,
        conductor_nombre=cond_nombre,
        bus_id=v.bus_id,
        bus_placa=v.bus.placa if v.bus else None,
        fecha=v.fecha,
        estado=v.estado,
        inicio_at=v.inicio_at,
        fin_at=v.fin_at,
        total_estudiantes_ruta=total_est,
        total_ausencias_hoy=len(ausencias),
        total_recogidos_hoy=len(recogidos),
    )


@router.get(
    "",
    response_model=List[ViajeResponse],
    summary="Listar viajes diarios aplicando filtro por rol (RF-07, RF-15)",
)
def listar_viajes(
    ruta_id: Optional[int] = Query(None),
    fecha: Optional[date] = Query(None),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    roles = set(get_user_roles(current_user))
    query = (
        db.query(Viaje)
        .join(Ruta, Viaje.ruta_id == Ruta.id)
        .filter(Ruta.cooperativa_id == current_user.cooperativa_id)
    )

    if ruta_id is not None:
        query = query.filter(Viaje.ruta_id == ruta_id)
    if fecha is not None:
        query = query.filter(Viaje.fecha == fecha)

    if "ADMIN" not in roles:
        if "CONDUCTOR" in roles and current_user.conductor:
            query = query.filter(Viaje.conductor_id == current_user.conductor.id)
        elif "PADRE" in roles:
            subq_rutas = (
                db.query(AsignacionEstudianteRuta.ruta_id)
                .join(Estudiante, AsignacionEstudianteRuta.estudiante_id == Estudiante.id)
                .filter(
                    Estudiante.representante_usuario_id == current_user.id,
                    AsignacionEstudianteRuta.activa == 1,
                )
            )
            query = query.filter(Viaje.ruta_id.in_(subq_rutas))
        else:
            return []

    viajes = query.order_by(Viaje.fecha.desc(), Viaje.id.desc()).all()
    return [_serialize_viaje(v) for v in viajes]


@router.post(
    "/iniciar",
    response_model=ViajeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Iniciar el viaje del día para una ruta (RF-07, RF-09)",
)
def iniciar_viaje(
    payload: IniciarViajeRequest,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    ruta = (
        db.query(Ruta)
        .filter(
            Ruta.id == payload.ruta_id,
            Ruta.cooperativa_id == current_user.cooperativa_id,
            Ruta.activa == 1,
        )
        .first()
    )
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada o inactiva")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        if not current_user.conductor or ruta.conductor_id != current_user.conductor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el conductor responsable de esta ruta puede iniciar el viaje (RF-15).",
            )

    fecha_viaje = payload.fecha or date.today()
    viaje_existente = (
        db.query(Viaje)
        .filter(
            Viaje.ruta_id == ruta.id,
            Viaje.fecha == fecha_viaje,
            Viaje.estado.in_(["PROGRAMADO", "EN_CURSO"]),
        )
        .first()
    )
    if viaje_existente:
        viaje_existente.estado = "EN_CURSO"
        if not viaje_existente.inicio_at:
            viaje_existente.inicio_at = datetime.utcnow()
        db.commit()
        db.refresh(viaje_existente)
        return _serialize_viaje(viaje_existente)

    nuevo_viaje = Viaje(
        ruta_id=ruta.id,
        conductor_id=ruta.conductor_id,
        bus_id=ruta.bus_id,
        fecha=fecha_viaje,
        estado="EN_CURSO",
        inicio_at=datetime.utcnow(),
    )
    db.add(nuevo_viaje)
    db.commit()
    db.refresh(nuevo_viaje)
    return _serialize_viaje(nuevo_viaje)


@router.get(
    "/conductor/mi-ruta/estudiantes",
    response_model=List[EstudianteHojaRutaResponse],
    summary="Consultar los estudiantes de la ruta del conductor y su estado de asistencia del día (RF-07)",
)
@router.get(
    "/conductor/mi-ruta-hoy",
    response_model=List[EstudianteHojaRutaResponse],
    include_in_schema=False,
)
def consultar_hoja_ruta_conductor(
    ruta_id: Optional[int] = Query(None, description="ID de ruta opcional si el conductor tiene más de una"),
    fecha: Optional[date] = Query(None),
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Cumple RF-07 y RF-15:
      - Obtiene la ruta asignada al conductor autenticado.
      - Devuelve la lista de estudiantes ordenada por `paradas.orden`, incluyendo el estado
        de recogida o ausencia en el viaje del día (`PENDIENTE`, `RECOGIDO`, `AUSENCIA_PREVIA`, `NO_ASISTIO`).
    """
    roles = set(get_user_roles(current_user))
    if ruta_id is not None:
        ruta = db.query(Ruta).filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id).first()
    else:
        if not current_user.conductor:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Debe especificar `ruta_id` o iniciar sesión con una cuenta de conductor.",
            )
        ruta = (
            db.query(Ruta)
            .filter(Ruta.conductor_id == current_user.conductor.id, Ruta.activa == 1)
            .first()
        )

    if not ruta:
        raise HTTPException(status_code=404, detail="No se encontró una ruta activa asignada.")

    if "ADMIN" not in roles:
        if not current_user.conductor or ruta.conductor_id != current_user.conductor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede consultar los estudiantes de su propia ruta (RF-15).",
            )

    fecha_consulta = fecha or date.today()
    viaje_hoy = (
        db.query(Viaje)
        .filter(Viaje.ruta_id == ruta.id, Viaje.fecha == fecha_consulta)
        .order_by(Viaje.id.desc())
        .first()
    )

    mapa_estados = {}
    mapa_motivos = {}
    if viaje_hoy:
        for reg in viaje_hoy.ausencias or []:
            if reg.estado == "RECOGIDO":
                mapa_estados[reg.estudiante_id] = "RECOGIDO"
            elif reg.estado == "CONFIRMADA":
                mapa_estados[reg.estudiante_id] = "NO_ASISTIO"
            elif reg.estado == "REPORTADA":
                mapa_estados[reg.estudiante_id] = "AUSENCIA_PREVIA"
            mapa_motivos[reg.estudiante_id] = reg.motivo_padre

    asignaciones = (
        db.query(AsignacionEstudianteRuta)
        .join(Parada, AsignacionEstudianteRuta.parada_id == Parada.id)
        .join(Estudiante, AsignacionEstudianteRuta.estudiante_id == Estudiante.id)
        .filter(
            AsignacionEstudianteRuta.ruta_id == ruta.id,
            AsignacionEstudianteRuta.activa == 1,
            Estudiante.activo == 1,
        )
        .order_by(Parada.orden.asc(), Estudiante.apellido.asc())
        .all()
    )

    hoja: List[EstudianteHojaRutaResponse] = []
    for a in asignaciones:
        est = a.estudiante
        rep = est.representante if est else None
        par = a.parada
        hoja.append(
            EstudianteHojaRutaResponse(
                estudiante_id=est.id,
                estudiante_nombre_completo=f"{est.nombre} {est.apellido}",
                cedula=est.cedula,
                grado=est.grado,
                representante_nombre=f"{rep.nombre} {rep.apellido}" if rep else None,
                representante_telefono=rep.telefono if rep else None,
                parada_id=par.id,
                parada_nombre=par.nombre,
                parada_orden=par.orden,
                parada_geom=par.geom,
                parada_eta=par.eta_estimado,
                estado_hoy=mapa_estados.get(est.id, "PENDIENTE"),
                motivo_ausencia=mapa_motivos.get(est.id),
            )
        )
    return hoja


@router.post(
    "/{viaje_id}/ausencias",
    summary="Reportar ausencia previa de un estudiante para el viaje del día (RF-07, RF-08, RF-15)",
)
def reportar_ausencia_estudiante(
    viaje_id: int,
    payload: ReportarAusenciaRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    viaje = db.query(Viaje).filter(Viaje.id == viaje_id).first()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    est = db.query(Estudiante).filter(Estudiante.id == payload.estudiante_id).first()
    if not est:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles and "CONDUCTOR" not in roles:
        if est.representante_usuario_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede reportar ausencias de sus propios representados (RF-15).",
            )

    # Calcular anticipación en minutos respecto a la hora campana
    anticipacion_min = 60
    if viaje.ruta and viaje.ruta.hora_campana:
        dt_campana = datetime.combine(viaje.fecha, viaje.ruta.hora_campana)
        diff = (dt_campana - datetime.now()).total_seconds() / 60.0
        anticipacion_min = max(0, int(round(diff)))

    politica = "ANTICIPACION_VALIDA" if anticipacion_min >= 30 else "ULTIMO_MINUTO"

    registro = (
        db.query(AusenciaEstudiante)
        .filter(
            AusenciaEstudiante.viaje_id == viaje_id,
            AusenciaEstudiante.estudiante_id == payload.estudiante_id,
        )
        .first()
    )
    if registro:
        registro.estado = "REPORTADA"
        registro.motivo_padre = payload.motivo_padre.strip()
        registro.anticipacion_min = anticipacion_min
        registro.politica_aplicada = politica
    else:
        registro = AusenciaEstudiante(
            viaje_id=viaje_id,
            estudiante_id=payload.estudiante_id,
            anticipacion_min=anticipacion_min,
            politica_aplicada=politica,
            estado="REPORTADA",
            motivo_padre=payload.motivo_padre.strip(),
        )
        db.add(registro)

    db.commit()
    db.refresh(registro)
    return {
        "mensaje": "Ausencia registrada exitosamente",
        "ausencia_id": registro.id,
        "estudiante_id": registro.estudiante_id,
        "estado": registro.estado,
        "anticipacion_min": registro.anticipacion_min,
        "politica_aplicada": registro.politica_aplicada,
    }


@router.post(
    "/{viaje_id}/asistencia",
    summary="Registrar asistencia/recogida o inasistencia del estudiante por parte del conductor (RF-07)",
)
def registrar_asistencia_conductor(
    viaje_id: int,
    payload: RegistrarAsistenciaRequest,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    viaje = db.query(Viaje).filter(Viaje.id == viaje_id).first()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        if not current_user.conductor or viaje.conductor_id != current_user.conductor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el conductor asignado a este viaje puede registrar asistencia (RF-15).",
            )

    est = db.query(Estudiante).filter(Estudiante.id == payload.estudiante_id).first()
    if not est:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    estado_bd = "RECOGIDO" if payload.estado_asistencia in ("RECOGIDO", "PRESENTE") else "CONFIRMADA"

    registro = (
        db.query(AusenciaEstudiante)
        .filter(
            AusenciaEstudiante.viaje_id == viaje_id,
            AusenciaEstudiante.estudiante_id == payload.estudiante_id,
        )
        .first()
    )
    if registro:
        registro.estado = estado_bd
        if payload.observacion:
            registro.motivo_padre = payload.observacion.strip()
        registro.responded_at = datetime.utcnow()
        registro.responded_by_usuario_id = current_user.id
    else:
        registro = AusenciaEstudiante(
            viaje_id=viaje_id,
            estudiante_id=payload.estudiante_id,
            anticipacion_min=0,
            politica_aplicada="REGISTRO_CONDUCTOR_EN_PARADA",
            estado=estado_bd,
            motivo_padre=payload.observacion.strip() if payload.observacion else f"Marcado como {payload.estado_asistencia} por el conductor",
            responded_at=datetime.utcnow(),
            responded_by_usuario_id=current_user.id,
        )
        db.add(registro)

    # Registrar trazabilidad en novedades_viaje (tipo = 'ASISTENCIA')
    novedad = NovedadViaje(
        viaje_id=viaje_id,
        reportado_por_usuario_id=current_user.id,
        tipo="ASISTENCIA",
        descripcion=(
            f"Estudiante {est.nombre} {est.apellido} ({est.cedula}): "
            f"{payload.estado_asistencia}. {payload.observacion or ''}".strip()
        ),
        estado="RESUELTO",
        ocurrido_at=datetime.utcnow(),
        resuelto_at=datetime.utcnow(),
        ubicacion=payload.ubicacion.model_dump() if payload.ubicacion else None,
    )
    db.add(novedad)

    db.commit()
    return {
        "mensaje": f"Asistencia registrada como {payload.estado_asistencia}",
        "viaje_id": viaje_id,
        "estudiante_id": est.id,
        "estudiante_nombre": f"{est.nombre} {est.apellido}",
        "estado_asistencia": payload.estado_asistencia,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.post(
    "/{viaje_id}/novedades",
    response_model=NovedadViajeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Reportar novedad o incidente durante el viaje (tráfico, avería, retraso)",
)
def crear_novedad_viaje(
    viaje_id: int,
    payload: NovedadViajeCreate,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    viaje = db.query(Viaje).filter(Viaje.id == viaje_id).first()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    nov = NovedadViaje(
        viaje_id=viaje_id,
        reportado_por_usuario_id=current_user.id,
        tipo=payload.tipo,
        descripcion=payload.descripcion.strip(),
        estado="ABIERTO",
        ocurrido_at=datetime.utcnow(),
        ubicacion=payload.ubicacion.model_dump() if payload.ubicacion else None,
    )
    db.add(nov)
    db.commit()
    db.refresh(nov)
    return nov


@router.get(
    "/{viaje_id}/novedades",
    response_model=List[NovedadViajeResponse],
    summary="Consultar novedades registradas en un viaje",
)
def listar_novedades_viaje(
    viaje_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(NovedadViaje)
        .filter(NovedadViaje.viaje_id == viaje_id)
        .order_by(NovedadViaje.ocurrido_at.desc())
        .all()
    )


@router.post(
    "/{viaje_id}/finalizar",
    response_model=ViajeResponse,
    summary="Finalizar el recorrido del día (RF-07, RF-09)",
)
def finalizar_viaje(
    viaje_id: int,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    viaje = db.query(Viaje).filter(Viaje.id == viaje_id).first()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        if not current_user.conductor or viaje.conductor_id != current_user.conductor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el conductor responsable puede finalizar este viaje (RF-15).",
            )

    viaje.estado = "FINALIZADO"
    viaje.fin_at = datetime.utcnow()
    db.commit()
    db.refresh(viaje)
    return _serialize_viaje(viaje)
