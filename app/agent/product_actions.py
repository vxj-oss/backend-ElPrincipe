import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.choices import respuesta_opciones
from app.agent.customer_actions import es_crear_cliente
from app.agent.fechas_texto import _sin_acentos
from app.models.category import Categoria
from app.models.product import Producto
from app.services.product_service import ProductService
from app.services.quote_note_service import candidatos, normalizar, tokens

PREFIJO_PRODUCTO = "¿De qué producto hablas?"
PREFIJO_NOMBRE_PRODUCTO = "¿Cómo se llama el producto nuevo?"
PREFIJO_VALOR = "¿Qué "

V_EDITAR = r"(?:cambia\w*|actualiza\w*|modifica\w*|ajusta\w*|sube\w*|baja\w*|aumenta\w*|reduce\w*|corrige\w*|renombra\w*|pon(?:le)?|edita\w*)"
V_ELIMINAR = r"(?:elimina\w*|borra\w*|quita\w*|saca\w*|retira\w*|desactiva\w*|deshabilita\w*|inactiva\w*|da de baja)"
V_REACTIVAR = r"(?:reactiva\w*|activa\w*|habilita\w*|vuelve a activar)"

PAT_EXCLUIR = re.compile(r"\b(?:cliente|clientes|descuento|credito|pedido|pedidos|cotizacion|cotizaciones|condicion|condiciones|grafic\w*)\b")
PAT_ATRIBUTO = re.compile(r"\b(?:precio|costo|minimo|rotacion|nombre|categoria|cuesta|vale)\b")
PAT_AHORA_CUESTA = re.compile(r"\b(?:ahora|ya|nuevo)\b[^.\n]{0,25}\b(?:cuesta|vale)\b|\b(?:cuesta|vale)\b[^.\n]{0,15}\b(?:ahora|desde hoy)\b")

ATRIBUTOS = {
    "precio_unitario": ("Precio de venta", "precio", "soles"),
    "precio_costo": ("Costo", "costo", "soles"),
    "stock_minimo": ("Stock mínimo", "stock mínimo", "entero"),
    "nivel_rotacion": ("Rotación", "rotación", "texto"),
    "nombre": ("Nombre", "nombre", "texto"),
    "categoria_id": ("Categoría", "categoría", "texto"),
}
PREGUNTA_VALOR = {
    "precio_unitario": ("precio de venta", "precio"),
    "precio_costo": ("costo", "costo"),
    "stock_minimo": ("stock mínimo", "stock mínimo"),
    "nivel_rotacion": ("nivel de rotación", "rotación"),
}

RUIDO = {
    "cambia", "cambiale", "actualiza", "actualizale", "modifica", "ajusta", "sube", "subele", "baja", "bajale", "aumenta",
    "reduce", "corrige", "renombra", "ponle", "pon", "edita", "precio", "costo", "venta", "minimo", "stock", "rotacion",
    "nombre", "categoria", "cuesta", "vale", "ahora", "soles", "sol", "nuevo", "nueva", "producto", "productos", "el",
    "la", "los", "las", "de", "del", "al", "a", "en", "por", "un", "una", "quiero", "favor", "alta", "media", "elimina",
    "borra", "quita", "saca", "retira", "desactiva", "reactiva", "activa", "habilita", "deshabilita", "inactiva", "catalogo",
    "inventario", "porciento", "ciento", "ya", "desde", "hoy", "que", "sea", "es", "cantidad", "dar", "baja", "s",
}


