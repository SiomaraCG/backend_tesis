"""Controlador de Gestión de Socios, Conductores y Buses (RF-02)."""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.security import get_password_hash
from app.models import Bus, Conductor, Rol, Socio, Usuario, UsuarioRol
from app.schemas.common import EstadoActivoPatch
from app.schemas.socios_buses import (
    BusCreate,
    BusResponse,
    BusUpdate,
    ConductorCreate,
    ConductorResponse,
    ConductorUpdate,
    SocioCreate,
    SocioResponse,
    SocioUpdate,
)

router = APIRouter(prefix="/flota", tags=["Socios, Conductores y Buses (RF-02)"])


def _serialize_socio(socio: Socio) -> SocioResponse:
    u = socio.usuario
    return SocioResponse(
        id=socio.id,
        cooperativa_id=socio.cooperativa_id,
        usuario_id=socio.usuario_id,
        nombre_razon_social=socio.nombre_razon_social,
        activo=socio.activo,
        usuario_nombre=u.nombre if u else None,
        usuario_apellido=u.apellido if u else None,
        usuario_cedula=u.cedula if u else None,
        usuario_email=u.email if u else None,
        usuario_telefono=u.telefono if u else None,
        total_buses=len(socio.buses) if socio.buses else 0,
    )


def _serialize_conductor(conductor: Conductor) -> ConductorResponse:
    u = conductor.usuario
    return ConductorResponse(
        id=conductor.id,
        usuario_id=conductor.usuario_id,
        licencia=conductor.licencia,
        activo=conductor.activo,
        nombre=u.nombre if u else None,
        apellido=u.apellido if u else None,
        cedula=u.cedula if u else None,
        email=u.email if u else None,
        telefono=u.telefono if u else None,
    )


def _serialize_bus(bus: Bus) -> BusResponse:
    return BusResponse(
        id=bus.id,
        socio_id=bus.socio_id,
        socio_nombre=bus.socio.nombre_razon_social if bus.socio else None,
        placa=bus.placa,
        capacidad=bus.capacidad,
        activo=bus.activo,
    )


def _get_or_create_usuario(
    db: Session,
    cooperativa_id: int,
    usuario_id: Optional[int],
    email: Optional[str],
    password: Optional[str],
    nombre: Optional[str],
    apellido: Optional[str],
    cedula: Optional[str],
    telefono: Optional[str],
) -> Usuario:
    """Obtiene un usuario existente o crea uno nuevo validando que no existan duplicados (RF-02)."""
    if usuario_id is not None:
        user = db.query(Usuario).filter(Usuario.id == usuario_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No existe el usuario con id={usuario_id}",
            )
        return user

    if not all([email, nombre, apellido, cedula]):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe enviar usuario_id existente o los datos completos (email, nombre, apellido, cedula)",
        )

    duplicado = (
        db.query(Usuario)
        .filter(or_(Usuario.email == email.strip(), Usuario.cedula == cedula.strip()))
        .first()
    )
    if duplicado:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un usuario registrado con ese correo electrónico o número de cédula (RF-02).",
        )

    nuevo_usuario = Usuario(
        cooperativa_id=cooperativa_id,
        email=email.strip(),
        password_hash=get_password_hash(password or "temporal123"),
        nombre=nombre.strip(),
        apellido=apellido.strip(),
        cedula=cedula.strip(),
        telefono=telefono.strip() if telefono else None,
        activo=1,
    )
    db.add(nuevo_usuario)
    db.flush()
    return nuevo_usuario


# ============================================================================
# ENDPOINTS DE SOCIOS DE TRANSPORTE (RF-02)
# ============================================================================

