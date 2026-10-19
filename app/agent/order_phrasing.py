import re
from typing import Callable, List, Pattern

SIN_ACENTOS = str.maketrans("áéíóúüÁÉÍÓÚÜ", "aeiouuAEIOUU")

NOMBRES_ACCION = r"(?:cotizacion|proforma|presupuesto|pedido|venta|orden de venta|nota de pedido)"
ARTICULO_INDEFINIDO = r"(?:un|una|otro|otra|nuevo|nueva)"

VERBOS_SINONIMOS = (
    r"(?:anota|anotar|anotame|anotale|apunta|apuntar|apuntame|apuntale|ingresa|ingresar|ingresame|ingresale"
    r"|levanta|levantar|levantame|levantale|saca|sacar|sacame|sacale|toma|tomar|tomame|tomale"
    r"|manda|mandar|mandame|mandale|envia|enviar|enviame|enviale|emite|emitir|emiteme|emitele"
    r"|extiende|extiendeme|confecciona|confeccionar|confeccioname|realiza|realizar|realizame|realizale"
    r"|monta|montar|formula|formular|elabora|elaborar|elaborame|elaborale|redacta|redactar|redactame|redactale"
    r"|dale|dame|danos|pasale|pasame|pasanos)"
)

ARRANQUE_ACCION = re.compile(
    r"^(?:(?:una|un|la|el|otra|otro|nueva|nuevo)\s+)?(?:cotizacion|proforma|presupuesto|pedido|orden de venta|venta|cliente)\b"
    r"|^(?:arm|haz|hag|hac|cre|gener|registr|prepar|elabor|redact|cotiz|anot|apunt|ingres|levant|sac|tom|mand|envi|emit"
    r"|vend|dal|dam|pas|convert|aprueb|confirm|cancel|anul|elimin|borr|agreg|anad|quit|cambi|repit|marc|despach"
    r"|entreg|proces|actualiz|modific|sub|baj|pon|desactiv|reactiv|da |dar )",
    re.IGNORECASE,
)
INTERROGATIVO = re.compile(r"^\W*(?:cuant|que |cual|como|donde|quien|por que|cuando)", re.IGNORECASE)
CODIGO = re.compile(r"\b(?:ped|cot)-\w+", re.IGNORECASE)
INICIO_CORTESIA = re.compile(
    r"^\W*(?:(?:oye|oiga|hola|disculpa|disculpe|bueno|entonces|ahora|ok|okey|por favor|porfa|porfis|porfavor)[,\s]+)+",
    re.IGNORECASE,
)
FIN_CORTESIA = re.compile(r"[,\s]+(?:por favor|porfa|porfis|porfavor|gracias)\W*$", re.IGNORECASE)
MODAL = re.compile(
    r"^(?:(?:me|nos)\s+)?(?:puedes|podrias|pudieras|ayudas a|ayudarias a|ayudame a|quiero que|necesito que|quisiera que"
    r"|quisiera|quiero|necesito|deseo|me gustaria|tienes que|vas a|va a|puede|podria|pueden)\s+(?:(?:me|nos)\s+)?",
    re.IGNORECASE,
)
ACCION_EN_TEXTO = re.compile(
    r"\b(?:cotiza\w*|proforma|presupuesto|pedido|venta|vende\w*|vendele|orden de venta|da de alta|da de baja|dar de alta"
    r"|dar de baja|entreg\w+|visto bueno|luz verde|repit\w+|de siempre|lo habitual|anota\w*|apunta\w*|inscribe|precios?)\b",
    re.IGNORECASE,
)


