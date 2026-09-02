import logging
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import get_password_hash
from app.models.category import Categoria
from app.models.customer import Cliente
from app.models.product import Producto
from app.models.user import Usuario

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed")


def _create_admin(db: Session) -> None:
    admin_user = db.scalar(
        select(Usuario).where(Usuario.nombre_usuario == settings.FIRST_SUPERUSER)
    )
    if not admin_user:
        admin_user = Usuario(
            nombre_usuario=settings.FIRST_SUPERUSER,
            clave_hash=get_password_hash(settings.FIRST_SUPERUSER_PASSWORD),
            nombre_completo="Victor Nontol",
            correo="victor.nontol@elprincipe.pe",
            rol="administrador",
            esta_activo=True,
        )
        db.add(admin_user)
        db.commit()
        logger.info(f"Usuario Administrador '{settings.FIRST_SUPERUSER}' creado.")
    else:
        logger.info(f"Usuario Administrador '{settings.FIRST_SUPERUSER}' ya existe.")


def seed_data(db: Session) -> None:
    _create_admin(db)

    asesor_user = db.scalar(
        select(Usuario).where(Usuario.nombre_usuario == settings.SEED_ASESOR_USERNAME)
    )
    if not asesor_user:
        asesor_user = Usuario(
            nombre_usuario=settings.SEED_ASESOR_USERNAME,
            clave_hash=get_password_hash(settings.SEED_ASESOR_PASSWORD),
            nombre_completo="Carlos Asesor Ventas",
            correo="carlos.asesor@elprincipe.pe",
            rol="asesor_comercial",
            esta_activo=True,
        )
        db.add(asesor_user)
        logger.info(f"Usuario Asesor Comercial '{settings.SEED_ASESOR_USERNAME}' creado.")

    # ── 2. Categorías ─────────────────────────────────────────────────────────
    categorias_data = [
        {"nombre": "Detergentes y Desinfectantes", "descripcion": "Línea de limpieza profunda y desinfección industrial"},
        {"nombre": "Lavavajillas y Desengrasantes", "descripcion": "Químicos para áreas de cocina, grasas pesadas y vajilla"},
        {"nombre": "Cuidado de Pisos", "descripcion": "Ceras, selladores y removedores para superficies de alto tránsito"},
        {"nombre": "Higiene Personal", "descripcion": "Jabones líquidos, alcohol en gel y dispensadores"},
    ]

    cat_map = {}
    for cat in categorias_data:
        db_cat = db.scalar(select(Categoria).where(Categoria.nombre == cat["nombre"]))
        if not db_cat:
            db_cat = Categoria(**cat)
            db.add(db_cat)
            db.flush()
            logger.info(f"Categoría '{cat['nombre']}' creada.")
        cat_map[cat["nombre"]] = db_cat
    productos_data = [
        {
            "categoria_id": cat_map["Detergentes y Desinfectantes"].id,
            "sku": "DET-LIQ-001",
            "nombre": "Detergente Líquido Industrial 5L",
            "descripcion": "Detergente multiusos concentrado baja espuma",
            "unidad_medida": "Bidón 5L",
            "precio_unitario": Decimal("38.50"),
            "precio_costo": Decimal("22.00"),
            "stock_actual": 120,
            "stock_minimo": 20,
            "nivel_rotacion": "Alta",
        },
        {
            "categoria_id": cat_map["Detergentes y Desinfectantes"].id,
            "sku": "CLO-CON-002",
            "nombre": "Cloro Concentrado al 7.5% Galón",
            "descripcion": "Desinfectante clorado para saneamiento hospitalario e industrial",
            "unidad_medida": "Galón",
            "precio_unitario": Decimal("18.00"),
            "precio_costo": Decimal("9.50"),
            "stock_actual": 200,
            "stock_minimo": 30,
            "nivel_rotacion": "Alta",
        },
        {
            "categoria_id": cat_map["Lavavajillas y Desengrasantes"].id,
            "sku": "DES-IND-003",
            "nombre": "Desengrasante Pesado Alcalino 5L",
            "descripcion": "Removedor de grasa carbonizada para campanas y motores",
            "unidad_medida": "Bidón 5L",
            "precio_unitario": Decimal("48.00"),
            "precio_costo": Decimal("28.00"),
            "stock_actual": 45,
            "stock_minimo": 10,
            "nivel_rotacion": "Media",
        },
        {
            "categoria_id": cat_map["Cuidado de Pisos"].id,
            "sku": "CER-AUT-004",
            "nombre": "Cera Autobrillante Antideslizante Galón",
            "descripcion": "Acabado acrílico brillante para pisos vinílicos y granito",
            "unidad_medida": "Galón",
            "precio_unitario": Decimal("55.00"),
            "precio_costo": Decimal("32.00"),
            "stock_actual": 30,
            "stock_minimo": 8,
            "nivel_rotacion": "Media",
        },
        {
            "categoria_id": cat_map["Higiene Personal"].id,
            "sku": "JAB-BAC-005",
            "nombre": "Jabón Líquido Antibacterial 5L",
            "descripcion": "Jabón con glicerina y aroma suave para dispensador",
            "unidad_medida": "Bidón 5L",
            "precio_unitario": Decimal("32.00"),
            "precio_costo": Decimal("17.50"),
            "stock_actual": 85,
            "stock_minimo": 15,
            "nivel_rotacion": "Alta",
        },
    ]

    for prod in productos_data:
        db_prod = db.scalar(select(Producto).where(Producto.sku == prod["sku"]))
        if not db_prod:
            db_prod = Producto(**prod)
            db.add(db_prod)
            logger.info(f" Producto '{prod['nombre']}' ({prod['sku']}) creado.")

    clientes_data = [
        {
            "ruc_dni": "20601234567",
            "razon_social": "DISTRIBUIDORA COMERCIAL NORTE S.A.C.",
            "tipo_cliente": "Mayorista",
            "direccion": "Av. España 1450",
            "distrito": "Trujillo",
            "telefono": "944123456",
            "correo": "ventas@distribuidoranorte.pe",
            "estado": "Activo",
        },
        {
            "ruc_dni": "20509876543",
            "razon_social": "CLÍNICA SAN ANDRÉS E.I.R.L.",
            "tipo_cliente": "Institucional",
            "direccion": "Jr. San Martín 820",
            "distrito": "Trujillo",
            "telefono": "948765432",
            "correo": "logistica@clinicasanandres.pe",
            "estado": "Activo",
        },
        {
            "ruc_dni": "10456789012",
            "razon_social": "BODEGA Y MINIMARKET EL SOL - JORGE ROJAS",
            "tipo_cliente": "Minorista",
            "direccion": "Av. Larco 430",
            "distrito": "Víctor Larco Herrera",
            "telefono": "949112233",
            "correo": "minimarketelsol@gmail.com",
            "estado": "Activo",
        },
    ]

    for cli in clientes_data:
        db_cli = db.scalar(select(Cliente).where(Cliente.ruc_dni == cli["ruc_dni"]))
        if not db_cli:
            db_cli = Cliente(**cli)
            db.add(db_cli)
            logger.info(f" Cliente '{cli['razon_social']}' registrado.")

    db.commit()
    logger.info("🎉 Proceso de seed finalizado con éxito.")


def run_seed() -> None:
    db = SessionLocal()
    try:
        seed_data(db)
    except Exception as e:
        logger.error(f"Error durante el sembrado de datos: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


def seed_admin_only() -> None:
    """Crea únicamente el usuario administrador inicial, sin clientes/productos
    ficticios. Pensado para producción, donde las tablas deben quedar en blanco
    salvo por el primer usuario con el que se puede iniciar sesión."""
    db = SessionLocal()
    try:
        _create_admin(db)
    except Exception as e:
        logger.error(f"Error creando el usuario administrador: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Sembrado de datos iniciales.")
    parser.add_argument(
        "--admin-only",
        action="store_true",
        help="Crea solo el usuario administrador, sin datos de demo (para producción).",
    )
    args = parser.parse_args()

    if args.admin_only:
        seed_admin_only()
    else:
        run_seed()