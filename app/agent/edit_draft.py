import copy
import re
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.quote_intent import _buscar_cliente_en_texto
from app.models.product import Producto
from app.services.quote_note_service import candidatos, normalizar

MAX_CANTIDAD = 9999
MAX_OPCIONES = 8

VERBOS_QUITAR = r"quita|quitar|quitale|elimina|eliminar|eliminale|saca|sacar|sacale|borra|borrar|borrale|retira|retirar|remueve|remover"
VERBOS_AGREGAR = r"agrega|agregar|agregale|anade|anadir|anadele|suma|sumar|sumale|incluye|incluir|incluyele|ponle|adiciona|adicionar"
VERBOS_CAMBIAR = r"cambia|cambiar|cambiale|pon|poner|deja|dejalo|dejala|ajusta|ajustar|modifica|modificar|actualiza|actualizar|sube|subele|baja|bajale|aumenta|aumentar|reduce|reducir|disminuye"
VERBOS_SUBIR = {"sube", "subele", "aumenta", "aumentar"}
VERBOS_BAJAR = {"baja", "bajale", "reduce", "reducir", "disminuye"}

PAT_EDICION = re.compile(rf"\b(?:{VERBOS_QUITAR}|{VERBOS_AGREGAR}|{VERBOS_CAMBIAR})\b")
PAT_DIVISION = re.compile(
    rf"\s*(?:,|;|\by tambien\b|\by ademas\b|\bademas\b|\by luego\b|\by (?=(?:{VERBOS_QUITAR}|{VERBOS_AGREGAR}|{VERBOS_CAMBIAR})\b)|\by (?=\d))\s*"
)
PAT_CLIENTE = re.compile(r"\b(?:cliente|para)\s+(?:es |sea |a )?(?P<c>[a-z0-9 .]+)$")
PAT_CAMBIAR_CANT = re.compile(
    rf"^(?P<verbo>{VERBOS_CAMBIAR})\s+(?:la cantidad de |las cantidades de |cantidad de )?(?:las |los |el |la |lo )?"
    r"(?P<texto>.+?)\s+(?P<prep>a|por|en|hasta|con)\s+(?P<n>\d{1,5})(?:\s*(?:unidades|unidad|und|u|piezas))?$"
)
PAT_VERBO_INICIAL = re.compile(rf"^(?P<verbo>{VERBOS_QUITAR}|{VERBOS_AGREGAR}|{VERBOS_CAMBIAR})\b\s*(?P<resto>.*)$")
RUIDO_INICIO = re.compile(r"^(?:por favor|porfa|ahora|tambien|ademas|luego|y|pero)\s+")
ARTICULOS = re.compile(r"^(?:(?:la|las|el|los|lo|un|una|unos|unas|al|a|de|del|mas)\s+)+")
NUMEROS_TEXTO = {
    "un": "1", "uno": "1", "una": "1", "dos": "2", "tres": "3", "cuatro": "4", "cinco": "5", "seis": "6",
    "siete": "7", "ocho": "8", "nueve": "9", "diez": "10", "once": "11", "doce": "12", "quince": "15", "veinte": "20",
}


def es_edicion(texto: str) -> bool:
    return bool(PAT_EDICION.search(normalizar(texto)))


def _numeros_en_letras(texto: str) -> str:
    return " ".join(NUMEROS_TEXTO.get(p, p) if p not in {"un", "uno", "una"} else p for p in texto.split())


def _clausulas(limpio: str) -> List[str]:
    return [c.strip() for c in PAT_DIVISION.split(limpio) if c and c.strip()]


def _orden_agregar(resto: str) -> Dict[str, Any]:
    coincidencia = re.search(r"\b(\d{1,5})\b", resto)
    cantidad = int(coincidencia.group(1)) if coincidencia else 1
    texto = re.sub(r"\b\d{1,5}\b", " ", resto, count=1)
    texto = re.sub(r"\b(?:unidades|unidad|und|piezas)\b", " ", texto)
    texto = re.sub(r"\s+", " ", texto).strip()
    return {"accion": "agregar", "texto": ARTICULOS.sub("", texto).strip(), "cantidad": cantidad}


