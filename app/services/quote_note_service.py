import json
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.llm_client import llm_client
from app.models.customer import Cliente
from app.models.product import Producto
from app.schemas.customer_request import (
    NotaCotizacionItem,
    NotaCotizacionOpcion,
    NotaCotizacionRequest,
    NotaCotizacionResponse,
)

PALABRAS_VACIAS = {
    "de", "del", "la", "el", "los", "las", "x", "para", "con", "y", "en",
    "un", "una", "unos", "unas", "por", "al", "a",
}

UNIDADES = {
    "l": "lt", "lt": "lt", "lts": "lt", "litro": "lt", "litros": "lt",
    "ml": "ml", "kg": "kg", "kilo": "kg", "kilos": "kg",
    "g": "g", "gr": "g", "gramos": "g", "galon": "galon", "galones": "galon",
}

PATRON_MEDIDA = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(litros?|lts?|l|ml|kilos?|kg|gramos|gr|g|galon(?:es)?)\b"
)

SINONIMOS = {
    "cloro": "lejia",
    "lavandina": "lejia",
    "hipoclorito": "lejia",
    "detergentes": "detergente",
    "jabones": "jabon",
}

SINONIMOS_PRODUCTO = {
    "mopa": "trapeador",
    "mopas": "trapeador",
    "trapero": "trapeador",
    "trapeadora": "trapeador",
    "basurero": "tacho",
    "basureros": "tacho",
    "rasqueta": "jalador",
    "escobilla": "escobillo",
    "lavavajillas": "lavavajilla",
    "ph": "papel higienico",
    "unidad": "und",
    "unidades": "und",
    "uni": "und",
    "unid": "und",
}
LARGO_MIN_ERRATA = 6
LARGO_MIN_ERRATA_DOBLE = 9

MAX_CANDIDATOS = 6
MAX_OPCIONES = 40
COBERTURA_SEGURA = 1.0
PUNTAJE_SEGURO = 0.75

UMBRAL_COBERTURA = 0.6
UMBRAL_PUNTAJE = 0.5
CANTIDAD_MAXIMA = 10000

PROMPT_SELECCION = (
    "Eres el asistente de cotizaciones de Distribuidora EL PRÍNCIPE. "
    "Para cada producto que pidió el vendedor, elige de su lista de candidatos del catálogo el que mejor corresponde. "
    "Considera sinónimos y lenguaje coloquial (por ejemplo, cloro o lavandina equivalen a lejía) y respeta la marca o la "
    "presentación si el vendedor la indicó. Si el vendedor no indicó presentación y hay varias, elige la más común o la primera. "
    "Si ningún candidato corresponde razonablemente, usa null. No inventes identificadores. "
    "Responde estrictamente en JSON: "
    '{"selecciones": [{"indice": int, "producto_id": int|null}]}'
)

