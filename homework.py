import logging
import os
import sys
import time
from http import HTTPStatus
from json import JSONDecodeError

import requests
import telegram
from dotenv import load_dotenv

from exception import EmergencyStop, ErrorGetApi, StatusNotOK

load_dotenv()

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}


def check_tokens():
    """Проверка доступности обязательных переменных окружения."""
    if not all((TELEGRAM_TOKEN, PRACTICUM_TOKEN, TELEGRAM_CHAT_ID)):
        logger.critical('Отсутствуют обязательные переменные')
        raise EmergencyStop


def send_message(bot, message):
    """Отправка сообщения в чат телеграмма."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID,
                         text=message)
        logger.debug('Отправка сообщения в телеграмм')
    except telegram.TelegramError as error:
        logger.error(f'Ошибка при отправке сообщения: {error}!')


def get_api_answer(timestamp):
    """Запрос к сервису Яндекс-практикум."""
    payload = {'from_date': timestamp}

    try:
        logger.info(f'Попытка отправить Get запрос к endpoint {ENDPOINT}')
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        response.raise_for_status()
    except requests.RequestException as error:
        raise ErrorGetApi(f'Ошибка при запросе к endpoint:{ENDPOINT} {error}')

    if response.status_code != HTTPStatus.OK:
        raise StatusNotOK(f'Параметры запроса:'
                          f'endpoint: {ENDPOINT}'
                          f'params: {payload}'
                          f'статус-код:{response.status_code}'
                          f'контент ответа:{response.content}')

    try:
        response = response.json()
    except JSONDecodeError:
        raise ValueError('Ошибка конвертации данных из json')

    logger.info(f'Получен успешный ответ от endpoint {ENDPOINT}')
    return response


def check_response(response):
    """Проверка корректности данных ответа.
    с Яндекс-практикума.
    """
    if not isinstance(response, dict):
        raise TypeError('Ответ сервера не является типом "dict"')

    if 'homeworks' not in response:
        raise KeyError('Ключ "homeworks" отсутствует в ответе')
    homework = response.get('homeworks')

    if not isinstance(homework, list):
        raise TypeError('Данные по ключу "homeworks" не являются'
                        ' типом "list"')
    logger.info('Получены корректные данные ответа с сервера Яндекс-практикум')

    return homework


def parse_status(homework):
    """Получение статуса домашней работы."""
    if 'homework_name' not in homework:
        raise KeyError('Отсутсвует ключ "homework_name"')
    homework_name = homework['homework_name']

    if 'status' not in homework:
        raise KeyError('Отсутсвует ключ "status"')
    status = homework['status']

    try:
        verdict = HOMEWORK_VERDICTS[status]
    except KeyError as error:
        raise KeyError(f'Неизвестный статус домашней работы {error}')

    logger.info('В ответе присутствуют ключи "homework_name", "status"')
    logger.info('Получен статус домашней работы')

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()
    logger.info('Присутствуют все обязательные переменные окружения')

    try:
        logger.info('Попытка запустить telegram-bot')
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except telegram.TelegramError as error:
        logger.critical(f'Ошибка при запуске бота {str(error)}')
        raise EmergencyStop

    logger.info('Telegram-bot успешно запущен')

    timestamp = int(time.time())

    while True:
        try:
            response = get_api_answer(timestamp)
            timestamp = response.get('current_date')
            homeworks = check_response(response)

            if homeworks:
                message = parse_status(homeworks[0])
                send_message(bot, message)
            logger.debug('Статус домашней работы не изменился')

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            logger.error(f'Сбой в работе программы: {error}')
            send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
