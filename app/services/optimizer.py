from datetime import date, datetime, time, timedelta
from typing import Dict, List, Optional, Tuple
import httpx
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import (
    AsignacionEstudianteRuta,
    AusenciaEstudiante,
    Parada,
    Ruta,
    haversine_distance_m,
    parse_point,
)
from app.schemas.common import CoordenadaSchema
from app.schemas.viajes_optimizacion import (
    ParadaOptimizadaItem,
    RutaOptimizacionResponse,
)

FACTOR_VIAL_URBANO = 1.30  


def _road_distance_fallback_m(c1: Dict[str, float], c2: Dict[str, float]) -> int:
    """Calcula distancia vial estimada en metros mediante fórmula esférica Haversine."""
    dist_lineal = haversine_distance_m(c1["lat"], c1["lng"], c2["lat"], c2["lng"])
    return int(round(dist_lineal * FACTOR_VIAL_URBANO))


def _build_distance_matrix(nodes_coords: List[Dict[str, float]]) -> List[List[int]]:
    """
    Construye la matriz N x N de distancias en metros entre todos los puntos:
      - Primero intenta consultar OSRM Table API (`router.project-osrm.org`) para distancias reales por calles.
      - Si no hay conexión o tarda más de 2.5s, calcula instantáneamente con Haversine ponderado.
    """
    n = len(nodes_coords)
    coords_str = ";".join(f"{c['lng']:.6f},{c['lat']:.6f}" for c in nodes_coords)
    url = f"{settings.OSRM_BASE_URL}/table/v1/driving/{coords_str}?annotations=distance"

    try:
        with httpx.Client(timeout=2.5) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                distances = data.get("distances")
                if distances and len(distances) == n:
                    return [
                        [int(round(val or 0)) for val in row]
                        for row in distances
                    ]
    except Exception:
        pass

    # Fallback determinístico Haversine (sin requerir internet)
    matrix: List[List[int]] = []
    for i in range(n):
        row: List[int] = []
        for j in range(n):
            if i == j:
                row.append(0)
            else:
                row.append(_road_distance_fallback_m(nodes_coords[i], nodes_coords[j]))
        matrix.append(row)
    return matrix


def _fetch_osrm_street_polyline(ordered_coords: List[Dict[str, float]]) -> List[CoordenadaSchema]:
    """
    Obtiene los puntos detallados de la polilínea siguiendo las calles reales mediante OSRM Route API.
    Si no hay conexión a internet, devuelve los vértices directos de las paradas ordenadas.
    """
    if len(ordered_coords) < 2:
        return [CoordenadaSchema(**c) for c in ordered_coords]

    coords_str = ";".join(f"{c['lng']:.6f},{c['lat']:.6f}" for c in ordered_coords)
    url = f"{settings.OSRM_BASE_URL}/route/v1/driving/{coords_str}?overview=full&geometries=geojson"

    try:
        with httpx.Client(timeout=2.5) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                routes = data.get("routes", [])
                if routes:
                    geojson_coords = routes[0].get("geometry", {}).get("coordinates", [])
                    if geojson_coords:
                        return [
                            CoordenadaSchema(lat=float(pt[1]), lng=float(pt[0]))
                            for pt in geojson_coords
                        ]
    except Exception:
        pass

    return [CoordenadaSchema(**c) for c in ordered_coords]