PROMPT_SISTEMA = (
    "Eres el asistente de cotizaciones de Distribuidora EL PRÍNCIPE. "
    "Recibes la nota que escribió un vendedor con lo que pide un cliente y extraes la lista de productos con sus cantidades. "
    "Reglas: no inventes productos; copia el nombre del producto tal como lo escribió el vendedor, incluyendo marca y presentación; "
    "la cantidad es un entero mayor o igual a 1 (si no se indica, usa 1; una docena es 12; media docena es 6); "
    "no incluyas precios; si la nota menciona el nombre del cliente, devuélvelo en 'cliente', si no, null. "
    "Responde estrictamente en JSON con esta forma: "
    '{"cliente": str|null, "items": [{"producto": str, "cantidad": int}]}'
)


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFKD", texto or "")
    texto = "".join(c for c in texto if not unicodedata.combining(c)).lower()
    texto = texto.replace(",", ".")
    texto = PATRON_MEDIDA.sub(lambda m: f"{m.group(1)}{UNIDADES[m.group(2)]}", texto)
    texto = re.sub(r"[^a-z0-9.]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def tokens(texto: str) -> List[str]:
    return [SINONIMOS.get(t, t) for t in normalizar(texto).split() if t not in PALABRAS_VACIAS]


def _tokens_tolerantes(texto: str) -> List[str]:
    base = re.sub(r"(\d+(?:\.\d+)?)\s*x\s*(\d+(?:\.\d+)?)", r"\1 \2", normalizar(texto))
    resultado: List[str] = []
    for t in base.split():
        if t in PALABRAS_VACIAS:
            continue
        reemplazo = SINONIMOS_PRODUCTO.get(SINONIMOS.get(t, t), SINONIMOS.get(t, t))
        resultado.extend(reemplazo.split())
    return resultado


def _distancia(a: str, b: str) -> int:
    filas = [[0] * (len(b) + 1) for _ in range(len(a) + 1)]
    for i in range(len(a) + 1):
        filas[i][0] = i
    for j in range(len(b) + 1):
        filas[0][j] = j
    for i in range(1, len(a) + 1):
        for j in range(1, len(b) + 1):
            costo = 0 if a[i - 1] == b[j - 1] else 1
            filas[i][j] = min(filas[i - 1][j] + 1, filas[i][j - 1] + 1, filas[i - 1][j - 1] + costo)
            if i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                filas[i][j] = min(filas[i][j], filas[i - 2][j - 2] + 1)
    return filas[len(a)][len(b)]


def _token_tolerante(consulta: str, candidato: str) -> bool:
    if _token_coincide(consulta, candidato):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?", consulta) and re.fullmatch(rf"{re.escape(consulta)}[a-z]+", candidato):
        return True
    if consulta.isalpha() and candidato.isalpha() and consulta[0] == candidato[0]:
        menor = min(len(consulta), len(candidato))
        if menor >= LARGO_MIN_ERRATA_DOBLE:
            return _distancia(consulta, candidato) <= 2
        if menor >= LARGO_MIN_ERRATA:
            return _distancia(consulta, candidato) <= 1
    return False


def _singular(token: str) -> str:
    if token.isdigit():
        return token
    if len(token) > 5 and token.endswith("es"):
        return token[:-2]
    if len(token) > 3 and token.endswith("s"):
        return token[:-1]
    return token


def _token_coincide(consulta: str, candidato: str) -> bool:
    if consulta == candidato:
        return True
    if _singular(consulta) == _singular(candidato):
        return True
    if (
        min(len(consulta), len(candidato)) >= 4
        and abs(len(consulta) - len(candidato)) <= 2
        and (candidato.startswith(consulta) or consulta.startswith(candidato))
    ):
        return True
    if consulta.isdigit() or candidato.isdigit():
        return False
    return SequenceMatcher(None, consulta, candidato).ratio() >= 0.9


def _coincidentes_tolerantes(tq: List[str], tp: List[str]) -> int:
    total = 0
    i = 0
    while i < len(tq):
        if i + 1 < len(tq) and any(_token_tolerante(tq[i] + tq[i + 1], p) for p in tp):
            total += 2
            i += 2
            continue
        if any(_token_tolerante(tq[i], p) for p in tp):
            total += 1
        elif any(_token_tolerante(tq[i], tp[j] + tp[j + 1]) for j in range(len(tp) - 1)):
            total += 1
        i += 1
    return min(total, len(tq))


def puntaje(consulta: str, candidato: str, tolerante: bool = False) -> Tuple[float, float]:
    tq = _tokens_tolerantes(consulta) if tolerante else tokens(consulta)
    tp = _tokens_tolerantes(candidato) if tolerante else tokens(candidato)
    if not tq or not tp:
        return 0.0, 0.0
    if tolerante:
        coincidentes = _coincidentes_tolerantes(tq, tp)
    else:
        coincidentes = sum(1 for q in tq if any(_token_coincide(q, p) for p in tp))
    cobertura = coincidentes / len(tq)
    jaccard = coincidentes / (len(tq) + len(tp) - coincidentes)
    ratio = SequenceMatcher(None, " ".join(tq), " ".join(tp)).ratio()
    return cobertura, 0.5 * cobertura + 0.2 * jaccard + 0.3 * ratio


def mejor_coincidencia(consulta: str, opciones: Sequence[Tuple[Any, str]], tolerante: bool = False) -> Optional[Any]:
    mejor = None
    mejor_puntaje = 0.0
    for identificador, nombre in opciones:
        cobertura, total = puntaje(consulta, nombre, tolerante)
        if cobertura >= UMBRAL_COBERTURA and total >= UMBRAL_PUNTAJE and total > mejor_puntaje:
            mejor = identificador
            mejor_puntaje = total
    return mejor


def candidatos(consulta: str, opciones: Sequence[Tuple[Any, str]], tolerante: bool = False) -> List[Tuple[Any, str, float, float]]:
    resultado = []
    for identificador, nombre in opciones:
        cobertura, total = puntaje(consulta, nombre, tolerante)
        if cobertura > 0:
            resultado.append((identificador, nombre, cobertura, total))
    resultado.sort(key=lambda fila: fila[3], reverse=True)
    return resultado


def _entero_positivo(valor: Any) -> int:
    try:
        numero = int(float(valor))
    except (TypeError, ValueError):
        return 1
    return max(1, min(numero, CANTIDAD_MAXIMA))


class NotaCotizacionService:
    @staticmethod
    def _extraer_con_ia(texto: str) -> Optional[Dict[str, Any]]:
        respuesta = llm_client.generate_response(
            system_prompt=PROMPT_SISTEMA,
            user_prompt=f"Nota del vendedor:\n{texto}\n\nExtrae los productos y cantidades.",
            max_tokens=1200,
        )
        try:
            inicio = respuesta.find("{")
            fin = respuesta.rfind("}") + 1
            parsed = json.loads(respuesta[inicio:fin])
        except Exception:
            return None
        if not isinstance(parsed, dict) or not isinstance(parsed.get("items"), list):
            return None
        return parsed

    @staticmethod
    def _elegir_con_ia(consultas: List[Dict[str, Any]]) -> Dict[int, Optional[int]]:
        if not consultas:
            return {}
        respuesta = llm_client.generate_response(
            system_prompt=PROMPT_SELECCION,
            user_prompt=json.dumps(consultas, ensure_ascii=False),
            max_tokens=1200,
        )
        try:
            inicio = respuesta.find("{")
            fin = respuesta.rfind("}") + 1
            parsed = json.loads(respuesta[inicio:fin])
            selecciones = parsed.get("selecciones", [])
        except Exception:
            return {}
        elegidas: Dict[int, Optional[int]] = {}
        for sel in selecciones if isinstance(selecciones, list) else []:
            if not isinstance(sel, dict):
                continue
            try:
                indice = int(sel.get("indice"))
            except (TypeError, ValueError):
                continue
            producto_id = sel.get("producto_id")
            elegidas[indice] = producto_id if isinstance(producto_id, int) else None
        return elegidas

    @staticmethod
    def interpretar(db: Session, payload: NotaCotizacionRequest) -> NotaCotizacionResponse:
        parsed = NotaCotizacionService._extraer_con_ia(payload.texto)
        if parsed is None:
            return NotaCotizacionResponse(
                ia_disponible=False,
                advertencias=[
                    "La IA no pudo interpretar la nota en este momento. Agrega los productos manualmente."
                ],
            )

        productos = list(db.scalars(select(Producto).where(Producto.activo.is_(True))).all())
        opciones_producto = [(p.id, p.nombre) for p in productos]
        por_id = {p.id: p for p in productos}

        pedidos: List[Tuple[str, int]] = []
        for crudo in parsed["items"]:
            if not isinstance(crudo, dict):
                continue
            texto_producto = str(crudo.get("producto") or "").strip()
            if texto_producto:
                pedidos.append((texto_producto, _entero_positivo(crudo.get("cantidad"))))

        resueltos: Dict[int, Optional[int]] = {}
        opciones_por_indice: Dict[int, List[Tuple[Any, str, float, float]]] = {}
        por_consultar: List[Dict[str, Any]] = []
        for indice, (texto_producto, _) in enumerate(pedidos):
            lista = candidatos(texto_producto, opciones_producto, True)
            exactos = [c for c in lista if c[2] >= COBERTURA_SEGURA]
            if len(exactos) == 1:
                resueltos[indice] = exactos[0][0]
            elif len(exactos) >= 2:
                resueltos[indice] = None
                opciones_por_indice[indice] = sorted(exactos, key=lambda c: c[1])[:MAX_OPCIONES]
            elif lista:
                por_consultar.append(
                    {
                        "indice": indice,
                        "pedido": texto_producto,
                        "candidatos": [{"id": c[0], "nombre": c[1]} for c in lista[:MAX_CANDIDATOS]],
                    }
                )
            else:
                resueltos[indice] = None

        elegidas = NotaCotizacionService._elegir_con_ia(por_consultar)
        for consulta in por_consultar:
            indice = consulta["indice"]
            ids_validos = {c["id"] for c in consulta["candidatos"]}
            if indice in elegidas:
                elegido = elegidas[indice]
                resueltos[indice] = elegido if elegido in ids_validos else None
            else:
                resueltos[indice] = mejor_coincidencia(pedidos[indice][0], opciones_producto, True)

        items: List[NotaCotizacionItem] = []
        sin_coincidencia: List[str] = []
        a_elegir: List[str] = []
        for indice, (texto_producto, cantidad) in enumerate(pedidos):
            producto_id = resueltos.get(indice)
            if indice in opciones_por_indice:
                opciones = opciones_por_indice[indice]
                a_elegir.append(f"'{texto_producto}' ({len(opciones)} opciones)")
                items.append(
                    NotaCotizacionItem(
                        nombre=texto_producto[:255],
                        texto_original=texto_producto,
                        cantidad=cantidad,
                        coincidencia="ambiguo",
                        opciones=[
                            NotaCotizacionOpcion(
                                producto_id=c[0],
                                nombre=c[1],
                                precio=por_id[c[0]].precio_unitario,
                                stock=por_id[c[0]].stock_actual,
                            )
                            for c in opciones
                        ],
                    )
                )
                continue
            if producto_id is None:
                sin_coincidencia.append(texto_producto)
                items.append(
                    NotaCotizacionItem(
                        nombre=texto_producto[:255],
                        texto_original=texto_producto,
                        cantidad=cantidad,
                        coincidencia="sin_coincidencia",
                    )
                )
                continue
            producto = por_id[producto_id]
            items.append(
                NotaCotizacionItem(
                    producto_id=producto.id,
                    nombre=producto.nombre,
                    texto_original=texto_producto,
                    cantidad=cantidad,
                    precio_esperado=producto.precio_unitario,
                    stock=producto.stock_actual,
                    coincidencia="catalogo",
                )
            )

        advertencias: List[str] = []
        if not items:
            advertencias.append("No se encontraron productos en la nota.")
        if a_elegir:
            advertencias.append("Elige el producto en: " + ", ".join(a_elegir) + ".")
        if sin_coincidencia:
            advertencias.append(
                "No se encontraron en el catálogo: " + ", ".join(f"'{t}'" for t in sin_coincidencia) + "."
            )

        cliente_sugerido_id = None
        mencionado = parsed.get("cliente")
        if payload.cliente_id is None and isinstance(mencionado, str) and mencionado.strip():
            clientes = list(db.scalars(select(Cliente).where(Cliente.estado == "Activo")).all())
            cliente_sugerido_id = mejor_coincidencia(
                mencionado, [(c.id, c.razon_social) for c in clientes]
            )

        return NotaCotizacionResponse(
            items=items,
            cliente_sugerido_id=cliente_sugerido_id,
            ia_disponible=True,
            advertencias=advertencias,
        )
