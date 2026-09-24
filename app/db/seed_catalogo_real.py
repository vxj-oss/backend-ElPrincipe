"""Importa el catálogo real de la tienda (categorías + productos) provisto por
el negocio. Idempotente: si una categoría o producto ya existe (por nombre),
no lo duplica.

Reglas aplicadas (acordadas con el negocio):
- precio_costo = precio_unitario x 0.70 (margen estimado 30%, no hay costos reales).
- unidad_medida se extrae del propio nombre del producto (texto libre).
- stock_actual es una estimación razonable por rango de precio (no hay inventario
  real todavía); stock_minimo = 20% del stock estimado (mínimo 2).
- nivel_rotacion = "Media" por defecto para todos.
- SKU autogenerado: prefijo de categoría + secuencial.
- Productos que el negocio listó repetidos en más de una categoría se registran
  una sola vez, en la categoría donde temáticamente encajan mejor.
"""
import logging
import re
from decimal import ROUND_HALF_UP, Decimal
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.category import Categoria
from app.models.product import Producto

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("seed_catalogo_real")

CATALOGO: dict[str, list[tuple[str, float]]] = {
    "Limpieza y desinfección": [
        ("Pulidor en polvo con frasco Sapolio x 450 g", 6.50),
        ("Pulidor en polvo en bolsa Sapolio", 4.50),
        ("Ambientadores en spray Glade", 9.50),
        ("Ambientador en spray Sapolio", 8.00),
        ("Plop insecticida para cucarachas", 20.00),
        ("Super Flyp para moscas o zancudos", 17.00),
        ("Raid mata cucarachas", 14.00),
        ("Detergente Marsella x 13.5 kg", 85.00),
        ("Detergente Sapolio x 13.5 kg", 75.00),
        ("Detergente Topaz x 14 kg", 65.00),
        ("Detergente Doffi x 15 kg", 68.00),
        ("Pastillas para tanque Mr Músculo", 21.00),
        ("Pastillas para tanque", 14.00),
        ("Pastilla para tanque", 7.00),
        ("Pastilla para urinario repuesto", 6.00),
        ("Pastillas perfumadas", 2.00),
        ("Desinfectante Pino bidón x 19 lt", 45.00),
        ("Pino Gel x 900 ml", 7.00),
        ("Limpiatodo x 600 ml", 6.00),
        ("Limpiatodo x 500 ml", 4.00),
        ("Jabón líquido antibacterial bidón x 19 lt", 70.00),
        ("Jabón líquido x 400 ml", 5.00),
        ("Alcohol isopropílico bidón x 19 lt", 200.00),
        ("Alcohol isopropílico x 3.8 lt", 45.00),
        ("Alcohol isopropílico x 900 ml", 14.00),
        ("Desinfectante virucida bidón x 19 lt", 95.00),
        ("Desinfectante virucida galón x 3.8 lt", 20.00),
        ("Alcohol en gel x 900 ml", 14.00),
        ("Alcohol en gel x 400 ml", 8.00),
        ("Súper Ácido bidón x 19 lt", 70.00),
        ("Pino Gel bidón x 19 lt", 70.00),
        ("Pino Gel galón x 3.8 lt", 20.00),
        ("Quitasarro bidón x 19 lt", 55.00),
        ("Alcohol puro 96° bidón x 19 lt", 160.00),
        ("Alcohol puro 96° galón x 3.8 lt", 35.00),
        ("Alcohol medicinal 70° bidón x 19 lt", 140.00),
        ("Alcohol medicinal 70° x 900 ml", 8.00),
        ("Limpiatodo x 900 ml", 4.00),
        ("Jabón líquido antibacterial galón x 3.8 lt", 20.00),
        ("Quitasarro galón x 3.8 lt", 20.00),
        ("Quitasarro x 900 ml", 7.00),
        ("Alcohol medicinal 70° galón x 3.8 lt", 30.00),
        ("Alcohol puro 96°", 9.00),
        ("Jabón líquido antibacterial x 900 ml", 7.00),
        ("Limpiatodo galón x 3.8 lt", 15.00),
        ("Lejía galón x 3.8 lt", 12.00),
    ],
    "Utensilios de limpieza": [
        ("Pisos alfombrado grande", 25.00),
        ("Pisos alfombrado con carita", 8.00),
        ("Piso de bienvenida de jebe", 55.00),
        ("Pisos de bienvenida 90cm x 60cm", 35.00),
        ("Pisos de bienvenida 60cm x 40cm", 12.00),
        ("Trapeador de microfibra", 7.00),
        ("Trapeador yute doble", 6.00),
        ("Trapeador de yute simple", 3.00),
        ("Trapeador de frazada", 7.00),
        ("Trapeador de microfibra (chico)", 6.00),
        ("Set Reyna", 28.00),
        ("Set Tayta", 30.00),
        ("Set de limpieza Perico", 25.00),
        ("Set de limpieza Eco", 22.00),
        ("Set de limpieza Ardilla/Blanquimax", 35.00),
        ("Trapeador Ardilla", 28.00),
        ("Trapeadores Ardilla", 22.00),
        ("Recogedor Mega Flyp", 12.00),
        ("Recogedor Flyp", 10.00),
        ("Recogedor chico - Hude", 8.00),
        ("Recogedor c/filete de goma", 6.00),
        ("Recogedor s/filete de goma", 3.00),
        ("Encerador completo", 16.00),
        ("Lavatodo", 15.00),
        ("Escobillon de fibra grande", 30.00),
        ("Escobillon de fibra", 25.00),
        ("Lucha", 10.00),
        ("Escobina", 12.00),
        ("Escoba hogareña", 12.00),
        ("Escobestia", 18.00),
        ("Escobon", 15.00),
        ("Escobillon multiusos", 35.00),
        ("Escoba Venecia - Pisos delicados", 14.00),
        ("Escoba Italina", 10.00),
        ("Escoba Chinita", 9.00),
        ("Escoba Tumbadora", 8.00),
        ("Escoba Máximo", 8.00),
        ("Pack Tumbadora (escoba + recogedor)", 10.00),
        ("Repuesto mechón Daryza", 12.00),
        ("Repuesto mechón 800gr", 12.00),
        ("Repuesto de mechón 500gr", 8.00),
        ("Trapeador de mechón con tuerca y palo inoxidable", 36.00),
        ("Trapeador de mechón con palanca grande", 16.00),
        ("Trapeador de mechón con palanca", 12.00),
        ("Palo de metal plastificado", 4.00),
        ("Palo de madera forrado", 3.00),
        ("Adaptador de palo", 2.00),
        ("Palo de madera con adaptador", 4.00),
        ("Palo de madera", 3.00),
        ("Recogedor de metal grande", 25.00),
        ("Recogedor de metal mediano", 16.00),
        ("Recogedor de metal pequeño", 8.00),
        ("Baldeador 1 mt", 45.00),
        ("Baldeador 80 cm", 38.00),
        ("Baldeador 60 cm", 30.00),
        ("Baldeador 40 cm", 16.00),
        ("Escobillon tipo J", 14.00),
        ("Escobillo 1mt - Cerda de caballo", 48.00),
        ("Escobillo 80cm - Cerda de caballo", 40.00),
        ("Escobillon de fibra parrillero", 14.00),
        ("Escobillon de fibra modelo Condor", 20.00),
        ("Escobillon de fibra taco rojo", 16.00),
        ("Escobillon de fibra taco azul", 12.00),
        ("Escoba de paja de 5 pitas", 28.00),
        ("Escoba de paja 3 pitas", 18.00),
        ("Escoba de paja de 2 pitas", 15.00),
        ("Erizo naylon con palo de madera grande", 28.00),
        ("Palo de madera con cabezal erizo de cerda", 28.00),
        ("Cabezal de madera erizo naylon", 18.00),
        ("Cabezal de madera erizo cerda", 18.00),
        ("Pulverizador de 1 lt", 6.00),
        ("Pulverizador 1/2 lt", 4.00),
        ("Pulverizador punta de metal", 5.00),
        ("Pulverizador punta cuadrada", 2.50),
        ("Dispensador de gel 1lt", 6.00),
        ("Dispensador de gel 1/2 lt", 4.00),
        ("Cabezal de dispensador de gel pico de pato", 3.00),
        ("Jalador negro 50cm grande", 18.00),
        ("Jalador Dayr 40cm", 16.00),
        ("Jalador Dayr 30cm", 12.00),
        ("Jalador de color 1mt", 45.00),
        ("Jalador de madera 80cm", 40.00),
        ("Jalador de madera 60cm", 35.00),
        ("Jalador de color 40cm", 12.00),
        ("Jalador negro 50cm", 12.00),
        ("Jalador negro x 40cm", 8.00),
        ("Canastilla de urinario", 9.00),
        ("Chupones de jebe grande", 8.00),
        ("Chupones de jebe", 4.00),
        ("Cabezal hisopo", 3.00),
        ("Hisopo Luna", 8.00),
        ("Hisopo Estrella", 6.00),
        ("Hisopo Lunita", 5.00),
        ("Desatorador de baño", 6.00),
    ],
    "Cocina y vajilla": [
        ("Paño esponja", 14.00),
        ("Paño esponja Virutex", 3.50),
        ("Paños Virutex x 20 und", 18.00),
        ("Paños Maqui Mary x 20 und", 15.00),
        ("Paños de microfibra 45 x 70 cm", 6.00),
        ("Paños de microfibra 40 x 40 cm", 4.00),
        ("Paños de microfibra 30 x 30 cm", 3.00),
        ("Esponja doble uso Maqui Mary", 2.00),
        ("Esponja doble uso Scotch-Brite", 3.50),
        ("Esponja Scotch-Brite", 2.00),
        ("Esponja El Príncipe", 1.00),
        ("Caja de guantes nitrilo", 25.00),
        ("Caja de guantes de látex", 22.00),
        ("Guantes de lavandería Virutex", 12.00),
        ("Guantes Virutex corrugado", 9.00),
        ("Guantes Virutex Conveniente", 6.00),
        ("Guantes negros calibre 30", 12.00),
        ("Guantes negros calibre 20", 10.00),
        ("Guantes Indulatex", 12.00),
        ("Sacagrasa bidón x 19lt", 70.00),
        ("Sacagrasa galón x 3.8lt", 20.00),
        ("Lavavajilla líquida galón x 3.8lt", 25.00),
        ("Sacagrasa x 900ml", 7.00),
    ],
    "Pisos y superficies": [
        ("Cera sachet x 300ml", 5.00),
        ("Limpiavidrios bidón x 19lt", 55.00),
        ("Limpia mayólicas galón x 3.8lt", 18.00),
        ("Limpia mayólicas bidón x 19lt", 70.00),
        ("Limpiatodo bidón x 19lt", 50.00),
        ("Cera líquida blanca bidón x 19lt", 45.00),
        ("Cera líquida colores bidón x 19lt", 55.00),
        ("Limpia mayólicas x 900ml", 7.00),
        ("Limpiavidrios x 900ml", 6.00),
        ("Shampoo de alfombras galón x 3.8lt", 20.00),
        ("Desinfectante Pino galón x 3.8lt", 15.00),
        ("Cera líquida negro galón x 3.8lt", 18.00),
        ("Cera líquida colores galón x 3.8lt", 18.00),
        ("Cera para madera clara galón x 3.8lt", 45.00),
        ("Cera con ocre Wax rojo galón x 3.8lt", 35.00),
        ("Cera con ocre Wax amarillo galón x 3.8lt", 35.00),
        ("Cera con ocre Wax verde galón x 3.8lt", 35.00),
        ("Cera líquida rojo x 900ml", 6.00),
        ("Cera autobrillante x 900ml", 10.00),
        ("Cera con ocre Wax negro x 900ml", 15.00),
        ("Cera con ocre Wax rojo x 900ml", 15.00),
        ("Cera líquida neutral x 900ml", 6.00),
        ("Cera líquida neutral galón x 3.8lt", 18.00),
        ("Limpiavidrios galón x 3.8lt", 18.00),
    ],
    "Limpieza automotriz": [
        ("Silicona blanca perfumada x 900ml", 15.00),
        ("Silicona transparente x 500ml", 10.00),
        ("Silicona transparente x 900ml", 20.00),
        ("Silicona blanca perfumada galón x 3.8lt", 45.00),
        ("Silicona transparente galón x 3.8lt", 55.00),
        ("Silicona Knauff x 450ml", 12.00),
        ("Shampoo Car galón x 3.8lt", 20.00),
        ("Silicona Kit en aerosol x 420ml", 25.00),
    ],
    "Bolsas, papeleras y papel": [
        ("Bolsa de basura 220 lt", 75.00),
        ("Bolsa de basura de 140 lt", 55.00),
        ("Bolsa de basura gruesa 20cm x 30cm", 18.00),
        ("Bolsa de basura delgada 20cm x 30cm", 10.00),
        ("Bolsa de basura gruesa 26cm x 40cm", 28.00),
        ("Bolsa de basura delgada 26cm x 40cm", 16.00),
        ("Bolsa de basura gruesa 14cm x 20cm", 15.00),
        ("Bolsa de basura delgada 14cm x 20cm", 10.00),
        ("Tacho con ruedas de 1100 lt", 1700.00),
        ("Tacho con ruedas de 660 lt", 950.00),
        ("Tacho con ruedas de 240 lt", 280.00),
        ("Tacho con ruedas de 120 lt", 180.00),
        ("Papel institucional Elite x4 und - 500 mts", 50.00),
        ("Papel institucional Scott Brand x4 und - 400 mt", 45.00),
        ("Papel institucional Amical x6 und - 80 mts", 16.00),
        ("Papel institucional Ecoroll x6 und - 50-80 mts", 14.00),
        ("Papel institucional Rendipel x6 und - 245mt", 42.00),
        ("Papel institucional Rendipel x 6 und", 26.00),
        ("Papel toalla Nova", 3.00),
        ("Papel toalla Bambi", 15.00),
        ("Papel toalla Paracas x 12 und", 40.00),
        ("Papel toalla Nova Ultra x 12 und", 40.00),
        ("Papel toalla Elite x 2 und", 45.00),
        ("Papel higienico Paracas Black x 4 und", 7.50),
        ("Papel higienico Noble x 20 uni", 18.00),
        ("Papel higienico Suave x 20 uni", 20.00),
        ("Papel higienico Elite Naranja x 40 und", 28.00),
        ("Papel higienico Elite x 24 uni", 24.00),
        ("Tacho Italiano #70", 45.00),
        ("Papelera Dayr Española #25", 20.00),
        ("Papelera Dayr - 20lt", 16.00),
        ("Dispensador de jabon liquido - 1lt", 45.00),
        ("Dispensador de jabon liquido - 500 ml", 20.00),
        ("Dispensador de papel toalla", 140.00),
        ("Dispensador de papel higienico", 40.00),
        ("Papel interfoliado Clasico", 8.00),
        ("Papel interfoliado Elite XL", 14.00),
        ("Papel interfoliado Elite Professional", 13.00),
        ("Papel Paracas institucional", 10.00),
        ("Papel toalla Scott", 85.00),
        ("Papel toalla ecológico Bambi", 15.00),
        ("Papel toalla blanco Nevado", 9.00),
    ],
}

