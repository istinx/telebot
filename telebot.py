#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
import configparser
import time
import os
import random
import string
import json
import logging
from pathlib import Path
from typing import Optional, List, Tuple, Dict, Any

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class TelegramBot:
    """Класс для работы с Telegram Bot API"""

    def __init__(self, config_path: str = 'telebot.cfg'):
        self.config = self._load_config(config_path)
        self.api_url = self.config['api_url']
        self.bot_token = self.config['secret']
        self.admin_id = self.config['admin_id']
        self.interval = self.config['interval']
        self.offset = self.config['offset']

        # Создание необходимых директорий
        self._setup_directories()

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Загрузка конфигурации"""
        config = configparser.ConfigParser()

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file {config_path} not found")

        config.read(config_path, encoding='utf-8')

        return {
            'interval': config.getfloat('SectionBot', 'interval'),
            'admin_id': config.getint('SectionBot', 'admin_id'),
            'api_url': config.get('SectionBot', 'api_url'),
            'secret': config.get('SectionBot', 'secret'),
            'offset': config.getint('SectionBot', 'offset')
        }

    def _setup_directories(self):
        """Создание необходимых директорий"""
        directories = ['chatlogs', 'dict', 'tmp']
        for directory in directories:
            Path(directory).mkdir(exist_ok=True)

    def get_updates(self) -> Optional[List[Dict]]:
        """Получение обновлений от Telegram API"""
        params = {
            'offset': self.offset + 1,
            'limit': 100,
            'timeout': 30
        }

        try:
            response = requests.get(
                f"{self.api_url}{self.bot_token}/getUpdates",
                params=params,
                timeout=35
            )
            response.raise_for_status()
            data = response.json()

            if data.get('ok') and data.get('result'):
                updates = data['result']
                if updates:
                    self.offset = updates[-1]['update_id']
                return updates

        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting updates: {e}")
        except json.JSONDecodeError as e:
            logger.error(f"Error parsing JSON: {e}")

        return None

    def send_message(self, chat_id: int, text: str) -> bool:
        """Отправка сообщения"""
        payload = {
            'chat_id': chat_id,
            'text': text,
            'parse_mode': 'HTML'
        }

        try:
            response = requests.post(
                f"{self.api_url}{self.bot_token}/sendMessage",
                json=payload,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Sent to {chat_id}: {text[:50]}...")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Error sending message: {e}")
            return False

    def extract_message_info(self, update: Dict) -> Optional[Tuple]:
        """Извлечение информации из обновления"""
        if 'message' not in update or 'text' not in update['message']:
            return None

        message = update['message']
        chat = message['chat']
        from_user = message.get('from', {})

        # ID чата
        chat_id = chat['id']

        # Тип чата
        chat_type = chat.get('type', 'private')

        # Имя пользователя/чата
        if chat_type == 'group' or chat_type == 'supergroup':
            chat_name = chat.get('title', f'Chat {chat_id}')
        else:
            first_name = from_user.get('first_name', '')
            last_name = from_user.get('last_name', '')
            chat_name = f"{first_name} {last_name}".strip() or f"User {from_user.get('id', '')}"

        # Текст сообщения
        text = message['text']

        # Логирование
        user_name = f"{first_name} {last_name}".strip() or f"User {from_user.get('id', '')}"
        self.log_event(f"Message from {user_name}: {text}", chat_name)

        return (text, chat_id, chat_name, chat_id)

    def log_event(self, text: str, logname: str):
        """Логирование событий"""
        # Очистка имени файла от недопустимых символов
        safe_name = ''.join(c for c in logname if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if not safe_name:
            safe_name = 'unknown'

        filename = f'chatlogs/{safe_name}_log.txt'

        try:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"{time.ctime()} >> {text}\n")
        except IOError as e:
            logger.error(f"Error writing log: {e}")

    def learn_phrase(self, phrase: str, chat_number: str):
        """Обучение бота - сохранение фразы"""
        safe_chat_id = str(chat_number).replace('+', '').replace('-', '')
        phrase = phrase.replace('/learn', '').strip()

        if not phrase:
            return

        filename = f'dict/{safe_chat_id}_words.dat'

        try:
            with open(filename, 'a', encoding='utf-8') as f:
                f.write(f"{phrase}\n")
            logger.info(f"Learned phrase for chat {safe_chat_id}")
        except IOError as e:
            logger.error(f"Error saving phrase: {e}")

    @staticmethod
    def longest_common_substring(s1: str, s2: str) -> str:
        """Поиск наибольшей общей подстроки"""
        m = len(s1)
        n = len(s2)
        dp = [[0] * (n + 1) for _ in range(m + 1)]
        max_len = 0
        end_pos = 0

        for i in range(1, m + 1):
            for j in range(1, n + 1):
                if s1[i - 1] == s2[j - 1]:
                    dp[i][j] = dp[i - 1][j - 1] + 1
                    if dp[i][j] > max_len:
                        max_len = dp[i][j]
                        end_pos = i

        return s1[end_pos - max_len:end_pos] if max_len > 0 else ""

    def find_similar_phrases(self, message: str, chat_number: str) -> Optional[str]:
        """Поиск похожих фраз в словаре"""
        safe_chat_id = str(chat_number).replace('+', '').replace('-', '')
        filename = f'dict/{safe_chat_id}_words.dat'

        if not os.path.exists(filename):
            return None

        try:
            with open(filename, 'r', encoding='utf-8') as f:
                phrases = [line.strip() for line in f if line.strip()]
        except IOError:
            return None

        if not phrases:
            return None

        # Очистка сообщения
        message_words = message.lower().translate(
            str.maketrans('', '', string.punctuation)
        ).split()

        matched_phrases = []

        for phrase in phrases:
            # Проверка на точное совпадение слов
            phrase_words = phrase.lower().translate(
                str.maketrans('', '', string.punctuation)
            ).split()

            # Проверяем совпадение хотя бы одного слова на 80%
            for msg_word in message_words:
                for phr_word in phrase_words:
                    common = self.longest_common_substring(msg_word, phr_word)
                    if len(common) >= 0.8 * len(phr_word):
                        matched_phrases.append(phrase)
                        break
                if phrase in matched_phrases:
                    break

        if matched_phrases:
            return random.choice(matched_phrases)

        return None

    def process_message(self, message: str, chat_name: str, chat_number: str) -> Optional[str]:
        """Обработка входящего сообщения"""
        # Обработка команд
        if message.startswith('/'):
            parts = message.split(' ', 1)
            command = parts[0].lower()

            if command == '/help':
                return "Telebot - Simple Telegram Bot\nCommands:\n/help - Show help\n/learn <phrase> - Teach bot a phrase\n/start - Start bot"

            elif command == '/stop':
                return "Bot stopped"

            elif command == '/start':
                return "Bot started!"

            elif command == '/learn' and len(parts) > 1:
                self.learn_phrase(parts[1], chat_number)
                return "Phrase learned!"

        # Поиск похожих фраз
        response = self.find_similar_phrases(message, chat_number)
        return response

    def run(self):
        """Основной цикл бота"""
        logger.info("Starting Telegram bot...")

        # Проверка блокировки
        lock_file = 'tmp/telebot.lock'
        if os.path.exists(lock_file):
            logger.warning("Lock file exists. Another instance may be running.")
            try:
                # Проверяем, активен ли процесс
                with open(lock_file, 'r') as f:
                    pid = f.read().strip()
                    # Простая проверка (для Linux)
                    if os.path.exists(f'/proc/{pid}'):
                        logger.error("Bot is already running. Exiting.")
                        return
            except:
                pass

        # Создание lock файла
        try:
            with open(lock_file, 'w') as f:
                f.write(str(os.getpid()))
        except IOError as e:
            logger.error(f"Cannot create lock file: {e}")
            return

        try:
            while True:
                try:
                    updates = self.get_updates()

                    if updates:
                        for update in updates:
                            message_info = self.extract_message_info(update)
                            if message_info:
                                text, chat_id, chat_name, chat_number = message_info
                                response = self.process_message(text, chat_name, chat_number)

                                if response:
                                    self.send_message(chat_id, response)

                    time.sleep(self.interval)

                except KeyboardInterrupt:
                    logger.info("Bot stopped by user")
                    break
                except Exception as e:
                    logger.error(f"Error in main loop: {e}")
                    time.sleep(self.interval * 2)  # Увеличенная пауза при ошибке

        finally:
            # Удаление lock файла
            try:
                os.remove(lock_file)
            except:
                pass
            logger.info("Bot stopped")


if __name__ == "__main__":
    try:
        bot = TelegramBot()
        bot.run()
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")