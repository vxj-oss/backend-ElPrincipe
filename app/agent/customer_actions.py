import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agent.choices import respuesta_opciones
from app.models.customer import Cliente
from app.services.quote_note_service import normalizar

PREFIJO_CLIENTE_NOMBRE = "¿Cómo se llama el cliente nuevo?"

PAT_CREAR_CLIENTE = re.compile(
    r"\b(?:crea|crear|creame|registra|registrar|registrame|agrega|agregar|agregame|anade|anadir|"
    r"da de alta|dar de alta|inscribe|inscribir|ingresa|ingresar|haz|hacer|nuevo|nueva|quiero)\b[^.\n]{0,20}\bcliente\b"
)
PAT_EXCLUIR = re.compile(r"\b(?:cotizacion|cotizaciones|pedido|pedidos|stock|condicion|condiciones)\b")

PAT_MARCADOR_CAMPO = re.compile(
    r"(?i)(?:,|;|\bruc\b|\bdni\b|\btel[eé]fono\b|\bcelular\b|\bcel\b|\bwhatsapp\b|\bcorreo\b|\be-?mail\b|"
    r"\bdirecci[oó]n\b|\bdistrito\b|\btipo\b|\bmayorista\b|\binstitucional\b|\bminorista\b|\bvip\b|"
    r"\bcon\s+(?:ruc|dni|tel|cel|correo|direcci|distrito|tipo|descuento|credito)|\bdescuento\b|\bcredito\b|\by\s+(?:ruc|dni|tel|cel|correo|direcci|distrito|tipo)|\bque es\b|\bes\s+(?:mayorista|minorista|institucional))"
)
PAT_RUC = re.compile(r"(?i)\b(?:ruc|dni)\b\D{0,3}(\d{8,11})\b")
PAT_RUC_SUELTO = re.compile(r"\b(\d{11}|\d{8})\b")
PAT_TELEFONO = re.compile(r"(?i)\b(?:tel[eé]fono|tel|celular|cel|whatsapp|fono)\b\D{0,3}((?:\+?\d[\d\s\-]{5,15}\d))")
PAT_TELEFONO_SUELTO = re.compile(r"\b(9\d{8})\b")
PAT_CORREO = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PAT_DIRECCION = re.compile(r"(?i)\bdirecci[oó]n\b\s*:?\s*(?:es\s*)?([^,;]+)")
PAT_DISTRITO = re.compile(r"(?i)\bdistrito\b\s*(?:de\s*)?:?\s*([^,;]+)")
PAT_NOMBRE_EXPLICITO = re.compile(r"(?i)\b(?:nombre|llamad[oa]|se llama|raz[oó]n social)\b\s*:?\s*(?:es\s*)?([^,;]+)")
PAT_VIP = re.compile(r"(?i)\bvip\b")
TIPOS = {"mayorista": "Mayorista", "institucional": "Institucional", "minorista": "Minorista"}
RELLENO_INICIO = re.compile(r"(?i)^(?:[:\-–]\s*|(?:nuevo|nueva|un|una|el|la)\s+)+")


def es_crear_cliente(texto: str) -> bool:
    limpio = normalizar(texto)
    return bool(PAT_CREAR_CLIENTE.search(limpio)) and not PAT_EXCLUIR.search(limpio)


def _extraer_nombre(prompt: str) -> str:
    explicito = PAT_NOMBRE_EXPLICITO.search(prompt)
    if explicito:
        nombre = explicito.group(1)
    else:
        posicion = re.search(r"(?i)\bcliente\b", prompt)
        resto = prompt[posicion.end():] if posicion else prompt
        resto = re.sub(r"(?i)^\s*(?:nuevo|nueva)?\s*(?:llamad[oa]|de nombre|que se llama|:)?\s*", "", resto)
        corte = PAT_MARCADOR_CAMPO.search(resto)
        nombre = resto[: corte.start()] if corte else resto
    corte_nombre = PAT_MARCADOR_CAMPO.search(nombre)
    if corte_nombre:
        nombre = nombre[: corte_nombre.start()]
    nombre = RELLENO_INICIO.sub("", nombre.strip())
    return re.sub(r"\s+", " ", nombre).strip(" .:-–\"'«»")


def _recortar(valor: str) -> str:
    corte = PAT_MARCADOR_CAMPO.search(valor)
    return (valor[: corte.start()] if corte else valor).strip(" .")


