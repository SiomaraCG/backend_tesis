"""Controlador de Estudiantes, Representantes (Padres), Tarifas y Asignaciones a Rutas (RF-04, RF-05, RF-15)."""
from datetime import date
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, get_user_roles, require_role
from app.core.security import get_password_hash
from app.models import (
    AsignacionEstudianteRuta,
    Estudiante,
    Parada,
    Rol,
    Ruta,
    TarifaEstudiante,
    Usuario,
    UsuarioRol,
)
from app.schemas.common import EstadoActivoPatch
from app.schemas.estudiantes import (
    AsignacionRutaCreate,
    AsignacionRutaResponse,
    EstudianteCreate,
    EstudianteResponse,
    EstudianteUpdate,
    PadreCreate,
    PadreResponse,
    RegistroPadreEstudianteCreate,
    RegistroPadreEstudianteResponse,
    TarifaCreate,
    TarifaResponse,
)

router = APIRouter(prefix="/estudiantes", tags=["Estudiantes y Representantes (RF-04, RF-05)"])


def _serialize_asignacion(a: AsignacionEstudianteRuta) -> AsignacionRutaResponse:
    est = a.estudiante
    rep = est.representante if est else None
    par = a.parada
    ruta = a.ruta
    return AsignacionRutaResponse(
        id=a.id,
        estudiante_id=a.estudiante_id,
        estudiante_nombre_completo=f"{est.nombre} {est.apellido}" if est else None,
        estudiante_cedula=est.cedula if est else None,
        estudiante_grado=est.grado if est else None,
        representante_nombre=f"{rep.nombre} {rep.apellido}" if rep else None,
        representante_telefono=rep.telefono if rep else None,
        ruta_id=a.ruta_id,
        ruta_nombre=ruta.nombre if ruta else None,
        parada_id=a.parada_id,
        parada_nombre=par.nombre if par else None,
        parada_orden=par.orden if par else None,
        parada_geom=par.geom if par else None,
        parada_eta=par.eta_estimado if par else None,
        activa=a.activa,
    )


def _serialize_estudiante(est: Estudiante) -> EstudianteResponse:
    rep = est.representante
    tarifa_vigente = None
    if est.tarifas:
        ordenadas = sorted(est.tarifas, key=lambda t: t.vigente_desde, reverse=True)
        tarifa_vigente = ordenadas[0].monto_mensual

    asignaciones_activas = [
        _serialize_asignacion(a) for a in (est.asignaciones or []) if a.activa == 1
    ]

    return EstudianteResponse(
        id=est.id,
        representante_usuario_id=est.representante_usuario_id,
        representante_nombre=f"{rep.nombre} {rep.apellido}" if rep else None,
        representante_cedula=rep.cedula if rep else None,
        representante_telefono=rep.telefono if rep else None,
        representante_email=rep.email if rep else None,
        cedula=est.cedula,
        nombre=est.nombre,
        apellido=est.apellido,
        grado=est.grado,
        activo=est.activo,
        domicilio_geom=est.domicilio_geom,
        domicilio_direccion=est.domicilio_direccion,
        tarifa_actual=tarifa_vigente,
        asignaciones_activas=asignaciones_activas,
    )


# ============================================================================
# GESTIÓN DE PADRES / REPRESENTANTES LEGALES (RF-04: Registrados por CONDUCTOR o ADMIN)
# ============================================================================

