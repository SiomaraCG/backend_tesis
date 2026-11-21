
from datetime import date, time
from decimal import Decimal
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymysql
from sqlalchemy.engine.url import make_url

from app.core.config import settings
from app.core.database import Base, SessionLocal, engine
from app.core.security import get_password_hash
from app.models import (
    Cooperativa,
    Usuario,
    Rol,
    UsuarioRol,
    Socio,
    Conductor,
    Bus,
    InstitucionEducativa,
    Ruta,
    Parada,
    Estudiante,
    TarifaEstudiante,
    AsignacionEstudianteRuta,
)


def ensure_mysql_database_exists():
    """Si DATABASE_URL apunta a MySQL, crea la base de datos si aún no existe."""
    if not settings.DATABASE_URL.startswith("mysql"):
        return

    url = make_url(settings.DATABASE_URL)
    db_name = url.database
    try:
        conn = pymysql.connect(
            host=url.host or "localhost",
            port=url.port or 3306,
            user=url.username or "root",
            password=url.password or "",
            charset="utf8mb4",
        )
        with conn.cursor() as cursor:
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"
            )
        conn.commit()
        conn.close()
        print(f"[OK] Base de datos MySQL '{db_name}' verificada/creada.")
    except Exception as exc:
        print(f"[AVISO] No se pudo conectar a MySQL ({exc}). Verifica las credenciales en backend/.env")
        raise