@router.get(
    "/socios",
    response_model=List[SocioResponse],
    summary="Listar socios de transporte de la cooperativa (RF-02)",
)
def listar_socios(
    solo_activos: bool = Query(False, description="Filtrar únicamente socios activos"),
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = db.query(Socio).filter(Socio.cooperativa_id == current_user.cooperativa_id)
    if solo_activos:
        query = query.filter(Socio.activo == 1)
    socios = query.order_by(Socio.id.desc()).all()
    return [_serialize_socio(s) for s in socios]


@router.get(
    "/socios/{socio_id}",
    response_model=SocioResponse,
    summary="Consultar detalle de un socio de transporte (RF-02)",
)
def obtener_socio(
    socio_id: int,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    socio = (
        db.query(Socio)
        .filter(Socio.id == socio_id, Socio.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not socio:
        raise HTTPException(status_code=404, detail="Socio de transporte no encontrado")
    return _serialize_socio(socio)


@router.post(
    "/socios",
    response_model=SocioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear socio de transporte evitando duplicados (RF-02)",
)
def crear_socio(
    payload: SocioCreate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    # Validar que no se repita la razón social en la cooperativa
    existe_razon = (
        db.query(Socio)
        .filter(
            Socio.cooperativa_id == current_user.cooperativa_id,
            Socio.nombre_razon_social == payload.nombre_razon_social.strip(),
        )
        .first()
    )
    if existe_razon:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe un socio registrado con esa razón social en la cooperativa (RF-02).",
        )

    user = _get_or_create_usuario(
        db=db,
        cooperativa_id=current_user.cooperativa_id,
        usuario_id=payload.usuario_id,
        email=payload.email,
        password=payload.password,
        nombre=payload.nombre,
        apellido=payload.apellido,
        cedula=payload.cedula,
        telefono=payload.telefono,
    )

    if db.query(Socio).filter(Socio.usuario_id == user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este usuario ya se encuentra registrado como socio de transporte (RF-02).",
        )

    nuevo_socio = Socio(
        cooperativa_id=current_user.cooperativa_id,
        usuario_id=user.id,
        nombre_razon_social=payload.nombre_razon_social.strip(),
        activo=1,
    )
    db.add(nuevo_socio)
    db.commit()
    db.refresh(nuevo_socio)
    return _serialize_socio(nuevo_socio)


@router.put(
    "/socios/{socio_id}",
    response_model=SocioResponse,
    summary="Actualizar datos de un socio de transporte (RF-02)",
)
def actualizar_socio(
    socio_id: int,
    payload: SocioUpdate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    socio = (
        db.query(Socio)
        .filter(Socio.id == socio_id, Socio.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not socio:
        raise HTTPException(status_code=404, detail="Socio no encontrado")

    if payload.nombre_razon_social is not None:
        dup = (
            db.query(Socio)
            .filter(
                Socio.cooperativa_id == current_user.cooperativa_id,
                Socio.nombre_razon_social == payload.nombre_razon_social.strip(),
                Socio.id != socio_id,
            )
            .first()
        )
        if dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Otro socio ya posee esa razón social (RF-02).",
            )
        socio.nombre_razon_social = payload.nombre_razon_social.strip()

    if payload.activo is not None:
        socio.activo = payload.activo

    if socio.usuario:
        if payload.email is not None and payload.email.strip() != socio.usuario.email:
            if db.query(Usuario).filter(Usuario.email == payload.email.strip(), Usuario.id != socio.usuario.id).first():
                raise HTTPException(status_code=409, detail="El correo electrónico ya está en uso.")
            socio.usuario.email = payload.email.strip()
        if payload.nombre is not None:
            socio.usuario.nombre = payload.nombre.strip()
        if payload.apellido is not None:
            socio.usuario.apellido = payload.apellido.strip()
        if payload.telefono is not None:
            socio.usuario.telefono = payload.telefono.strip()

    db.commit()
    db.refresh(socio)
    return _serialize_socio(socio)


@router.patch(
    "/socios/{socio_id}/estado",
    response_model=SocioResponse,
    summary="Activar o desactivar un socio de transporte (RF-02)",
)
def cambiar_estado_socio(
    socio_id: int,
    payload: EstadoActivoPatch,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    socio = (
        db.query(Socio)
        .filter(Socio.id == socio_id, Socio.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not socio:
        raise HTTPException(status_code=404, detail="Socio no encontrado")

    socio.activo = payload.activo
    db.commit()
    db.refresh(socio)
    return _serialize_socio(socio)


# ============================================================================
# ENDPOINTS DE CONDUCTORES (RF-02, RF-03)
# ============================================================================

@router.get(
    "/conductores",
    response_model=List[ConductorResponse],
    summary="Listar conductores registrados (RF-02, RF-03)",
)
def listar_conductores(
    solo_activos: bool = Query(False),
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Conductor)
        .join(Usuario, Conductor.usuario_id == Usuario.id)
        .filter(Usuario.cooperativa_id == current_user.cooperativa_id)
    )
    if solo_activos:
        query = query.filter(Conductor.activo == 1)
    conductores = query.order_by(Conductor.id.desc()).all()
    return [_serialize_conductor(c) for c in conductores]


@router.post(
    "/conductores",
    response_model=ConductorResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un conductor evitando duplicados de licencia/cédula (RF-02, RF-03)",
)
def crear_conductor(
    payload: ConductorCreate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    licencia_clean = payload.licencia.strip().upper()
    if db.query(Conductor).filter(Conductor.licencia == licencia_clean).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un conductor con la licencia '{licencia_clean}'.",
        )

    user = _get_or_create_usuario(
        db=db,
        cooperativa_id=current_user.cooperativa_id,
        usuario_id=payload.usuario_id,
        email=payload.email,
        password=payload.password,
        nombre=payload.nombre,
        apellido=payload.apellido,
        cedula=payload.cedula,
        telefono=payload.telefono,
    )

    if db.query(Conductor).filter(Conductor.usuario_id == user.id).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Este usuario ya tiene un perfil de conductor asignado.",
        )

    # Garantizar rol CONDUCTOR en usuario_rol
    rol_conductor = db.query(Rol).filter(Rol.nombre == "CONDUCTOR").first()
    if rol_conductor:
        tiene_rol = (
            db.query(UsuarioRol)
            .filter_by(usuario_id=user.id, rol_id=rol_conductor.id)
            .first()
        )
        if not tiene_rol:
            db.add(UsuarioRol(usuario_id=user.id, rol_id=rol_conductor.id))

    conductor = Conductor(
        usuario_id=user.id,
        licencia=licencia_clean,
        activo=1,
    )
    db.add(conductor)
    db.commit()
    db.refresh(conductor)
    return _serialize_conductor(conductor)


@router.put(
    "/conductores/{conductor_id}",
    response_model=ConductorResponse,
    summary="Actualizar datos de un conductor (RF-02, RF-03)",
)
def actualizar_conductor(
    conductor_id: int,
    payload: ConductorUpdate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    conductor = db.query(Conductor).filter(Conductor.id == conductor_id).first()
    if not conductor:
        raise HTTPException(status_code=404, detail="Conductor no encontrado")

    if payload.licencia is not None:
        lic = payload.licencia.strip().upper()
        if db.query(Conductor).filter(Conductor.licencia == lic, Conductor.id != conductor_id).first():
            raise HTTPException(status_code=409, detail="La licencia ya pertenece a otro conductor.")
        conductor.licencia = lic

    if payload.activo is not None:
        conductor.activo = payload.activo

    if conductor.usuario:
        if payload.email is not None and payload.email.strip() != conductor.usuario.email:
            if db.query(Usuario).filter(Usuario.email == payload.email.strip(), Usuario.id != conductor.usuario.id).first():
                raise HTTPException(status_code=409, detail="El correo electrónico ya está registrado.")
            conductor.usuario.email = payload.email.strip()
        if payload.nombre is not None:
            conductor.usuario.nombre = payload.nombre.strip()
        if payload.apellido is not None:
            conductor.usuario.apellido = payload.apellido.strip()
        if payload.telefono is not None:
            conductor.usuario.telefono = payload.telefono.strip()

    db.commit()
    db.refresh(conductor)
    return _serialize_conductor(conductor)


@router.patch(
    "/conductores/{conductor_id}/estado",
    response_model=ConductorResponse,
    summary="Activar o desactivar un conductor",
)
def cambiar_estado_conductor(
    conductor_id: int,
    payload: EstadoActivoPatch,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    conductor = db.query(Conductor).filter(Conductor.id == conductor_id).first()
    if not conductor:
        raise HTTPException(status_code=404, detail="Conductor no encontrado")
    conductor.activo = payload.activo
    db.commit()
    db.refresh(conductor)
    return _serialize_conductor(conductor)


# ============================================================================
# ENDPOINTS DE BUSES / UNIDADES (RF-02, RF-03)
# ============================================================================

@router.get(
    "/buses",
    response_model=List[BusResponse],
    summary="Listar buses registrados (RF-02)",
)
def listar_buses(
    socio_id: Optional[int] = Query(None),
    solo_activos: bool = Query(False),
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Bus)
        .join(Socio, Bus.socio_id == Socio.id)
        .filter(Socio.cooperativa_id == current_user.cooperativa_id)
    )
    if socio_id is not None:
        query = query.filter(Bus.socio_id == socio_id)
    if solo_activos:
        query = query.filter(Bus.activo == 1)
    buses = query.order_by(Bus.id.desc()).all()
    return [_serialize_bus(b) for b in buses]


@router.post(
    "/buses",
    response_model=BusResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar un bus vinculado a un socio validando placa única (RF-02)",
)
def crear_bus(
    payload: BusCreate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    socio = (
        db.query(Socio)
        .filter(Socio.id == payload.socio_id, Socio.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not socio:
        raise HTTPException(status_code=404, detail="El socio especificado no existe en la cooperativa")

    placa_norm = payload.placa.strip().upper()
    if db.query(Bus).filter(Bus.placa == placa_norm).first():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Ya existe un bus registrado con la placa '{placa_norm}' (RF-02).",
        )

    nuevo_bus = Bus(
        socio_id=payload.socio_id,
        placa=placa_norm,
        capacidad=payload.capacidad,
        activo=1,
    )
    db.add(nuevo_bus)
    db.commit()
    db.refresh(nuevo_bus)
    return _serialize_bus(nuevo_bus)


@router.put(
    "/buses/{bus_id}",
    response_model=BusResponse,
    summary="Actualizar datos de un bus (RF-02)",
)
def actualizar_bus(
    bus_id: int,
    payload: BusUpdate,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    bus = db.query(Bus).filter(Bus.id == bus_id).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus no encontrado")

    if payload.placa is not None:
        placa_norm = payload.placa.strip().upper()
        if db.query(Bus).filter(Bus.placa == placa_norm, Bus.id != bus_id).first():
            raise HTTPException(status_code=409, detail="La placa ya pertenece a otra unidad.")
        bus.placa = placa_norm

    if payload.socio_id is not None:
        if not db.query(Socio).filter(Socio.id == payload.socio_id).first():
            raise HTTPException(status_code=404, detail="Socio no encontrado")
        bus.socio_id = payload.socio_id

    if payload.capacidad is not None:
        bus.capacidad = payload.capacidad

    if payload.activo is not None:
        bus.activo = payload.activo

    db.commit()
    db.refresh(bus)
    return _serialize_bus(bus)


@router.patch(
    "/buses/{bus_id}/estado",
    response_model=BusResponse,
    summary="Activar o desactivar un bus",
)
def cambiar_estado_bus(
    bus_id: int,
    payload: EstadoActivoPatch,
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    bus = db.query(Bus).filter(Bus.id == bus_id).first()
    if not bus:
        raise HTTPException(status_code=404, detail="Bus no encontrado")
    bus.activo = payload.activo
    db.commit()
    db.refresh(bus)
    return _serialize_bus(bus)
