"""Utilidades de hash de contraseñas y tokens JWT enriquecidos con permisos de rol (Capa 2: Seguridad - RF-01, RF-15)."""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
import bcrypt
from jose import JWTError, jwt
from app.core.config import settings


def get_password_hash(password: str) -> str:
    """Genera el hash bcrypt de una contraseña en texto plano."""
    pwd_bytes = password.encode("utf-8")
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(pwd_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña en texto plano contra su hash bcrypt."""
    try:
        return bcrypt.checkpw(
            plain_password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except Exception:
        return False


def create_access_token(
    subject: str | int,
    cooperativa_id: int,
    roles: List[str],
    conductor_id: Optional[int] = None,
    socio_id: Optional[int] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    Crea un token JWT firmado que encapsula la identidad y el alcance de permisos del usuario:
      - `sub`: ID del usuario (`usuarios.id`)
      - `cooperativa_id`: ID de la cooperativa a la que pertenece
      - `roles`: Lista de roles activos (`ADMIN`, `CONDUCTOR`, `PADRE`)
      - `conductor_id`: ID de conductor si tiene ese perfil (para aislar su ruta en RF-15)
      - `socio_id`: ID de socio si tiene ese perfil
    """
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode: Dict[str, Any] = {
        "sub": str(subject),
        "cooperativa_id": cooperativa_id,
        "roles": roles,
        "conductor_id": conductor_id,
        "socio_id": socio_id,
        "exp": expire,
    }
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decodifica y valida la firma y expiración de un token JWT."""
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None
