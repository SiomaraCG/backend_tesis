"""
Dependencias de Autenticación, Matriz de Permisos por Ruta basada en Token JWT y Aislamiento de Datos (Capa 2: Seguridad - RF-01, RF-15).
"""
import re
from typing import Callable, List, Optional, Tuple
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import Conductor, Usuario
from app.utils.response import response_error

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/auth/token")

# ============================================================================
# MATRIZ CENTRALIZADA DE PERMISOS POR RUTA Y MÉTODO HTTP SEGÚN EL TOKEN (RF-01, RF-15)
# Formato: (Expresión Regular de Ruta, Métodos HTTP Permitidos, Roles Autorizados en el Token)
# ============================================================================
ROUTE_PERMISSION_RULES: List[Tuple[re.Pattern, List[str], List[str]]] = [
    # 1. Perfil y sesión personal: cualquier usuario con token válido
    (re.compile(r"^/api/auth/(me|cambiar-password)$"), ["GET", "POST"], ["ADMIN", "CONDUCTOR", "PADRE"]),

    # 2. Gestión de Socios, Conductores y Buses (RF-02): EXCLUSIVO ADMIN
    (re.compile(r"^/api/flota/.*$"), ["GET", "POST", "PUT", "PATCH", "DELETE"], ["ADMIN"]),

    # 3. Optimización de Rutas con Google OR-Tools (RF-08): ADMIN y CONDUCTOR
    (re.compile(r"^/api/rutas/\d+/optimizar$"), ["POST"], ["ADMIN", "CONDUCTOR"]),

    # 4. Consulta de Estudiantes por Ruta (RF-05, RF-07): ADMIN y CONDUCTOR
    (re.compile(r"^/api/rutas/\d+/estudiantes$"), ["GET"], ["ADMIN", "CONDUCTOR"]),
    (re.compile(r"^/api/estudiantes/por-ruta/\d+$"), ["GET"], ["ADMIN", "CONDUCTOR"]),

    # 5. Consulta de Rutas, Instituciones y Paradas (RF-03, RF-10, RF-15):
    #    - GET permitido para ADMIN, CONDUCTOR (solo su ruta) y PADRE (solo ruta de sus hijos)
    #    - Crear/editar paradas de su ruta: ADMIN y CONDUCTOR
    #    - Crear/editar rutas e instituciones: EXCLUSIVO ADMIN
    (re.compile(r"^/api/rutas(/.*)?$"), ["GET"], ["ADMIN", "CONDUCTOR", "PADRE"]),
    (re.compile(r"^/api/rutas/(\d+/paradas|paradas/\d+)$"), ["POST", "PUT", "DELETE"], ["ADMIN", "CONDUCTOR"]),
    (re.compile(r"^/api/rutas(/.*)?$"), ["POST", "PUT", "PATCH", "DELETE"], ["ADMIN"]),

    # 6. Gestión de Padres, Estudiantes, Tarifas y Asignaciones (RF-04, RF-15):
    #    - ADMIN y CONDUCTOR registran y gestionan al Padre de Familia y al Estudiante (su tarifa y su parada/ruta)
    #    - Consulta GET de estudiantes y tarifas: ADMIN, CONDUCTOR (su ruta) y PADRE (solo sus hijos)
    (re.compile(r"^/api/estudiantes/padres$"), ["GET", "POST"], ["ADMIN", "CONDUCTOR"]),
    (re.compile(r"^/api/estudiantes/registrar-padre-y-estudiante$"), ["POST"], ["ADMIN", "CONDUCTOR"]),
    (re.compile(r"^/api/estudiantes/asignaciones-ruta(/.*)?$"), ["POST", "PATCH"], ["ADMIN", "CONDUCTOR"]),
    (re.compile(r"^/api/estudiantes/\d+/tarifas?$"), ["POST"], ["ADMIN", "CONDUCTOR"]),
    (re.compile(r"^/api/estudiantes/\d+/tarifas?$"), ["GET"], ["ADMIN", "CONDUCTOR", "PADRE"]),
    (re.compile(r"^/api/estudiantes(/\d+)?$"), ["GET"], ["ADMIN", "CONDUCTOR", "PADRE"]),
    (re.compile(r"^/api/estudiantes(/.*)?$"), ["POST", "PUT", "PATCH", "DELETE"], ["ADMIN", "CONDUCTOR"]),

    # 7. Operación Diaria de Viajes y Asistencia (RF-07):
    #    - Iniciar/finalizar viaje, hoja de ruta del conductor, registrar asistencia y novedades: CONDUCTOR y ADMIN
    #    - Reportar ausencia previa de estudiante y consultar viajes: ADMIN, CONDUCTOR y PADRE
    (re.compile(r"^/api/viajes$"), ["GET"], ["ADMIN", "CONDUCTOR", "PADRE"]),
    (re.compile(r"^/api/viajes/\d+/ausencias$"), ["POST"], ["ADMIN", "CONDUCTOR", "PADRE"]),
    (re.compile(r"^/api/viajes/\d+/novedades$"), ["GET"], ["ADMIN", "CONDUCTOR", "PADRE"]),
    (re.compile(r"^/api/viajes/(iniciar|conductor/.*|\d+/asistencia|\d+/novedades|\d+/finalizar)$"), ["GET", "POST"], ["ADMIN", "CONDUCTOR"]),

    # 8. Monitoreo GPS en Tiempo Real y Geocercas (RF-09, RF-10, RF-11):
    #    - Emitir posición GPS de la unidad (RF-09): CONDUCTOR y ADMIN
    #    - Consultar ubicación actual de la ruta (RF-10) y bandeja de notificaciones (RF-11): ADMIN, CONDUCTOR y PADRE
    (re.compile(r"^/api/gps/viajes/\d+/posicion$"), ["POST"], ["ADMIN", "CONDUCTOR"]),
    (re.compile(r"^/api/gps/rutas/\d+/ubicacion-actual$"), ["GET"], ["ADMIN", "CONDUCTOR", "PADRE"]),
    (re.compile(r"^/api/gps/notificaciones(/.*)?$"), ["GET", "PATCH"], ["ADMIN", "CONDUCTOR", "PADRE"]),

    # 9. Pagos y Comprobantes con OCR (RF-12, RF-13, RF-14):
    #    - Generar cobros del mes y aprobar/rechazar comprobantes: EXCLUSIVO ADMIN
    #    - Subir comprobante en imagen y confirmar datos OCR (RF-12, RF-13): PADRE y ADMIN
    #    - Consultar estado de pagos (RF-14): ADMIN, CONDUCTOR (su ruta) y PADRE (sus hijos)
    (re.compile(r"^/api/pagos/generar-mes$"), ["POST"], ["ADMIN"]),
    (re.compile(r"^/api/pagos/comprobantes/\d+/revisar$"), ["PATCH"], ["ADMIN"]),
    (re.compile(r"^/api/pagos/\d+/comprobante$"), ["POST"], ["PADRE", "ADMIN"]),
    (re.compile(r"^/api/pagos/comprobantes/\d+/confirmar-datos$"), ["PUT"], ["PADRE", "ADMIN"]),
    (re.compile(r"^/api/pagos$"), ["GET"], ["ADMIN", "CONDUCTOR", "PADRE"]),

    # 10. Exportación de Reportes en PDF y Excel (RF-06): EXCLUSIVO ADMIN
    (re.compile(r"^/api/reportes/.*$"), ["GET"], ["ADMIN"]),
]

