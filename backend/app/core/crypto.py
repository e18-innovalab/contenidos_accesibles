from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

try:
    _fernet = Fernet(settings.DB_ENCRYPTION_KEY.get_secret_value().encode())
except Exception as exc:
    raise RuntimeError(
        "DB_ENCRYPTION_KEY inválida. Generala con: "
        "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    ) from exc


def encrypt_value(raw: str) -> str:
    return _fernet.encrypt(raw.encode()).decode()


def decrypt_value(token: str) -> str:
    try:
        return _fernet.decrypt(token.encode()).decode()
    except InvalidToken as exc:
        raise ValueError(
            "No se pudo desencriptar la key almacenada; ¿cambió DB_ENCRYPTION_KEY?"
        ) from exc
