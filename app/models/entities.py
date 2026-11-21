"""Mapeo ORM SQLAlchemy de las 21 tablas del modelo de datos (model.pdf)."""
from datetime import datetime, date, time
from decimal import Decimal
from sqlalchemy import (
    Column,
    Integer,
    BigInteger,
    SmallInteger,
    String,
    Text,
    Date,
    Time,
    DateTime,
    Numeric,
    Enum,
    ForeignKey,
)
from sqlalchemy.orm import relationship
from app.core.database import Base
from app.models.geo_utils import PointGeometry


# 1. cooperativas
class Cooperativa(Base):
    __tablename__ = "cooperativas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(200), nullable=False)
    ruc = Column(String(13), nullable=False, unique=True, index=True)
    direccion = Column(String(300), nullable=True)
    telefono = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    activa = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    usuarios = relationship("Usuario", back_populates="cooperativa")
    socios = relationship("Socio", back_populates="cooperativa")
    instituciones = relationship("InstitucionEducativa", back_populates="cooperativa")
    rutas = relationship("Ruta", back_populates="cooperativa")


# 2. usuarios
class Usuario(Base):
    __tablename__ = "usuarios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cooperativa_id = Column(Integer, ForeignKey("cooperativas.id"), nullable=False, index=True)
    email = Column(String(100), nullable=False, unique=True, index=True)
    password_hash = Column(String(255), nullable=False)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    cedula = Column(String(10), nullable=False, unique=True, index=True)
    telefono = Column(String(20), nullable=True)
    activo = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    cooperativa = relationship("Cooperativa", back_populates="usuarios")
    usuario_roles = relationship("UsuarioRol", back_populates="usuario", cascade="all, delete-orphan")
    socio = relationship("Socio", back_populates="usuario", uselist=False)
    conductor = relationship("Conductor", back_populates="usuario", uselist=False)
    estudiantes_representados = relationship("Estudiante", back_populates="representante")
    notificaciones = relationship("Notificacion", back_populates="usuario")


# 3. roles
class Rol(Base):
    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(30), nullable=False, unique=True)
    descripcion = Column(String(200), nullable=True)

    usuario_roles = relationship("UsuarioRol", back_populates="rol")


# 4. usuario_rol
class UsuarioRol(Base):
    __tablename__ = "usuario_rol"

    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), primary_key=True)
    rol_id = Column(Integer, ForeignKey("roles.id"), primary_key=True)

    usuario = relationship("Usuario", back_populates="usuario_roles")
    rol = relationship("Rol", back_populates="usuario_roles")


# 5. socios
class Socio(Base):
    __tablename__ = "socios"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cooperativa_id = Column(Integer, ForeignKey("cooperativas.id"), nullable=False, index=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, unique=True)
    nombre_razon_social = Column(String(200), nullable=False)
    activo = Column(SmallInteger, nullable=False, default=1)

    cooperativa = relationship("Cooperativa", back_populates="socios")
    usuario = relationship("Usuario", back_populates="socio")
    buses = relationship("Bus", back_populates="socio")


# 6. conductores
class Conductor(Base):
    __tablename__ = "conductores"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, unique=True)
    licencia = Column(String(20), nullable=False, unique=True)
    activo = Column(SmallInteger, nullable=False, default=1)

    usuario = relationship("Usuario", back_populates="conductor")
    rutas = relationship("Ruta", back_populates="conductor")
    viajes = relationship("Viaje", back_populates="conductor")


# 7. buses
class Bus(Base):
    __tablename__ = "buses"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    socio_id = Column(Integer, ForeignKey("socios.id"), nullable=False, index=True)
    placa = Column(String(15), nullable=False, unique=True, index=True)
    capacidad = Column(Integer, nullable=False)
    activo = Column(SmallInteger, nullable=False, default=1)

    socio = relationship("Socio", back_populates="buses")
    rutas = relationship("Ruta", back_populates="bus")
    viajes = relationship("Viaje", back_populates="bus")