@router.get(
    "/padres",
    response_model=List[PadreResponse],
    summary="Listar padres/representantes registrados en la cooperativa (RF-04)",
)
def listar_padres(
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    padres = (
        db.query(Usuario)
        .join(UsuarioRol, Usuario.id == UsuarioRol.usuario_id)
        .join(Rol, UsuarioRol.rol_id == Rol.id)
        .filter(
            Usuario.cooperativa_id == current_user.cooperativa_id,
            Rol.nombre == "PADRE",
        )
        .order_by(Usuario.apellido.asc())
        .all()
    )
    return [
        PadreResponse(
            id=p.id,
            email=p.email,
            nombre=p.nombre,
            apellido=p.apellido,
            cedula=p.cedula,
            telefono=p.telefono,
            activo=p.activo,
            total_representados=len(p.estudiantes_representados or []),
        )
        for p in padres
    ]


@router.post(
    "/padres",
    response_model=PadreResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un nuevo padre/representante por parte del CONDUCTOR o ADMIN (RF-04)",
)
def crear_padre(
    payload: PadreCreate,
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    existente = (
        db.query(Usuario)
        .filter(
            or_(
                Usuario.email == payload.email.strip(),
                Usuario.cedula == payload.cedula.strip(),
            )
        )
        .first()
    )
    if existente:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario con ese correo electrónico o número de cédula.",
        )

    rol_padre = db.query(Rol).filter(Rol.nombre == "PADRE").first()
    if not rol_padre:
        rol_padre = Rol(nombre="PADRE", descripcion="Padre de familia o representante legal")
        db.add(rol_padre)
        db.flush()

    nuevo_padre = Usuario(
        cooperativa_id=current_user.cooperativa_id,
        email=payload.email.strip(),
        password_hash=get_password_hash(payload.password),
        nombre=payload.nombre.strip(),
        apellido=payload.apellido.strip(),
        cedula=payload.cedula.strip(),
        telefono=payload.telefono.strip() if payload.telefono else None,
        activo=1,
    )
    db.add(nuevo_padre)
    db.flush()
    db.add(UsuarioRol(usuario_id=nuevo_padre.id, rol_id=rol_padre.id))
    db.commit()
    db.refresh(nuevo_padre)

    return PadreResponse(
        id=nuevo_padre.id,
        email=nuevo_padre.email,
        nombre=nuevo_padre.nombre,
        apellido=nuevo_padre.apellido,
        cedula=nuevo_padre.cedula,
        telefono=nuevo_padre.telefono,
        activo=nuevo_padre.activo,
        total_representados=0,
    )


@router.post(
    "/registrar-padre-y-estudiante",
    response_model=RegistroPadreEstudianteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="El CONDUCTOR (o ADMIN) registra en un solo paso al Padre de Familia y al Estudiante en su ruta (RF-04)",
)
def registrar_padre_y_estudiante(
    payload: RegistroPadreEstudianteCreate,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    Flujo jerárquico donde el CONDUCTOR registra al Padre de Familia y al Estudiante:
      1. Crea al Padre con rol `PADRE` (o lo reutiliza si ya está registrado con esa cédula/correo).
      2. Crea al Estudiante vinculado al Padre con su tarifa mensual.
      3. Si el usuario es CONDUCTOR (o envía `ruta_id`), crea su parada de recogida con `domicilio_geom`
         y lo asigna automáticamente a la ruta del conductor.
    """
    if db.query(Estudiante).filter(Estudiante.cedula == payload.estudiante.cedula.strip()).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un estudiante registrado con la cédula '{payload.estudiante.cedula.strip()}' (RF-04).",
        )

    # 1. Obtener o crear al Padre de Familia
    padre_user = (
        db.query(Usuario)
        .filter(
            or_(
                Usuario.cedula == payload.padre.cedula.strip(),
                Usuario.email == payload.padre.email.strip(),
            )
        )
        .first()
    )
    rol_padre = db.query(Rol).filter(Rol.nombre == "PADRE").first()
    if not rol_padre:
        rol_padre = Rol(nombre="PADRE", descripcion="Padre de familia o representante legal")
        db.add(rol_padre)
        db.flush()

    if not padre_user:
        padre_user = Usuario(
            cooperativa_id=current_user.cooperativa_id,
            email=payload.padre.email.strip(),
            password_hash=get_password_hash(payload.padre.password),
            nombre=payload.padre.nombre.strip(),
            apellido=payload.padre.apellido.strip(),
            cedula=payload.padre.cedula.strip(),
            telefono=payload.padre.telefono.strip() if payload.padre.telefono else None,
            activo=1,
        )
        db.add(padre_user)
        db.flush()
        db.add(UsuarioRol(usuario_id=padre_user.id, rol_id=rol_padre.id))
    else:
        tiene_rol = (
            db.query(UsuarioRol)
            .filter(UsuarioRol.usuario_id == padre_user.id, UsuarioRol.rol_id == rol_padre.id)
            .first()
        )
        if not tiene_rol:
            db.add(UsuarioRol(usuario_id=padre_user.id, rol_id=rol_padre.id))

    # 2. Crear al Estudiante
    est_in = payload.estudiante
    nuevo_est = Estudiante(
        representante_usuario_id=padre_user.id,
        cedula=est_in.cedula.strip(),
        nombre=est_in.nombre.strip(),
        apellido=est_in.apellido.strip(),
        grado=est_in.grado.strip() if est_in.grado else None,
        activo=1,
        domicilio_geom=est_in.domicilio_geom.model_dump() if est_in.domicilio_geom else None,
        domicilio_direccion=est_in.domicilio_direccion.strip() if est_in.domicilio_direccion else None,
    )
    db.add(nuevo_est)
    db.flush()

    if est_in.monto_mensual_inicial is not None:
        db.add(
            TarifaEstudiante(
                estudiante_id=nuevo_est.id,
                monto_mensual=est_in.monto_mensual_inicial,
                vigente_desde=date.today(),
                observacion="Tarifa inicial registrada por el conductor",
            )
        )

    # 3. Determinar ruta del conductor y asignar parada automáticamente
    ruta_destino: Optional[Ruta] = None
    if payload.ruta_id is not None:
        ruta_destino = db.query(Ruta).filter(Ruta.id == payload.ruta_id, Ruta.activa == 1).first()
    elif current_user.conductor:
        ruta_destino = (
            db.query(Ruta)
            .filter(Ruta.conductor_id == current_user.conductor.id, Ruta.activa == 1)
            .first()
        )

    if ruta_destino:
        parada_id_final = payload.parada_id
        if parada_id_final is None and est_in.domicilio_geom is not None:
            total_paradas = db.query(Parada).filter(Parada.ruta_id == ruta_destino.id).count()
            nueva_parada = Parada(
                ruta_id=ruta_destino.id,
                nombre=est_in.domicilio_direccion or f"Parada {nuevo_est.nombre} {nuevo_est.apellido}",
                orden=total_paradas + 1,
                geom=est_in.domicilio_geom.model_dump(),
                radio_metros=80,
            )
            db.add(nueva_parada)
            db.flush()
            parada_id_final = nueva_parada.id
        elif parada_id_final is None:
            primera_parada = (
                db.query(Parada)
                .filter(Parada.ruta_id == ruta_destino.id)
                .order_by(Parada.orden.asc())
                .first()
            )
            if primera_parada:
                parada_id_final = primera_parada.id

        if parada_id_final is not None:
            db.add(
                AsignacionEstudianteRuta(
                    estudiante_id=nuevo_est.id,
                    ruta_id=ruta_destino.id,
                    parada_id=parada_id_final,
                    activa=1,
                )
            )

    db.commit()
    db.refresh(padre_user)
    db.refresh(nuevo_est)

    return RegistroPadreEstudianteResponse(
        padre=PadreResponse(
            id=padre_user.id,
            email=padre_user.email,
            nombre=padre_user.nombre,
            apellido=padre_user.apellido,
            cedula=padre_user.cedula,
            telefono=padre_user.telefono,
            activo=padre_user.activo,
            total_representados=len(padre_user.estudiantes_representados or []),
        ),
        estudiante=_serialize_estudiante(nuevo_est),
    )


# ============================================================================
# GESTIÓN DE ESTUDIANTES (RF-04, RF-05, RF-15)
# ============================================================================

@router.get(
    "",
    response_model=List[EstudianteResponse],
    summary="Listar estudiantes respetando aislamiento por rol (RF-04, RF-05, RF-15)",
)
def listar_estudiantes(
    ruta_id: Optional[int] = Query(None, description="Filtrar estudiantes por ruta (RF-05)"),
    solo_activos: bool = Query(False),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Cumple RF-04, RF-05 y RF-15:
      - ADMIN: puede consultar todos los estudiantes o filtrar por `ruta_id`.
      - PADRE: únicamente ve a sus hijos (`representante_usuario_id == current_user.id`).
      - CONDUCTOR: únicamente ve a los estudiantes asignados a su ruta.
    """
    roles = set(get_user_roles(current_user))
    query = (
        db.query(Estudiante)
        .join(Usuario, Estudiante.representante_usuario_id == Usuario.id)
        .filter(Usuario.cooperativa_id == current_user.cooperativa_id)
    )

    if solo_activos:
        query = query.filter(Estudiante.activo == 1)

    if ruta_id is not None:
        query = query.join(
            AsignacionEstudianteRuta,
            AsignacionEstudianteRuta.estudiante_id == Estudiante.id,
        ).filter(
            AsignacionEstudianteRuta.ruta_id == ruta_id,
            AsignacionEstudianteRuta.activa == 1,
        )

    if "ADMIN" not in roles:
        if "PADRE" in roles:
            query = query.filter(Estudiante.representante_usuario_id == current_user.id)
        elif "CONDUCTOR" in roles and current_user.conductor:
            subq_est = (
                db.query(AsignacionEstudianteRuta.estudiante_id)
                .join(Ruta, AsignacionEstudianteRuta.ruta_id == Ruta.id)
                .filter(
                    Ruta.conductor_id == current_user.conductor.id,
                    AsignacionEstudianteRuta.activa == 1,
                )
            )
            query = query.filter(Estudiante.id.in_(subq_est))
        else:
            return []

    estudiantes = query.order_by(Estudiante.apellido.asc(), Estudiante.nombre.asc()).all()
    return [_serialize_estudiante(e) for e in estudiantes]


@router.get(
    "/por-ruta/{ruta_id}",
    response_model=List[EstudianteResponse],
    summary="Consultar estudiantes activos por ruta (RF-05)",
)
def obtener_estudiantes_por_ruta(
    ruta_id: int,
    current_user: Usuario = Depends(require_role(["ADMIN", "CONDUCTOR"])),
    db: Session = Depends(get_db),
):
    return listar_estudiantes(
        ruta_id=ruta_id,
        solo_activos=True,
        current_user=current_user,
        db=db,
    )


@router.get(
    "/{estudiante_id}",
    response_model=EstudianteResponse,
    summary="Obtener detalle de un estudiante (RF-04, RF-15)",
)
def obtener_estudiante(
    estudiante_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    est = db.query(Estudiante).filter(Estudiante.id == estudiante_id).first()
    if not est:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        if "PADRE" in roles and est.representante_usuario_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo puede consultar la información de sus representados (RF-15).",
            )

    return _serialize_estudiante(est)


@router.post(
    "",
    response_model=EstudianteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar estudiante y vincularlo a su representante legal por CONDUCTOR o ADMIN (RF-04)",
)
def crear_estudiante(
    payload: EstudianteCreate,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    rep = (
        db.query(Usuario)
        .filter(
            Usuario.id == payload.representante_usuario_id,
            Usuario.cooperativa_id == current_user.cooperativa_id,
        )
        .first()
    )
    if not rep:
        raise HTTPException(status_code=404, detail="El representante (padre) seleccionado no existe")

    if db.query(Estudiante).filter(Estudiante.cedula == payload.cedula.strip()).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un estudiante registrado con la cédula '{payload.cedula.strip()}' (RF-04).",
        )

    nuevo_est = Estudiante(
        representante_usuario_id=payload.representante_usuario_id,
        cedula=payload.cedula.strip(),
        nombre=payload.nombre.strip(),
        apellido=payload.apellido.strip(),
        grado=payload.grado.strip() if payload.grado else None,
        activo=1,
        domicilio_geom=payload.domicilio_geom.model_dump() if payload.domicilio_geom else None,
        domicilio_direccion=payload.domicilio_direccion.strip() if payload.domicilio_direccion else None,
    )
    db.add(nuevo_est)
    db.flush()

    if payload.monto_mensual_inicial is not None:
        db.add(
            TarifaEstudiante(
                estudiante_id=nuevo_est.id,
                monto_mensual=payload.monto_mensual_inicial,
                vigente_desde=date.today(),
                observacion="Tarifa inicial al registrar estudiante",
            )
        )

    # Si quien lo registra es un CONDUCTOR con ruta activa, asignarlo automáticamente a su ruta
    if current_user.conductor:
        ruta_cond = (
            db.query(Ruta)
            .filter(Ruta.conductor_id == current_user.conductor.id, Ruta.activa == 1)
            .first()
        )
        if ruta_cond:
            parada_id_asig = None
            if payload.domicilio_geom is not None:
                total_paradas = db.query(Parada).filter(Parada.ruta_id == ruta_cond.id).count()
                nueva_parada = Parada(
                    ruta_id=ruta_cond.id,
                    nombre=payload.domicilio_direccion or f"Parada {nuevo_est.nombre} {nuevo_est.apellido}",
                    orden=total_paradas + 1,
                    geom=payload.domicilio_geom.model_dump(),
                    radio_metros=80,
                )
                db.add(nueva_parada)
                db.flush()
                parada_id_asig = nueva_parada.id
            else:
                primera_parada = (
                    db.query(Parada)
                    .filter(Parada.ruta_id == ruta_cond.id)
                    .order_by(Parada.orden.asc())
                    .first()
                )
                if primera_parada:
                    parada_id_asig = primera_parada.id

            if parada_id_asig is not None:
                db.add(
                    AsignacionEstudianteRuta(
                        estudiante_id=nuevo_est.id,
                        ruta_id=ruta_cond.id,
                        parada_id=parada_id_asig,
                        activa=1,
                    )
                )

    db.commit()
    db.refresh(nuevo_est)
    return _serialize_estudiante(nuevo_est)


@router.put(
    "/{estudiante_id}",
    response_model=EstudianteResponse,
    summary="Actualizar datos de un estudiante o su representante vinculado (RF-04)",
)
def actualizar_estudiante(
    estudiante_id: int,
    payload: EstudianteUpdate,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    est = db.query(Estudiante).filter(Estudiante.id == estudiante_id).first()
    if not est:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    if payload.cedula is not None and payload.cedula.strip() != est.cedula:
        if db.query(Estudiante).filter(Estudiante.cedula == payload.cedula.strip(), Estudiante.id != estudiante_id).first():
            raise HTTPException(status_code=409, detail="La cédula ya pertenece a otro estudiante.")
        est.cedula = payload.cedula.strip()

    if payload.representante_usuario_id is not None:
        if not db.query(Usuario).filter(Usuario.id == payload.representante_usuario_id).first():
            raise HTTPException(status_code=404, detail="Representante no encontrado")
        est.representante_usuario_id = payload.representante_usuario_id

    if payload.nombre is not None:
        est.nombre = payload.nombre.strip()
    if payload.apellido is not None:
        est.apellido = payload.apellido.strip()
    if payload.grado is not None:
        est.grado = payload.grado.strip()
    if payload.domicilio_geom is not None:
        est.domicilio_geom = payload.domicilio_geom.model_dump()
    if payload.domicilio_direccion is not None:
        est.domicilio_direccion = payload.domicilio_direccion.strip()
    if payload.activo is not None:
        est.activo = payload.activo

    db.commit()
    db.refresh(est)
    return _serialize_estudiante(est)


@router.patch(
    "/{estudiante_id}/estado",
    response_model=EstudianteResponse,
    summary="Activar o desactivar un estudiante (RF-04)",
)
def cambiar_estado_estudiante(
    estudiante_id: int,
    payload: EstadoActivoPatch,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    est = db.query(Estudiante).filter(Estudiante.id == estudiante_id).first()
    if not est:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")
    est.activo = payload.activo
    db.commit()
    db.refresh(est)
    return _serialize_estudiante(est)


# ============================================================================
# TARIFAS MENSUALES Y ASIGNACIÓN A RUTA / PUNTO DE RECOGIDA (RF-04)
# ============================================================================

@router.post(
    "/{estudiante_id}/tarifa",
    response_model=TarifaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Definir tarifa mensual para un estudiante",
)
def definir_tarifa_estudiante(
    estudiante_id: int,
    payload: TarifaCreate,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    est = db.query(Estudiante).filter(Estudiante.id == estudiante_id).first()
    if not est:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado")

    tarifa = TarifaEstudiante(
        estudiante_id=estudiante_id,
        monto_mensual=payload.monto_mensual,
        vigente_desde=payload.vigente_desde,
        vigente_hasta=payload.vigente_hasta,
        observacion=payload.observacion,
    )
    db.add(tarifa)
    db.commit()
    db.refresh(tarifa)
    return tarifa


@router.get(
    "/{estudiante_id}/tarifas",
    response_model=List[TarifaResponse],
    summary="Listar historial de tarifas de un estudiante",
)
def listar_tarifas_estudiante(
    estudiante_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return (
        db.query(TarifaEstudiante)
        .filter(TarifaEstudiante.estudiante_id == estudiante_id)
        .order_by(TarifaEstudiante.vigente_desde.desc())
        .all()
    )


@router.post(
    "/asignaciones-ruta",
    response_model=AsignacionRutaResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Asignar estudiante a una ruta y punto de recogida validando capacidad del bus (RF-04)",
)
def asignar_estudiante_a_ruta(
    payload: AsignacionRutaCreate,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    est = db.query(Estudiante).filter(Estudiante.id == payload.estudiante_id, Estudiante.activo == 1).first()
    if not est:
        raise HTTPException(status_code=404, detail="Estudiante no encontrado o inactivo")

    ruta = db.query(Ruta).filter(Ruta.id == payload.ruta_id, Ruta.activa == 1).first()
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada o inactiva")

    parada = (
        db.query(Parada)
        .filter(Parada.id == payload.parada_id, Parada.ruta_id == payload.ruta_id)
        .first()
    )
    if not parada:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La parada indicada no pertenece a la ruta seleccionada.",
        )

    # Verificar si ya tiene asignación activa en la misma ruta
    existente = (
        db.query(AsignacionEstudianteRuta)
        .filter(
            AsignacionEstudianteRuta.estudiante_id == payload.estudiante_id,
            AsignacionEstudianteRuta.ruta_id == payload.ruta_id,
            AsignacionEstudianteRuta.activa == 1,
        )
        .first()
    )
    if existente:
        existente.parada_id = payload.parada_id
        db.commit()
        db.refresh(existente)
        return _serialize_asignacion(existente)

    # Validar capacidad máxima del bus asignado a la ruta
    ocupados = (
        db.query(AsignacionEstudianteRuta)
        .filter(
            AsignacionEstudianteRuta.ruta_id == payload.ruta_id,
            AsignacionEstudianteRuta.activa == 1,
        )
        .count()
    )
    if ruta.bus and ocupados >= ruta.bus.capacidad:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"El bus de la ruta ({ruta.bus.placa}) ha alcanzado su capacidad máxima ({ruta.bus.capacidad} estudiantes).",
        )

    nueva_asig = AsignacionEstudianteRuta(
        estudiante_id=payload.estudiante_id,
        ruta_id=payload.ruta_id,
        parada_id=payload.parada_id,
        activa=1,
    )
    db.add(nueva_asig)
    db.commit()
    db.refresh(nueva_asig)
    return _serialize_asignacion(nueva_asig)


@router.patch(
    "/asignaciones-ruta/{asignacion_id}/estado",
    response_model=AsignacionRutaResponse,
    summary="Activar o desactivar la asignación de un estudiante a una ruta",
)
def cambiar_estado_asignacion(
    asignacion_id: int,
    payload: EstadoActivoPatch,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    asig = db.query(AsignacionEstudianteRuta).filter(AsignacionEstudianteRuta.id == asignacion_id).first()
    if not asig:
        raise HTTPException(status_code=404, detail="Asignación no encontrada")
    asig.activa = payload.activo
    db.commit()
    db.refresh(asig)
    return _serialize_asignacion(asig)