CATEGORIA_DESCRIPCIONES = {
    "Limpieza y desinfección": "Lejías, desinfectantes, limpiatodo, detergentes, alcoholes, jabones líquidos, ácidos y ambientadores.",
    "Utensilios de limpieza": "Escobas, trapeadores y mopas, recogedores, hisopos, chupones y equipo de limpieza industrial.",
    "Cocina y vajilla": "Lavavajillas, sacagrasas, esponjas, fibras, paños de cocina y guantes.",
    "Pisos y superficies": "Ceras para pisos, limpiadores de pisos, cuidado de madera y shampoo para alfombras.",
    "Limpieza automotriz": "Siliconas y shampoo para autos, paños y franelas.",
    "Bolsas, papeleras y papel": "Bolsas, papeleras, papel higiénico, papel institucional, toallas de papel y servilletas.",
}

PREFIJO_SKU = {
    "Limpieza y desinfección": "LIM",
    "Utensilios de limpieza": "UTI",
    "Cocina y vajilla": "COC",
    "Pisos y superficies": "PIS",
    "Limpieza automotriz": "AUT",
    "Bolsas, papeleras y papel": "BOL",
}

_PATRONES_UNIDAD = [
    re.compile(r"bid[oó]n\s*x?\s*\d+(?:[.,]\d+)?\s*lt", re.IGNORECASE),
    re.compile(r"gal[oó]n\s*x?\s*\d+(?:[.,]\d+)?\s*lt", re.IGNORECASE),
    re.compile(r"x\s*\d+(?:[.,]\d+)?\s*(?:kg|g|ml|lt|l)\b", re.IGNORECASE),
    re.compile(r"x\s*\d+\s*(?:und|uni)\b", re.IGNORECASE),
    re.compile(r"\d+(?:[.,]\d+)?\s*(?:kg|g|ml|lt)\b", re.IGNORECASE),
    re.compile(r"\d+\s*cm\s*x\s*\d+\s*cm", re.IGNORECASE),
    re.compile(r"\d+\s*mt\b", re.IGNORECASE),
    re.compile(r"\d+\s*cm\b", re.IGNORECASE),
]


