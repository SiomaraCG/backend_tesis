"""Controlador de Monitoreo GPS en Tiempo Real, WebSockets y Notificaciones de Proximidad (RF-09, RF-10, RF-11, RF-15)."""
from typing import List
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.orm import Session

from app.core.database import SessionLocal, get_db
from app.core.deps import get_current_user, get_user_roles, require_role
from app.core.security import decode_access_token
from app.models import (
    AsignacionEstudianteRuta,
    Estudiante,
    EtaHistorico,
    Notificacion,
    Parada,
    PosicionGps,
    Ruta,
    Usuario,
    Viaje,
    haversine_distance_m,
    parse_point,
)
from app.schemas.common import CoordenadaSchema
from app.schemas.gps_notificaciones import (
    DistanciaParadaResumenSchema,
    MonitoreoRutaActualResponse,
    NotificacionResponse,
    PosicionGpsResponse,
    RegistrarPosicionGpsRequest,
)
from app.services.geofence import procesar_posicion_y_geocercas, ws_manager

router = APIRouter(prefix="/gps", tags=["Monitoreo GPS y Geocercas (RF-09, RF-10, RF-11)"])


def _verificar_acceso_monitoreo_ruta(db: Session, current_user: Usuario, ruta: Ruta) -> None:
    """Garantiza que solo el Admin, el Conductor de la ruta o los Padres vinculados a esa ruta vean su GPS (RF-10, RF-15)."""
    roles = set(get_user_roles(current_user))
    if "ADMIN" in roles:
        return

    if "CONDUCTOR" in roles and current_user.conductor and ruta.conductor_id == current_user.conductor.id:
        return

    if "PADRE" in roles:
        vinculo = (
            db.query(AsignacionEstudianteRuta)
            .join(Estudiante, AsignacionEstudianteRuta.estudiante_id == Estudiante.id)
            .filter(
                AsignacionEstudianteRuta.ruta_id == ruta.id,
                AsignacionEstudianteRuta.activa == 1,
                Estudiante.representante_usuario_id == current_user.id,
            )
            .first()
        )
        if vinculo:
            return

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Acceso restringido: solo puede monitorear la ubicación de la ruta asignada a sus representados (RF-10, RF-15).",
    )


# ============================================================================
# INGESTA DE UBICACIÓN GPS EN TIEMPO REAL Y GEOCERCAS (RF-09, RF-11)
# ============================================================================

@router.post(
    "/viajes/{viaje_id}/posicion",
    response_model=PosicionGpsResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Registrar coordenada GPS del transporte, evaluar geocercas y notificar a padres (RF-09, RF-11)",
)
async def emitir_posicion_gps(
    viaje_id: int,
    payload: RegistrarPosicionGpsRequest,
    current_user: Usuario = Depends(require_role(["CONDUCTOR", "ADMIN"])),
    db: Session = Depends(get_db),
):
    """
    El conductor envía su posición GPS cuando tiene activo el seguimiento (`RF-09`):
      1. Almacena la coordenada `POINT` en `posiciones_gps`.
      2. Evalúa si ingresó al `radio_metros` de alguna parada (`RF-11`).
      3. Si está próximo, crea las alertas en `notificaciones` para los padres correspondientes.
      4. Transmite el paquete en vivo por WebSocket a los padres que están viendo el mapa (`RF-10`).
    """
    viaje = db.query(Viaje).filter(Viaje.id == viaje_id).first()
    if not viaje:
        raise HTTPException(status_code=404, detail="Viaje no encontrado")

    roles = set(get_user_roles(current_user))
    if "ADMIN" not in roles:
        if not current_user.conductor or viaje.conductor_id != current_user.conductor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Solo el conductor responsable del viaje puede emitir coordenadas GPS (RF-15).",
            )

    if viaje.estado != "EN_CURSO":
        viaje.estado = "EN_CURSO"

    resultado = procesar_posicion_y_geocercas(
        db=db,
        viaje=viaje,
        lat=payload.lat,
        lng=payload.lng,
        velocidad_kmh=payload.velocidad_kmh,
        heading=payload.heading,
    )

    # Retransmitir por WebSocket a todos los padres conectados al canal de la ruta (RF-10)
    await ws_manager.broadcast_to_route(
        viaje.ruta_id,
        {
            "evento": "ACTUALIZACION_GPS",
            "data": resultado.model_dump(mode="json"),
        },
    )

    return resultado


