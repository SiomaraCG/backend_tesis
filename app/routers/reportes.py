"""Controlador de Generación y Exportación de Reportes en PDF, Excel y JSON (RF-06)."""
from typing import Literal, Optional
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_role
from app.models import (
    AsignacionEstudianteRuta,
    Estudiante,
    Pago,
    Ruta,
    Usuario,
)
from app.services.report_service import generar_excel_bytes, generar_pdf_bytes

router = APIRouter(prefix="/reportes", tags=["Reportes PDF/Excel (RF-06)"])


def _entregar_archivo_o_json(
    formato: str,
    nombre_base: str,
    titulo: str,
    subtitulo: str,
    columnas: list[str],
    filas: list[list],
    datos_json: list[dict],
):
    if formato == "excel":
        contenido = generar_excel_bytes(titulo, columnas, filas)
        return Response(
            content=contenido,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{nombre_base}.xlsx"'},
        )
    if formato == "pdf":
        contenido = generar_pdf_bytes(titulo, subtitulo, columnas, filas)
        return Response(
            content=contenido,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{nombre_base}.pdf"'},
        )
    return {
        "titulo": titulo,
        "subtitulo": subtitulo,
        "total_registros": len(datos_json),
        "registros": datos_json,
    }


@router.get(
    "/rutas",
    summary="Generar y exportar reporte de rutas, unidades y conductores en PDF, Excel o JSON (RF-06)",
)
def exportar_reporte_rutas(
    formato: Literal["pdf", "excel", "json"] = Query(default="pdf"),
    solo_activas: bool = Query(default=False),
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = db.query(Ruta).filter(Ruta.cooperativa_id == current_user.cooperativa_id)
    if solo_activas:
        query = query.filter(Ruta.activa == 1)

    rutas = query.order_by(Ruta.id.asc()).all()
    columnas = [
        "ID",
        "Ruta",
        "Sector",
        "Turno",
        "Hora Campana",
        "Institución Educativa",
        "Placa Bus",
        "Capacidad",
        "Conductor Responsable",
        "Paradas",
        "Estudiantes",
        "Estado",
    ]
    filas = []
    datos_json = []

    for r in rutas:
        cond_u = r.conductor.usuario if r.conductor else None
        cond_nombre = f"{cond_u.nombre} {cond_u.apellido}" if cond_u else "Sin asignar"
        total_est = len([a for a in (r.asignaciones or []) if a.activa == 1])
        total_par = len(r.paradas or [])
        estado_str = "ACTIVA" if r.activa == 1 else "INACTIVA"

        filas.append(
            [
                r.id,
                r.nombre,
                r.sector or "-",
                r.turno,
                str(r.hora_campana or "-"),
                r.institucion.nombre if r.institucion else "-",
                r.bus.placa if r.bus else "-",
                r.bus.capacidad if r.bus else 0,
                cond_nombre,
                total_par,
                total_est,
                estado_str,
            ]
        )
        datos_json.append(
            {
                "id": r.id,
                "nombre": r.nombre,
                "sector": r.sector,
                "turno": r.turno,
                "institucion": r.institucion.nombre if r.institucion else None,
                "bus_placa": r.bus.placa if r.bus else None,
                "conductor": cond_nombre,
                "total_paradas": total_par,
                "total_estudiantes": total_est,
                "estado": estado_str,
            }
        )

    return _entregar_archivo_o_json(
        formato=formato,
        nombre_base="reporte_rutas_transporte",
        titulo="Reporte General de Rutas y Unidades de Transporte Escolar",
        subtitulo=f"Cooperativa ID {current_user.cooperativa_id}",
        columnas=columnas,
        filas=filas,
        datos_json=datos_json,
    )


@router.get(
    "/estudiantes",
    summary="Generar y exportar reporte de estudiantes por ruta en PDF, Excel o JSON (RF-05, RF-06)",
)
def exportar_reporte_estudiantes(
    formato: Literal["pdf", "excel", "json"] = Query(default="pdf"),
    ruta_id: Optional[int] = Query(default=None),
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Estudiante)
        .join(Usuario, Estudiante.representante_usuario_id == Usuario.id)
        .filter(Usuario.cooperativa_id == current_user.cooperativa_id)
    )
    if ruta_id is not None:
        query = query.join(
            AsignacionEstudianteRuta,
            AsignacionEstudianteRuta.estudiante_id == Estudiante.id,
        ).filter(
            AsignacionEstudianteRuta.ruta_id == ruta_id,
            AsignacionEstudianteRuta.activa == 1,
        )

    estudiantes = query.order_by(Estudiante.apellido.asc(), Estudiante.nombre.asc()).all()
    columnas = [
        "ID",
        "Cédula",
        "Estudiante",
        "Grado",
        "Representante Legal",
        "Teléfono Padre",
        "Ruta Asignada",
        "Parada de Recogida",
        "Tarifa Mensual (USD)",
        "Estado",
    ]
    filas = []
    datos_json = []

    for e in estudiantes:
        rep = e.representante
        asig_activa = next((a for a in (e.asignaciones or []) if a.activa == 1), None)
        ruta_nom = asig_activa.ruta.nombre if (asig_activa and asig_activa.ruta) else "Sin ruta"
        parada_nom = asig_activa.parada.nombre if (asig_activa and asig_activa.parada) else "Sin parada"
        tarifa_val = (
            sorted(e.tarifas, key=lambda t: t.vigente_desde, reverse=True)[0].monto_mensual
            if e.tarifas
            else "0.00"
        )
        estado_str = "ACTIVO" if e.activo == 1 else "INACTIVO"

        filas.append(
            [
                e.id,
                e.cedula,
                f"{e.apellido} {e.nombre}",
                e.grado or "-",
                f"{rep.nombre} {rep.apellido}" if rep else "-",
                rep.telefono if rep else "-",
                ruta_nom,
                parada_nom,
                f"${tarifa_val}",
                estado_str,
            ]
        )
        datos_json.append(
            {
                "id": e.id,
                "cedula": e.cedula,
                "estudiante": f"{e.apellido} {e.nombre}",
                "grado": e.grado,
                "representante": f"{rep.nombre} {rep.apellido}" if rep else None,
                "telefono": rep.telefono if rep else None,
                "ruta": ruta_nom,
                "parada": parada_nom,
                "tarifa_mensual": str(tarifa_val),
                "estado": estado_str,
            }
        )

    subtitulo = f"Filtro Ruta ID: {ruta_id}" if ruta_id else "Todos los estudiantes de la cooperativa"
    return _entregar_archivo_o_json(
        formato=formato,
        nombre_base="reporte_estudiantes_transporte",
        titulo="Padrón de Estudiantes y Asignación de Rutas Escolares",
        subtitulo=subtitulo,
        columnas=columnas,
        filas=filas,
        datos_json=datos_json,
    )