def _extraer_campos(prompt: str) -> Dict[str, Any]:
    campos: Dict[str, Any] = {}
    advertencias: List[str] = []

    ruc = PAT_RUC.search(prompt)
    if ruc:
        campos["ruc_dni"] = ruc.group(1)
    else:
        suelto = PAT_RUC_SUELTO.search(prompt)
        if suelto and not PAT_TELEFONO_SUELTO.fullmatch(suelto.group(1)):
            campos["ruc_dni"] = suelto.group(1)
    if campos.get("ruc_dni") and len(campos["ruc_dni"]) not in (8, 11):
        advertencias.append("El RUC debe tener 11 dígitos y el DNI 8; lo dejé en blanco.")
        campos.pop("ruc_dni")

    telefono = PAT_TELEFONO.search(prompt)
    if telefono:
        campos["telefono"] = re.sub(r"[\s\-]", "", telefono.group(1))[:20]
    else:
        suelto_tel = PAT_TELEFONO_SUELTO.search(prompt)
        if suelto_tel and suelto_tel.group(1) != campos.get("ruc_dni"):
            campos["telefono"] = suelto_tel.group(1)

    correo = PAT_CORREO.search(prompt)
    if correo:
        campos["correo"] = correo.group(0)

    direccion = PAT_DIRECCION.search(prompt)
    if direccion:
        campos["direccion"] = _recortar(direccion.group(1))
    distrito = PAT_DISTRITO.search(prompt)
    if distrito:
        campos["distrito"] = _recortar(distrito.group(1))

    for clave, valor in TIPOS.items():
        if re.search(rf"(?i)\b{clave}\b", prompt):
            campos["tipo_cliente"] = valor
            break
    campos["clasificacion"] = "VIP" if PAT_VIP.search(prompt) else "Regular"
    campos["_advertencias"] = advertencias
    return campos


def _buscar_duplicado(db: Session, nombre: str, ruc: Optional[str]) -> Optional[Cliente]:
    if ruc:
        existente = db.scalar(select(Cliente).where(Cliente.ruc_dni == ruc))
        if existente:
            return existente
    objetivo = normalizar(nombre)
    for cliente in db.scalars(select(Cliente)).all():
        if normalizar(cliente.razon_social) == objetivo:
            return cliente
    return None


def responder_crear_cliente(db: Session, prompt: str) -> Optional[Dict[str, Any]]:
    if not es_crear_cliente(prompt):
        return None

    nombre = _extraer_nombre(prompt)
    campos = _extraer_campos(prompt)
    advertencias: List[str] = campos.pop("_advertencias")

    if not nombre or len(nombre) < 2:
        return {
            "respuesta": (
                f"{PREFIJO_CLIENTE_NOMBRE} Puedes darme también el RUC o DNI, teléfono, distrito y tipo "
                "(mayorista, institucional o minorista). Por ejemplo: «Lavandería El Sol, RUC 20123456789, "
                "teléfono 987654321, mayorista»."
            ),
            "datos_estructurados": None,
        }

    duplicado = _buscar_duplicado(db, nombre, campos.get("ruc_dni"))
    if duplicado:
        return respuesta_opciones(
            f"Ya existe el cliente «{duplicado.razon_social}» ({duplicado.tipo_cliente}"
            f"{', ' + duplicado.distrito if duplicado.distrito else ''}). No lo vuelvo a crear.",
            [
                ("Ver ficha", f"resumen del cliente {duplicado.razon_social}"),
                ("Armar cotización", f"Arma una cotización para {duplicado.razon_social}"),
            ],
        )

    if "tipo_cliente" not in campos:
        return respuesta_opciones(
            f"¿Qué tipo de cliente es «{nombre}»?",
            [(tipo, f"{prompt} tipo {tipo.lower()}") for tipo in TIPOS.values()],
        )

    cliente = {
        "razon_social": nombre[:200],
        "ruc_dni": campos.get("ruc_dni", ""),
        "tipo_cliente": campos["tipo_cliente"],
        "telefono": campos.get("telefono", ""),
        "correo": campos.get("correo", ""),
        "direccion": campos.get("direccion", ""),
        "distrito": campos.get("distrito", ""),
        "clasificacion": campos["clasificacion"],
    }
    texto = f"Preparé el registro del cliente «{cliente['razon_social']}» ({cliente['tipo_cliente']}). Revísalo, completa lo que falte y confírmalo aquí abajo."
    if advertencias:
        texto += " " + " ".join(advertencias)
    datos = {
        "tipo": "borrador_cliente",
        "cliente": cliente,
        "advertencias": advertencias,
        "explicacion": {
            "resumen": "Separé del texto el nombre, RUC o DNI, teléfono, correo, dirección, distrito y tipo. Nada se guarda hasta que confirmes, y puedes corregir los campos.",
            "fuentes": ["Tu mensaje", "Clientes registrados (para evitar duplicados por nombre o RUC)"],
            "formula": None,
            "periodo": "datos al momento de la consulta",
        },
    }
    return {"respuesta": texto, "datos_estructurados": datos}