def _parsear(clausula: str, anterior: Optional[str] = None) -> Optional[Dict[str, Any]]:
    clausula = RUIDO_INICIO.sub("", clausula).strip()
    if anterior == "agregar" and re.match(r"^(?:\d{1,5}|un|una|uno)\b", clausula):
        return _orden_agregar(clausula)
    cambiar = PAT_CAMBIAR_CANT.match(clausula)
    if cambiar:
        verbo = cambiar.group("verbo")
        n = int(cambiar.group("n"))
        relativo = cambiar.group("prep") == "en" and (verbo in VERBOS_SUBIR or verbo in VERBOS_BAJAR)
        return {
            "accion": "cambiar",
            "texto": ARTICULOS.sub("", cambiar.group("texto")).strip(),
            "cantidad": n,
            "delta": (n if verbo in VERBOS_SUBIR else -n) if relativo else None,
        }
    inicial = PAT_VERBO_INICIAL.match(clausula)
    if not inicial:
        return None
    verbo, resto = inicial.group("verbo"), inicial.group("resto").strip()
    if re.fullmatch(VERBOS_QUITAR, verbo):
        return {"accion": "quitar", "texto": ARTICULOS.sub("", resto).strip()}
    if re.fullmatch(VERBOS_AGREGAR, verbo) or verbo == "pon":
        return _orden_agregar(resto)
    return None


def _campo_precio(tipo: str) -> str:
    return "precio_esperado" if tipo == "cotizacion" else "precio_unitario"


def _buscar_en_items(items: List[Dict[str, Any]], texto: str) -> List[int]:
    lista = candidatos(texto, [(i, it["nombre"]) for i, it in enumerate(items)], True)
    return [c[0] for c in lista if c[2] >= 1.0]


def _total(items: List[Dict[str, Any]], campo: str) -> float:
    return sum(float(it.get(campo) or 0) * int(it.get("cantidad") or 0) for it in items)


def _aplicar_cantidad(item: Dict[str, Any], cantidad: int) -> Optional[str]:
    if cantidad < 1 or cantidad > MAX_CANTIDAD:
        return f"La cantidad de «{item['nombre']}» debe estar entre 1 y {MAX_CANTIDAD}."
    item["cantidad"] = cantidad
    return None