@router.get(
    "/pagos",
    summary="Generar y exportar reporte financiero de pagos y comprobantes OCR en PDF, Excel o JSON (RF-06, RF-14)",
)
def exportar_reporte_pagos(
    formato: Literal["pdf", "excel", "json"] = Query(default="pdf"),
    mes: Optional[int] = Query(default=None, ge=1, le=12),
    anio: Optional[int] = Query(default=None, ge=2024, le=2035),
    estado: Optional[str] = Query(default=None),
    current_user: Usuario = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Pago)
        .join(Estudiante, Pago.estudiante_id == Estudiante.id)
        .join(Usuario, Estudiante.representante_usuario_id == Usuario.id)
        .filter(Usuario.cooperativa_id == current_user.cooperativa_id)
    )
    if mes is not None:
        query = query.filter(Pago.mes == mes)
    if anio is not None:
        query = query.filter(Pago.anio == anio)
    if estado is not None:
        query = query.filter(Pago.estado == estado.upper())

    pagos = query.order_by(Pago.anio.desc(), Pago.mes.desc(), Pago.id.desc()).all()
    columnas = [
        "ID Pago",
        "Periodo",
        "Cédula Est.",
        "Estudiante",
        "Representante",
        "Monto (USD)",
        "Estado Pago",
        "Banco (OCR)",
        "Referencia (OCR)",
        "Confianza OCR",
    ]
    filas = []
    datos_json = []

    for p in pagos:
        est = p.estudiante
        rep = est.representante if est else None
        ult_comp = p.comprobantes[-1] if p.comprobantes else None

        filas.append(
            [
                p.id,
                f"{p.mes:02d}/{p.anio}",
                est.cedula if est else "-",
                f"{est.apellido} {est.nombre}" if est else "-",
                f"{rep.nombre} {rep.apellido}" if rep else "-",
                f"${p.monto}",
                p.estado,
                ult_comp.banco if ult_comp else "-",
                ult_comp.referencia_extraida if ult_comp else "-",
                f"{ult_comp.ocr_confianza}%" if (ult_comp and ult_comp.ocr_confianza) else "-",
            ]
        )
        datos_json.append(
            {
                "pago_id": p.id,
                "periodo": f"{p.mes:02d}/{p.anio}",
                "estudiante": f"{est.apellido} {est.nombre}" if est else None,
                "representante": f"{rep.nombre} {rep.apellido}" if rep else None,
                "monto": str(p.monto),
                "estado": p.estado,
                "banco_ocr": ult_comp.banco if ult_comp else None,
                "referencia_ocr": ult_comp.referencia_extraida if ult_comp else None,
                "confianza_ocr": str(ult_comp.ocr_confianza) if (ult_comp and ult_comp.ocr_confianza) else None,
            }
        )

    subtitulo = f"Periodo: {mes or 'Todos'}/{anio or 'Todos'} | Estado: {estado or 'Todos'}"
    return _entregar_archivo_o_json(
        formato=formato,
        nombre_base="reporte_pagos_transporte",
        titulo="Reporte de Recaudación de Pagos y Validación OCR",
        subtitulo=subtitulo,
        columnas=columnas,
        filas=filas,
        datos_json=datos_json,
    )