# 8. instituciones_educativas
class InstitucionEducativa(Base):
    __tablename__ = "instituciones_educativas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cooperativa_id = Column(Integer, ForeignKey("cooperativas.id"), nullable=False, index=True)
    nombre = Column(String(200), nullable=False)
    direccion = Column(String(300), nullable=True)
    tipo = Column(String(50), nullable=True)
    geom = Column(PointGeometry, nullable=True)
    activa = Column(SmallInteger, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    cooperativa = relationship("Cooperativa", back_populates="instituciones")
    rutas = relationship("Ruta", back_populates="institucion")


# 9. rutas
class Ruta(Base):
    __tablename__ = "rutas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    cooperativa_id = Column(Integer, ForeignKey("cooperativas.id"), nullable=False, index=True)
    conductor_id = Column(Integer, ForeignKey("conductores.id"), nullable=False, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False, index=True)
    institucion_id = Column(Integer, ForeignKey("instituciones_educativas.id"), nullable=False, index=True)
    nombre = Column(String(100), nullable=False)
    sector = Column(String(120), nullable=True)
    turno = Column(Enum("AM", "PM", name="turno_ruta_enum"), nullable=False)
    hora_campana = Column(Time, nullable=True)
    activa = Column(SmallInteger, nullable=False, default=1)

    cooperativa = relationship("Cooperativa", back_populates="rutas")
    conductor = relationship("Conductor", back_populates="rutas")
    bus = relationship("Bus", back_populates="rutas")
    institucion = relationship("InstitucionEducativa", back_populates="rutas")
    paradas = relationship("Parada", back_populates="ruta", cascade="all, delete-orphan", order_by="Parada.orden")
    asignaciones = relationship("AsignacionEstudianteRuta", back_populates="ruta")
    viajes = relationship("Viaje", back_populates="ruta")


# 10. paradas
class Parada(Base):
    __tablename__ = "paradas"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ruta_id = Column(Integer, ForeignKey("rutas.id", ondelete="CASCADE"), nullable=False, index=True)
    orden = Column(Integer, nullable=False, default=1)
    nombre = Column(String(200), nullable=False)
    geom = Column(PointGeometry, nullable=True)
    radio_metros = Column(Integer, nullable=False, default=150)
    eta_estimado = Column(Time, nullable=True)

    ruta = relationship("Ruta", back_populates="paradas")
    asignaciones = relationship("AsignacionEstudianteRuta", back_populates="parada")
    etas_historicos = relationship("EtaHistorico", back_populates="parada")


# 11. estudiantes
class Estudiante(Base):
    __tablename__ = "estudiantes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    representante_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False, index=True)
    cedula = Column(String(10), nullable=False, unique=True, index=True)
    nombre = Column(String(100), nullable=False)
    apellido = Column(String(100), nullable=False)
    grado = Column(String(50), nullable=True)
    activo = Column(SmallInteger, nullable=False, default=1)
    domicilio_geom = Column(PointGeometry, nullable=True)
    domicilio_direccion = Column(String(300), nullable=True)

    representante = relationship("Usuario", back_populates="estudiantes_representados")
    tarifas = relationship("TarifaEstudiante", back_populates="estudiante", cascade="all, delete-orphan")
    asignaciones = relationship("AsignacionEstudianteRuta", back_populates="estudiante", cascade="all, delete-orphan")
    ausencias = relationship("AusenciaEstudiante", back_populates="estudiante")
    pagos = relationship("Pago", back_populates="estudiante")


# 12. tarifas_estudiante
class TarifaEstudiante(Base):
    __tablename__ = "tarifas_estudiante"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    estudiante_id = Column(Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True)
    monto_mensual = Column(Numeric(10, 2), nullable=False)
    vigente_desde = Column(Date, nullable=False)
    vigente_hasta = Column(Date, nullable=True)
    observacion = Column(String(300), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    estudiante = relationship("Estudiante", back_populates="tarifas")
    pagos = relationship("Pago", back_populates="tarifa")


# 13. asignaciones_estudiante_ruta
class AsignacionEstudianteRuta(Base):
    __tablename__ = "asignaciones_estudiante_ruta"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    estudiante_id = Column(Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True)
    ruta_id = Column(Integer, ForeignKey("rutas.id", ondelete="CASCADE"), nullable=False, index=True)
    parada_id = Column(Integer, ForeignKey("paradas.id"), nullable=False, index=True)
    activa = Column(SmallInteger, nullable=False, default=1)

    estudiante = relationship("Estudiante", back_populates="asignaciones")
    ruta = relationship("Ruta", back_populates="asignaciones")
    parada = relationship("Parada", back_populates="asignaciones")


# 14. viajes
class Viaje(Base):
    __tablename__ = "viajes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    ruta_id = Column(Integer, ForeignKey("rutas.id"), nullable=False, index=True)
    conductor_id = Column(Integer, ForeignKey("conductores.id"), nullable=False, index=True)
    bus_id = Column(Integer, ForeignKey("buses.id"), nullable=False, index=True)
    fecha = Column(Date, nullable=False, index=True)
    estado = Column(
        Enum("PROGRAMADO", "EN_CURSO", "FINALIZADO", "CANCELADO", name="estado_viaje_enum"),
        nullable=False,
        default="PROGRAMADO",
    )
    inicio_at = Column(DateTime, nullable=True)
    fin_at = Column(DateTime, nullable=True)

    ruta = relationship("Ruta", back_populates="viajes")
    conductor = relationship("Conductor", back_populates="viajes")
    bus = relationship("Bus", back_populates="viajes")
    novedades = relationship("NovedadViaje", back_populates="viaje", cascade="all, delete-orphan")
    ausencias = relationship("AusenciaEstudiante", back_populates="viaje", cascade="all, delete-orphan")
    posiciones_gps = relationship("PosicionGps", back_populates="viaje", cascade="all, delete-orphan")
    etas_historicos = relationship("EtaHistorico", back_populates="viaje", cascade="all, delete-orphan")


# 15. novedades_viaje
class NovedadViaje(Base):
    __tablename__ = "novedades_viaje"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    viaje_id = Column(Integer, ForeignKey("viajes.id", ondelete="CASCADE"), nullable=False, index=True)
    reportado_por_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=False)
    tipo = Column(
        Enum("ASISTENCIA", "RETRASO", "AVERIA", "TRAFICO", "INCIDENTE", "OTRO", name="tipo_novedad_enum"),
        nullable=False,
    )
    descripcion = Column(Text, nullable=True)
    estado = Column(
        Enum("ABIERTO", "EN_PROCESO", "RESUELTO", name="estado_novedad_enum"),
        nullable=False,
        default="ABIERTO",
    )
    ocurrido_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    resuelto_at = Column(DateTime, nullable=True)
    ubicacion = Column(PointGeometry, nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    viaje = relationship("Viaje", back_populates="novedades")
    reportado_por = relationship("Usuario")


# 16. ausencias_estudiante
class AusenciaEstudiante(Base):
    __tablename__ = "ausencias_estudiante"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    viaje_id = Column(Integer, ForeignKey("viajes.id", ondelete="CASCADE"), nullable=False, index=True)
    estudiante_id = Column(Integer, ForeignKey("estudiantes.id", ondelete="CASCADE"), nullable=False, index=True)
    anticipacion_min = Column(Integer, nullable=True)
    politica_aplicada = Column(String(50), nullable=True)
    estado = Column(
        Enum("REPORTADA", "CONFIRMADA", "RECHAZADA", "RECOGIDO", name="estado_ausencia_enum"),
        nullable=False,
        default="REPORTADA",
    )
    motivo_padre = Column(Text, nullable=True)
    responded_at = Column(DateTime, nullable=True)
    responded_by_usuario_id = Column(Integer, ForeignKey("usuarios.id"), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    viaje = relationship("Viaje", back_populates="ausencias")
    estudiante = relationship("Estudiante", back_populates="ausencias")
    responded_by = relationship("Usuario")


# 17. posiciones_gps
class PosicionGps(Base):
    __tablename__ = "posiciones_gps"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True, autoincrement=True)
    viaje_id = Column(Integer, ForeignKey("viajes.id", ondelete="CASCADE"), nullable=False, index=True)
    geom = Column(PointGeometry, nullable=False)
    velocidad_kmh = Column(Numeric(7, 2), nullable=True)
    heading = Column(Numeric(6, 2), nullable=True)
    recorded_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    viaje = relationship("Viaje", back_populates="posiciones_gps")


# 18. eta_historico
class EtaHistorico(Base):
    __tablename__ = "eta_historico"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    viaje_id = Column(Integer, ForeignKey("viajes.id", ondelete="CASCADE"), nullable=False, index=True)
    parada_id = Column(Integer, ForeignKey("paradas.id", ondelete="CASCADE"), nullable=False, index=True)
    observado_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    tiempo_real_seg = Column(Integer, nullable=True)
    distancia_m = Column(Numeric(12, 2), nullable=True)
    velocidad_prom_kmh = Column(Numeric(7, 2), nullable=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    viaje = relationship("Viaje", back_populates="etas_historicos")
    parada = relationship("Parada", back_populates="etas_historicos")


# 19. pagos
class Pago(Base):
    __tablename__ = "pagos"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    estudiante_id = Column(Integer, ForeignKey("estudiantes.id"), nullable=False, index=True)
    tarifa_id = Column(Integer, ForeignKey("tarifas_estudiante.id"), nullable=False, index=True)
    monto = Column(Numeric(10, 2), nullable=False)
    mes = Column(SmallInteger, nullable=False)
    anio = Column(SmallInteger, nullable=False)
    estado = Column(
        Enum("PENDIENTE", "EN_REVISION", "PAGADO", "RECHAZADO", name="estado_pago_enum"),
        nullable=False,
        default="PENDIENTE",
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    estudiante = relationship("Estudiante", back_populates="pagos")
    tarifa = relationship("TarifaEstudiante", back_populates="pagos")
    comprobantes = relationship("Comprobante", back_populates="pago", cascade="all, delete-orphan")


# 20. comprobantes
class Comprobante(Base):
    __tablename__ = "comprobantes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    pago_id = Column(Integer, ForeignKey("pagos.id", ondelete="CASCADE"), nullable=False, index=True)
    canal = Column(
        Enum("APP_MOVIL", "WEB", "WHATSAPP", "VENTANILLA", name="canal_comprobante_enum"),
        nullable=False,
        default="APP_MOVIL",
    )
    archivo_url = Column(String(500), nullable=False)
    banco = Column(String(100), nullable=True)
    monto_extraido = Column(Numeric(10, 2), nullable=True)
    fecha_transferencia = Column(Date, nullable=True)
    referencia_extraida = Column(String(100), nullable=True)
    ocr_confianza = Column(Numeric(5, 2), nullable=True)
    estado = Column(
        Enum("PENDIENTE_REVISION", "VALIDADO", "OBSERVADO", "RECHAZADO", name="estado_comprobante_enum"),
        nullable=False,
        default="PENDIENTE_REVISION",
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    pago = relationship("Pago", back_populates="comprobantes")


# 21. notificaciones
class Notificacion(Base):
    __tablename__ = "notificaciones"

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, index=True, autoincrement=True)
    usuario_id = Column(Integer, ForeignKey("usuarios.id", ondelete="CASCADE"), nullable=False, index=True)
    titulo = Column(String(200), nullable=False)
    mensaje = Column(Text, nullable=False)
    tipo = Column(String(50), nullable=False)
    leida = Column(SmallInteger, nullable=False, default=0)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    usuario = relationship("Usuario", back_populates="notificaciones")