def responder_edicion(db: Session, prompt: str, borrador: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tipo = borrador.get("tipo")
    if tipo not in ("cotizacion", "pedido"):
        return None
    campo = _campo_precio(tipo)
    descuento = float(borrador.get("descuento_pct") or 0)
    items = copy.deepcopy(borrador.get("items") or [])
    cliente = borrador.get("cliente")
    limpio = _numeros_en_letras(normalizar(prompt))

    cambios: List[str] = []
    problemas: List[str] = []
    entendio = False

    if tipo == "cotizacion":
        coincidencia = re.search(r"\b(?:cambia|pon|deja|usa|cambiale)\b.*\b(?:cliente|para)\b", limpio)
        busqueda = PAT_CLIENTE.search(limpio)
        if coincidencia and busqueda:
            nuevo, dudosos = _buscar_cliente_en_texto(db, busqueda.group("c"))
            if nuevo:
                cliente = {"id": nuevo.id, "nombre": nuevo.razon_social}
                cambios.append(f"cliente: {nuevo.razon_social}")
                entendio = True
                limpio = limpio[: coincidencia.start()].strip()
            elif dudosos:
                problemas.append("Hay varios clientes parecidos: " + ", ".join(c.razon_social for c in dudosos[:4]) + ". Dime el nombre completo.")
                entendio = True
                limpio = limpio[: coincidencia.start()].strip()

    catalogo: Optional[List[Producto]] = None

    anterior: Optional[str] = None
    for clausula in _clausulas(limpio):
        orden = _parsear(clausula, anterior)
        if not orden or not orden["texto"]:
            continue
        entendio = True
        anterior = orden["accion"]
        texto = orden["texto"]

        if orden["accion"] in ("cambiar", "quitar"):
            indices = _buscar_en_items(items, texto)
            if not indices:
                problemas.append(f"No encontré «{texto}» en el borrador.")
                continue
            if len(indices) > 1:
                nombres = ", ".join(items[i]["nombre"] for i in indices[:4])
                problemas.append(f"«{texto}» coincide con varios productos del borrador ({nombres}). Dime cuál.")
                continue
            indice = indices[0]
            item = items[indice]
            if orden["accion"] == "quitar":
                cambios.append(f"quité {item['nombre']}")
                items.pop(indice)
                continue
            nueva = orden["cantidad"]
            if orden.get("delta") is not None:
                nueva = int(item.get("cantidad") or 0) + orden["delta"]
            if nueva <= 0 and orden.get("delta") is None:
                cambios.append(f"quité {item['nombre']}")
                items.pop(indice)
                continue
            error = _aplicar_cantidad(item, nueva)
            if error:
                problemas.append(error)
            else:
                cambios.append(f"{item['nombre']} ahora {nueva} u.")
            continue

        if catalogo is None:
            catalogo = list(db.scalars(select(Producto).where(Producto.activo.is_(True))).all())
        por_id = {p.id: p for p in catalogo}
        lista = candidatos(texto, [(p.id, p.nombre) for p in catalogo], True)
        exactos = [c for c in lista if c[2] >= 1.0]
        objetivo = normalizar(texto)
        iguales = [c for c in exactos if normalizar(c[1]) == objetivo]
        if iguales:
            exactos = iguales[:1]
        cantidad = max(1, orden["cantidad"])

        if not exactos:
            problemas.append(f"No encontré «{texto}» en el catálogo.")
            continue

        if len(exactos) > 1:
            if tipo == "pedido":
                nombres = ", ".join(c[1] for c in exactos[:4])
                problemas.append(f"«{texto}» coincide con varios productos ({nombres}). Dime cuál agregar.")
                continue
            items.append(
                {
                    "producto_id": None,
                    "nombre": texto,
                    "texto_original": texto,
                    "cantidad": cantidad,
                    "precio_esperado": None,
                    "stock": None,
                    "coincidencia": "ambiguo",
                    "opciones": [
                        {
                            "producto_id": por_id[c[0]].id,
                            "nombre": por_id[c[0]].nombre,
                            "precio": float(por_id[c[0]].precio_unitario),
                            "stock": por_id[c[0]].stock_actual,
                        }
                        for c in sorted(exactos, key=lambda c: c[1])[:MAX_OPCIONES]
                    ],
                }
            )
            cambios.append(f"agregué «{texto}» ({len(exactos)} opciones, elige cuál)")
            continue

        producto = por_id[exactos[0][0]]
        existente = next((it for it in items if it.get("producto_id") == producto.id), None)
        if existente:
            existente["cantidad"] = min(MAX_CANTIDAD, int(existente.get("cantidad") or 0) + cantidad)
            cambios.append(f"{producto.nombre} ahora {existente['cantidad']} u.")
            continue
        precio = float(producto.precio_unitario)
        if tipo == "pedido":
            precio = round(precio * (1 - descuento / 100), 2)
        nuevo_item = {
            "producto_id": producto.id,
            "nombre": producto.nombre,
            "cantidad": cantidad,
            campo: precio,
            "stock": producto.stock_actual,
        }
        if tipo == "cotizacion":
            nuevo_item.update({"texto_original": texto, "coincidencia": "catalogo", "opciones": []})
        items.append(nuevo_item)
        cambios.append(f"agregué {cantidad} × {producto.nombre}")

    if not entendio:
        return None

    partes: List[str] = []
    if cambios:
        partes.append("Listo: " + "; ".join(c.rstrip(".") for c in cambios) + ".")
        partes.append(f"Total aprox. S/ {_total(items, campo):,.2f}.")
    partes += problemas
    if not cambios and not problemas:
        return None

    datos: Dict[str, Any] = {
        "tipo": "edicion_borrador",
        "mensaje_id": borrador.get("mensaje_id"),
        "borrador_tipo": tipo,
        "items": items if cambios else borrador.get("items"),
        "cliente": cliente,
        "aplicado": bool(cambios),
    }
    return {"respuesta": " ".join(partes), "datos_estructurados": datos}