class _Texto:
    def __init__(self, original: str):
        self.original = original
        self.plano = original.translate(SIN_ACENTOS)

    def reemplazar(self, patron: Pattern, funcion: Callable[[re.Match, str], str]) -> None:
        partes_o: List[str] = []
        partes_p: List[str] = []
        cursor = 0
        for m in patron.finditer(self.plano):
            nuevo = funcion(m, self.original)
            partes_o.append(self.original[cursor : m.start()])
            partes_p.append(self.plano[cursor : m.start()])
            partes_o.append(nuevo)
            partes_p.append(nuevo.translate(SIN_ACENTOS))
            cursor = m.end()
        if not partes_o:
            return
        partes_o.append(self.original[cursor:])
        partes_p.append(self.plano[cursor:])
        self.original = "".join(partes_o)
        self.plano = "".join(partes_p)

    def sustituir(self, patron: str, nuevo: str, flags: int = re.IGNORECASE) -> None:
        self.reemplazar(re.compile(patron, flags), lambda m, o: nuevo)

    def recortar_inicio(self, patron: Pattern) -> None:
        m = patron.search(self.plano)
        if m and m.start() == 0 and m.end() > 0:
            self.original = self.original[m.end() :]
            self.plano = self.plano[m.end() :]


def _quitar_cortesia(t: _Texto) -> None:
    t.recortar_inicio(INICIO_CORTESIA)
    m = FIN_CORTESIA.search(t.plano)
    if m:
        t.original = t.original[: m.start()]
        t.plano = t.plano[: m.start()]
    modal = MODAL.match(t.plano)
    if modal:
        resto = t.plano[modal.end() :]
        if ARRANQUE_ACCION.match(resto):
            t.original = t.original[modal.end() :]
            t.plano = resto
    suelto = re.match(r"(?:me|nos)\s+(?=\w)", t.plano, re.IGNORECASE)
    if suelto and ARRANQUE_ACCION.match(t.plano[suelto.end() :]):
        t.original = t.original[suelto.end() :]
        t.plano = t.plano[suelto.end() :]


def _estados(t: _Texto) -> None:
    t.sustituir(r"\b(?:da|dar|dale|dalo|dala)\s+por\s+entregad[oa]s?\b", "marca como entregado")
    if re.search(r"\bpedido\b", t.plano):
        t.sustituir(r"\bya\s+(?:se\s+)?(?:entrego|entregue|fue\s+entregad[oa])\b", "marca como entregado")
    t.sustituir(r"\b(?:da|dar|dale)\s+(?:el\s+|un\s+)?(?:visto\s+bueno|vb|ok|vamos|luz\s+verde)\b", "aprueba")
    t.sustituir(r"\bda(?:r)?\s+de\s+baja\s+(?=(?:a\s+|al\s+|el\s+|la\s+)?pedido\b)", "cancela ")
    t.sustituir(r"\bda(?:r)?\s+de\s+baja\s+(?=(?:a\s+|al\s+|el\s+|la\s+)?(?:producto|cliente)\b)", "desactiva ")
    t.sustituir(r"\bda(?:r)?\s+de\s+baja\s+(?=(?:a\s+|al\s+|el\s+|la\s+)?cotizacion\b)", "anula ")


def _altas(t: _Texto) -> None:
    t.sustituir(r"\bda(?:r)?\s+de\s+alta\s+(?:a\s+|al\s+)?(?=cliente\b)", "crea el ")
    t.sustituir(
        r"\bda(?:r)?\s+de\s+alta\s+(?:a\s+)?(?!(?:el\s+|al\s+|un\s+|una\s+)?(?:producto|cliente|usuario|trabajador|vendedor|asesor|empleado)\b)",
        "crea el cliente ",
    )
    t.sustituir(r"\b(?:anota|apunta)\s+al\s+cliente\b", "crea el cliente")


def _repetir(t: _Texto) -> None:
    t.sustituir(r"\brepit(?:e|a)(?:le|me|nos)\b", "repite")
    t.sustituir(r"\blo\s+(?:mismo\s+)?de\s+siempre\b|\blo\s+habitual\b", "lo mismo que la última vez")


