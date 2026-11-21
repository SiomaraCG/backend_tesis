from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import os

from app.core.config import settings
from app.core.database import Base, engine
import app.models  # noqa: F401 - Registra las 21 tablas en Base.metadata
from seed import run_seed
from app.core.deps import TokenRouteGuardMiddleware
from app.utils.response import register_standard_responses, response_ok
from app.routers import (
    auth,
    socios_buses,
    rutas_paradas,
    estudiantes,
    viajes_asistencia,
    gps_tracking,
    pagos_ocr,
    reportes,
)

# Crear tablas y datos semilla automáticamente al iniciar el backend
try:
    Base.metadata.create_all(bind=engine)
    run_seed()
except Exception as _seed_err:
    print(f"[AVISO STARTUP] Error al inicializar tablas/seed: {_seed_err}")

app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "Backend en Arquitectura de N-Capas Modulares para gestión de cooperativas, "
        "optimización de rutas (Google OR-Tools), monitoreo GPS en tiempo real y OCR de pagos."
    ),
    version=settings.VERSION,
)

# Configuración CORS para permitir peticiones desde el Frontend (Next.js PWA)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estandarización global de respuestas con `cod_ok` (app/utils/response.py)
register_standard_responses(app)

# Protección global de rutas por rol mediante el Token JWT (RF-01, RF-15)
app.add_middleware(TokenRouteGuardMiddleware)

# Registro de Controladores REST por Módulo (Capa 1: Presentación)
app.include_router(auth.router, prefix=settings.API_V1_STR)
app.include_router(socios_buses.router, prefix=settings.API_V1_STR)
app.include_router(rutas_paradas.router, prefix=settings.API_V1_STR)
app.include_router(estudiantes.router, prefix=settings.API_V1_STR)
app.include_router(viajes_asistencia.router, prefix=settings.API_V1_STR)
app.include_router(gps_tracking.router, prefix=settings.API_V1_STR)
app.include_router(pagos_ocr.router, prefix=settings.API_V1_STR)
app.include_router(reportes.router, prefix=settings.API_V1_STR)

# Exponer directorio de comprobantes subidos (RF-12)
os.makedirs("uploads/comprobantes", exist_ok=True)
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


@app.get("/", tags=["Health"])
def root():
    return response_ok(
        data={
            "docs": "/docs",
            "arquitectura": "Monolito Modular en 4 Capas",
        },
        mensaje="API de Transporte Escolar activa",
    )


@app.get("/health", tags=["Health"])
def health_check():
    return response_ok(
        data={
            "status": "ok",
            "service": "transporte-escolar-backend",
            "layers": {
                "presentation": "routers + schemas",
                "security": "core",
                "business_engines": "services (OR-Tools, Geofence, OCR, Reports)",
                "persistence": "models (SQLAlchemy)",
                "utils": "utils/response.py (cod_ok)",
            },
        },
        mensaje="Servidor operativo al 100%",
    )
