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
from core import MessageError

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

message_log = MessageError()

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
        message_log.error = f'Ошибка при запросе к endpoint:{ENDPOINT} {error}'
        raise ErrorGetApi

    if response.status_code != HTTPStatus.OK:
        message_log.error = (f'Параметры запроса:'
                             f'endpoint: {ENDPOINT}'
                             f'params: {payload}'
                             f'статус-код:{response.status_code}'
                             f'контент ответа:{response.content}')
        raise StatusNotOK

    try:
        response = response.json()
    except JSONDecodeError:
        message_log.error = 'Ошибка конвертации данных из json'
        raise ValueError

    logger.info(f'Получен успешный ответ от endpoint {ENDPOINT}')
    return response


def check_response(response):
    """Проверка корректности данных ответа.
    с Яндекс-практикума.
    """
    if not isinstance(response, dict):
        message_log.error = 'Ответ сервера не является типом "dict"'
        raise TypeError

    if 'homeworks' in response:
        homework = response.get('homeworks')
    else:
        message_log.error = 'Ключ "homeworks" отсутствует в ответе'
        raise KeyError

    if not isinstance(homework, list):
        message_log.error = ('Данные по ключу "homeworks" не являются'
                             ' типом "list"')
        raise TypeError
    logger.info('Получены корректные данные ответа с сервера Яндекс-практикум')

    return homework


def parse_status(homework):
    """Получение статуса домашней работы."""
    if 'homework_name' in homework:
        homework_name = homework['homework_name']
    else:
        message_log.error = 'Отсутсвует ключ "homework_name"'
        raise KeyError

    if 'status' in homework:
        status = homework['status']
    else:
        message_log.error = 'Отсутсвует ключ "status"'
        raise KeyError

    try:
        verdict = HOMEWORK_VERDICTS[status]
    except KeyError as error:
        message_log.error = f'Неизвестный статус домашней работы {error}'
        raise KeyError

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

            if not homeworks:
                logger.debug('Статус домашней работы не изменился')
            else:
                message = parse_status(homeworks[0])
                send_message(bot, message)

        except Exception as error:
            message = f'Сбой в работе программы: {message_log.error}'
            logger.error(f'{message_log.error} {error}')
            send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