def derivar_unidad_medida(nombre: str) -> str:
    for patron in _PATRONES_UNIDAD:
        match = patron.search(nombre)
        if match:
            texto = match.group(0).strip()
            if texto[:2].lower() == "x ":
                texto = texto[2:].strip()
            return texto[0].upper() + texto[1:]
    return "Unidad"


def estimar_stock(precio: float) -> tuple[int, int]:
    """Devuelve (stock_actual, stock_minimo) estimados según el precio de venta.
    Productos baratos rotan más rápido -> más stock; productos caros/voluminosos
    rotan menos -> menos stock. Es una estimación inicial editable después."""
    if precio < 10:
        actual = 80
    elif precio < 30:
        actual = 40
    elif precio < 80:
        actual = 20
    elif precio < 200:
        actual = 10
    else:
        actual = 4
    minimo = max(2, round(actual * 0.2))
    return actual, minimo


def _redondear(valor: float) -> Decimal:
    return Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _get_or_create_categoria(db: Session, nombre: str) -> Categoria:
    cat = db.scalar(select(Categoria).where(Categoria.nombre == nombre))
    if cat:
        return cat
    cat = Categoria(nombre=nombre, descripcion=CATEGORIA_DESCRIPCIONES.get(nombre))
    db.add(cat)
    db.flush()
    logger.info(f"Categoría creada: {nombre}")
    return cat


