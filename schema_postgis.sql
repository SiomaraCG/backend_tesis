-- ============================================================================
-- SCRIPT DDL: SISTEMA DE GESTIÓN Y MONITOREO DE TRANSPORTE ESCOLAR
-- Motor: PostgreSQL 16 + Extensión Espacial PostGIS 3.4
-- Basado 100% en las 21 tablas del diagrama Entidad-Relación (model.pdf)
-- Se ejecuta automáticamente al levantar el contenedor Docker por primera vez
-- ============================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- Tipos ENUM personalizados del modelo
DO $$ BEGIN
    CREATE TYPE turno_ruta_enum AS ENUM ('AM', 'PM');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE estado_viaje_enum AS ENUM ('PROGRAMADO', 'EN_CURSO', 'FINALIZADO', 'CANCELADO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE tipo_novedad_enum AS ENUM ('ASISTENCIA', 'RETRASO', 'AVERIA', 'TRAFICO', 'INCIDENTE', 'OTRO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE estado_novedad_enum AS ENUM ('ABIERTO', 'EN_PROCESO', 'RESUELTO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE estado_ausencia_enum AS ENUM ('REPORTADA', 'CONFIRMADA', 'RECHAZADA', 'RECOGIDO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE estado_pago_enum AS ENUM ('PENDIENTE', 'EN_REVISION', 'PAGADO', 'RECHAZADO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE canal_comprobante_enum AS ENUM ('APP_MOVIL', 'WEB', 'WHATSAPP', 'VENTANILLA');
EXCEPTION WHEN duplicate_object THEN null; END $$;

DO $$ BEGIN
    CREATE TYPE estado_comprobante_enum AS ENUM ('PENDIENTE_REVISION', 'VALIDADO', 'OBSERVADO', 'RECHAZADO');
EXCEPTION WHEN duplicate_object THEN null; END $$;

-- 1. Tabla: cooperativas
CREATE TABLE IF NOT EXISTS cooperativas (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL,
    ruc VARCHAR(13) NOT NULL UNIQUE,
    direccion VARCHAR(300) NULL,
    telefono VARCHAR(20) NULL,
    email VARCHAR(100) NULL,
    activa SMALLINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 2. Tabla: usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    cooperativa_id INT NOT NULL REFERENCES cooperativas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    cedula VARCHAR(10) NOT NULL UNIQUE,
    telefono VARCHAR(20) NULL,
    activo SMALLINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_usuarios_cooperativa ON usuarios(cooperativa_id);

-- 3. Tabla: roles
CREATE TABLE IF NOT EXISTS roles (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL UNIQUE,
    descripcion VARCHAR(200) NULL
);

-- 4. Tabla: usuario_rol
CREATE TABLE IF NOT EXISTS usuario_rol (
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE ON UPDATE CASCADE,
    rol_id INT NOT NULL REFERENCES roles(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    PRIMARY KEY (usuario_id, rol_id)
);

-- 5. Tabla: socios
CREATE TABLE IF NOT EXISTS socios (
    id SERIAL PRIMARY KEY,
    cooperativa_id INT NOT NULL REFERENCES cooperativas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    usuario_id INT NOT NULL UNIQUE REFERENCES usuarios(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    nombre_razon_social VARCHAR(200) NOT NULL,
    activo SMALLINT NOT NULL DEFAULT 1
);

-- 6. Tabla: conductores
CREATE TABLE IF NOT EXISTS conductores (
    id SERIAL PRIMARY KEY,
    usuario_id INT NOT NULL UNIQUE REFERENCES usuarios(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    licencia VARCHAR(20) NOT NULL UNIQUE,
    activo SMALLINT NOT NULL DEFAULT 1
);

-- 7. Tabla: buses
CREATE TABLE IF NOT EXISTS buses (
    id SERIAL PRIMARY KEY,
    socio_id INT NOT NULL REFERENCES socios(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    placa VARCHAR(15) NOT NULL UNIQUE,
    capacidad INT NOT NULL,
    activo SMALLINT NOT NULL DEFAULT 1
);

-- 8. Tabla: instituciones_educativas (con GEOMETRY Point SRID 4326 en PostGIS)
CREATE TABLE IF NOT EXISTS instituciones_educativas (
    id SERIAL PRIMARY KEY,
    cooperativa_id INT NOT NULL REFERENCES cooperativas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    nombre VARCHAR(200) NOT NULL,
    direccion VARCHAR(300) NULL,
    tipo VARCHAR(50) NULL,
    geom GEOMETRY(Point, 4326) NULL,
    activa SMALLINT NOT NULL DEFAULT 1,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_instituciones_geom ON instituciones_educativas USING GIST (geom);

-- 9. Tabla: rutas
CREATE TABLE IF NOT EXISTS rutas (
    id SERIAL PRIMARY KEY,
    cooperativa_id INT NOT NULL REFERENCES cooperativas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    conductor_id INT NOT NULL REFERENCES conductores(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    bus_id INT NOT NULL REFERENCES buses(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    institucion_id INT NOT NULL REFERENCES instituciones_educativas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    nombre VARCHAR(100) NOT NULL,
    sector VARCHAR(120) NULL,
    turno turno_ruta_enum NOT NULL,
    hora_campana TIME NULL,
    activa SMALLINT NOT NULL DEFAULT 1
);

-- 10. Tabla: paradas (con GEOMETRY Point SRID 4326 en PostGIS)
CREATE TABLE IF NOT EXISTS paradas (
    id SERIAL PRIMARY KEY,
    ruta_id INT NOT NULL REFERENCES rutas(id) ON DELETE CASCADE ON UPDATE CASCADE,
    orden INT NOT NULL DEFAULT 1,
    nombre VARCHAR(200) NOT NULL,
    geom GEOMETRY(Point, 4326) NULL,
    radio_metros INT NOT NULL DEFAULT 150,
    eta_estimado TIME NULL
);
CREATE INDEX IF NOT EXISTS idx_paradas_geom ON paradas USING GIST (geom);

-- 11. Tabla: estudiantes (con domicilio_geom Point SRID 4326 en PostGIS)
CREATE TABLE IF NOT EXISTS estudiantes (
    id SERIAL PRIMARY KEY,
    representante_usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    cedula VARCHAR(10) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    grado VARCHAR(50) NULL,
    activo SMALLINT NOT NULL DEFAULT 1,
    domicilio_geom GEOMETRY(Point, 4326) NULL,
    domicilio_direccion VARCHAR(300) NULL
);
CREATE INDEX IF NOT EXISTS idx_estudiantes_geom ON estudiantes USING GIST (domicilio_geom);

-- 12. Tabla: tarifas_estudiante
CREATE TABLE IF NOT EXISTS tarifas_estudiante (
    id SERIAL PRIMARY KEY,
    estudiante_id INT NOT NULL REFERENCES estudiantes(id) ON DELETE CASCADE ON UPDATE CASCADE,
    monto_mensual NUMERIC(10,2) NOT NULL,
    vigente_desde DATE NOT NULL,
    vigente_hasta DATE NULL,
    observacion VARCHAR(300) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 13. Tabla: asignaciones_estudiante_ruta
CREATE TABLE IF NOT EXISTS asignaciones_estudiante_ruta (
    id SERIAL PRIMARY KEY,
    estudiante_id INT NOT NULL REFERENCES estudiantes(id) ON DELETE CASCADE ON UPDATE CASCADE,
    ruta_id INT NOT NULL REFERENCES rutas(id) ON DELETE CASCADE ON UPDATE CASCADE,
    parada_id INT NOT NULL REFERENCES paradas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    activa SMALLINT NOT NULL DEFAULT 1
);

-- 14. Tabla: viajes
CREATE TABLE IF NOT EXISTS viajes (
    id SERIAL PRIMARY KEY,
    ruta_id INT NOT NULL REFERENCES rutas(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    conductor_id INT NOT NULL REFERENCES conductores(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    bus_id INT NOT NULL REFERENCES buses(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    fecha DATE NOT NULL,
    estado estado_viaje_enum NOT NULL DEFAULT 'PROGRAMADO',
    inicio_at TIMESTAMP(6) NULL,
    fin_at TIMESTAMP(6) NULL
);

-- 15. Tabla: novedades_viaje (con ubicacion Point SRID 4326 en PostGIS)
CREATE TABLE IF NOT EXISTS novedades_viaje (
    id SERIAL PRIMARY KEY,
    viaje_id INT NOT NULL REFERENCES viajes(id) ON DELETE CASCADE ON UPDATE CASCADE,
    reportado_por_usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    tipo tipo_novedad_enum NOT NULL,
    descripcion TEXT NULL,
    estado estado_novedad_enum NOT NULL DEFAULT 'ABIERTO',
    ocurrido_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resuelto_at TIMESTAMP(6) NULL,
    ubicacion GEOMETRY(Point, 4326) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 16. Tabla: ausencias_estudiante
CREATE TABLE IF NOT EXISTS ausencias_estudiante (
    id SERIAL PRIMARY KEY,
    viaje_id INT NOT NULL REFERENCES viajes(id) ON DELETE CASCADE ON UPDATE CASCADE,
    estudiante_id INT NOT NULL REFERENCES estudiantes(id) ON DELETE CASCADE ON UPDATE CASCADE,
    anticipacion_min INT NULL,
    politica_aplicada VARCHAR(50) NULL,
    estado estado_ausencia_enum NOT NULL DEFAULT 'REPORTADA',
    motivo_padre TEXT NULL,
    responded_at TIMESTAMP(6) NULL,
    responded_by_usuario_id INT NULL REFERENCES usuarios(id) ON DELETE SET NULL ON UPDATE CASCADE,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 17. Tabla: posiciones_gps (con geom Point SRID 4326 en PostGIS)
CREATE TABLE IF NOT EXISTS posiciones_gps (
    id BIGSERIAL PRIMARY KEY,
    viaje_id INT NOT NULL REFERENCES viajes(id) ON DELETE CASCADE ON UPDATE CASCADE,
    geom GEOMETRY(Point, 4326) NOT NULL,
    velocidad_kmh NUMERIC(7,2) NULL,
    heading NUMERIC(6,2) NULL,
    recorded_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_posiciones_gps_geom ON posiciones_gps USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_posiciones_viaje_recorded ON posiciones_gps (viaje_id, recorded_at);

-- 18. Tabla: eta_historico
CREATE TABLE IF NOT EXISTS eta_historico (
    id SERIAL PRIMARY KEY,
    viaje_id INT NOT NULL REFERENCES viajes(id) ON DELETE CASCADE ON UPDATE CASCADE,
    parada_id INT NOT NULL REFERENCES paradas(id) ON DELETE CASCADE ON UPDATE CASCADE,
    observado_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tiempo_real_seg INT NULL,
    distancia_m NUMERIC(12,2) NULL,
    velocidad_prom_kmh NUMERIC(7,2) NULL,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 19. Tabla: pagos
CREATE TABLE IF NOT EXISTS pagos (
    id SERIAL PRIMARY KEY,
    estudiante_id INT NOT NULL REFERENCES estudiantes(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    tarifa_id INT NOT NULL REFERENCES tarifas_estudiante(id) ON DELETE RESTRICT ON UPDATE CASCADE,
    monto NUMERIC(10,2) NOT NULL,
    mes SMALLINT NOT NULL,
    anio SMALLINT NOT NULL,
    estado estado_pago_enum NOT NULL DEFAULT 'PENDIENTE',
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 20. Tabla: comprobantes
CREATE TABLE IF NOT EXISTS comprobantes (
    id SERIAL PRIMARY KEY,
    pago_id INT NOT NULL REFERENCES pagos(id) ON DELETE CASCADE ON UPDATE CASCADE,
    canal canal_comprobante_enum NOT NULL DEFAULT 'APP_MOVIL',
    archivo_url VARCHAR(500) NOT NULL,
    banco VARCHAR(100) NULL,
    monto_extraido NUMERIC(10,2) NULL,
    fecha_transferencia DATE NULL,
    referencia_extraida VARCHAR(100) NULL,
    ocr_confianza NUMERIC(5,2) NULL,
    estado estado_comprobante_enum NOT NULL DEFAULT 'PENDIENTE_REVISION',
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 21. Tabla: notificaciones
CREATE TABLE IF NOT EXISTS notificaciones (
    id BIGSERIAL PRIMARY KEY,
    usuario_id INT NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE ON UPDATE CASCADE,
    titulo VARCHAR(200) NOT NULL,
    mensaje TEXT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    leida SMALLINT NOT NULL DEFAULT 0,
    created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP
);

