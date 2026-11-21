"""Utilidades Geoespaciales y Tipo SQLAlchemy POINT (Capa 4: Persistencia)."""
import math
import re
import struct
from typing import Any, Dict, Optional, Tuple, Union
from sqlalchemy import func
from sqlalchemy.types import UserDefinedType
from app.core.config import settings

_WKT_POINT_RE = re.compile(
    r"POINT\s*\(\s*([+-]?\d+(?:\.\d+)?)\s+([+-]?\d+(?:\.\d+)?)\s*\)",
    re.IGNORECASE,
)


def coords_to_wkt(lat: float, lng: float) -> str:
    """Convierte (lat, lng) al formato estándar OGC WKT: 'POINT(lng lat)'."""
    return f"POINT({float(lng):.7f} {float(lat):.7f})"


def parse_point(value: Any) -> Optional[Dict[str, float]]:
    """
    Convierte cualquier representación de un punto espacial a {'lat': float, 'lng': float}.
    Soporta:
      - dict {'lat': ..., 'lng': ...}
      - tupla/lista (lat, lng)
      - cadena WKT 'POINT(lng lat)'
      - binario interno de MySQL 8 (4 bytes SRID + 21 bytes WKB Point)
    """
    if value is None:
        return None

    if isinstance(value, dict):
        if "lat" in value and "lng" in value:
            return {"lat": float(value["lat"]), "lng": float(value["lng"])}
        return None

    if isinstance(value, (tuple, list)) and len(value) == 2:
        return {"lat": float(value[0]), "lng": float(value[1])}

    if isinstance(value, bytes):
        # Formato binario MySQL POINT: 4 bytes SRID + 1 byte endian + 4 bytes tipo + 8 bytes X (lng) + 8 bytes Y (lat) = 25 bytes
        if len(value) == 25:
            byte_order = value[4]
            fmt = "<dd" if byte_order == 1 else ">dd"
            lng, lat = struct.unpack(fmt, value[9:25])
            return {"lat": round(lat, 7), "lng": round(lng, 7)}
        try:
            value = value.decode("utf-8")
        except Exception:
            return None

    if isinstance(value, str):
        val_str = value.strip()
        match = _WKT_POINT_RE.search(val_str)
        if match:
            lng = float(match.group(1))
            lat = float(match.group(2))
            return {"lat": lat, "lng": lng}
        # Soporte EWKB hexadecimal de PostGIS (ej. '0101000020E6100000...')
        if len(val_str) in (42, 50) and all(c in "0123456789abcdefABCDEF" for c in val_str):
            try:
                raw_b = bytes.fromhex(val_str)
                endian = "<" if raw_b[0] == 1 else ">"
                offset = 9 if len(raw_b) == 25 else 5
                lng, lat = struct.unpack(f"{endian}dd", raw_b[offset : offset + 16])
                return {"lat": round(lat, 7), "lng": round(lng, 7)}
            except Exception:
                pass
        # Soporte alternativo "lat,lng"
        if "," in val_str:
            parts = val_str.split(",")
            if len(parts) == 2:
                return {"lat": float(parts[0].strip()), "lng": float(parts[1].strip())}

    return None


def serialize_point_to_wkt(
    value: Optional[Union[Dict[str, float], Tuple[float, float], str]]
) -> Optional[str]:
    """Serializa dict {'lat', 'lng'}, tupla (lat, lng) o WKT a cadena 'POINT(lng lat)'."""
    if value is None:
        return None
    parsed = parse_point(value)
    if parsed is None:
        return None
    return coords_to_wkt(parsed["lat"], parsed["lng"])


def haversine_distance_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """
    Calcula la distancia esférica en metros entre dos coordenadas GPS (equivalente a ST_Distance_Sphere).
    Usado en el motor de geocercas (RF-11) y matriz de optimización (RF-08).
    """
    r_earth = 6371000.0  # Radio terrestre medio en metros
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lng2 - lng1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))
    return r_earth * c


class PointGeometry(UserDefinedType):
    """
    Tipo SQLAlchemy para columnas espaciales `POINT` del diagrama model.pdf:
      - En MySQL 8 usa el tipo nativo `POINT` con `ST_GeomFromText` y `ST_AsText`.
      - En SQLite (pruebas locales) almacena WKT en texto de forma transparente.
      - En Python recibe y devuelve automáticamente `{'lat': float, 'lng': float}`.
    """

    cache_ok = True

    def get_col_spec(self, **kw) -> str:
        from app.core.database import ACTIVE_DB_DIALECT
        if ACTIVE_DB_DIALECT == "postgresql":
            return "geometry(Point, 4326)"
        if ACTIVE_DB_DIALECT == "mysql":
            return "POINT"
        return "VARCHAR(100)"

    def bind_expression(self, bindvalue):
        from app.core.database import ACTIVE_DB_DIALECT
        if ACTIVE_DB_DIALECT == "postgresql":
            return func.ST_GeomFromText(bindvalue, 4326)
        if ACTIVE_DB_DIALECT == "mysql":
            return func.ST_GeomFromText(bindvalue)
        return bindvalue

    def column_expression(self, col):
        from app.core.database import ACTIVE_DB_DIALECT
        if ACTIVE_DB_DIALECT in ("postgresql", "mysql"):
            return func.ST_AsText(col, type_=self)
        return col

    def bind_processor(self, dialect):
        def process(value):
            return serialize_point_to_wkt(value)

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            return parse_point(value)

        return process