def _solve_ortools_sequence(
    distance_matrix: List[List[int]],
    turno: str,
) -> List[int]:
    """
    Ejecuta Google OR-Tools (`pywrapcp`) sobre la matriz de distancias:
      - Los índices `0 .. N-2` corresponden a las paradas activas.
      - El índice `N-1` corresponde a la Institución Educativa.
      - Si `turno == 'AM'`: ruta abierta que inicia en la parada más conveniente y termina en `N-1` (Institución).
      - Si `turno == 'PM'`: ruta abierta que inicia en `N-1` (Institución) y visita todas las paradas.
    Retorna la lista de índices de paradas (`0 .. N-2`) en el orden óptimo de visita.
    """
    total_real_nodes = len(distance_matrix)
    num_paradas = total_real_nodes - 1
    if num_paradas <= 1:
        return list(range(num_paradas))

    inst_idx = total_real_nodes - 1
    dummy_idx = total_real_nodes  # Nodo ficticio con costo 0 para extremo abierto
    total_solver_nodes = total_real_nodes + 1

    if turno == "AM":
        manager = pywrapcp.RoutingIndexManager(total_solver_nodes, 1, [dummy_idx], [inst_idx])
    else:
        manager = pywrapcp.RoutingIndexManager(total_solver_nodes, 1, [inst_idx], [dummy_idx])

    routing = pywrapcp.RoutingModel(manager)

    def distance_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        if from_node == dummy_idx or to_node == dummy_idx:
            return 0
        return distance_matrix[from_node][to_node]

    transit_callback_index = routing.RegisterTransitCallback(distance_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    search_parameters.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    search_parameters.time_limit.seconds = 1

    solution = routing.SolveWithParameters(search_parameters)
    if not solution:
        return list(range(num_paradas))

    ordered_paradas: List[int] = []
    index = routing.Start(0)
    while not routing.IsEnd(index):
        node = manager.IndexToNode(index)
        if 0 <= node < num_paradas:
            ordered_paradas.append(node)
        index = solution.Value(routing.NextVar(index))

    return ordered_paradas


def optimizar_ruta_ortools(
    db: Session,
    ruta: Ruta,
    viaje_id: Optional[int] = None,
    velocidad_promedio_kmh: float = 25.0,
) -> RutaOptimizacionResponse:
    """
    Optimiza el orden de las paradas de `ruta` usando Google OR-Tools (RF-08),
    actualiza `paradas.orden` y `paradas.eta_estimado` en la base de datos
    y devuelve el resumen completo del recorrido optimizado con la polilínea para el mapa.
    """
    paradas_todas: List[Parada] = (
        db.query(Parada)
        .filter(Parada.ruta_id == ruta.id)
        .order_by(Parada.orden.asc())
        .all()
    )

    # 1. Identificar estudiantes con ausencia reportada en el viaje del día (si se envía viaje_id)
    estudiantes_ausentes_ids = set()
    if viaje_id is not None:
        ausencias = (
            db.query(AusenciaEstudiante)
            .filter(
                AusenciaEstudiante.viaje_id == viaje_id,
                AusenciaEstudiante.estado.in_(["REPORTADA", "CONFIRMADA"]),
            )
            .all()
        )
        estudiantes_ausentes_ids = {a.estudiante_id for a in ausencias}

    paradas_activas: List[Tuple[Parada, int]] = []
    paradas_omitidas: List[str] = []

    total_asignaciones_ruta = (
        db.query(AsignacionEstudianteRuta)
        .filter(
            AsignacionEstudianteRuta.ruta_id == ruta.id,
            AsignacionEstudianteRuta.activa == 1,
        )
        .count()
    )

    for p in paradas_todas:
        if not p.geom:
            continue
        asignaciones_p = [
            a
            for a in (p.asignaciones or [])
            if a.activa == 1 and a.estudiante_id not in estudiantes_ausentes_ids
        ]
        if total_asignaciones_ruta > 0 and len(p.asignaciones or []) > 0 and len(asignaciones_p) == 0:
            paradas_omitidas.append(p.nombre)
            continue

        paradas_activas.append((p, len(asignaciones_p)))

    if not paradas_activas:
        return RutaOptimizacionResponse(
            ruta_id=ruta.id,
            ruta_nombre=ruta.nombre,
            turno=ruta.turno,
            distancia_total_km=0.0,
            tiempo_total_estimado_min=0.0,
            paradas_activas_optimizadas=[],
            paradas_omitidas_por_ausencia=paradas_omitidas,
            polilinea_coordenadas=[],
        )

    inst_geom = parse_point(
        ruta.institucion.geom
        if (ruta.institucion and ruta.institucion.geom)
        else paradas_activas[-1][0].geom
    ) or {"lat": -0.180653, "lng": -78.467834}

    # 2. Construir matriz de distancias y resolver con Google OR-Tools
    nodes_coords = [parse_point(p[0].geom) for p in paradas_activas] + [inst_geom]
    distance_matrix = _build_distance_matrix(nodes_coords)
    secuencia_indices = _solve_ortools_sequence(distance_matrix, ruta.turno)
    inst_node_idx = len(nodes_coords) - 1

    velocidad_m_s = (velocidad_promedio_kmh * 1000.0) / 3600.0
    hora_base = ruta.hora_campana or (time(7, 15) if ruta.turno == "AM" else time(13, 0))
    dt_referencia = datetime.combine(date.today(), hora_base)

    paradas_ordenadas_tuplas = [paradas_activas[idx] for idx in secuencia_indices]
    distancias_tramos: List[float] = []
    distancia_acumulada_m = 0.0

    for pos_i, matrix_node_idx in enumerate(secuencia_indices):
        if pos_i == 0:
            if ruta.turno == "PM":
                d_m = float(distance_matrix[inst_node_idx][matrix_node_idx])
            else:
                d_m = 0.0
        else:
            prev_matrix_idx = secuencia_indices[pos_i - 1]
            d_m = float(distance_matrix[prev_matrix_idx][matrix_node_idx])
        distancias_tramos.append(d_m)
        distancia_acumulada_m += d_m

    if ruta.turno == "AM":
        ultimo_matrix_idx = secuencia_indices[-1]
        distancia_acumulada_m += float(distance_matrix[ultimo_matrix_idx][inst_node_idx])

    tiempo_total_seg = distancia_acumulada_m / max(velocidad_m_s, 1.0) + (
        len(paradas_ordenadas_tuplas) * 45
    )

    if ruta.turno == "AM":
        dt_cursor = dt_referencia - timedelta(minutes=10) - timedelta(seconds=tiempo_total_seg)
    else:
        dt_cursor = dt_referencia

    items_optimizados: List[ParadaOptimizadaItem] = []
    ordered_waypoints_for_polyline: List[Dict[str, float]] = []

    if ruta.turno == "PM":
        ordered_waypoints_for_polyline.append(inst_geom)

    for nuevo_idx, (parada_obj, cant_est) in enumerate(paradas_ordenadas_tuplas, start=1):
        orden_previo = parada_obj.orden
        tramo_m = distancias_tramos[nuevo_idx - 1]
        seg_tramo = (tramo_m / max(velocidad_m_s, 1.0)) + (45 if nuevo_idx > 1 else 0)
        dt_cursor = dt_cursor + timedelta(seconds=seg_tramo)

        nuevo_eta = dt_cursor.time().replace(microsecond=0)
        parada_obj.orden = nuevo_idx
        parada_obj.eta_estimado = nuevo_eta

        p_geom = parse_point(parada_obj.geom) or {"lat": -0.180653, "lng": -78.467834}
        ordered_waypoints_for_polyline.append(p_geom)
        items_optimizados.append(
            ParadaOptimizadaItem(
                parada_id=parada_obj.id,
                nombre=parada_obj.nombre,
                orden_anterior=orden_previo,
                orden_optimizado=nuevo_idx,
                geom=CoordenadaSchema.model_validate(p_geom),
                eta_estimado=nuevo_eta,
                estudiantes_activos=cant_est,
                distancia_desde_anterior_m=round(tramo_m, 2),
            )
        )

    if ruta.turno == "AM":
        ordered_waypoints_for_polyline.append(inst_geom)

    db.commit()

    polilinea_vial = _fetch_osrm_street_polyline(ordered_waypoints_for_polyline)

    return RutaOptimizacionResponse(
        ruta_id=ruta.id,
        ruta_nombre=ruta.nombre,
        turno=ruta.turno,
        distancia_total_km=round(distancia_acumulada_m / 1000.0, 2),
        tiempo_total_estimado_min=round(tiempo_total_seg / 60.0, 1),
        paradas_activas_optimizadas=items_optimizados,
        paradas_omitidas_por_ausencia=paradas_omitidas,
        polilinea_coordenadas=polilinea_vial,
    )
