import os
import sys
import logging
import asyncio
import random
import time
import threading
import importlib.util

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import FSInputFile
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

load_dotenv()

API_TOKEN = os.getenv('BOT_KEY')
CHAT_ID = int(os.getenv('CHAT_ID'))
CHAT_ID_KENTIK = int(os.getenv('CHAT_ID_KENTIK'))

FOLDER = "zvuchok"

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s') # Улучшенный формат логов

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ===== Загружаем oski.py =====
def load_sounds():
    if not os.path.exists("oski.py"):
        logging.info("Файл oski.py не найден, создаю пустую базу.")
        # Создаем пустой файл, чтобы избежать ошибки при первом запуске
        with open("oski.py", "w", encoding="utf-8") as f:
            f.write("SOUNDS = {}\n")
        return {}

    spec = importlib.util.spec_from_file_location("oski", "oski.py")
    oski = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oski)
    return getattr(oski, "SOUNDS", {})

SOUNDS = load_sounds()
logging.info(f"Загружено {len(SOUNDS)} звуков из oski.py.")

# ===== Inline ответ =====
@dp.inline_query()
async def inline_echo(inline_query: types.InlineQuery):
    text = inline_query.query or ''
    results = []

    if text.strip():
        # Поиск по запросу
        filtered_sounds = {title: file_id for title, file_id in SOUNDS.items() if text.lower() in title.lower()}
        for title, file_id in filtered_sounds.items():
            results.append(types.InlineQueryResultCachedVoice(
                id=str(hash(title)), # Хэш title для уникального ID
                voice_file_id=file_id,
                title=title.capitalize()
            ))
        logging.info(f"Inline query '{text}' - найдено {len(filtered_sounds)} результатов.")
    else:
        # Случайные звуки, если запрос пустой
        # Проверяем, чтобы избежать ошибки, если SOUNDS пуст
        if SOUNDS:
            sample = random.sample(list(SOUNDS.items()), min(40, len(SOUNDS)))
            for title, file_id in sample:
                results.append(types.InlineQueryResultCachedVoice(
                    id=str(hash(title)), # Хэш title для уникального ID
                    voice_file_id=file_id,
                    title=title.capitalize()
                ))
            logging.info(f"Inline query пуст - выдано {len(sample)} случайных звуков.")
        else:
            logging.info("Inline query пуст, но база SOUNDS тоже пуста.")

    await inline_query.answer(results=results, cache_time=1, is_personal=True)


