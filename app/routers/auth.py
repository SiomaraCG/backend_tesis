"""Controlador de Autenticación y Perfil por Rol (RF-01, RF-15)."""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import (
    build_menu_for_roles,
    check_route_permission_by_token_roles,
    get_current_user,
    get_user_roles,
)
from app.core.security import (
    create_access_token,
    get_password_hash,
    verify_password,
)
from app.models import Usuario
from app.schemas.auth import (
    CambiarPasswordRequest,
    LoginRequest,
    LoginResponse,
    UsuarioPerfilSchema,
)

router = APIRouter(prefix="/auth", tags=["Autenticación (RF-01, RF-15)"])


def _authenticate_user(db: Session, identificador: str, password: str) -> Usuario:
    """Busca usuario por email o cédula y valida contraseña y estado activo."""
    ident = identificador.strip()
    user = (
        db.query(Usuario)
        .filter(or_(Usuario.email == ident, Usuario.cedula == ident))
        .first()
    )
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Correo/cédula o contraseña incorrectos",
        )
    if user.activo != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Su cuenta está desactivada. Comuníquese con la administración.",
        )
    return user


def _build_user_profile(user: Usuario) -> UsuarioPerfilSchema:
    roles = get_user_roles(user)
    return UsuarioPerfilSchema(
        id=user.id,
        cooperativa_id=user.cooperativa_id,
        cooperativa_nombre=user.cooperativa.nombre if user.cooperativa else None,
        email=user.email,
        nombre=user.nombre,
        apellido=user.apellido,
        cedula=user.cedula,
        telefono=user.telefono,
        activo=user.activo,
        roles=roles,
        conductor_id=user.conductor.id if user.conductor else None,
        socio_id=user.socio.id if user.socio else None,
    )


@router.post(
    "/login",
    response_model=LoginResponse,
    summary="Iniciar sesión por email o cédula y obtener menú por rol (RF-01)",
)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    """
    Permite el inicio de sesión de administradores, conductores y padres mediante
    credenciales (`email` o `cedula` + `password`), devolviendo el token JWT,
    los datos de su perfil y el menú asignado según su rol (`RF-01`).
    """
    user = _authenticate_user(db, payload.identificador, payload.password)
    roles = get_user_roles(user)
    access_token = create_access_token(
        subject=user.id,
        cooperativa_id=user.cooperativa_id,
        roles=roles,
        conductor_id=user.conductor.id if user.conductor else None,
        socio_id=user.socio.id if user.socio else None,
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        usuario=_build_user_profile(user),
        menu=build_menu_for_roles(roles),
    )


@router.post(
    "/token",
    summary="Endpoint OAuth2 para botón Authorize en Swagger UI (/docs)",
)
def login_oauth2_swagger(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """Permite autenticarse directamente desde el botón 'Authorize' de Swagger `/docs`."""
    user = _authenticate_user(db, form_data.username, form_data.password)
    roles = get_user_roles(user)
    access_token = create_access_token(
        subject=user.id,
        cooperativa_id=user.cooperativa_id,
        roles=roles,
        conductor_id=user.conductor.id if user.conductor else None,
        socio_id=user.socio.id if user.socio else None,
    )
    return {"access_token": access_token, "token_type": "bearer"}


@router.get(
    "/me",
    response_model=LoginResponse,
    summary="Obtener perfil actual y menú permitido según el rol del token (RF-01, RF-15)",
)
def get_me(current_user: Usuario = Depends(get_current_user)):
    """Devuelve la sesión activa del usuario junto con sus roles y menú autorizado."""
    roles = get_user_roles(current_user)
    access_token = create_access_token(
        subject=current_user.id,
        cooperativa_id=current_user.cooperativa_id,
        roles=roles,
        conductor_id=current_user.conductor.id if current_user.conductor else None,
        socio_id=current_user.socio.id if current_user.socio else None,
    )
    return LoginResponse(
        access_token=access_token,
        token_type="bearer",
        usuario=_build_user_profile(current_user),
        menu=build_menu_for_roles(roles),
    )


@router.post(
    "/cambiar-password",
    summary="Cambiar contraseña del usuario autenticado",
)
def cambiar_password(
    payload: CambiarPasswordRequest,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if not verify_password(payload.password_actual, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta",
        )
    current_user.password_hash = get_password_hash(payload.password_nueva)
    db.commit()
    return {"mensaje": "Contraseña actualizada exitosamente"}
