import os
from dotenv import load_dotenv
import asyncio
from aiogram import Bot, Dispatcher, BaseMiddleware
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import requests


load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
API_KEY = os.getenv('API_KEY')

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

class LoggingMiddleware(BaseMiddleware):
    async def __call__(self, handler, event: Message, data: dict):
        print(f"Получено сообщение: {event.text}")
        return await handler(event, data)

dp.message.middleware(LoggingMiddleware())

users = {}


class Profile(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity_minutes = State()
    city = State()
    water_goal = State()
    calories_goal = State()


class Food(StatesGroup):
    food_name = State()
    food_calories = State()
    food_weight = State()


@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply(
        "Привет! Я бот для расчета нормы воды, калорий и трекинга активности. Вот что я умею:\n\n"
        "/set_profile — настройка вашего профиля (вес, рост, возраст, уровень активности, город, цели).\n\n"
        "/log_water <количество> — записать количество выпитой воды (в мл).\n\n"
        "/log_food <название продукта> — записать съеденную еду. Бот спросит, сколько граммов вы съели.\n\n"
        "/log_workout <тип тренировки> <время (мин)> — записать тренировку, сожженные калории и потраченную воду.\n\n"
        "/check_progress — проверить текущий прогресс по воде, калориям и сожженным калориям.\n\n"
        "Если вы готовы начать, используйте команду /set_profile, чтобы настроить свой профиль!"
    )


@dp.message(Command("set_profile"))
async def set_profile(message: Message, state: FSMContext):
    await message.reply("Введите ваш вес (в кг):")
    await state.set_state(Profile.weight)


@dp.message(Profile.weight)
async def process_weight(message: Message, state: FSMContext):
    await state.update_data(weight=int(message.text))
    await message.reply("Введите ваш рост (в см):")
    await state.set_state(Profile.height)


@dp.message(Profile.height)
async def process_height(message: Message, state: FSMContext):
    await state.update_data(height=int(message.text))
    await message.reply("Введите ваш возраст:")
    await state.set_state(Profile.age)


@dp.message(Profile.age)
async def process_age(message: Message, state: FSMContext):
    await state.update_data(age=int(message.text))
    await message.reply("Сколько минут активности у вас в день?")
    await state.set_state(Profile.activity_minutes)


@dp.message(Profile.activity_minutes)
async def process_activity_minutes(message: Message, state: FSMContext):
    await state.update_data(activity_minutes=int(message.text))
    await message.reply("В каком городе вы находитесь?")
    await state.set_state(Profile.city)


@dp.message(Profile.city)
async def process_city(message: Message, state: FSMContext):
    city = message.text
    temperature = get_current_temperature(city)
    if temperature is None:
        await message.reply("Город не найден. Попробуйте снова.")
        return

    data = await state.get_data()
    await state.update_data(city=city, temperature=temperature)

    weight = data["weight"]
    activity = data["activity_minutes"]
    recommended_water_goal = round(weight * 30 + (500 * (activity // 30)) + (500 if temperature > 25 else 0) + (500 if temperature > 35 else 0))
    recommended_calories_goal = round(10 * weight + 6.25 * data["height"] - 5 * data["age"] + (200 if activity >= 30 else 0) + (200 if activity >= 60 else 0))

    await state.update_data(recommended_calories_goal=recommended_calories_goal)
    await message.reply(
        f"Рекомендованная норма воды: {recommended_water_goal} мл.\n"
        f"Рекомендованная норма калорий: {recommended_calories_goal} ккал.\n\n"
        f"Введите вашу цель по воде (в мл):"
    )
    await state.set_state(Profile.water_goal)


@dp.message(Profile.water_goal)
async def set_water_goal(message: Message, state: FSMContext):
    try:
        water_goal = int(message.text)
        await state.update_data(water_goal=water_goal)
        await message.reply(f"Цель по воде установлена: {water_goal} мл.\nВведите вашу цель по калориям (в ккал):")
        await state.set_state(Profile.calories_goal)
    except ValueError:
        await message.reply("Введите корректное число для цели по воде.")


@dp.message(Profile.calories_goal)
async def set_calories_goal(message: Message, state: FSMContext):
    try:
        calories_goal = int(message.text)
        await state.update_data(calories_goal=calories_goal)

        data = await state.get_data()

        water_goal = data["water_goal"]

        users[message.from_user.id] = {
            "weight": data["weight"],
            "height": data["height"],
            "age": data["age"],
            "activity": data["activity_minutes"],
            "city": data["city"],
            "temperature": data["temperature"],
            "water_goal": water_goal,
            "calories_goal": calories_goal,
            "calories_balance": data["recommended_calories_goal"],
            "logged_water": 0,
            "logged_calories": 0,
            "burned_calories": 0
        }

        await state.clear()
        await message.reply(
            f"Профиль настроен!\n"
            f"Цель по воде: {water_goal} мл.\n"
            f"Цель по калориям: {calories_goal} ккал."
        )
    except ValueError:
        await message.reply("Введите корректное число для цели по калориям.")


def get_current_temperature(city):
    response = requests.get(f"http://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={API_KEY}")
    if response.ok:
        data = response.json()
        if not data:
            return None
        lat, lon = data[0]['lat'], data[0]['lon']
        weather_response = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={API_KEY}&units=metric"
        )
        if weather_response.ok:
            return weather_response.json()['main']['temp']
        return None
    return None


@dp.message(Command("log_water"))
async def log_water(message: Message):
    user_data = users.get(message.from_user.id, None)
    if not user_data:
        await message.reply("Ваш профиль не найден. Сначала настройте профиль с помощью команды /set_profile.")
        return
    try:
        amount = int(message.text.split()[1])
        user_data = users.get(message.from_user.id, {})
        user_data["logged_water"] += amount
        remaining = max(0, user_data["water_goal"] - user_data["logged_water"])
        users[message.from_user.id] = user_data
        await message.reply(f"Записано {amount} мл воды. Осталось: {remaining} мл.")
    except (IndexError, ValueError):
        await message.reply("Введите количество воды после команды: /log_water <количество>")


@dp.message(Command("log_food"))
async def log_food(message: Message, state: FSMContext):
    user_data = users.get(message.from_user.id, None)
    if not user_data:
        await message.reply("Ваш профиль не найден. Сначала настройте профиль с помощью команды /set_profile.")
        return
    try:
        product_name = " ".join(message.text.split()[1:])
        if not product_name:
            await message.reply("Введите название продукта после команды: /log_food <продукт>")
            return

        food_info = get_food_info(product_name)
        if not food_info:
            await message.reply("Не удалось найти продукт.")
            return

        await state.update_data(food_name=food_info['name'], food_calories=food_info['calories'])
        await message.reply(
                f"{food_info['name']} содержит {food_info['calories']} ккал на 100 г. Сколько грамм вы съели?"
            )
        await state.set_state(Food.food_weight)
    except Exception as e:
        await message.reply(f"Произошла ошибка: {e}")


@dp.message(Food.food_weight)
async def process_food_weight(reply: Message, state: FSMContext):
    try:
        weight = float(reply.text)
        user_data = users.get(reply.from_user.id, {})
        food_info = await state.get_data()

        calories_consumed = round((weight / 100) * food_info['food_calories'])
        user_data["logged_calories"] += calories_consumed

        remaining = max(0, user_data["calories_goal"] - user_data["logged_calories"])

        users[reply.from_user.id] = user_data

        await reply.reply(
            f"Записано: {calories_consumed} ккал из {food_info['food_name']}. "
            f"Осталось: {remaining} ккал."
        )
        await state.clear()
    except ValueError:
        await reply.reply("Введите корректное число (в граммах).")


def get_food_info(product_name):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        products = data.get('products', [])
        if products:
            first_product = products[0]
            return {
                'name': first_product.get('product_name', 'Неизвестно'),
                'calories': first_product.get('nutriments', {}).get('energy-kcal_100g', 0)
            }
        return None
    print(f"Ошибка: {response.status_code}")
    return None


@dp.message(Command("log_workout"))
async def log_workout(message: Message):
    user_data = users.get(message.from_user.id, None)
    if not user_data:
        await message.reply("Ваш профиль не найден. Сначала настройте профиль с помощью команды /set_profile.")
        return
    try:
        parts = message.text.split(maxsplit=2)
        if len(parts) < 3:
            await message.reply("Введите команду в формате: /log_workout <тип тренировки> <время (мин)>")
            return

        workout_type = parts[1]
        workout_time = int(parts[2])

        calories_burned = workout_time * 10
        additional_water = (workout_time // 30) * 200

        user_data["burned_calories"] += calories_burned
        user_data["water_goal"] += additional_water
        users[message.from_user.id] = user_data

        await message.reply(
            f"{workout_type.capitalize()} на {workout_time} минут — {calories_burned} ккал. "
            f"Дополнительно: выпейте {additional_water} мл воды."
        )
    except (ValueError, IndexError):
        await message.reply("Введите команду в формате: /log_workout <тип тренировки> <время (мин)>")


@dp.message(Command("check_progress"))
async def check_progress(message: Message):
    user_data = users.get(message.from_user.id, None)
    if not user_data:
        await message.reply("Ваш профиль не найден. Сначала настройте профиль с помощью команды /set_profile.")
        return

    water_goal = user_data["water_goal"]
    calories_goal = user_data["calories_goal"]
    calories_balance = user_data["calories_balance"]
    logged_water = user_data["logged_water"]
    logged_calories = user_data["logged_calories"]
    burned_calories = user_data["burned_calories"]

    remaining_water = max(0, water_goal - logged_water)

    await message.reply(
        f"📊 Прогресс:\n\n"
        f"Вода:\n"
        f"- Выпито: {logged_water} мл из {water_goal} мл.\n"
        f"- Осталось: {remaining_water} мл.\n\n"
        f"Калории:\n"
        f"- Потреблено: {logged_calories} ккал из {calories_goal} ккал.\n"
        f"- Сожжено: {burned_calories} ккал.\n"
        f"- Баланс: {calories_balance} ккал.\n"
    )


async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