# ===== Обработка .ogg от владельца =====
@dp.message(F.from_user.id == CHAT_ID or F.from_user.id == CHAT_ID_KENTIK)
async def handle_ogg_upload(message: types.Message):
    logging.info(f"Получено сообщение от CHAT_ID ({message.from_user.id}) для загрузки.")
    # Для отладки можно временно раскомментировать
    # logging.info(json.dumps(message.model_dump(), indent=4, ensure_ascii=False))

    file = None
    file_name_for_storage = None # Имя файла для сохранения на диске
    title_for_sounds = None      # Название, которое будет ключом в базе SOUNDS

    # 1. Проверяем, является ли это голосовым сообщением (message.voice)
    # Это будет основной путь для файлов, отправленных через upload.py
    if message.voice and message.voice.mime_type == "audio/ogg":
        file = message.voice
        # Для сохранения на диске используем уникальный ID, т.к. message.voice не имеет file_name
        file_name_for_storage = f"{message.voice.file_unique_id}.ogg"
        
        # Берем название из подписи (caption)
        if message.caption:
            title_for_sounds = message.caption.upper().strip()
        
        logging.info(f"Распознано как VOICE. MIME: {message.voice.mime_type}. Подпись: '{message.caption}'.")

    # 2. Если не voice, проверяем как обычное аудио (message.audio)
    # Для файлов, которые пользователь отправил как аудиофайл, а не голосовое сообщение
    elif message.audio and message.audio.file_name and message.audio.file_name.endswith(".ogg"):
        file = message.audio
        file_name_for_storage = message.audio.file_name
        title_for_sounds = os.path.splitext(message.audio.file_name)[0].replace('_', ' ').upper()
        logging.info(f"Распознано как AUDIO. Имя файла: '{file_name_for_storage}'. MIME: {message.audio.mime_type}.")

    # 3. Если не voice и не audio, проверяем как документ (message.document)
    # Для файлов, которые пользователь отправил как документ
    elif message.document and message.document.file_name and message.document.file_name.endswith(".ogg"):
        file = message.document
        file_name_for_storage = message.document.file_name
        title_for_sounds = os.path.splitext(message.document.file_name)[0].replace('_', ' ').upper()
        logging.info(f"Распознано как DOCUMENT. Имя файла: '{file_name_for_storage}'. MIME: {message.document.mime_type}.")

    else:
        await message.answer("⚠️ Отправь .ogg файл как *аудио* или *документ* (для использования имени файла) или *голосовое сообщение с подписью* (для OPUS).")
        logging.warning(f"Не удалось распознать сообщение как .ogg аудио, документ или голосовое сообщение. Content type: {message.content_type}")
        return

    # Проверка, удалось ли получить название для базы
    if not title_for_sounds:
        await message.answer("⚠️ Не удалось определить название для звука. Для голосовых сообщений используйте подпись, для других файлов - имя файла.")
        logging.warning("Не удалось получить 'title_for_sounds'. Сообщение будет проигнорировано.")
        return

    # Проверка на существование в базе
    if title_for_sounds in SOUNDS:
        await message.answer(f"⚠️ Звук \"{title_for_sounds}\" уже есть в базе.")
        logging.info(f"Звук '{title_for_sounds}' уже существует в базе, пропуск.")
        return

    # Создаем папку FOLDER, если её нет
    os.makedirs(FOLDER, exist_ok=True)
    
    # Скачиваем ogg
    file_path = os.path.join(FOLDER, file_name_for_storage)
    try:
        await bot.download(file, destination=file_path)
        logging.info(f"Файл '{file_name_for_storage}' успешно скачан в '{FOLDER}'.")
    except Exception as e:
        await message.answer(f"❌ Ошибка при скачивании файла: {e}")
        logging.error(f"Ошибка при скачивании файла '{file_name_for_storage}': {e}")
        return

    # Отправляем скачанный файл обратно как voice, чтобы получить file_id для SOUNDS
    try:
        voice_to_send = FSInputFile(file_path)
        # Отправляем без caption, т.к. он нам нужен был только для получения title, 
        # а повторная отправка нужна только для получения Telegram file_id
        msg = await bot.send_voice(chat_id=message.chat.id, voice=voice_to_send) 
        file_id = msg.voice.file_id
        
        SOUNDS[title_for_sounds] = file_id # Используем наше "человеческое" название
        await message.answer(f"✅ Добавлено: {title_for_sounds}")
        logging.info(f"Звук '{title_for_sounds}' добавлен. File ID: {file_id}")

        # Сохраняем обновленную базу в oski.py
        with open("oski.py", "w", encoding="utf-8") as f:
            f.write("SOUNDS = {\n")
            for t, fid in sorted(SOUNDS.items()):
                f.write(f'    "{t}": "{fid}",\n')
            f.write("}\n")
        logging.info(f"Файл oski.py обновлён для '{title_for_sounds}'.")

    except Exception as e:
        await message.answer(f"❌ Ошибка при обработке звука: {e}")
        logging.error(f"Ошибка при отправке/обработке звука '{title_for_sounds}': {e}")
    finally:
        # Очистка: удаляем временный файл после обработки
        if os.path.exists(file_path):
            os.remove(file_path)
            logging.info(f"Временный файл '{file_path}' удален.")


# ===== Автоматический перезапуск при изменении oski.py =====
def restart():
    logging.info("Файл oski.py изменён. Перезапуск бота...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

class OskiChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("oski.py"):
            logging.info(f"Обнаружено изменение файла: {event.src_path}")
            # Небольшая задержка, чтобы убедиться, что файл полностью записан
            time.sleep(1) 
            restart()

def start_watcher():
    event_handler = OskiChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()
    logging.info("Наблюдатель за oski.py запущен.")

# ===== Запуск =====
async def main():
    if not os.path.exists(FOLDER):
        os.makedirs(FOLDER)
        logging.info(f"Создана папка '{FOLDER}'.")

    watcher_thread = threading.Thread(target=start_watcher, daemon=True)
    watcher_thread.start()
    logging.info("Бот запущен. Ожидание сообщений...")
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Бот выключен пользователем (KeyboardInterrupt).")
    except Exception as e:
        logging.error(f"Произошла непредвиденная ошибка при запуске бота: {e}", exc_info=True)