"""Controlador de Instituciones Educativas, Rutas y Paradas (RF-03, RF-05, RF-15)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_user_roles, require_role
from app.models import (
    AsignacionEstudianteRuta,
    Bus,
    Conductor,
    Estudiante,
    InstitucionEducativa,
    Parada,
    Ruta,
    Usuario,
)
from app.schemas.common import EstadoActivoPatch
from app.schemas.estudiantes import AsignacionRutaResponse
from app.schemas.rutas_paradas import (
    InstitucionCreate,
    InstitucionResponse,
    InstitucionUpdate,
    ParadaCreate,
    ParadaResponse,
    ParadaUpdate,
    RutaCreate,
    RutaResponse,
    RutaUpdate,
)
from app.schemas.viajes_optimizacion import (
    OptimizarRutaRequest,
    RutaOptimizacionResponse,
)
from app.services.optimizer import optimizar_ruta_ortools

router = APIRouter(prefix="/rutas", tags=["Rutas y Paradas (RF-03, RF-05, RF-08)"])


def _serialize_parada(p: Parada) -> ParadaResponse:
    activas = [a for a in (p.asignaciones or []) if a.activa == 1]
    return ParadaResponse(
        id=p.id,
        ruta_id=p.ruta_id,
        orden=p.orden,
        nombre=p.nombre,
        geom=p.geom,
        radio_metros=p.radio_metros,
        eta_estimado=p.eta_estimado,
        total_estudiantes_asignados=len(activas),
    )


def _serialize_ruta(r: Ruta) -> RutaResponse:
    cond_user = r.conductor.usuario if r.conductor else None
    cond_nombre = f"{cond_user.nombre} {cond_user.apellido}" if cond_user else None
    asignaciones_activas = [a for a in (r.asignaciones or []) if a.activa == 1]
    paradas_ordenadas = sorted(r.paradas or [], key=lambda x: x.orden)

    return RutaResponse(
        id=r.id,
        cooperativa_id=r.cooperativa_id,
        conductor_id=r.conductor_id,
        conductor_nombre=cond_nombre,
        bus_id=r.bus_id,
        bus_placa=r.bus.placa if r.bus else None,
        bus_capacidad=r.bus.capacidad if r.bus else None,
        institucion_id=r.institucion_id,
        institucion_nombre=r.institucion.nombre if r.institucion else None,
        nombre=r.nombre,
        sector=r.sector,
        turno=r.turno,
        hora_campana=r.hora_campana,
        activa=r.activa,
        total_paradas=len(paradas_ordenadas),
        total_estudiantes=len(asignaciones_activas),
        paradas=[_serialize_parada(p) for p in paradas_ordenadas],
    )


# ============================================================================
# INSTITUCIONES EDUCATIVAS (RF-03)
# ============================================================================

@router.get(
    "/instituciones",
    response_model=List[InstitucionResponse],
    summary="Listar instituciones educativas de la cooperativa",
)
def listar_instituciones(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(InstitucionEducativa)
        .filter(InstitucionEducativa.cooperativa_id == current_user.cooperativa_id)
        .order_by(InstitucionEducativa.nombre.asc())
        .all()
    )


@router.post(
    "/instituciones",
    response_model=InstitucionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear institución educativa con coordenada geom POINT (RF-03)",
)
def crear_institucion(
    payload: InstitucionCreate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    inst = InstitucionEducativa(
        cooperativa_id=current_user.cooperativa_id,
        nombre=payload.nombre.strip(),
        direccion=payload.direccion.strip() if payload.direccion else None,
        tipo=payload.tipo,
        geom=payload.geom.model_dump() if payload.geom else None,
        activa=1,
    )
    db.add(inst)
    db.commit()
    db.refresh(inst)
    return inst


@router.put(
    "/instituciones/{institucion_id}",
    response_model=InstitucionResponse,
    summary="Actualizar institución educativa",
)
def actualizar_institucion(
    institucion_id: int,
    payload: InstitucionUpdate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    inst = (
        db.query(InstitucionEducativa)
        .filter(
            InstitucionEducativa.id == institucion_id,
            InstitucionEducativa.cooperativa_id == current_user.cooperativa_id,
        )
        .first()
    )
    if not inst:
        raise HTTPException(status_code=404, detail="Institución educativa no encontrada")

    if payload.nombre is not None:
        inst.nombre = payload.nombre.strip()
    if payload.direccion is not None:
        inst.direccion = payload.direccion.strip()
    if payload.tipo is not None:
        inst.tipo = payload.tipo
    if payload.geom is not None:
        inst.geom = payload.geom.model_dump()
    if payload.activa is not None:
        inst.activa = payload.activa

    db.commit()
    db.refresh(inst)
    return inst


# ============================================================================
# GESTIÓN DE RUTAS (RF-03, RF-15)
# ============================================================================

@router.get(
    "",
    response_model=List[RutaResponse],
    summary="Listar rutas aplicando filtro automático por rol (RF-03, RF-15)",
)
def listar_rutas(
    solo_activas: bool = Query(False),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cumple RF-03 y RF-15:
      - Si es ADMIN: ve todas las rutas de la cooperativa.
      - Si es CONDUCTOR: solo ve las rutas asignadas a su `conductor_id`.
      - Si es PADRE: solo ve las rutas donde tiene hijos/representados activos asignados.
    """
    roles = set(get_user_roles(current_user))
    query = db.query(Ruta).filter(Ruta.cooperativa_id == current_user.cooperativa_id)

    if solo_activas:
        query = query.filter(Ruta.activa == 1)

    if "ADMIN" not in roles:
        if "CONDUCTOR" in roles and current_user.conductor:
            query = query.filter(Ruta.conductor_id == current_user.conductor.id)
        elif "PADRE" in roles:
            subq_rutas_padre = (
                db.query(AsignacionEstudianteRuta.ruta_id)
                .join(Estudiante, AsignacionEstudianteRuta.estudiante_id == Estudiante.id)
                .filter(
                    Estudiante.representante_usuario_id == current_user.id,
                    AsignacionEstudianteRuta.activa == 1,
                )
            )
            query = query.filter(Ruta.id.in_(subq_rutas_padre))
        else:
            return []

    rutas = query.order_by(Ruta.id.desc()).all()
    return [_serialize_ruta(r) for r in rutas]