def _texto(respuesta: str, datos: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {"respuesta": respuesta, "datos_estructurados": datos}


def _soles(valor: float) -> str:
    return f"S/ {float(valor):,.2f}"


def _numero_a_float(texto: str) -> float:
    return float(texto.replace(",", "."))


def _explicacion(accion: str) -> Dict[str, Any]:
    return {
        "resumen": "Identifiqué el producto y los valores que quieres cambiar. Se aplica solo cuando confirmas, usa el mismo servicio de la pantalla de Productos y queda en el historial de auditoría.",
        "fuentes": ["Tu mensaje", "Catálogo de productos", "Pedidos y movimientos de stock del producto (para saber si se puede eliminar)"],
        "formula": None,
        "periodo": "datos al momento de la consulta",
    }


def _buscar_producto(
    db: Session, prompt: str, quitar_numeros: Optional[List[str]], incluir_inactivos: bool
) -> Tuple[Optional[Producto], Optional[Dict[str, Any]], str]:
    consulta_tokens = []
    pendientes = list(quitar_numeros or [])
    for t in tokens(prompt):
        if t in RUIDO:
            continue
        if t in pendientes:
            pendientes.remove(t)
            continue
        consulta_tokens.append(t)
    consulta = " ".join(consulta_tokens)
    if not consulta:
        return None, None, ""
    filtro = select(Producto) if incluir_inactivos else select(Producto).where(Producto.activo.is_(True))
    productos = list(db.scalars(filtro).all())
    por_id = {p.id: p for p in productos}
    lista = candidatos(consulta, [(p.id, p.nombre) for p in productos])
    exactos = [c for c in lista if c[2] >= 1.0]
    objetivo = normalizar(consulta)
    iguales = [c for c in exactos if normalizar(c[1]) == objetivo]
    if iguales:
        exactos = iguales[:1]
    if not exactos:
        return None, _texto(f"No encontré «{consulta}» en el catálogo."), consulta
    if len(exactos) > 1:
        return None, {"_ambiguos": [por_id[c[0]] for c in sorted(exactos, key=lambda c: c[1])[:8]]}, consulta
    return por_id[exactos[0][0]], None, consulta


def _atributos_en_texto(limpio: str) -> List[str]:
    atributos: List[str] = []
    sin_costo = re.sub(r"\bprecio de costo\b", "costo", limpio)
    if re.search(r"\bcosto\b", sin_costo):
        atributos.append("precio_costo")
    sin_costo_precio = re.sub(r"\bprecio de costo\b|\bcosto\b", " ", sin_costo)
    if re.search(r"\bprecio\b|\bcuesta\b|\bvale\b", sin_costo_precio):
        atributos.append("precio_unitario")
    if re.search(r"\bstock minimo\b|\bminimo\b", limpio):
        atributos.append("stock_minimo")
    if re.search(r"\brotacion\b", limpio):
        atributos.append("nivel_rotacion")
    if re.search(r"\brenombra\w*\b|\bnombre\b", limpio):
        atributos.append("nombre")
    if re.search(r"\bcategoria\b", limpio):
        atributos.append("categoria_id")
    return atributos


def _numero_cerca(texto: str, claves: str) -> Optional[str]:
    m = re.search(rf"(?:{claves})\s*(?:de\s+|a\s+|en\s+|por\s+|=\s*|es\s+)?(?:s/\.?\s*)?(\d+(?:[.,]\d+)?)\b", texto)
    return m.group(1) if m else None


def _ultimo_numero(texto: str) -> Optional[str]:
    numeros = re.findall(r"(?<![\w.])(\d+(?:[.,]\d+)?)(?![\w])", texto)
    return numeros[-1] if numeros else None


def _frase_edicion(nombre: str, valores: Dict[str, str]) -> str:
    partes = []
    for campo, valor in valores.items():
        etiqueta = ATRIBUTOS[campo][1]
        partes.append(f"el {etiqueta} de {nombre} a {valor}")
    return "cambia " + " y ".join(partes)


def _editar(db: Session, prompt: str, limpio: str, atributos: List[str]) -> Dict[str, Any]:
    texto = _sin_acentos(prompt)
    valores: Dict[str, str] = {}
    delta: Optional[Tuple[str, float, bool]] = None
    quitar: List[str] = []
    texto_producto = prompt

    relativo = re.search(r"\b(?:sube\w*|aumenta\w*|baja\w*|reduce\w*)\b[^.\n]{0,40}\ben\s+(?:un\s+)?(\d+(?:[.,]\d+)?)\s*(%|por ?ciento)?", texto)
    if relativo and len(atributos) == 1 and atributos[0] in ("precio_unitario", "precio_costo", "stock_minimo"):
        subir = bool(re.search(r"\b(?:sube\w*|aumenta\w*)\b", texto))
        delta = (relativo.group(1), 1.0 if subir else -1.0, bool(relativo.group(2)))
        quitar = [relativo.group(1).replace(",", ".")]

    if delta is None:
        for campo in atributos:
            if campo == "precio_unitario":
                valor = _numero_cerca(texto, r"precio(?:\s+de\s+venta)?|cuesta|vale")
            elif campo == "precio_costo":
                valor = _numero_cerca(texto, r"costo|precio\s+de\s+costo")
            elif campo == "stock_minimo":
                valor = _numero_cerca(texto, r"stock\s+minimo|minimo")
            elif campo == "nivel_rotacion":
                m = re.search(r"rotacion\s*(?:a\s+|de\s+|en\s+|es\s+)?(alta|media|baja)", texto)
                valor = m.group(1).capitalize() if m else None
                if valor is None:
                    m = re.search(r"\b(alta|media|baja)\b", texto)
                    valor = m.group(1).capitalize() if m else None
            elif campo == "nombre":
                m = re.search(r"(?:renombra\w*|nombre\s+de)\s+(.*?)\s+a\s+(.+)$", prompt, re.IGNORECASE)
                valor = m.group(2).strip(" .\"'«»") if m else None
                if m:
                    texto_producto = m.group(1)
            else:
                m = re.search(r"categoria\s*(?:a\s+|de\s+|en\s+|es\s+)?(.+)$", prompt, re.IGNORECASE)
                valor = m.group(1).strip(" .\"'«»") if m else None
            if valor is not None:
                valores[campo] = valor
        numericos = [c for c in atributos if c in ("precio_unitario", "precio_costo", "stock_minimo")]
        if len(numericos) == 1 and numericos[0] not in valores:
            ultimo = _ultimo_numero(texto)
            if ultimo:
                valores[numericos[0]] = ultimo
        if len(numericos) > 1:
            clausulas = re.split(r"\s+y\s+(?=(?:el\s+|la\s+)?(?:precio|costo|stock|minimo|rotacion))", texto)
            claves = {"precio_unitario": r"\bprecio\b|\bcuesta\b|\bvale\b", "precio_costo": r"\bcosto\b", "stock_minimo": r"\bminimo\b"}
            for campo in numericos:
                if campo in valores:
                    continue
                for clausula in clausulas:
                    if campo == "precio_unitario" and re.search(r"\bcosto\b", clausula):
                        continue
                    if re.search(claves[campo], clausula):
                        ultimo = _ultimo_numero(clausula)
                        if ultimo:
                            valores[campo] = ultimo
                            break
        quitar = [valores[c].replace(",", ".") for c in numericos if c in valores]

    producto, problema, consulta = _buscar_producto(db, texto_producto, quitar, incluir_inactivos=False)
    if producto is None and problema is None:
        return _texto(f"{PREFIJO_PRODUCTO} Dime el nombre, por ejemplo: «lejía» o «escoba de paja».")
    if producto is None and problema and "_ambiguos" in problema:
        cambios_txt = " y ".join(f"{ATRIBUTOS[c][1]} a {v}" for c, v in valores.items()) if valores else ""
        return respuesta_opciones(
            f"Encontré {len(problema['_ambiguos'])} productos para «{consulta}». ¿Cuál modifico?",
            [(p.nombre, _frase_edicion(p.nombre, valores) if valores else f"cambia el {ATRIBUTOS[atributos[0]][1]} de {p.nombre}") for p in problema["_ambiguos"]],
        )
    if producto is None:
        return problema

    if delta is not None:
        campo = atributos[0]
        actual = float(getattr(producto, campo) or 0)
        cantidad = _numero_a_float(delta[0])
        nuevo = actual * (1 + delta[1] * cantidad / 100) if delta[2] else actual + delta[1] * cantidad
        valores = {campo: f"{nuevo:.2f}" if campo != "stock_minimo" else str(int(round(nuevo)))}

    faltantes = [c for c in atributos if c not in valores and c in PREGUNTA_VALOR]
    if not valores or faltantes:
        campo = (faltantes or atributos)[0]
        if campo in PREGUNTA_VALOR:
            etiqueta, _ = PREGUNTA_VALOR[campo]
            actual = getattr(producto, campo)
            actual_txt = _soles(actual) if campo in ("precio_unitario", "precio_costo") else str(actual)
            return _texto(f"{PREFIJO_VALOR}{etiqueta} quieres para «{producto.nombre}»? (hoy: {actual_txt})")
        return _texto(f"¿Qué valor quieres para el {ATRIBUTOS[campo][1]} de «{producto.nombre}»?")

    cambios: List[Dict[str, Any]] = []
    payload: Dict[str, Any] = {}
    advertencias: List[str] = []
    for campo, valor in valores.items():
        etiqueta, _, formato = ATRIBUTOS[campo]
        if campo in ("precio_unitario", "precio_costo"):
            nuevo = round(_numero_a_float(valor), 2)
            actual = float(getattr(producto, campo) or 0)
            payload[campo] = nuevo
        elif campo == "stock_minimo":
            nuevo = int(_numero_a_float(valor))
            actual = int(producto.stock_minimo or 0)
            payload[campo] = nuevo
        elif campo == "nivel_rotacion":
            nuevo = valor
            actual = producto.nivel_rotacion
            payload[campo] = nuevo
        elif campo == "nombre":
            nuevo = valor[:200]
            actual = producto.nombre
            payload[campo] = nuevo
        else:
            categorias = list(db.scalars(select(Categoria)).all())
            elegidas = [c for c in candidatos(valor, [(c.id, c.nombre) for c in categorias]) if c[2] >= 1.0]
            if len(elegidas) != 1:
                nombres = ", ".join(c.nombre for c in categorias)
                return _texto(f"No identifiqué la categoría «{valor}». Las disponibles son: {nombres}.")
            nuevo = elegidas[0][1]
            actual = producto.categoria.nombre if producto.categoria else "—"
            payload["categoria_id"] = elegidas[0][0]
        if nuevo == actual:
            continue
        cambios.append({"campo": campo, "etiqueta": etiqueta, "actual": actual, "nuevo": nuevo, "formato": formato})

    if not cambios:
        return _texto(f"«{producto.nombre}» ya tiene esos valores. No hay nada que cambiar.")

    precio = payload.get("precio_unitario", float(producto.precio_unitario or 0))
    costo = payload.get("precio_costo", float(producto.precio_costo or 0))
    if costo > precio:
        advertencias.append("El costo queda por encima del precio de venta: el margen sería negativo.")
    if any(c["campo"] in ("precio_unitario", "precio_costo") for c in cambios):
        advertencias.append("El cambio de precio o costo afecta los márgenes y las cotizaciones futuras; las ya registradas no cambian.")

    datos = {
        "tipo": "accion_producto",
        "accion": "editar",
        "producto": {"id": producto.id, "nombre": producto.nombre, "sku": producto.sku},
        "cambios": cambios,
        "payload": payload,
        "advertencias": advertencias,
        "explicacion": _explicacion("editar"),
    }
    resumen = "; ".join(
        f"{c['etiqueta'].lower()}: {_soles(c['actual']) + ' → ' + _soles(c['nuevo']) if c['formato'] == 'soles' else str(c['actual']) + ' → ' + str(c['nuevo'])}"
        for c in cambios
    )
    return _texto(f"¿Actualizo «{producto.nombre}»? {resumen}. Confírmalo aquí abajo.", datos)


def _eliminar(db: Session, prompt: str) -> Dict[str, Any]:
    producto, problema, consulta = _buscar_producto(db, prompt, None, incluir_inactivos=True)
    if producto is None and problema is None:
        return _texto(f"{PREFIJO_PRODUCTO} Dime el nombre, por ejemplo: «elimina el producto escoba de paja».")
    if producto is None and problema and "_ambiguos" in problema:
        return respuesta_opciones(
            f"Encontré {len(problema['_ambiguos'])} productos para «{consulta}». ¿Cuál elimino?",
            [(p.nombre, f"elimina el producto {p.nombre}") for p in problema["_ambiguos"]],
        )
    if producto is None:
        return problema
    if not producto.activo:
        return _texto(f"«{producto.nombre}» ya está inactivo. Si quieres volver a usarlo, dime «reactiva el producto {producto.nombre}».")

    historial = ProductService._tiene_historial(db, producto.id)
    advertencia = (
        "Tiene historial de pedidos, cotizaciones o movimientos de stock: no se borrará, se marcará como inactivo."
        if historial
        else "No tiene historial: se eliminará definitivamente del catálogo."
    )
    datos = {
        "tipo": "accion_producto",
        "accion": "eliminar",
        "producto": {"id": producto.id, "nombre": producto.nombre, "sku": producto.sku},
        "tiene_historial": historial,
        "advertencias": [advertencia],
        "explicacion": _explicacion("eliminar"),
    }
    verbo = "desactivo" if historial else "elimino"
    return _texto(f"¿{verbo.capitalize()} el producto «{producto.nombre}»? {advertencia} Confírmalo aquí abajo.", datos)


def _reactivar(db: Session, prompt: str) -> Dict[str, Any]:
    producto, problema, consulta = _buscar_producto(db, prompt, None, incluir_inactivos=True)
    if producto is None and problema is None:
        return _texto(f"{PREFIJO_PRODUCTO} Dime el nombre del producto que quieres reactivar.")
    if producto is None and problema and "_ambiguos" in problema:
        inactivos = [p for p in problema["_ambiguos"] if not p.activo] or problema["_ambiguos"]
        return respuesta_opciones(
            f"Encontré {len(inactivos)} productos para «{consulta}». ¿Cuál reactivo?",
            [(p.nombre, f"reactiva el producto {p.nombre}") for p in inactivos],
        )
    if producto is None:
        return problema
    if producto.activo:
        return _texto(f"«{producto.nombre}» ya está activo.")
    datos = {
        "tipo": "accion_producto",
        "accion": "reactivar",
        "producto": {"id": producto.id, "nombre": producto.nombre, "sku": producto.sku},
        "advertencias": [],
        "explicacion": _explicacion("reactivar"),
    }
    return _texto(f"¿Reactivo el producto «{producto.nombre}»? Volverá a aparecer en el catálogo y en las cotizaciones.", datos)


PAT_CREAR_PRODUCTO = re.compile(
    r"\b(?:crea\w*|registra\w*|agrega\w*|anade\w*|da de alta|dar de alta|inscribe\w*|ingresa\w*|nuevo|nueva)\b[^.\n]{0,25}\bproducto\b"
)
PAT_MARCADOR_PRODUCTO = re.compile(
    r"(?i)(?:,|;|\bprecio\b|\bcosto\b|\bcategor[ií]a\b|\bunidad\b|\bstock\b|\bm[ií]nimo\b|\brotaci[oó]n\b|\bsku\b|\bc[oó]digo\b|"
    r"\bcon\s+(?:precio|costo|stock|categor|unidad)|\by\s+(?:precio|costo|stock|categor|unidad)|\bcuesta\b|\bvale\b)"
)
RELLENO_NOMBRE = re.compile(r"(?i)^(?:[:\-–]\s*|(?:nuevo|nueva|un|una|el|la|llamado|llamada|de nombre|con nombre)\b\s*[:\-–]?\s*)+")
MAX_SKU = 50


def _generar_sku(db: Session, nombre: str) -> str:
    base = unicodedata.normalize("NFD", nombre or "")
    base = "".join(c for c in base if not unicodedata.combining(c)).upper()
    letras = re.sub(r"[^A-Z\s]", "", base).strip()
    prefijo = (letras.split()[0] if letras.split() else "PRD")[:3] or "PRD"
    existentes = {sku.upper() for sku in db.scalars(select(Producto.sku)).all()}
    numero = 1
    while f"{prefijo}-{numero:03d}" in existentes:
        numero += 1
    return f"{prefijo}-{numero:03d}"


def _extraer_nombre_producto(prompt: str) -> str:
    explicito = re.search(r"(?i)\b(?:nombre|llamad[oa])\s*:?\s*(?:es\s*)?([^,;]+)", prompt)
    if explicito:
        return RELLENO_NOMBRE.sub("", explicito.group(1)).strip(" .:-–\"'«»")
    posicion = re.search(r"(?i)\bproducto\b", prompt)
    resto = prompt[posicion.end():] if posicion else prompt
    resto = RELLENO_NOMBRE.sub("", resto.strip())
    corte = PAT_MARCADOR_PRODUCTO.search(resto)
    nombre = resto[: corte.start()] if corte else resto
    nombre = RELLENO_NOMBRE.sub("", nombre.strip())
    return re.sub(r"\s+", " ", nombre).strip(" .:-–\"'«»")


def _num(patron: str, texto: str) -> Optional[str]:
    m = re.search(patron, texto)
    return m.group(1).replace(",", ".") if m else None


def _extraer_campos_producto(prompt: str) -> Dict[str, Any]:
    texto = _sin_acentos(prompt)
    campos: Dict[str, Any] = {}
    minimo = _num(r"(?:stock\s+minimo|minimo)\s*(?:de|a|es|=|:)?\s*(\d+)", texto)
    sin_minimo = re.sub(r"(?:stock\s+minimo|minimo)\s*(?:de|a|es|=|:)?\s*\d+", " ", texto)
    costo = _num(r"(?:precio\s+de\s+costo|costo)\s*(?:de|a|es|=|:)?\s*(?:s/\.?\s*)?(\d+(?:[.,]\d+)?)", sin_minimo)
    sin_costo = re.sub(r"(?:precio\s+de\s+costo|costo)\s*(?:de|a|es|=|:)?\s*(?:s/\.?\s*)?\d+(?:[.,]\d+)?", " ", sin_minimo)
    precio = _num(r"(?:precio(?:\s+de\s+venta)?|cuesta|vale)\s*(?:de|a|es|=|:)?\s*(?:s/\.?\s*)?(\d+(?:[.,]\d+)?)", sin_costo)
    stock = _num(r"stock(?:\s+inicial)?\s*(?:de|a|es|=|:)?\s*(\d+)", sin_costo)
    if precio is not None:
        campos["precio_unitario"] = round(float(precio), 2)
    if costo is not None:
        campos["precio_costo"] = round(float(costo), 2)
    if stock is not None:
        campos["stock_actual"] = int(stock)
    if minimo is not None:
        campos["stock_minimo"] = int(minimo)
    unidad = re.search(r"(?i)\bunidad(?:\s+de\s+medida)?\s*(?:de|es|=|:)?\s*([^,;]+)", prompt)
    if unidad:
        campos["unidad_medida"] = PAT_MARCADOR_PRODUCTO.split(unidad.group(1))[0].strip(" .")[:100]
    rotacion = re.search(r"(?i)\brotaci[oó]n\s*(?:de|es|=|:)?\s*(alta|media|baja)", prompt)
    if rotacion:
        campos["nivel_rotacion"] = rotacion.group(1).capitalize()
    sku = re.search(r"(?i)\b(?:sku|c[oó]digo)\s*(?:de|es|=|:)?\s*([A-Za-z0-9\-]{2,40})", prompt)
    if sku:
        campos["sku"] = sku.group(1).upper()
    categoria = re.search(r"(?i)\bcategor[ií]a\s*(?:de|es|=|:)?\s*(?:«([^»]+)»|([^,;]+))", prompt)
    if categoria:
        campos["_categoria"] = (categoria.group(1) or categoria.group(2)).strip(" .")
    return campos


def _frase_crear(nombre: str, campos: Dict[str, Any], categoria: Optional[str] = None) -> str:
    partes = [f"crea el producto {nombre}"]
    if categoria:
        partes.append(f"categoría «{categoria}»")
    if "precio_unitario" in campos:
        partes.append(f"precio {campos['precio_unitario']}")
    if "precio_costo" in campos:
        partes.append(f"costo {campos['precio_costo']}")
    if "stock_actual" in campos:
        partes.append(f"stock {campos['stock_actual']}")
    if "stock_minimo" in campos:
        partes.append(f"stock mínimo {campos['stock_minimo']}")
    if "unidad_medida" in campos:
        partes.append(f"unidad {campos['unidad_medida']}")
    if "nivel_rotacion" in campos:
        partes.append(f"rotación {campos['nivel_rotacion']}")
    return ", ".join(partes)


def _crear(db: Session, prompt: str) -> Dict[str, Any]:
    nombre = _extraer_nombre_producto(prompt)
    campos = _extraer_campos_producto(prompt)
    categoria_texto = campos.pop("_categoria", None)

    if not nombre or len(nombre) < 2:
        return _texto(
            f"{PREFIJO_NOMBRE_PRODUCTO} Dime también precio, costo y categoría. Por ejemplo: "
            "«Jabón líquido 1 lt, precio 12, costo 8, categoría Limpieza y desinfección, stock 20». "
            f"(Llevo: {_frase_crear('', campos)})"
        )

    objetivo = normalizar(nombre)
    for existente in db.scalars(select(Producto)).all():
        if normalizar(existente.nombre) == objetivo:
            return respuesta_opciones(
                f"Ya existe el producto «{existente.nombre}» ({existente.sku}), con precio {_soles(existente.precio_unitario)} y stock {existente.stock_actual or 0}. No lo vuelvo a crear.",
                [
                    ("Reponer stock", f"repon el stock de {existente.nombre}"),
                    ("Cambiar precio", f"cámbiale el precio a {existente.nombre}"),
                    ("Ver stock y precio", f"stock de {existente.nombre}"),
                ],
            )

    categorias = list(db.scalars(select(Categoria).order_by(Categoria.nombre)).all())
    categoria = None
    if categoria_texto:
        exactas = [c for c in candidatos(categoria_texto, [(c.id, c.nombre) for c in categorias]) if c[2] >= 1.0]
        normalizado = normalizar(categoria_texto)
        iguales = [c for c in exactas if normalizar(c[1]) == normalizado]
        if iguales:
            exactas = iguales[:1]
        if len(exactas) == 1:
            categoria = next(c for c in categorias if c.id == exactas[0][0])

    llevo = _frase_crear(nombre, campos, categoria.nombre if categoria else None)
    faltan = []
    if categoria is None:
        faltan.append("la categoría")
    if "precio_unitario" not in campos:
        faltan.append("el precio de venta")
    if "precio_costo" not in campos:
        faltan.append("el costo")

    if categoria is None and ("precio_unitario" in campos and "precio_costo" in campos):
        return respuesta_opciones(
            f"¿En qué categoría registro «{nombre}»?",
            [(c.nombre, f"{llevo}, categoría «{c.nombre}»") for c in categorias],
        )
    if faltan:
        return _texto(
            f"Para registrar «{nombre}» me falta {' y '.join(faltan) if len(faltan) < 3 else ', '.join(faltan[:-1]) + ' y ' + faltan[-1]}. "
            f"Dímelo así: «precio 12, costo 8, categoría Limpieza». (Llevo: {llevo})"
        )

    advertencias: List[str] = []
    if campos["precio_costo"] > campos["precio_unitario"]:
        advertencias.append("El costo está por encima del precio de venta: el margen sería negativo.")
    sku = campos.get("sku") or _generar_sku(db, nombre)
    datos = {
        "tipo": "borrador_producto",
        "producto": {
            "nombre": nombre[:200],
            "sku": sku[:MAX_SKU],
            "categoria_id": categoria.id,
            "unidad_medida": campos.get("unidad_medida", "Unidad"),
            "precio_unitario": campos["precio_unitario"],
            "precio_costo": campos["precio_costo"],
            "stock_actual": campos.get("stock_actual", 0),
            "stock_minimo": campos.get("stock_minimo", 5),
            "nivel_rotacion": campos.get("nivel_rotacion", "Media"),
        },
        "categorias": [{"id": c.id, "nombre": c.nombre} for c in categorias],
        "advertencias": advertencias,
        "explicacion": _explicacion("crear"),
    }
    return _texto(
        f"Preparé el registro de «{nombre}» en {categoria.nombre}: precio {_soles(campos['precio_unitario'])}, costo {_soles(campos['precio_costo'])}. Revísalo, corrige lo que haga falta y confírmalo aquí abajo.",
        datos,
    )


def resolver_pendiente_producto(ultimo_agente: Optional[str], prompt: str) -> Optional[str]:
    if not ultimo_agente:
        return None
    llevo = re.search(r"\(Llevo: (.*)\)\s*$", ultimo_agente)
    if llevo and "?" not in prompt:
        base = llevo.group(1)
        if ultimo_agente.startswith(PREFIJO_NOMBRE_PRODUCTO):
            return f"crea el producto {prompt}" if not base.strip().rstrip(",") else f"{base}, nombre {prompt}"
        return f"{base}, {prompt}"
    m = re.match(r"^¿Qué (precio de venta|costo|stock mínimo|nivel de rotación) quieres para «(.+)»\?", ultimo_agente)
    if m and re.search(r"\d|alta|media|baja", prompt.lower()):
        etiqueta = {"precio de venta": "precio", "costo": "costo", "stock mínimo": "stock mínimo", "nivel de rotación": "rotación"}[m.group(1)]
        return f"cambia el {etiqueta} de {m.group(2)} a {prompt.strip()}"
    return None


def responder_producto(db: Session, prompt: str, es_admin: bool) -> Optional[Dict[str, Any]]:
    limpio = normalizar(prompt)
    if PAT_EXCLUIR.search(limpio) or es_crear_cliente(prompt):
        return None

    if PAT_CREAR_PRODUCTO.search(limpio):
        if not es_admin:
            return _texto("Solo un administrador puede crear productos.")
        return _crear(db, prompt)

    if re.search(rf"\b{V_REACTIVAR}\b[^.\n]{{0,30}}\bproducto\b|\breactiva\w*\b", limpio) and re.search(r"\bproducto\b|\breactiva", limpio):
        if not es_admin:
            return _texto("Solo un administrador puede reactivar productos.")
        return _reactivar(db, prompt)

    if re.search(rf"\b{V_ELIMINAR}\b", limpio) and re.search(r"\bproducto\b|\bdel catalogo\b|\bdel inventario\b|\bdesactiva\w*\b|\bdeshabilita\w*\b|\binactiva\w*\b", limpio):
        if not es_admin:
            return _texto("Solo un administrador puede eliminar o desactivar productos.")
        return _eliminar(db, prompt)

    atributos = _atributos_en_texto(limpio)
    if not atributos:
        return None
    hay_verbo = re.search(rf"\b{V_EDITAR}\b", limpio) or PAT_AHORA_CUESTA.search(limpio)
    if not hay_verbo:
        return None
    if "stock_minimo" not in atributos and re.search(r"\bstock\b", limpio) and not re.search(r"\bminimo\b", limpio):
        return None
    if not es_admin:
        return _texto("Solo un administrador puede editar productos.")
    return _editar(db, prompt, limpio, atributos)