PUBLIC_API_PATHS = {
    "/",
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/auth/login",
    "/api/auth/token",
}


def check_route_permission_by_token_roles(path: str, method: str, token_roles: List[str]) -> Tuple[bool, List[str]]:
    """
    Evalúa si los roles contenidos en el token JWT tienen permiso para invocar `(method, path)`.
    Retorna `(autorizado: bool, roles_requeridos: List[str])`.
    """
    method_upper = method.upper()
    user_roles_set = set(token_roles)

    roles_requeridos_para_ruta: List[str] = []
    for pattern, allowed_methods, allowed_roles in ROUTE_PERMISSION_RULES:
        if pattern.match(path) and method_upper in allowed_methods:
            roles_requeridos_para_ruta = allowed_roles
            if user_roles_set.intersection(set(allowed_roles)):
                return True, allowed_roles

    return False, roles_requeridos_para_ruta


class TokenRouteGuardMiddleware(BaseHTTPMiddleware):
    """
    Middleware de Seguridad Basado en Token JWT (RF-01, RF-15):
      - Intercepta todas las peticiones hacia `/api/...` (excepto login/token y OPTIONS CORS).
      - Extrae y valida el token Bearer JWT.
      - Verifica en la matriz `ROUTE_PERMISSION_RULES` que el rol del token tenga acceso
        a esa ruta y verbo HTTP antes de ejecutar el controlador.
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        if method == "OPTIONS" or path in PUBLIC_API_PATHS or not path.startswith("/api/"):
            return await call_next(request)

        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.lower().startswith("bearer "):
            return response_error(
                mensaje="Acceso restringido: debe enviar un token Bearer JWT válido en la cabecera Authorization (RF-01).",
                codigo=status.HTTP_401_UNAUTHORIZED,
            )

        raw_token = auth_header.split(" ", 1)[1].strip()
        payload = decode_access_token(raw_token)
        if not payload or "sub" not in payload:
            return response_error(
                mensaje="Token JWT inválido o expirado. Inicie sesión nuevamente (RF-01).",
                codigo=status.HTTP_401_UNAUTHORIZED,
            )

        token_roles: List[str] = payload.get("roles", [])
        autorizado, roles_requeridos = check_route_permission_by_token_roles(path, method, token_roles)
        if not autorizado:
            roles_str = ", ".join(roles_requeridos) if roles_requeridos else "ADMIN"
            rol_actual_str = ", ".join(token_roles) if token_roles else "SIN_ROL"
            return response_error(
                mensaje=(
                    f"Acceso denegado por token (RF-15): su rol actual [{rol_actual_str}] "
                    f"no tiene permisos para ejecutar [{method} {path}]. Roles permitidos: [{roles_str}]."
                ),
                codigo=status.HTTP_403_FORBIDDEN,
            )

        # Adjuntar los claims del token al estado del request
        request.state.jwt_payload = payload
        return await call_next(request)


def get_user_roles(user: Usuario) -> List[str]:
    """Devuelve la lista de nombres de rol asignados al usuario."""
    return [ur.rol.nombre for ur in user.usuario_roles if ur.rol is not None]


def build_menu_for_roles(roles: List[str]) -> List[dict]:
    """
    Construye dinámicamente el menú de navegación y los módulos permitidos según los roles del token (RF-01).
    """
    catalogo_menu = [
        {
            "codigo": "DASHBOARD_ADMIN",
            "titulo": "Panel General",
            "ruta": "/admin/dashboard",
            "icono": "LayoutDashboard",
            "roles_permitidos": ["ADMIN"],
        },
        {
            "codigo": "SOCIOS_BUSES",
            "titulo": "Socios, Conductores y Buses",
            "ruta": "/admin/flota",
            "icono": "Bus",
            "roles_permitidos": ["ADMIN"],
        },
        {
            "codigo": "RUTAS_PARADAS",
            "titulo": "Rutas, Paradas y Optimización",
            "ruta": "/admin/rutas",
            "icono": "MapPin",
            "roles_permitidos": ["ADMIN"],
        },
        {
            "codigo": "ESTUDIANTES",
            "titulo": "Estudiantes y Representantes",
            "ruta": "/admin/estudiantes",
            "icono": "Users",
            "roles_permitidos": ["ADMIN"],
        },
        {
            "codigo": "REPORTES",
            "titulo": "Reportes y Exportación",
            "ruta": "/admin/reportes",
            "icono": "FileSpreadsheet",
            "roles_permitidos": ["ADMIN"],
        },
        {
            "codigo": "CONDUCTOR_REGISTRO_PADRE_ESTUDIANTE",
            "titulo": "Registrar Padre y Estudiante",
            "ruta": "/conductor/registrar-estudiante",
            "icono": "UserPlus",
            "roles_permitidos": ["CONDUCTOR"],
        },
        {
            "codigo": "CONDUCTOR_RUTA",
            "titulo": "Mi Ruta y Asistencia del Día",
            "ruta": "/conductor/mi-ruta",
            "icono": "CheckSquare",
            "roles_permitidos": ["CONDUCTOR"],
        },
        {
            "codigo": "CONDUCTOR_GPS",
            "titulo": "Recorrido y Emisión GPS",
            "ruta": "/conductor/recorrido-gps",
            "icono": "Navigation",
            "roles_permitidos": ["CONDUCTOR"],
        },
        {
            "codigo": "PADRE_MONITOREO",
            "titulo": "Ubicación en Tiempo Real",
            "ruta": "/padre/monitoreo",
            "icono": "LocateFixed",
            "roles_permitidos": ["PADRE"],
        },
        {
            "codigo": "PADRE_NOTIFICACIONES",
            "titulo": "Notificaciones de Proximidad",
            "ruta": "/padre/notificaciones",
            "icono": "Bell",
            "roles_permitidos": ["PADRE"],
        },
        {
            "codigo": "PAGOS_COMPROBANTES",
            "titulo": "Estado de Pagos y Comprobantes",
            "ruta": "/pagos",
            "icono": "CreditCard",
            "roles_permitidos": ["ADMIN", "CONDUCTOR", "PADRE"],
        },
    ]

    roles_set = set(roles)
    return [
        item
        for item in catalogo_menu
        if roles_set.intersection(set(item["roles_permitidos"]))
    ]


def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Usuario:
    """
    Valida el token Bearer JWT, verifica los claims del token (`sub`, `roles`)
    y retorna el Usuario activo desde la base de datos.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales no válidas o sesión expirada",
        headers={"WWW-Authenticate": "Bearer"},
    )

    payload = decode_access_token(token)
    if not payload or "sub" not in payload:
        raise credentials_exception

    try:
        user_id = int(payload["sub"])
    except (ValueError, TypeError):
        raise credentials_exception

    user = db.query(Usuario).filter(Usuario.id == user_id).first()
    if not user:
        raise credentials_exception

    if user.activo != 1:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="El usuario se encuentra desactivado. Contacte al administrador.",
        )

    return user


def require_role(allowed_roles: List[str]) -> Callable:
    """
    Dependencia de control de acceso basado en los roles del token JWT (RBAC - RF-01, RF-15).
    Verifica tanto los claims del token como los roles activos en base de datos.
    """
    allowed_set = set(allowed_roles)

    def role_checker(
        token: str = Depends(oauth2_scheme),
        current_user: Usuario = Depends(get_current_user),
    ) -> Usuario:
        payload = decode_access_token(token) or {}
        token_roles = set(payload.get("roles", [])) or set(get_user_roles(current_user))
        if not token_roles.intersection(allowed_set):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Acceso denegado por token (RF-15). Se requiere uno de los roles: "
                    f"{', '.join(allowed_roles)}"
                ),
            )
        return current_user

    return role_checker


def get_current_conductor(
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
) -> Conductor:
    """Obtiene el perfil Conductor vinculado al usuario autenticado (RF-07, RF-15)."""
    conductor = (
        db.query(Conductor)
        .filter(Conductor.usuario_id == current_user.id, Conductor.activo == 1)
        .first()
    )
    if not conductor:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="El usuario actual no tiene un perfil de conductor activo asociado.",
        )
    return conductor
