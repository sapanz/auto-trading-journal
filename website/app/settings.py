from sqlalchemy.orm import Session

from . import models


def get_setting(db: Session, key: str, default: str = "") -> str:
    row = db.get(models.Setting, key)
    return row.value if row else default


def set_setting(db: Session, key: str, value: str) -> None:
    row = db.get(models.Setting, key)
    if row:
        row.value = value
    else:
        db.add(models.Setting(key=key, value=value))
    db.commit()