@router.get(
    "/{ruta_id}",
    response_model=RutaResponse,
    summary="Obtener detalle de una ruta y sus paradas ordenadas (RF-03, RF-15)",
)
def obtener_ruta(
    ruta_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ruta = (
        db.query(Ruta)
        .filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        autorizado = False
        if "CONDUCTOR" in roles and current_user.conductor and ruta.conductor_id == current_user.conductor.id:
            autorizado = True
        if "PADRE" in roles:
            tiene_hijo = (
                db.query(AsignacionEstudianteRuta)
                .join(Estudiante, AsignacionEstudianteRuta.estudiante_id == Estudiante.id)
                .filter(
                    AsignacionEstudianteRuta.ruta_id == ruta.id,
                    AsignacionEstudianteRuta.activa == 1,
                    Estudiante.representante_usuario_id == current_user.id,
                )
                .first()
            )
            if tiene_hijo:
                autorizado = True
        if not autorizado:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="No tiene permiso para acceder a esta ruta (RF-15).",
            )

    return _serialize_ruta(ruta)


@router.post(
    "",
    response_model=RutaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear una ruta y asignar conductor y bus responsable (RF-03)",
)
def crear_ruta(
    payload: RutaCreate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    if not db.query(Conductor).filter(Conductor.id == payload.conductor_id, Conductor.activo == 1).first():
        raise HTTPException(status_code=404, detail="El conductor seleccionado no existe o está inactivo")
    if not db.query(Bus).filter(Bus.id == payload.bus_id, Bus.activo == 1).first():
        raise HTTPException(status_code=404, detail="El bus seleccionado no existe o está inactivo")
    if not db.query(InstitucionEducativa).filter(InstitucionEducativa.id == payload.institucion_id).first():
        raise HTTPException(status_code=404, detail="La institución educativa no existe")

    nueva_ruta = Ruta(
        cooperativa_id=current_user.cooperativa_id,
        conductor_id=payload.conductor_id,
        bus_id=payload.bus_id,
        institucion_id=payload.institucion_id,
        nombre=payload.nombre.strip(),
        sector=payload.sector.strip() if payload.sector else None,
        turno=payload.turno,
        hora_campana=payload.hora_campana,
        activa=1,
    )
    db.add(nueva_ruta)
    db.commit()
    db.refresh(nueva_ruta)
    return _serialize_ruta(nueva_ruta)


@router.put(
    "/{ruta_id}",
    response_model=RutaResponse,
    summary="Actualizar ruta o reasignar conductor/bus responsable (RF-03)",
)
def actualizar_ruta(
    ruta_id: int,
    payload: RutaUpdate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    ruta = (
        db.query(Ruta)
        .filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    if payload.conductor_id is not None:
        if not db.query(Conductor).filter(Conductor.id == payload.conductor_id).first():
            raise HTTPException(status_code=404, detail="Conductor no encontrado")
        ruta.conductor_id = payload.conductor_id

    if payload.bus_id is not None:
        if not db.query(Bus).filter(Bus.id == payload.bus_id).first():
            raise HTTPException(status_code=404, detail="Bus no encontrado")
        ruta.bus_id = payload.bus_id

    if payload.institucion_id is not None:
        if not db.query(InstitucionEducativa).filter(InstitucionEducativa.id == payload.institucion_id).first():
            raise HTTPException(status_code=404, detail="Institución educativa no encontrada")
        ruta.institucion_id = payload.institucion_id

    if payload.nombre is not None:
        ruta.nombre = payload.nombre.strip()
    if payload.sector is not None:
        ruta.sector = payload.sector.strip()
    if payload.turno is not None:
        ruta.turno = payload.turno
    if payload.hora_campana is not None:
        ruta.hora_campana = payload.hora_campana
    if payload.activa is not None:
        ruta.activa = payload.activa

    db.commit()
    db.refresh(ruta)
    return _serialize_ruta(ruta)


@router.patch(
    "/{ruta_id}/estado",
    response_model=RutaResponse,
    summary="Activar o desactivar una ruta (RF-03)",
)
def cambiar_estado_ruta(
    ruta_id: int,
    payload: EstadoActivoPatch,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id).first()
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")
    ruta.activa = payload.activo
    db.commit()
    db.refresh(ruta)
    return _serialize_ruta(ruta)


# ============================================================================
# GESTIÓN DE PARADAS DE UNA RUTA (RF-03, RF-11)
# ============================================================================

@router.get(
    "/{ruta_id}/paradas",
    response_model=List[ParadaResponse],
    summary="Listar paradas de una ruta en orden de recorrido",
)
def listar_paradas_ruta(
    ruta_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    paradas = (
        db.query(Parada)
        .filter(Parada.ruta_id == ruta_id)
        .order_by(Parada.orden.asc())
        .all()
    )
    return [_serialize_parada(p) for p in paradas]


@router.post(
    "/{ruta_id}/paradas",
    response_model=ParadaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Agregar una parada georreferenciada (POINT y radio_metros) a la ruta (RF-03, RF-11)",
)
def crear_parada(
    ruta_id: int,
    payload: ParadaCreate,
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id).first()
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    parada = Parada(
        ruta_id=ruta_id,
        nombre=payload.nombre.strip(),
        orden=payload.orden,
        geom=payload.geom.model_dump(),
        radio_metros=payload.radio_metros,
        eta_estimado=payload.eta_estimado,
    )
    db.add(parada)
    db.commit()
    db.refresh(parada)
    return _serialize_parada(parada)


@router.put(
    "/paradas/{parada_id}",
    response_model=ParadaResponse,
    summary="Actualizar parada (nombre, orden, geom, radio_metros o ETA)",
)
def actualizar_parada(
    parada_id: int,
    payload: ParadaUpdate,
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    parada = db.query(Parada).filter(Parada.id == parada_id).first()
    if not parada:
        raise HTTPException(status_code=404, detail="Parada no encontrada")

    if payload.nombre is not None:
        parada.nombre = payload.nombre.strip()
    if payload.orden is not None:
        parada.orden = payload.orden
    if payload.geom is not None:
        parada.geom = payload.geom.model_dump()
    if payload.radio_metros is not None:
        parada.radio_metros = payload.radio_metros
    if payload.eta_estimado is not None:
        parada.eta_estimado = payload.eta_estimado

    db.commit()
    db.refresh(parada)
    return _serialize_parada(parada)


@router.delete(
    "/paradas/{parada_id}",
    summary="Eliminar una parada si no tiene asignaciones activas",
)
def eliminar_parada(
    parada_id: int,
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    parada = db.query(Parada).filter(Parada.id == parada_id).first()
    if not parada:
        raise HTTPException(status_code=404, detail="Parada no encontrada")

    tiene_estudiantes = (
        db.query(AsignacionEstudianteRuta)
        .filter(AsignacionEstudianteRuta.parada_id == parada_id, AsignacionEstudianteRuta.activa == 1)
        .first()
    )
    if tiene_estudiantes:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No se puede eliminar la parada porque tiene estudiantes activos asignados.",
        )

    db.delete(parada)
    db.commit()
    return {"mensaje": "Parada eliminada correctamente"}


# ============================================================================
# CONSULTA DE ESTUDIANTES POR RUTA (RF-05, RF-07, RF-15)
# ============================================================================

@router.get(
    "/{ruta_id}/estudiantes",
    response_model=List[AsignacionRutaResponse],
    summary="Consultar todos los estudiantes asignados a una ruta ordenados por parada (RF-05)",
)
def consultar_estudiantes_por_ruta(
    ruta_id: int,
    solo_activos: bool = Query(True),
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    ruta = db.query(Ruta).filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id).first()
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles and "CONDUCTOR" in roles:
        if not current_user.conductor or ruta.conductor_id != current_user.conductor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede consultar los estudiantes de su propia ruta asignada (RF-15).",
            )

    query = (
        db.query(AsignacionEstudianteRuta)
        .join(Parada, AsignacionEstudianteRuta.parada_id == Parada.id)
        .join(Estudiante, AsignacionEstudianteRuta.estudiante_id == Estudiante.id)
        .filter(AsignacionEstudianteRuta.ruta_id == ruta_id)
    )
    if solo_activos:
        query = query.filter(AsignacionEstudianteRuta.activa == 1, Estudiante.activo == 1)

    asignaciones = query.order_by(Parada.orden.asc(), Estudiante.apellido.asc()).all()
    resultado = []
    for a in asignaciones:
        est = a.estudiante
        rep = est.representante if est else None
        par = a.parada
        resultado.append(
            AsignacionRutaResponse(
                id=a.id,
                estudiante_id=a.estudiante_id,
                estudiante_nombre_completo=f"{est.nombre} {est.apellido}" if est else None,
                estudiante_cedula=est.cedula if est else None,
                estudiante_grado=est.grado if est else None,
                representante_nombre=f"{rep.nombre} {rep.apellido}" if rep else None,
                representante_telefono=rep.telefono if rep else None,
                ruta_id=a.ruta_id,
                ruta_nombre=ruta.nombre,
                parada_id=a.parada_id,
                parada_nombre=par.nombre if par else None,
                parada_orden=par.orden if par else None,
                parada_geom=par.geom if par else None,
                parada_eta=par.eta_estimado if par else None,
                activa=a.activa,
            )
        )
    return resultado


# ============================================================================
# OPTIMIZACIÓN MATEMÁTICA DE RUTA CON GOOGLE OR-TOOLS (RF-08)
# ============================================================================

@router.post(
    "/{ruta_id}/optimizar",
    response_model=RutaOptimizacionResponse,
    summary="Generar ruta optimizada del recorrido con Google OR-Tools considerando paradas activas (RF-08)",
)
def optimizar_recorrido_ruta(
    ruta_id: int,
    payload: Optional[OptimizarRutaRequest] = None,
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    """
    Cumple RF-08:
      - Ejecuta Google OR-Tools sobre las paradas activas de la ruta (excluyendo aquellas cuyos
        estudiantes reportaron ausencia en el `viaje_id` indicado).
      - Reordena `paradas.orden`, recalcula `paradas.eta_estimado` y devuelve la polilínea óptima.
    """
    ruta = (
        db.query(Ruta)
        .filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles and "CONDUCTOR" in roles:
        if not current_user.conductor or ruta.conductor_id != current_user.conductor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede optimizar su propia ruta asignada (RF-15).",
            )

    req = payload or OptimizarRutaRequest()
    return optimizar_ruta_ortools(
        db=db,
        ruta=ruta,
        viaje_id=req.viaje_id,
        velocidad_promedio_kmh=req.velocidad_promedio_kmh,
    )
