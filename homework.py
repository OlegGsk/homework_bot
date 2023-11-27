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
        logger.error(
            f'Ошибка при отправке сообщения: {error}!'
        )


def get_api_answer(timestamp):
    """Запрос к сервису Яндекс-практикум."""
    payload = {'from_date': timestamp}
    message_error_api = 'Ошибка при запросе к сервису API:'
    message_status_not_200 = 'Сервер вернул статус-код отличный от 200'
    message_error_jsoin = 'Ошибка конвертации данных из json'

    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=payload)
        response.raise_for_status()
        logger.info('Получен ответ от endpoint')
    except requests.RequestException as error:
        logger.error(f'{message_error_api} {error}!')
        raise ErrorGetApi(f'{message_error_api} {error}!')

    if response.status_code != HTTPStatus.OK:
        logger.error(message_status_not_200)
        raise StatusNotOK(message_status_not_200)

    try:
        response = response.json()

    except JSONDecodeError as error:
        logger.error(f'{message_error_jsoin} {error}')
        raise ValueError(message_error_jsoin)

    return response


def check_response(response):
    """Проверка корректности данных ответа.
    с Яндекс-практикума.
    """
    if not isinstance(response, dict):
        logger.error('Ответ сервера не является словарём')
        raise TypeError

    homework = response.get('homeworks')

    if not isinstance(homework, list):
        logger.error('Данные по ключу "homeworks" не list')
        raise TypeError
    logger.info('Получены корректные данные ответа Яндекс-практикума')

    return homework


def parse_status(homework):
    """Получение статуса домашней работы."""
    try:
        homework_name = homework['homework_name']
        status = homework['status']
        logger.info('Присутствуют правильные ключи в ответе')
    except KeyError as error:
        logger.error(f'Отсутсвуют необходимые ключи {error}')
        raise KeyError('Отсутсвуют необходимые ключи')

    try:
        verdict = HOMEWORK_VERDICTS[status]
    except KeyError as error:
        logger.error(f'Неизвестный статус homework {error}')
        raise KeyError

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    check_tokens()

    try:
        bot = telegram.Bot(token=TELEGRAM_TOKEN)
    except telegram.TelegramError as error:
        logger.critical(f'Ошибка при запуске бота {str(error)}')
        raise EmergencyStop

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
            message = f'Сбой в работе программы: {error}'
            logger.error(f'Сбой в работе программы: {error}')
            send_message(bot, message)

        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()