def _verbos_y_nombres(t: _Texto) -> None:
    sin_codigo = not CODIGO.search(t.plano)
    if sin_codigo:
        t.sustituir(rf"\b{VERBOS_SINONIMOS}\b(?=\s+{ARTICULO_INDEFINIDO}\s+{NOMBRES_ACCION}\b)", "arma")
    t.sustituir(r"\bproforma(?:s)?\b", "cotización")
    if re.search(r"\d", t.plano):
        t.reemplazar(
            re.compile(rf"\b({ARTICULO_INDEFINIDO}|el)(\s+)presupuesto\b", re.IGNORECASE),
            lambda m, o: ("una" if o[m.start(1) : m.end(1)].lower() in ("un", "nuevo", "otro") else "la" if o[m.start(1) : m.end(1)].lower() == "el" else o[m.start(1) : m.end(1)])
            + o[m.start(2) : m.end(2)]
            + "cotización",
        )
    destino = "pedido" if re.search(r"\bde la cotizacion\b|\bcot-", t.plano) else "cotización"
    t.sustituir(r"\borden(?:es)? de venta\b", destino)
    t.sustituir(r"\bnota de pedido\b", "pedido")
    if re.search(r"\b(?:convierte|convertir|pasa|pasar|transforma|transformar)(?:la|lo|le|me)?\b", t.plano):
        t.sustituir(r"\b(?:en|a)\s+(?:una\s+)?venta\b", "en pedido")
    if re.search(r"\b(?:arma|armar|crea|crear|haz|hacer|hazle|hazme|genera|generar|registra|registrar|prepara|preparar|elabora|elaborar)\w*\b", t.plano):
        t.reemplazar(
            re.compile(r"\b(una|la|otra|nueva)(\s+)venta\b", re.IGNORECASE),
            lambda m, o: f"{o[m.start(1):m.end(1)]}{o[m.start(2):m.end(2)]}cotización",
        )
    t.sustituir(r"\bcotizar\b", "cotiza")


def _sin_verbo(t: _Texto) -> None:
    if INTERROGATIVO.match(t.plano) or CODIGO.search(t.plano):
        return
    m = re.match(r"(?:(?:una|un|la|el|otra|otro|nueva|nuevo)\s+)?(cotizacion|pedido)\s+(?:para|a|de)\s", t.plano, re.IGNORECASE)
    if not m:
        return
    if not (re.search(r"\d", t.plano) or re.search(r"\bcon\b", t.plano)):
        return
    articulo = "una" if m.group(1).lower() == "cotizacion" else "un"
    if re.match(r"(?:una|un|la|el|otra|otro|nueva|nuevo)\s", t.plano, re.IGNORECASE):
        t.original = "arma " + t.original
        t.plano = "arma " + t.plano
    else:
        t.original = f"arma {articulo} " + t.original
        t.plano = f"arma {articulo} " + t.plano


def _precio_para(t: _Texto) -> None:
    if re.match(r"(?:dame|pasame|dime|danos)\s+(?:el\s+|los\s+)?precios?\s+de\s+\d", t.plano, re.IGNORECASE) and re.search(r"\bpara\b", t.plano):
        t.sustituir(r"^(?:dame|pasame|dime|danos)\s+(?:el\s+|los\s+)?precios?\s+de\s+", "arma una cotización de ")


def _ventas(t: _Texto) -> None:
    def con_cliente(m: re.Match, original: str) -> str:
        items = original[m.start("items") : m.end("items")].strip()
        cliente = original[m.start("cli") : m.end("cli")].strip()
        return f"arma una cotización para {cliente} con {items}"

    t.reemplazar(
        re.compile(r"^(?:vende|vendele|vendeme|vendeles)\s+(?P<items>.+?)\s+a\s+(?P<cli>[^\d]+?)\s*$", re.IGNORECASE),
        con_cliente,
    )

    def cliente_primero(m: re.Match, original: str) -> str:
        cliente = original[m.start("cli") : m.end("cli")].strip()
        items = original[m.start("items") : m.end("items")].strip()
        return f"arma una cotización para {cliente} con {items}"

    t.reemplazar(
        re.compile(r"^(?:vende|vendele|vendeme|vendeles)\s+a\s+(?P<cli>[^\d]+?)\s+(?P<items>\d.*)$", re.IGNORECASE),
        cliente_primero,
    )


def normalizar_orden(texto: str) -> str:
    if not texto or not ACCION_EN_TEXTO.search(texto.translate(SIN_ACENTOS)):
        return texto
    t = _Texto(texto.strip())
    _quitar_cortesia(t)
    _estados(t)
    _altas(t)
    _repetir(t)
    _ventas(t)
    _precio_para(t)
    _verbos_y_nombres(t)
    _sin_verbo(t)
    resultado = re.sub(r"\s{2,}", " ", t.original).strip()
    return resultado or texto