def run_seed():
    # Crear las 21 tablas definidas en SQLAlchemy (en MySQL 8 o SQLite local activo)
    Base.metadata.create_all(bind=engine)
    print(f"[OK] Las 21 tablas del modelo (model.pdf) están creadas en: {engine.url}")

    db = SessionLocal()
    try:
        # 1. Cooperativa por defecto
        coop = db.query(Cooperativa).filter_by(ruc="1790012345001").first()
        if not coop:
            coop = Cooperativa(
                nombre="Cooperativa de Transporte Escolar San Francisco",
                ruc="1790012345001",
                direccion="Av. América y Naciones Unidas, Quito",
                telefono="022456789",
                email="info@coopsanfrancisco.ec",
                activa=1,
            )
            db.add(coop)
            db.flush()
            print(f"[SEED] Cooperativa creada: {coop.nombre} (ID={coop.id})")

        # 2. Roles base (ADMIN, CONDUCTOR, PADRE)
        roles_def = {
            "ADMIN": "Administrador general del sistema y de la cooperativa",
            "CONDUCTOR": "Conductor responsable de ruta y registro de asistencia/GPS",
            "PADRE": "Padre de familia o representante legal de estudiantes",
        }
        roles_map = {}
        for nombre_rol, desc in roles_def.items():
            rol_obj = db.query(Rol).filter_by(nombre=nombre_rol).first()
            if not rol_obj:
                rol_obj = Rol(nombre=nombre_rol, descripcion=desc)
                db.add(rol_obj)
                db.flush()
                print(f"[SEED] Rol creado: {nombre_rol}")
            roles_map[nombre_rol] = rol_obj

        # 3. Usuario Administrador Inicial
        admin_user = db.query(Usuario).filter_by(email="admin@cooperativa.ec").first()
        if not admin_user:
            admin_user = Usuario(
                cooperativa_id=coop.id,
                email="admin@cooperativa.ec",
                password_hash=get_password_hash("admin123"),
                nombre="Carlos",
                apellido="Mendoza (Admin)",
                cedula="1700000001",
                telefono="0991111111",
                activo=1,
            )
            db.add(admin_user)
            db.flush()
            db.add(UsuarioRol(usuario_id=admin_user.id, rol_id=roles_map["ADMIN"].id))
            print("[SEED] Usuario ADMIN creado -> email: admin@cooperativa.ec | pass: admin123")

        # 4. Usuario Conductor + Socio + Bus Inicial
        driver_user = db.query(Usuario).filter_by(email="conductor@cooperativa.ec").first()
        if not driver_user:
            driver_user = Usuario(
                cooperativa_id=coop.id,
                email="conductor@cooperativa.ec",
                password_hash=get_password_hash("conductor123"),
                nombre="Luis",
                apellido="Andrade",
                cedula="1700000002",
                telefono="0992222222",
                activo=1,
            )
            db.add(driver_user)
            db.flush()
            db.add(UsuarioRol(usuario_id=driver_user.id, rol_id=roles_map["CONDUCTOR"].id))
            print("[SEED] Usuario CONDUCTOR creado -> email: conductor@cooperativa.ec | pass: conductor123")

        socio = db.query(Socio).filter_by(usuario_id=driver_user.id).first()
        if not socio:
            socio = Socio(
                cooperativa_id=coop.id,
                usuario_id=driver_user.id,
                nombre_razon_social="Transporte Escolar Andrade S.A.",
                activo=1,
            )
            db.add(socio)
            db.flush()

        conductor = db.query(Conductor).filter_by(usuario_id=driver_user.id).first()
        if not conductor:
            conductor = Conductor(
                usuario_id=driver_user.id,
                licencia="PROF-E-1700000002",
                activo=1,
            )
            db.add(conductor)
            db.flush()

        bus = db.query(Bus).filter_by(placa="PAA-1024").first()
        if not bus:
            bus = Bus(
                socio_id=socio.id,
                placa="PAA-1024",
                capacidad=24,
                activo=1,
            )
            db.add(bus)
            db.flush()

        # 5. Institución Educativa + Ruta + Paradas con coordenadas POINT
        inst = db.query(InstitucionEducativa).filter_by(nombre="Unidad Educativa Sebastián de Benalcázar").first()
        if not inst:
            inst = InstitucionEducativa(
                cooperativa_id=coop.id,
                nombre="Unidad Educativa Sebastián de Benalcázar",
                direccion="Av. 6 de Diciembre e Irlanda, Quito",
                tipo="FISCAL",
                geom={"lat": -0.186590, "lng": -78.479210},
                activa=1,
            )
            db.add(inst)
            db.flush()

        ruta = db.query(Ruta).filter_by(nombre="Ruta Norte - La Carolina").first()
        if not ruta:
            ruta = Ruta(
                cooperativa_id=coop.id,
                conductor_id=conductor.id,
                bus_id=bus.id,
                institucion_id=inst.id,
                nombre="Ruta Norte - La Carolina",
                sector="Norte / Iñaquito",
                turno="AM",
                hora_campana=time(7, 15),
                activa=1,
            )
            db.add(ruta)
            db.flush()

            paradas_seed = [
                ("Parada 1 - Av. Amazonas y Naciones Unidas", 1, {"lat": -0.176120, "lng": -78.485410}, time(6, 35)),
                ("Parada 2 - Av. Shyris y Eloy Alfaro", 2, {"lat": -0.181450, "lng": -78.481230}, time(6, 48)),
                ("Parada 3 - Av. República y Pradera", 3, {"lat": -0.189310, "lng": -78.486190}, time(7, 0)),
            ]
            paradas_objs = []
            for nombre_p, orden_p, coords_p, eta_p in paradas_seed:
                p = Parada(
                    ruta_id=ruta.id,
                    orden=orden_p,
                    nombre=nombre_p,
                    geom=coords_p,
                    radio_metros=150,
                    eta_estimado=eta_p,
                )
                db.add(p)
                db.flush()
                paradas_objs.append(p)

            # 6. Usuario Padre + Estudiante asignado
            padre_user = db.query(Usuario).filter_by(email="padre@cooperativa.ec").first()
            if not padre_user:
                padre_user = Usuario(
                    cooperativa_id=coop.id,
                    email="padre@cooperativa.ec",
                    password_hash=get_password_hash("padre123"),
                    nombre="María",
                    apellido="Gómez",
                    cedula="1700000003",
                    telefono="0993333333",
                    activo=1,
                )
                db.add(padre_user)
                db.flush()
                db.add(UsuarioRol(usuario_id=padre_user.id, rol_id=roles_map["PADRE"].id))
                print("[SEED] Usuario PADRE creado -> email: padre@cooperativa.ec | pass: padre123")

            est1 = db.query(Estudiante).filter_by(cedula="1750000001").first()
            if not est1:
                est1 = Estudiante(
                    representante_usuario_id=padre_user.id,
                    cedula="1750000001",
                    nombre="Mateo",
                    apellido="Gómez",
                    grado="8vo EGB",
                    activo=1,
                    domicilio_geom={"lat": -0.176120, "lng": -78.485410},
                    domicilio_direccion="Av. Amazonas N36-152 y Naciones Unidas",
                )
                db.add(est1)
                db.flush()

                db.add(
                    TarifaEstudiante(
                        estudiante_id=est1.id,
                        monto_mensual=Decimal("65.00"),
                        vigente_desde=date(2026, 9, 1),
                        observacion="Tarifa estándar mensual turno AM/PM",
                    )
                )
                db.add(
                    AsignacionEstudianteRuta(
                        estudiante_id=est1.id,
                        ruta_id=ruta.id,
                        parada_id=paradas_objs[0].id,
                        activa=1,
                    )
                )

        db.commit()
        print("[OK] Seeder finalizado exitosamente.")
    except Exception as exc:
        db.rollback()
        raise exc
    finally:
        db.close()


if __name__ == "__main__":
    run_seed()
