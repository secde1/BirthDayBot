import os
import asyncpg
import logging
import asyncio
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, executor
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from InlineKeyboardMarkup_ import make_admin_keyboard
from aiogram.dispatcher import FSMContext
from aiogram.types import Message
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.contrib.fsm_storage.memory import MemoryStorage

storage = MemoryStorage()

load_dotenv()

API_TOKEN = os.getenv("API_TOKEN")
ADMIN_IDS = os.getenv("ADMIN_IDS")
DATABASE_URL = os.environ.get('DATABASE_URL')
db_pool = None

logging.basicConfig(level=logging.INFO)

bot = Bot(token=API_TOKEN)

dp = Dispatcher(bot, storage=storage)


def is_admin(user_id):
    return str(user_id) in ADMIN_IDS


@dp.message_handler(commands=['admin'])
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("Извините, у вас нет доступа к админ-панели.")
        return
    await message.reply("Добро пожаловать в админ-панель.", reply_markup=make_admin_keyboard())


@dp.callback_query_handler(text=["addposition", "addemployee", "getemployees"])
async def handle_admin_buttons(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    if not is_admin(user_id):
        await callback_query.answer("Извините, у вас нет доступа к этой команде.", show_alert=True)
        return

    if callback_query.data == "addposition":
        await callback_query.message.answer(
            "Отправьте название новой должности в формате: /addposition Название_должности")
    elif callback_query.data == "addemployee":
        await callback_query.message.answer(
            "Отправьте данные нового сотрудника в формате: /addemployee Имя; Фамилия; Дата рождения; Должность; Ссылка на фото")
    elif callback_query.data == "getemployees":
        await send_all_employees(callback_query.message)
    await callback_query.answer()


async def create_db_pool():
    global db_pool
    db_pool = await asyncpg.create_pool(DATABASE_URL)


async def add_position(name):
    async with db_pool.acquire() as connection:
        try:
            await connection.execute('''
                INSERT INTO Position(name)
                VALUES($1)
            ''', name)
            logging.info("Должность успешно добавлена")
            return True
        except Exception as e:
            logging.error(f"Ошибка при добавлении должности: {e}")
            return False


@dp.message_handler(commands=['addposition'])
async def process_addposition_command(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.reply("Извините, у вас нет доступа к этой команде.")
        return

    args = message.text.split(maxsplit=1)
    if len(args) != 2:
        await message.reply("Пожалуйста, используйте формат: /addposition Название_должности")
        return

    position_name = args[1].strip()

    success = await add_position(position_name)
    if success:
        await message.reply(f"Должность '{position_name}' успешно добавлена в базу данных.")
    else:
        await message.reply("Произошла ошибка при добавлении должности.")


class EmployeeForm(StatesGroup):
    WaitingForName = State()
    WaitingForLastName = State()
    WaitingForBirthDate = State()
    WaitingForPosition = State()
    WaitingForPhoto = State()


@dp.message_handler(commands=['addemployee'], state="*")
async def add_employee_start(message: Message):
    await EmployeeForm.WaitingForName.set()
    await message.answer("Введите имя сотрудника:")


@dp.message_handler(state=EmployeeForm.WaitingForName)
async def employee_name_entered(message: Message, state: FSMContext):
    await state.update_data(first_name=message.text)
    await EmployeeForm.next()
    await message.answer("Введите фамилию сотрудника:")


@dp.message_handler(state=EmployeeForm.WaitingForLastName)
async def process_last_name(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['last_name'] = message.text
    await EmployeeForm.next()
    await message.reply("Введите дату рождения сотрудника (в формате ГГГГ-ММ-ДД):")


@dp.message_handler(state=EmployeeForm.WaitingForBirthDate)
async def process_birth_date(message: types.Message, state: FSMContext):
    # Преобразование строки в объект даты
    birth_date = datetime.strptime(message.text, '%Y-%m-%d').date()

    # Сохранение объекта даты в контекст состояния
    async with state.proxy() as data:
        data['birth_date'] = birth_date

    # Переход к следующему состоянию
    await EmployeeForm.next()
    await message.reply("Введите должность сотрудника:")


@dp.message_handler(state=EmployeeForm.WaitingForPosition)
async def process_position(message: types.Message, state: FSMContext):
    async with state.proxy() as data:
        data['position'] = message.text
    await EmployeeForm.next()
    print("-------------------------------------------------------------------")
    await message.reply("Пришлите фотографию сотрудника:")


@dp.message_handler(content_types=['photo'], state=EmployeeForm.WaitingForPhoto)
async def process_photo(message: types.Message, state: FSMContext):
    photo_file_id = message.photo[-1].file_id

    async with state.proxy() as data:
        data['photo'] = photo_file_id

    async with state.proxy() as data:
        first_name = data.get('first_name')
        last_name = data.get('last_name')
        birth_date = data.get('birth_date')
        position = data.get('position')
        photo = data.get('photo')

        async with db_pool.acquire() as connection:
            await connection.execute('''
                INSERT INTO Employees (first_name, last_name, birth_date, position_id, photo_url)
                VALUES ($1, $2, $3, (SELECT id FROM Position WHERE name = $4), $5)
            ''', first_name, last_name, birth_date, position, photo)

    await state.finish()
    await message.reply("Спасибо! Информация о сотруднике сохранена.")


async def birthday_reminder():
    today = datetime.now().date()
    async with db_pool.acquire() as connection:
        employees = await connection.fetch(
            '''
            SELECT e.first_name, e.last_name, e.photo_url, p.name as position_name
            FROM Employees e
            JOIN Position p ON e.position_id = p.id
            WHERE EXTRACT(MONTH FROM e.birth_date) = $1 AND EXTRACT(DAY FROM e.birth_date) = $2
            ''',
            today.month, today.day
        )
        for emp in employees:
            message = f"Сегодня день рождения у сотрудника: {emp['first_name']} {emp['last_name']}, Должность: {emp['position_name']}"
            photo_url = emp['photo_url']
            for admin_id in ADMIN_IDS.split(','):
                logging.info(f"Sending birthday reminder to admin: {admin_id}")
                if photo_url:
                    await bot.send_photo(admin_id, photo_url, caption=message)
                else:
                    await bot.send_message(admin_id, message)


async def get_all_employees():
    async with db_pool.acquire() as connection:
        employees = await connection.fetch(
            '''
            SELECT e.first_name, e.last_name, e.birth_date, p.name as position_name
            FROM Employees e
            JOIN Position p ON e.position_id = p.id
            '''
        )
        return employees


# @dp.message_handler(commands=['getemployees'])
async def send_all_employees(message):
    # if not is_admin(message.from_user.id):
    #     await message.reply("Извините, у вас нет доступа к этой команде.")
    #     return
    employees = await get_all_employees()
    if not employees:
        await message.answer("Сотрудники не найдены.")
        return

    reply_message = "Список всех сотрудников:\n\n"
    for employee in employees:
        reply_message += f"Имя: {employee['first_name']} {employee['last_name']}, Должность: {employee['position_name']}, Дата рождения: {employee['birth_date']:%Y-%m-%d}\n"

    while reply_message:
        part, reply_message = reply_message[:4096], reply_message[4096:]
        await message.answer(part)


@dp.message_handler(commands=['start'])
async def send_welcome(message: types.Message):
    await message.reply("Привет! Я бот напоминатель.")


@dp.message_handler(content_types=['text'])
async def handle_unknown_message(message: types.Message):
    await message.reply("Вы отправили не существующий запрос.")


async def scheduler():
    scheduler = AsyncIOScheduler(timezone="Asia/Tashkent")
    scheduler.add_job(birthday_reminder, 'cron', hour=16, minute=48)
    scheduler.start()


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    loop.run_until_complete(create_db_pool())
    executor.start_polling(dp, skip_updates=True)
