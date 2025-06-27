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
CHAT_ID = int(os.getenv('CHAT_ID'))  # обязательно int

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ===== Загружаем oski.py =====
def load_sounds():
    if not os.path.exists("oski.py"):
        return {}

    spec = importlib.util.spec_from_file_location("oski", "oski.py")
    oski = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oski)
    return getattr(oski, "SOUNDS", {})

SOUNDS = load_sounds()

# ===== Inline ответ =====
@dp.inline_query()
async def inline_echo(inline_query: types.InlineQuery):
    text = inline_query.query or ''
    results = []

    if text.strip():
        for title, file_id in SOUNDS.items():
            if text.lower() in title.lower():
                results.append(types.InlineQueryResultCachedVoice(
                    id=str(hash(title)),
                    voice_file_id=file_id,
                    title=title.capitalize()
                ))
    else:
        sample = random.sample(list(SOUNDS.items()), min(40, len(SOUNDS)))
        for title, file_id in sample:
            results.append(types.InlineQueryResultCachedVoice(
                id=str(hash(title)),
                voice_file_id=file_id,
                title=title.capitalize()
            ))

    await inline_query.answer(results=results, cache_time=1, is_personal=True)

# ===== Обработка .ogg от владельца =====
@dp.message(F.from_user.id == CHAT_ID)
async def handle_ogg_upload(message: types.Message):
    file = None
    file_name = None

    # Определяем файл и имя
    if message.audio and message.audio.file_name and message.audio.file_name.endswith(".ogg"):
        file = message.audio
        file_name = message.audio.file_name
    elif message.document and message.document.file_name and message.document.file_name.endswith(".ogg"):
        file = message.document
        file_name = message.document.file_name
    else:
        await message.answer("⚠️ Отправь .ogg файл аудио или документом.")
        return

    title = os.path.splitext(file_name)[0].replace('_', ' ').upper()

    if title in SOUNDS:
        await message.answer(f"⚠️ Звук \"{title}\" уже есть в базе.")
        return

    # Скачиваем ogg
    file_path = f"zvuchok/{file_name}"
    await bot.download(file, destination=file_path)

    # Отправляем как voice
    try:
        voice = FSInputFile(file_path)
        msg = await bot.send_voice(chat_id=CHAT_ID, voice=voice)
        file_id = msg.voice.file_id
        SOUNDS[title] = file_id
        await message.answer(f"✅ Добавлено: {title}")

        # Сохраняем в oski.py
        with open("oski.py", "w", encoding="utf-8") as f:
            f.write("SOUNDS = {\n")
            for t, fid in sorted(SOUNDS.items()):
                f.write(f'    "{t}": "{fid}",\n')
            f.write("}\n")

        print(f"[OK] {title} -> {file_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {e}")
        print(f"[ERROR] {title}: {e}")

# ===== Автоматический перезапуск при изменении oski.py =====
def restart():
    print("Файл oski.py изменён. Перезапуск бота...")
    python = sys.executable
    os.execl(python, python, *sys.argv)

class OskiChangeHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith("oski.py"):
            time.sleep(1)
            restart()

def start_watcher():
    event_handler = OskiChangeHandler()
    observer = Observer()
    observer.schedule(event_handler, path='.', recursive=False)
    observer.start()

# ===== Запуск =====
async def main():
    watcher_thread = threading.Thread(target=start_watcher, daemon=True)
    watcher_thread.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
