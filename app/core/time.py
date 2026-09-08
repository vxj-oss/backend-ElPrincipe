from datetime import datetime
from zoneinfo import ZoneInfo

LIMA_TZ = ZoneInfo("America/Lima")


def ahora_lima() -> datetime:
    return datetime.now(LIMA_TZ)


def fecha_hoy_lima():
    return datetime.now(LIMA_TZ).date()
