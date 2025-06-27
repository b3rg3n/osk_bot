import os
import logging
import asyncio
import random

from aiogram import Bot, Dispatcher, types
from oski import SOUNDS

from dotenv import load_dotenv

load_dotenv()

API_TOKEN = os.getenv('BOT_KEY')

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

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

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Бот выключен")