def seed_catalogo_real(db: Session) -> None:
    total_creados = 0
    total_omitidos = 0

    for categoria_nombre, productos in CATALOGO.items():
        categoria = _get_or_create_categoria(db, categoria_nombre)
        prefijo = PREFIJO_SKU[categoria_nombre]
        secuencia = 1

        for nombre, precio_venta in productos:
            existente = db.scalar(
                select(Producto).where(
                    Producto.nombre == nombre,
                    Producto.categoria_id == categoria.id,
                )
            )
            if existente:
                total_omitidos += 1
                continue

            precio_unitario = _redondear(precio_venta)
            precio_costo = _redondear(precio_venta * 0.70)
            stock_actual, stock_minimo = estimar_stock(precio_venta)
            unidad = derivar_unidad_medida(nombre)

            sku = f"{prefijo}-{secuencia:03d}"
            while db.scalar(select(Producto).where(Producto.sku == sku)):
                secuencia += 1
                sku = f"{prefijo}-{secuencia:03d}"

            producto = Producto(
                categoria_id=categoria.id,
                sku=sku,
                nombre=nombre,
                unidad_medida=unidad,
                precio_unitario=precio_unitario,
                precio_costo=precio_costo,
                stock_actual=stock_actual,
                stock_minimo=stock_minimo,
                nivel_rotacion="Media",
                activo=True,
            )
            db.add(producto)
            secuencia += 1
            total_creados += 1

        db.commit()

    logger.info(f"Catálogo importado: {total_creados} productos creados, {total_omitidos} ya existían.")


def run() -> None:
    db = SessionLocal()
    try:
        seed_catalogo_real(db)
    except Exception as e:
        logger.error(f"Error importando el catálogo real: {e}")
        db.rollback()
        raise e
    finally:
        db.close()


if __name__ == "__main__":
    run()
