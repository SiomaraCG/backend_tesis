-- ============================================================================
-- SCRIPT DDL: SISTEMA DE GESTIÓN Y MONITOREO DE TRANSPORTE ESCOLAR
-- Basado 100% en las 21 tablas del diagrama Entidad-Relación (model.pdf)
-- Motor: MySQL 8.0+ (Soporte Espacial POINT)
-- ============================================================================

CREATE DATABASE IF NOT EXISTS transporte_escolar
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE transporte_escolar;

-- 1. Tabla: cooperativas
CREATE TABLE IF NOT EXISTS cooperativas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(200) NOT NULL,
    ruc VARCHAR(13) NOT NULL UNIQUE,
    direccion VARCHAR(300) NULL,
    telefono VARCHAR(20) NULL,
    email VARCHAR(100) NULL,
    activa TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB;

-- 2. Tabla: usuarios
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cooperativa_id INT NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    cedula VARCHAR(10) NOT NULL UNIQUE,
    telefono VARCHAR(20) NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_usuarios_cooperativa (cooperativa_id),
    CONSTRAINT fk_usuarios_cooperativa FOREIGN KEY (cooperativa_id)
        REFERENCES cooperativas (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 3. Tabla: roles
CREATE TABLE IF NOT EXISTS roles (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(30) NOT NULL UNIQUE,
    descripcion VARCHAR(200) NULL
) ENGINE=InnoDB;

-- 4. Tabla: usuario_rol
CREATE TABLE IF NOT EXISTS usuario_rol (
    usuario_id INT NOT NULL,
    rol_id INT NOT NULL,
    PRIMARY KEY (usuario_id, rol_id),
    INDEX idx_usuario_rol_rol (rol_id),
    CONSTRAINT fk_usuario_rol_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_usuario_rol_rol FOREIGN KEY (rol_id)
        REFERENCES roles (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 5. Tabla: socios
CREATE TABLE IF NOT EXISTS socios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cooperativa_id INT NOT NULL,
    usuario_id INT NOT NULL UNIQUE,
    nombre_razon_social VARCHAR(200) NOT NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    INDEX idx_socios_cooperativa (cooperativa_id),
    CONSTRAINT fk_socios_cooperativa FOREIGN KEY (cooperativa_id)
        REFERENCES cooperativas (id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_socios_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 6. Tabla: conductores
CREATE TABLE IF NOT EXISTS conductores (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL UNIQUE,
    licencia VARCHAR(20) NOT NULL UNIQUE,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    CONSTRAINT fk_conductores_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 7. Tabla: buses
CREATE TABLE IF NOT EXISTS buses (
    id INT AUTO_INCREMENT PRIMARY KEY,
    socio_id INT NOT NULL,
    placa VARCHAR(15) NOT NULL UNIQUE,
    capacidad INT NOT NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    INDEX idx_buses_socio (socio_id),
    CONSTRAINT fk_buses_socio FOREIGN KEY (socio_id)
        REFERENCES socios (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 8. Tabla: instituciones_educativas
CREATE TABLE IF NOT EXISTS instituciones_educativas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cooperativa_id INT NOT NULL,
    nombre VARCHAR(200) NOT NULL,
    direccion VARCHAR(300) NULL,
    tipo VARCHAR(50) NULL,
    geom POINT NULL,
    activa TINYINT(1) NOT NULL DEFAULT 1,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_instituciones_cooperativa (cooperativa_id),
    CONSTRAINT fk_instituciones_cooperativa FOREIGN KEY (cooperativa_id)
        REFERENCES cooperativas (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 9. Tabla: rutas
CREATE TABLE IF NOT EXISTS rutas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    cooperativa_id INT NOT NULL,
    conductor_id INT NOT NULL,
    bus_id INT NOT NULL,
    institucion_id INT NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    sector VARCHAR(120) NULL,
    turno ENUM('AM', 'PM') NOT NULL,
    hora_campana TIME NULL,
    activa TINYINT(1) NOT NULL DEFAULT 1,
    INDEX idx_rutas_cooperativa (cooperativa_id),
    INDEX idx_rutas_conductor (conductor_id),
    INDEX idx_rutas_bus (bus_id),
    INDEX idx_rutas_institucion (institucion_id),
    CONSTRAINT fk_rutas_cooperativa FOREIGN KEY (cooperativa_id)
        REFERENCES cooperativas (id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_rutas_conductor FOREIGN KEY (conductor_id)
        REFERENCES conductores (id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_rutas_bus FOREIGN KEY (bus_id)
        REFERENCES buses (id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_rutas_institucion FOREIGN KEY (institucion_id)
        REFERENCES instituciones_educativas (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 10. Tabla: paradas
CREATE TABLE IF NOT EXISTS paradas (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ruta_id INT NOT NULL,
    orden INT NOT NULL DEFAULT 1,
    nombre VARCHAR(200) NOT NULL,
    geom POINT NULL,
    radio_metros INT NOT NULL DEFAULT 150,
    eta_estimado TIME NULL,
    INDEX idx_paradas_ruta (ruta_id),
    CONSTRAINT fk_paradas_ruta FOREIGN KEY (ruta_id)
        REFERENCES rutas (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 11. Tabla: estudiantes
CREATE TABLE IF NOT EXISTS estudiantes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    representante_usuario_id INT NOT NULL,
    cedula VARCHAR(10) NOT NULL UNIQUE,
    nombre VARCHAR(100) NOT NULL,
    apellido VARCHAR(100) NOT NULL,
    grado VARCHAR(50) NULL,
    activo TINYINT(1) NOT NULL DEFAULT 1,
    domicilio_geom POINT NULL,
    domicilio_direccion VARCHAR(300) NULL,
    INDEX idx_estudiantes_representante (representante_usuario_id),
    CONSTRAINT fk_estudiantes_representante FOREIGN KEY (representante_usuario_id)
        REFERENCES usuarios (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 12. Tabla: tarifas_estudiante
CREATE TABLE IF NOT EXISTS tarifas_estudiante (
    id INT AUTO_INCREMENT PRIMARY KEY,
    estudiante_id INT NOT NULL,
    monto_mensual DECIMAL(10,2) NOT NULL,
    vigente_desde DATE NOT NULL,
    vigente_hasta DATE NULL,
    observacion VARCHAR(300) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_tarifas_estudiante (estudiante_id),
    CONSTRAINT fk_tarifas_estudiante FOREIGN KEY (estudiante_id)
        REFERENCES estudiantes (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 13. Tabla: asignaciones_estudiante_ruta
CREATE TABLE IF NOT EXISTS asignaciones_estudiante_ruta (
    id INT AUTO_INCREMENT PRIMARY KEY,
    estudiante_id INT NOT NULL,
    ruta_id INT NOT NULL,
    parada_id INT NOT NULL,
    activa TINYINT(1) NOT NULL DEFAULT 1,
    INDEX idx_asignaciones_estudiante (estudiante_id),
    INDEX idx_asignaciones_ruta (ruta_id),
    INDEX idx_asignaciones_parada (parada_id),
    CONSTRAINT fk_asignaciones_estudiante FOREIGN KEY (estudiante_id)
        REFERENCES estudiantes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_asignaciones_ruta FOREIGN KEY (ruta_id)
        REFERENCES rutas (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_asignaciones_parada FOREIGN KEY (parada_id)
        REFERENCES paradas (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 14. Tabla: viajes
CREATE TABLE IF NOT EXISTS viajes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    ruta_id INT NOT NULL,
    conductor_id INT NOT NULL,
    bus_id INT NOT NULL,
    fecha DATE NOT NULL,
    estado ENUM('PROGRAMADO', 'EN_CURSO', 'FINALIZADO', 'CANCELADO') NOT NULL DEFAULT 'PROGRAMADO',
    inicio_at DATETIME(6) NULL,
    fin_at DATETIME(6) NULL,
    INDEX idx_viajes_ruta_fecha (ruta_id, fecha),
    CONSTRAINT fk_viajes_ruta FOREIGN KEY (ruta_id)
        REFERENCES rutas (id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_viajes_conductor FOREIGN KEY (conductor_id)
        REFERENCES conductores (id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_viajes_bus FOREIGN KEY (bus_id)
        REFERENCES buses (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 15. Tabla: novedades_viaje
CREATE TABLE IF NOT EXISTS novedades_viaje (
    id INT AUTO_INCREMENT PRIMARY KEY,
    viaje_id INT NOT NULL,
    reportado_por_usuario_id INT NOT NULL,
    tipo ENUM('ASISTENCIA', 'RETRASO', 'AVERIA', 'TRAFICO', 'INCIDENTE', 'OTRO') NOT NULL,
    descripcion TEXT NULL,
    estado ENUM('ABIERTO', 'EN_PROCESO', 'RESUELTO') NOT NULL DEFAULT 'ABIERTO',
    ocurrido_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    resuelto_at DATETIME(6) NULL,
    ubicacion POINT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_novedades_viaje (viaje_id),
    CONSTRAINT fk_novedades_viaje FOREIGN KEY (viaje_id)
        REFERENCES viajes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_novedades_usuario FOREIGN KEY (reportado_por_usuario_id)
        REFERENCES usuarios (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 16. Tabla: ausencias_estudiante
CREATE TABLE IF NOT EXISTS ausencias_estudiante (
    id INT AUTO_INCREMENT PRIMARY KEY,
    viaje_id INT NOT NULL,
    estudiante_id INT NOT NULL,
    anticipacion_min INT NULL,
    politica_aplicada VARCHAR(50) NULL,
    estado ENUM('REPORTADA', 'CONFIRMADA', 'RECHAZADA', 'RECOGIDO') NOT NULL DEFAULT 'REPORTADA',
    motivo_padre TEXT NULL,
    responded_at DATETIME(6) NULL,
    responded_by_usuario_id INT NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_ausencias_viaje (viaje_id),
    INDEX idx_ausencias_estudiante (estudiante_id),
    CONSTRAINT fk_ausencias_viaje FOREIGN KEY (viaje_id)
        REFERENCES viajes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_ausencias_estudiante FOREIGN KEY (estudiante_id)
        REFERENCES estudiantes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_ausencias_responded_by FOREIGN KEY (responded_by_usuario_id)
        REFERENCES usuarios (id) ON DELETE SET NULL ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 17. Tabla: posiciones_gps
CREATE TABLE IF NOT EXISTS posiciones_gps (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    viaje_id INT NOT NULL,
    geom POINT NOT NULL,
    velocidad_kmh DECIMAL(7,2) NULL,
    heading DECIMAL(6,2) NULL,
    recorded_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_posiciones_viaje_recorded (viaje_id, recorded_at),
    CONSTRAINT fk_posiciones_viaje FOREIGN KEY (viaje_id)
        REFERENCES viajes (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 18. Tabla: eta_historico
CREATE TABLE IF NOT EXISTS eta_historico (
    id INT AUTO_INCREMENT PRIMARY KEY,
    viaje_id INT NOT NULL,
    parada_id INT NOT NULL,
    observado_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    tiempo_real_seg INT NULL,
    distancia_m DECIMAL(12,2) NULL,
    velocidad_prom_kmh DECIMAL(7,2) NULL,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_eta_viaje_parada (viaje_id, parada_id),
    CONSTRAINT fk_eta_viaje FOREIGN KEY (viaje_id)
        REFERENCES viajes (id) ON DELETE CASCADE ON UPDATE CASCADE,
    CONSTRAINT fk_eta_parada FOREIGN KEY (parada_id)
        REFERENCES paradas (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 19. Tabla: pagos
CREATE TABLE IF NOT EXISTS pagos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    estudiante_id INT NOT NULL,
    tarifa_id INT NOT NULL,
    monto DECIMAL(10,2) NOT NULL,
    mes TINYINT NOT NULL,
    anio SMALLINT NOT NULL,
    estado ENUM('PENDIENTE', 'EN_REVISION', 'PAGADO', 'RECHAZADO') NOT NULL DEFAULT 'PENDIENTE',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    updated_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
    INDEX idx_pagos_estudiante_periodo (estudiante_id, anio, mes),
    CONSTRAINT fk_pagos_estudiante FOREIGN KEY (estudiante_id)
        REFERENCES estudiantes (id) ON DELETE RESTRICT ON UPDATE CASCADE,
    CONSTRAINT fk_pagos_tarifa FOREIGN KEY (tarifa_id)
        REFERENCES tarifas_estudiante (id) ON DELETE RESTRICT ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 20. Tabla: comprobantes
CREATE TABLE IF NOT EXISTS comprobantes (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pago_id INT NOT NULL,
    canal ENUM('APP_MOVIL', 'WEB', 'WHATSAPP', 'VENTANILLA') NOT NULL DEFAULT 'APP_MOVIL',
    archivo_url VARCHAR(500) NOT NULL,
    banco VARCHAR(100) NULL,
    monto_extraido DECIMAL(10,2) NULL,
    fecha_transferencia DATE NULL,
    referencia_extraida VARCHAR(100) NULL,
    ocr_confianza DECIMAL(5,2) NULL,
    estado ENUM('PENDIENTE_REVISION', 'VALIDADO', 'OBSERVADO', 'RECHAZADO') NOT NULL DEFAULT 'PENDIENTE_REVISION',
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_comprobantes_pago (pago_id),
    CONSTRAINT fk_comprobantes_pago FOREIGN KEY (pago_id)
        REFERENCES pagos (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

-- 21. Tabla: notificaciones
CREATE TABLE IF NOT EXISTS notificaciones (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    usuario_id INT NOT NULL,
    titulo VARCHAR(200) NOT NULL,
    mensaje TEXT NOT NULL,
    tipo VARCHAR(50) NOT NULL,
    leida TINYINT(1) NOT NULL DEFAULT 0,
    created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
    INDEX idx_notificaciones_usuario_leida (usuario_id, leida),
    CONSTRAINT fk_notificaciones_usuario FOREIGN KEY (usuario_id)
        REFERENCES usuarios (id) ON DELETE CASCADE ON UPDATE CASCADE
) ENGINE=InnoDB;

