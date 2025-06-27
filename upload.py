import os
import asyncio
import json
import importlib.util

from aiogram import Bot
from aiogram.types import FSInputFile
from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv('BOT_KEY')
CHAT_ID = os.getenv('CHAT_ID')

FOLDER = "zvuchok"

def load_existing_sounds():
    if not os.path.exists("oski.py"):
        return {}

    spec = importlib.util.spec_from_file_location("oski", "oski.py")
    oski = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(oski)
    return getattr(oski, "SOUNDS", {})

async def main():
    bot = Bot(token=API_TOKEN)
    existing_sounds = load_existing_sounds()
    sounds_dict = existing_sounds.copy()

    for filename in os.listdir(FOLDER):
        if filename.endswith(".ogg"):
            title = os.path.splitext(filename)[0].replace('_', ' ').upper()
            if title in existing_sounds:
                print(f"[SKIP] {title} уже существует.")
                continue

            filepath = os.path.join(FOLDER, filename)
            voice = FSInputFile(filepath)

            try:
                msg = await bot.send_voice(chat_id=CHAT_ID, voice=voice)
                file_id = msg.voice.file_id
                sounds_dict[title] = file_id
                print(f"[OK] {title} -> {file_id}")
            except Exception as e:
                print(f"[ERROR] {title}: {e}")

            await asyncio.sleep(5)

    await bot.session.close()

    with open("oski.py", "w", encoding="utf-8") as f:
        f.write("SOUNDS = {\n")
        for title, file_id in sorted(sounds_dict.items()):
            f.write(f'    "{title}": "{file_id}",\n')
        f.write("}\n")

    print("Файл oski.py обновлён.")

if __name__ == "__main__":
    asyncio.run(main())