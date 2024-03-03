import os
import asyncpg
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, executor, types
from apscheduler.schedulers.asyncio import AsyncIOScheduler

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")
DATABASE_URL = os.environ.get('DATABASE_URL')
db_pool = None

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)


def is_admin(user_id):
    return str(user_id) in ADMIN_IDS


@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("Извините, у вас нет доступа к админ-панели.")
        return
    await message.reply("Добро пожаловать в админ-панель.")


async def create_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)


async def add_employees(full_name, birth_date, department, photo_url, email, phone_number):
    async with db_pool.acquire() as connection:
        await connection.execute('''
            INSERT INTO employees(full_name, birth_date, department, photo_url, email, phone_number)
            VALUES($1, $2, $3, $4, $5, $6)
        ''', full_name, birth_date, department, photo_url, email, phone_number)


@dp.message_handler(commands=['addemployee'])
async def process_addemployee_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("Извините, у вас нет доступа к этой команде.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await message.reply(
            "Пожалуйста, используйте формат: /addemployee Полное имя; Дата рождения; Отдел; Ссылка на фото; Электронная почта; Номер телефона")
        return

    try:
        full_name, birth_date_str, department, photo_url, email, phone_number = [arg.strip() for arg in
                                                                                 args[1].split(';')]
        birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d').date()
        await add_employees(full_name, birth_date, department, photo_url, email, phone_number)
        await message.reply("Сотрудник успешно добавлен в базу данных.")
    except ValueError:
        await message.reply("Ошибка формата даты. Пожалуйста, используйте формат YYYY-MM-DD.")
    except Exception as e:
        await message.reply(f"Произошла ошибка: {e}")


@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Я бот напоминатель.")


async def birthday_reminder():
    today = datetime.now().date()
    async with db_pool.acquire() as connection:
        employees = await connection.fetch(
            "SELECT full_name, photo_url FROM employees WHERE EXTRACT(MONTH FROM birth_date) = $1 AND EXTRACT(DAY FROM birth_date) = $2",
            today.month, today.day
        )
        for emp in employees:
            message = f"Сегодня день рождения у сотрудника: {emp['full_name']}"
            photo_url = emp['photo_url']
            print(f"Photo URL: {photo_url}")
            for admin_id in ADMIN_IDS.split(','):
                logging.info(f"Sending birthday reminder to admin: {admin_id}")
                if photo_url:
                    await bot.send_photo(admin_id, photo_url, caption=message)
                else:
                    await bot.send_message(admin_id, message)


async def scheduler():
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(birthday_reminder, 'cron', hour=16, minute=52)
    scheduler.start()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    loop.run_until_complete(create_db_pool())
    executor.start_polling(dp, skip_updates=True)
