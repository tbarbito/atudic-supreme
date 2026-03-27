from datetime import datetime

def convert_datetime_to_str(obj):
    """
    Converte objetos datetime para string ISO format recursivamente.
    Usado para serializar resultados do PostgreSQL para JSON.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {key: convert_datetime_to_str(value) for key, value in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_datetime_to_str(item) for item in obj]
    return obj
