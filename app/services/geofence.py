"""
Motor de Geocercas Espaciales (`radio_metros`) y Gestor de Canales WebSocket en Tiempo Real (Capa 3: Servicios - RF-09, RF-10, RF-11).
Responsabilidades:
  1. Procesar cada coordenada GPS emitida por la unidad en `posiciones_gps`.
  2. Calcular la distancia esférica en metros hacia cada parada de la ruta.
  3. Detectar la entrada al `radio_metros` configurable de cada parada (`RF-11`).
  4. Registrar automáticamente el paso por la parada en `eta_historico` (sin duplicar alertas en el mismo viaje).
  5. Generar notificaciones automáticas en la tabla `notificaciones` para los padres vinculados a esa parada.
  6. Retransmitir (Broadcast) la ubicación y alertas por WebSocket a los padres conectados (`RF-10`).
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Tuple
from fastapi import WebSocket
from sqlalchemy.orm import Session

from app.models import (
    AsignacionEstudianteRuta,
    AusenciaEstudiante,
    EtaHistorico,
    Notificacion,
    Parada,
    PosicionGps,
    Viaje,
    haversine_distance_m,
    parse_point,
)
from app.schemas.common import CoordenadaSchema
from app.schemas.gps_notificaciones import (
    AlertaProximidadEmitidaSchema,
    PosicionGpsResponse,
)


class RouteTrackingConnectionManager:
    """Gestor de conexiones WebSocket agrupadas por `ruta_id` para monitoreo en tiempo real (RF-09, RF-10)."""

    def __init__(self) -> None:
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, ruta_id: int, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.setdefault(ruta_id, []).append(websocket)

    def disconnect(self, ruta_id: int, websocket: WebSocket) -> None:
        if ruta_id in self.active_connections:
            if websocket in self.active_connections[ruta_id]:
                self.active_connections[ruta_id].remove(websocket)
            if not self.active_connections[ruta_id]:
                del self.active_connections[ruta_id]

    async def broadcast_to_route(self, ruta_id: int, message: dict) -> None:
        connections = list(self.active_connections.get(ruta_id, []))
        stale: List[WebSocket] = []
        for ws in connections:
            try:
                await ws.send_json(message)
            except Exception:
                stale.append(ws)
        for ws in stale:
            self.disconnect(ruta_id, ws)


ws_manager = RouteTrackingConnectionManager()


def procesar_posicion_y_geocercas(
    db: Session,
    viaje: Viaje,
    lat: float,
    lng: float,
    velocidad_kmh: Optional[Decimal] = Decimal("0.00"),
    heading: Optional[Decimal] = Decimal("0.00"),
) -> PosicionGpsResponse:
    """
    Guarda la posición GPS en `posiciones_gps`, evalúa geocercas (`parada.radio_metros`)
    y dispara notificaciones automáticas a los padres cuando el bus está próximo (`RF-09`, `RF-11`).
    """
    ahora = datetime.utcnow()

    # 1. Insertar registro en posiciones_gps
    nueva_pos = PosicionGps(
        viaje_id=viaje.id,
        geom={"lat": lat, "lng": lng},
        velocidad_kmh=velocidad_kmh,
        heading=heading,
        recorded_at=ahora,
    )
    db.add(nueva_pos)
    db.flush()

    # 2. Consultar paradas de la ruta y verificar cuáles ya fueron notificadas en este viaje
    paradas: List[Parada] = (
        db.query(Parada)
        .filter(Parada.ruta_id == viaje.ruta_id)
        .order_by(Parada.orden.asc())
        .all()
    )

    paradas_ya_observadas = {
        eh.parada_id
        for eh in db.query(EtaHistorico).filter(EtaHistorico.viaje_id == viaje.id).all()
    }

    ausentes_viaje_ids = {
        a.estudiante_id
        for a in db.query(AusenciaEstudiante)
        .filter(
            AusenciaEstudiante.viaje_id == viaje.id,
            AusenciaEstudiante.estado.in_(["REPORTADA", "CONFIRMADA"]),
        )
        .all()
    }

    parada_cercana: Optional[Parada] = None
    distancia_minima: Optional[float] = None
    alertas_disparadas: List[AlertaProximidadEmitidaSchema] = []

    for parada in paradas:
        p_geom = parse_point(parada.geom)
        if not p_geom:
            continue

        dist_m = haversine_distance_m(
            lat, lng, p_geom["lat"], p_geom["lng"]
        )
        if distancia_minima is None or dist_m < distancia_minima:
            distancia_minima = dist_m
            parada_cercana = parada

        # 3. Evaluación de geocerca (RF-11): ¿Entró al radio configurable de la parada?
        radio_m = parada.radio_metros or 150
        if dist_m <= float(radio_m) and parada.id not in paradas_ya_observadas:
            tiempo_real_seg = 0
            if viaje.inicio_at:
                tiempo_real_seg = max(
                    0, int((ahora - viaje.inicio_at).total_seconds())
                )

            # Registrar el evento en eta_historico para auditoría y evitar alertas repetidas
            eta_hist = EtaHistorico(
                viaje_id=viaje.id,
                parada_id=parada.id,
                observado_at=ahora,
                tiempo_real_seg=tiempo_real_seg,
                distancia_m=Decimal(f"{dist_m:.2f}"),
                velocidad_prom_kmh=velocidad_kmh,
                created_at=ahora,
            )
            db.add(eta_hist)
            paradas_ya_observadas.add(parada.id)

            # Identificar a los representantes de los estudiantes asignados a esta parada
            asignaciones_parada = (
                db.query(AsignacionEstudianteRuta)
                .filter(
                    AsignacionEstudianteRuta.ruta_id == viaje.ruta_id,
                    AsignacionEstudianteRuta.parada_id == parada.id,
                    AsignacionEstudianteRuta.activa == 1,
                )
                .all()
            )

            padres_ids = set()
            for asig in asignaciones_parada:
                if asig.estudiante and asig.estudiante.activo == 1:
                    if asig.estudiante_id not in ausentes_viaje_ids:
                        padres_ids.add(asig.estudiante.representante_usuario_id)

            placa_bus = viaje.bus.placa if viaje.bus else "Unidad Escolar"
            titulo_alerta = f"Transporte próximo a {parada.nombre}"
            mensaje_alerta = (
                f"La unidad {placa_bus} de la ruta '{viaje.ruta.nombre if viaje.ruta else ''}' "
                f"se encuentra a {int(round(dist_m))} metros del punto de recogida '{parada.nombre}' "
                f"(radio configurado: {radio_m} m). Por favor aliste al estudiante."
            )

            for padre_uid in padres_ids:
                db.add(
                    Notificacion(
                        usuario_id=padre_uid,
                        titulo=titulo_alerta,
                        mensaje=mensaje_alerta,
                        tipo="PROXIMIDAD_PARADA",
                        leida=0,
                        created_at=ahora,
                    )
                )

            alertas_disparadas.append(
                AlertaProximidadEmitidaSchema(
                    parada_id=parada.id,
                    parada_nombre=parada.nombre,
                    distancia_m=round(dist_m, 2),
                    radio_configurado_m=radio_m,
                    padres_notificados_ids=sorted(list(padres_ids)),
                    mensaje=mensaje_alerta,
                )
            )

    db.commit()
    db.refresh(nueva_pos)

    return PosicionGpsResponse(
        id=nueva_pos.id,
        viaje_id=viaje.id,
        ruta_id=viaje.ruta_id,
        geom=CoordenadaSchema(lat=lat, lng=lng),
        velocidad_kmh=nueva_pos.velocidad_kmh,
        heading=nueva_pos.heading,
        recorded_at=nueva_pos.recorded_at,
        parada_mas_cercana_id=parada_cercana.id if parada_cercana else None,
        parada_mas_cercana_nombre=parada_cercana.nombre if parada_cercana else None,
        distancia_parada_mas_cercana_m=round(distancia_minima, 2) if distancia_minima is not None else None,
        alertas_disparadas=alertas_disparadas,
    )
