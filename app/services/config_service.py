from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.configuracion import ConfiguracionSistema


class ConfigService:
    @staticmethod
    def get(db: Session) -> ConfiguracionSistema:
        config = db.scalar(select(ConfiguracionSistema).where(ConfiguracionSistema.id == 1))
        if config is None:
            config = ConfiguracionSistema(id=1, meta_diaria_ventas=Decimal("6000.00"))
            db.add(config)
            db.commit()
            db.refresh(config)
        return config

    @staticmethod
    def update(db: Session, meta_diaria_ventas: Decimal) -> ConfiguracionSistema:
        config = ConfigService.get(db)
        config.meta_diaria_ventas = meta_diaria_ventas
        db.commit()
        db.refresh(config)
        return config
