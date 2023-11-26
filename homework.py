from http import HTTPStatus
from json import JSONDecodeError
import sys
import telegram

from dotenv import load_dotenv

import logging
import requests
import time
import os

from exception import AbsenceOfaMandatoryVar, ErrorGetApi


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

LIST_OF_ENVIRONMENT_VAR = [PRACTICUM_TOKEN, TELEGRAM_TOKEN, TELEGRAM_CHAT_ID]

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
    return all(LIST_OF_ENVIRONMENT_VAR)


def send_message(bot, message):
    """Отправка сообщения в чат телеграмма."""
    try:
        bot.send_message(TELEGRAM_CHAT_ID, message)
        logger.debug('Отправка сообщения в телеграмм')
    except telegram.TelegramError as error:
        logger.error(
            f'Ошибка при отправке сообщения: {error}!'
        )


def get_api_answer(timestamp):
    """Запрос к сервису Яндекс-практикум."""
    url = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
    headers = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
    payload = {'from_date': timestamp}

    try:
        response = requests.get(url, headers=headers, params=payload)
        response.raise_for_status()

    except requests.RequestException as error:
        logger.error(f'Ошибка при запросе к сервису API:{error}!')
        raise exceptions.GetAPIError(
            f'Ошибка при запросе к сервису API:{error}!')

    if response.status_code != HTTPStatus.OK:
        logger.error('Сервер вернул статус-код отличный от 200')
        raise exceptions.StatusNotOKError(
            'Сервер вернул статус-код отличный от 200'
        )

    try:
        response = response.json()

    except JSONDecodeError as error:
        logger.error(f'Ошибка конвертации данных из json {error}')
        raise ErrorGetApi('Ошибка конвертации данных из json')

    return response


def check_response(response):
    """Проверка корректности данных ответа
    с Яндекс-практикума.
    """
    if not isinstance(response, dict):
        logger.error('Ответ сервера не является словарём')
        raise TypeError
    homework = response.get('homeworks')

    if not isinstance(homework, list):
        logger.error('Данные по ключу "homeworks" не list')
        raise TypeError
    return homework


def parse_status(homework):
    """Получение статуса домашней работы."""
    try:
        homework_name = homework['homework_name']
        status = homework['status']
    except KeyError as error:
        logger.error(f'Отсутсвуют необходимые ключи {error}')
        raise KeyError('Отсутсвуют необходимые ключи')

    try:
        verdict = HOMEWORK_VERDICTS[status]
        print(verdict)

    except KeyError as error:
        logger.error(f'Неизвестный статус homework {error}')
        raise KeyError

    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        logger.critical('Отсутствуют обязательные переменные')
        sys.exit('Отсутствие необходимых токенов для работы программы!')

    bot = telegram.Bot(token=TELEGRAM_TOKEN)

    current_timestamp = 1698292093  # время запроса 26.10.2023

    while True:
        try:
            response = get_api_answer(current_timestamp)
            current_timestamp = response.get('current_date')
            homeworks = check_response(response)

            if not homeworks:
                logger.info('Статус домашней работы не изменился')
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
