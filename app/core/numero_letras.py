from decimal import ROUND_HALF_UP, Decimal

UNIDADES = [
    "", "UNO", "DOS", "TRES", "CUATRO", "CINCO", "SEIS", "SIETE", "OCHO", "NUEVE", "DIEZ", "ONCE", "DOCE",
    "TRECE", "CATORCE", "QUINCE", "DIECISEIS", "DIECISIETE", "DIECIOCHO", "DIECINUEVE", "VEINTE",
    "VEINTIUNO", "VEINTIDOS", "VEINTITRES", "VEINTICUATRO", "VEINTICINCO", "VEINTISEIS", "VEINTISIETE",
    "VEINTIOCHO", "VEINTINUEVE",
]
DECENAS = ["", "", "", "TREINTA", "CUARENTA", "CINCUENTA", "SESENTA", "SETENTA", "OCHENTA", "NOVENTA"]
CENTENAS = [
    "", "CIENTO", "DOSCIENTOS", "TRESCIENTOS", "CUATROCIENTOS", "QUINIENTOS", "SEISCIENTOS", "SETECIENTOS",
    "OCHOCIENTOS", "NOVECIENTOS",
]


def _menor_de_mil(n: int) -> str:
    if n == 100:
        return "CIEN"
    partes = []
    centenas, resto = divmod(n, 100)
    if centenas:
        partes.append(CENTENAS[centenas])
    if resto < 30:
        if resto:
            partes.append(UNIDADES[resto])
    else:
        decenas, unidades = divmod(resto, 10)
        partes.append(DECENAS[decenas] + (f" Y {UNIDADES[unidades]}" if unidades else ""))
    return " ".join(partes)


def entero_a_letras(n: int) -> str:
    if n == 0:
        return "CERO"
    partes = []
    millones, resto = divmod(n, 1_000_000)
    miles, unidades = divmod(resto, 1000)
    if millones:
        partes.append("UN MILLON" if millones == 1 else f"{entero_a_letras(millones)} MILLONES")
    if miles:
        partes.append("MIL" if miles == 1 else f"{_menor_de_mil(miles)} MIL")
    if unidades:
        partes.append(_menor_de_mil(unidades))
    texto = " ".join(partes)
    return texto.replace("UNO MIL", "UN MIL")


def monto_en_letras(monto) -> str:
    valor = Decimal(str(monto or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    entero = int(valor)
    centimos = int((valor - entero) * 100)
    return f"SON: {entero_a_letras(entero)} CON {centimos:02d}/100 SOLES"
