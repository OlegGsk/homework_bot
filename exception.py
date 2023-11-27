class StatusNotOK(Exception):
    """Статус ответа отличный от 200."""

    pass


class ErrorGetApi(Exception):
    """Ошибка при запросе к сервису API Яндекс-практикума."""

    pass


class EmergencyStop(Exception):
    """Отсутствие необходимых переменных."""

    pass