# ============================================================================
# CONSULTA DE UBICACIÓN EN TIEMPO REAL PARA PADRES Y ADMIN (RF-10, RF-15)
# ============================================================================

@router.get(
    "/rutas/{ruta_id}/ubicacion-actual",
    response_model=MonitoreoRutaActualResponse,
    summary="Consultar ubicación en tiempo real de la unidad y distancia a cada parada (RF-10)",
)
def obtener_ubicacion_actual_ruta(
    ruta_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    ruta = (
        db.query(Ruta)
        .filter(Ruta.id == ruta_id, Ruta.cooperativa_id == current_user.cooperativa_id)
        .first()
    )
    if not ruta:
        raise HTTPException(status_code=404, detail="Ruta no encontrada")

    _verificar_acceso_monitoreo_ruta(db, current_user, ruta)

    viaje_activo = (
        db.query(Viaje)
        .filter(Viaje.ruta_id == ruta.id)
        .order_by(Viaje.id.desc())
        .first()
    )

    ultima_pos = None
    historial_coords: List[CoordenadaSchema] = []
    paradas_visitadas_ids = set()

    if viaje_activo:
        posiciones = (
            db.query(PosicionGps)
            .filter(PosicionGps.viaje_id == viaje_activo.id)
            .order_by(PosicionGps.id.desc())
            .limit(30)
            .all()
        )
        if posiciones:
            ultima_pos = posiciones[0]
            historial_coords = [
                CoordenadaSchema.model_validate(p.geom) for p in reversed(posiciones) if parse_point(p.geom)
            ]
        paradas_visitadas_ids = {
            eh.parada_id
            for eh in db.query(EtaHistorico)
            .filter(EtaHistorico.viaje_id == viaje_activo.id)
            .all()
        }

    paradas_ruta = (
        db.query(Parada)
        .filter(Parada.ruta_id == ruta.id)
        .order_by(Parada.orden.asc())
        .all()
    )

    estado_paradas: List[DistanciaParadaResumenSchema] = []
    u_geom = parse_point(ultima_pos.geom) if ultima_pos else None
    for p in paradas_ruta:
        dist_actual = None
        dentro_radio = False
        p_geom = parse_point(p.geom)
        if u_geom and p_geom:
            dist_actual = round(
                haversine_distance_m(
                    u_geom["lat"],
                    u_geom["lng"],
                    p_geom["lat"],
                    p_geom["lng"],
                ),
                2,
            )
            dentro_radio = dist_actual <= float(p.radio_metros or 150)

        estado_paradas.append(
            DistanciaParadaResumenSchema(
                parada_id=p.id,
                orden=p.orden,
                nombre=p.nombre,
                geom=CoordenadaSchema.model_validate(p_geom) if p_geom else None,
                radio_metros=p.radio_metros,
                distancia_actual_m=dist_actual,
                dentro_de_radio=dentro_radio,
                visitada_en_viaje=(p.id in paradas_visitadas_ids),
            )
        )

    cond_user = ruta.conductor.usuario if ruta.conductor else None
    return MonitoreoRutaActualResponse(
        ruta_id=ruta.id,
        ruta_nombre=ruta.nombre,
        viaje_activo_id=viaje_activo.id if viaje_activo else None,
        estado_viaje=viaje_activo.estado if viaje_activo else "SIN_VIAJE_ACTIVO",
        bus_placa=ruta.bus.placa if ruta.bus else None,
        conductor_nombre=f"{cond_user.nombre} {cond_user.apellido}" if cond_user else None,
        conductor_telefono=cond_user.telefono if cond_user else None,
        ultima_posicion=CoordenadaSchema.model_validate(u_geom) if u_geom else None,
        velocidad_kmh=ultima_pos.velocidad_kmh if ultima_pos else None,
        heading=ultima_pos.heading if ultima_pos else None,
        ultima_actualizacion_at=ultima_pos.recorded_at if ultima_pos else None,
        paradas_estado=estado_paradas,
        historial_reciente=historial_coords,
    )


# ============================================================================
# CANAL WEBSOCKET EN VIVO POR RUTA (RF-09, RF-10)
# ============================================================================

@router.websocket("/ws/rutas/{ruta_id}")
async def websocket_monitoreo_ruta(
    websocket: WebSocket,
    ruta_id: int,
    token: str | None = Query(default=None, description="Token JWT para autorizar acceso al canal de la ruta"),
):
    """
    Canal WebSocket bidireccional en tiempo real (`WS /api/gps/ws/rutas/{ruta_id}?token=<JWT>`):
      - Valida el token JWT y verifica que el usuario tenga permiso sobre `ruta_id` (RF-10, RF-15).
      - Los padres suscritos reciben instantáneamente cada nueva coordenada y alerta de geocerca.
      - El conductor también puede enviar tramas JSON `{"viaje_id": 1, "lat": ..., "lng": ..., "velocidad_kmh": ...}`
        directamente por este socket.
    """
    if token:
        payload_jwt = decode_access_token(token)
        if not payload_jwt or "sub" not in payload_jwt:
            await websocket.close(code=1008, reason="Token JWT inválido o expirado")
            return
        db_check = SessionLocal()
        try:
            user_ws = db_check.query(Usuario).filter(Usuario.id == int(payload_jwt["sub"])).first()
            ruta_ws = db_check.query(Ruta).filter(Ruta.id == ruta_id).first()
            if not user_ws or not ruta_ws:
                await websocket.close(code=1008, reason="Usuario o ruta no válidos")
                return
            try:
                _verificar_acceso_monitoreo_ruta(db_check, user_ws, ruta_ws)
            except HTTPException as exc:
                await websocket.close(code=1008, reason=str(exc.detail))
                return
        finally:
            db_check.close()

    await ws_manager.connect(ruta_id, websocket)
    try:
        while True:
            payload = await websocket.receive_json()
            if "viaje_id" in payload and "lat" in payload and "lng" in payload:
                db = SessionLocal()
                try:
                    viaje = db.query(Viaje).filter(Viaje.id == int(payload["viaje_id"])).first()
                    if viaje and viaje.ruta_id == ruta_id:
                        res = procesar_posicion_y_geocercas(
                            db=db,
                            viaje=viaje,
                            lat=float(payload["lat"]),
                            lng=float(payload["lng"]),
                            velocidad_kmh=payload.get("velocidad_kmh", 0),
                            heading=payload.get("heading", 0),
                        )
                        await ws_manager.broadcast_to_route(
                            ruta_id,
                            {
                                "evento": "ACTUALIZACION_GPS",
                                "data": res.model_dump(mode="json"),
                            },
                        )
                finally:
                    db.close()
    except WebSocketDisconnect:
        ws_manager.disconnect(ruta_id, websocket)


# ============================================================================
# BANDEJA DE NOTIFICACIONES DE PADRES Y USUARIOS (RF-11)
# ============================================================================

@router.get(
    "/notificaciones",
    response_model=List[NotificacionResponse],
    summary="Listar notificaciones del usuario autenticado (alertas de proximidad y pagos - RF-11)",
)
def listar_mis_notificaciones(
    solo_no_leidas: bool = Query(False),
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = db.query(Notificacion).filter(Notificacion.usuario_id == current_user.id)
    if solo_no_leidas:
        query = query.filter(Notificacion.leida == 0)
    return query.order_by(Notificacion.id.desc()).limit(50).all()


@router.patch(
    "/notificaciones/{notificacion_id}/leer",
    response_model=NotificacionResponse,
    summary="Marcar una notificación como leída",
)
def marcar_notificacion_leida(
    notificacion_id: int,
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notif = (
        db.query(Notificacion)
        .filter(
            Notificacion.id == notificacion_id,
            Notificacion.usuario_id == current_user.id,
        )
        .first()
    )
    if not notif:
        raise HTTPException(status_code=404, detail="Notificación no encontrada")
    notif.leida = 1
    db.commit()
    db.refresh(notif)
    return notif


@router.patch(
    "/notificaciones/leer-todas",
    summary="Marcar todas las notificaciones del usuario como leídas",
)
def marcar_todas_leidas(
    current_user: Usuario = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    actualizadas = (
        db.query(Notificacion)
        .filter(Notificacion.usuario_id == current_user.id, Notificacion.leida == 0)
        .update({"leida": 1})
    )
    db.commit()
    return {"mensaje": "Notificaciones marcadas como leídas", "total_actualizadas": actualizadas}
