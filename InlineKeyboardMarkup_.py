from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def make_admin_keyboard():
    keyboard = InlineKeyboardMarkup(row_width=2)
    add_position_button = InlineKeyboardButton(text="Добавить должность", callback_data="addposition")
    add_employee_button = InlineKeyboardButton(text="Добавить сотрудника", callback_data="addemployee")
    get_employee_button = InlineKeyboardButton(text="Список всех сотрудников:", callback_data="getemployees")
    keyboard.add(add_position_button, add_employee_button, get_employee_button)
    return keyboard
