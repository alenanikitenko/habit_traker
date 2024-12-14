import json
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from telegram import ReplyKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext

# Настройка логирования
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# Класс для хранения информации о привычке
class Habit:
    def __init__(self, name, description, frequency, time):
        self.name = name
        self.description = description
        self.frequency = frequency  # каждый день, неделю, и т.д.
        self.time = time  # Время, когда должно приходить уведомление

    def __repr__(self):
        return f"Habit(name={self.name}, description={self.description}, frequency={self.frequency}, time={self.time})"

class HabitTracker:
    def __init__(self):
        self.habits = self.load_data()
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()

    def load_data(self):
        try:
            with open("data.json", "r") as file:
                return json.load(file)
        except FileNotFoundError:
            return {}

    def save_data(self):
        with open("data.json", "w") as file:
            json.dump(self.habits, file, indent=4)

    def add_habit(self, user_id, habit):
        if user_id not in self.habits:
            self.habits[user_id] = []
        self.habits[user_id].append({
            "name": habit.name,
            "description": habit.description,
            "frequency": habit.frequency,
            "time": habit.time.strftime("%H:%M")
        })
        self.save_data()

    def get_habits(self, user_id):
        return self.habits.get(user_id, [])

    def add_notification(self, job_name, time, job):
        self.scheduler.add_job(job, 'interval', minutes=1, start_date=time, id=job_name)

    def send_notification(self, update, habit_name):
        update.message.reply_text(f"Напоминание: Выполни привычку: {habit_name}")

habit_tracker = HabitTracker()

# Этапы диалога с пользователем (состояния)
(
    WAITING_NAME,
    WAITING_DESCRIPTION,
    WAITING_FREQUENCY,
    WAITING_TIME,
    WAITING_DELETE_HABIT,
) = range(5)

# Функция стартового сообщения с клавиатурой
async def start(update, context):
    keyboard = [
        ['Добавить привычку', 'Мои привычки'],
        ['Удалить привычку', 'Установка напоминаний'],
        ['Помощь']
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_text(
        "Привет! Я бот для формирования полезных привычек. Выберите одну из опций:",
        reply_markup=reply_markup
    )
async def ask_for_name(update, context):
    await update.message.reply_text("Введите название привычки:")
    return WAITING_NAME  # Переход к состоянию "Ожидание названия"
# Обработка кнопок
async def handle_reply(update, context):
    user_message = update.message.text  # Получаем текст, который был выбран на клавиатуре

    if user_message == 'Добавить привычку':
        # Начинаем диалог с пользователем для добавления привычки
        return await ask_for_name(update, context)
    elif user_message == 'Мои привычки':
        # Отображаем список привычек
        await list_habits(update, context)
        return ConversationHandler.END  # Заканчиваем диалог, если пользователь выбрал "Мои привычки"
    elif user_message == 'Установка напоминаний':
        await set_daily_reminder(update, context)
    elif user_message == 'Удалить привычку':
        # Переход к удалению привычки
        await update.message.reply_text("Введите название привычки, которую хотите удалить:")
        return WAITING_DELETE_HABIT  # Переход к состоянию ожидания ввода названия привычки
    elif user_message == 'Помощь':
        await update.message.reply_text("Список команд:\nДобавить привычку\nМои привычки\nУстановка напоминаний\nУдалить привычку")
    else:
        await update.message.reply_text("Неизвестная команда. Пожалуйста, выберите из списка.")

# Обработка ввода названия привычки
async def process_name(update, context):
    habit_name = update.message.text
    context.user_data['habit_name'] = habit_name
    await update.message.reply_text(f"Вы выбрали название: {habit_name}. Теперь введите описание привычки:")
    return WAITING_DESCRIPTION  # Переход к состоянию "Ожидание описания"

# Обработка ввода описания привычки
async def process_description(update, context):
    description = update.message.text
    context.user_data['description'] = description
    await update.message.reply_text(f"Вы выбрали описание: {description}. Теперь укажите частоту (каждый день / каждую неделю):")
    return WAITING_FREQUENCY  # Переход к состоянию "Ожидание частоты"

# Обработка ввода частоты привычки
async def process_frequency(update, context):
    frequency = update.message.text.lower()
    if frequency not in ['каждый день', 'каждую неделю']:
        await update.message.reply_text("Неверный формат. Введите 'каждый день' или 'каждую неделю'.")
        return WAITING_FREQUENCY  # Ожидание правильного ввода

    context.user_data['frequency'] = frequency
    await update.message.reply_text("Теперь укажите время в формате ЧЧ:ММ (например, 12:30):")
    return WAITING_TIME  # Переход к состоянию "Ожидание времени"

# Обработка ввода времени
async def process_time(update, context):
    time_str = update.message.text.strip()
    try:
        habit_time = datetime.strptime(time_str, "%H:%M").time()
    except ValueError:
        await update.message.reply_text("Ошибка формата времени. Используйте формат HH:MM (например, 12:10).")
        return WAITING_TIME  # Ожидание правильного формата времени

    context.user_data['habit_time'] = habit_time
    habit = Habit(
        name=context.user_data['habit_name'],
        description=context.user_data['description'],
        frequency=context.user_data['frequency'],
        time=habit_time
    )
    habit_tracker.add_habit(update.effective_user.id, habit)

    # Формируем строку времени без секунд
    habit_time_str = habit_time.strftime("%H:%M")  # Убираем секунды

    await update.message.reply_text(
        f"Привычка '{habit.name}' добавлена!\nОписание: {habit.description}\nВремя: {habit_time_str}\nЧастота: {habit.frequency}."
    )
    return ConversationHandler.END  # Завершение диалога



# Просмотр всех привычек пользователя
async def list_habits(update, context):
    user_habits = habit_tracker.get_habits(update.effective_user.id)
    if user_habits:
        response = "Ваши привычки:\n"
        for habit in user_habits:
            response += f"{habit['name']}: {habit['description']} (время: {habit['time']}, частота: {habit['frequency']})\n"
        await update.message.reply_text(response)
    else:
        await update.message.reply_text("У вас еще нет привычек.")

# Установка напоминаний
async def set_daily_reminder(update, context):
    user_habits = habit_tracker.get_habits(update.effective_user.id)
    if not user_habits:
        await update.message.reply_text("У вас нет добавленных привычек!")
        return

    for habit in user_habits:
        habit_time_str = habit['time']
        habit_time = datetime.strptime(habit_time_str, "%H:%M").time()
        now = datetime.now()
        reminder_time = datetime.combine(now.date(), habit_time)

        if reminder_time < now:
            reminder_time += timedelta(days=1)

        job_name = f"{habit['name']}_notification"
        existing_jobs = habit_tracker.scheduler.get_jobs()
        if any(job.id == job_name for job in existing_jobs):
            continue

        habit_tracker.add_notification(job_name, reminder_time,
                                       lambda update=update, habit=habit: habit_tracker.send_notification(update, habit['name']))

    await update.message.reply_text("Напоминания установлены для всех привычек.")

# Удаление привычки
async def ask_for_delete_habit(update, context):
    await update.message.reply_text("Введите название привычки, которую хотите удалить:")
    return WAITING_DELETE_HABIT  # Переход к состоянию "Ожидание удаления"

# Процесс удаления привычки
# Процесс удаления привычки
# Процесс удаления привычки
async def delete_habit(update: Update, context: CallbackContext) -> None:
    try:
        habit_name = update.message.text.strip()  # Получаем текст, который пользователь ввел

        # Проверка, что введено название привычки, а не команда
        if habit_name.lower() == "мои привычки":
            # Сообщение, если пытаемся удалить команду
            await update.message.reply_text("Вы не можете удалить команду 'Мои привычки'. Введите название привычки для удаления.")
            return

        if not habit_name:
            await update.message.reply_text(
                "Вы должны указать название привычки для удаления. Пример: 'Чтение'")
            return

        user_habits = habit_tracker.get_habits(update.effective_user.id)

        # Проверяем, есть ли привычка с таким названием
        habit_to_remove = None
        for habit in user_habits:
            if habit['name'].lower() == habit_name.lower():  # Сравниваем название с учётом регистра
                habit_to_remove = habit
                break

        if not habit_to_remove:
            await update.message.reply_text(f"Привычка с названием '{habit_name}' не найдена.")
            return

        # Удаляем привычку из хранилища данных
        habit_tracker.habits[update.effective_user.id].remove(habit_to_remove)
        habit_tracker.save_data()

        # Удаляем напоминание для этой привычки
        job_name = f"{habit_to_remove['name']}_notification"
        existing_jobs = habit_tracker.scheduler.get_jobs()
        job_to_remove = next((job for job in existing_jobs if job.id == job_name), None)

        if job_to_remove:
            job_to_remove.remove()
            logger.info(f"Удалено напоминание для привычки: {habit_to_remove['name']}")

        await update.message.reply_text(f"Привычка '{habit_to_remove['name']}' успешно удалена.")

        # Завершаем диалог после удаления привычки, чтобы можно было продолжить использовать другие команды
        return ConversationHandler.END

    except Exception as e:
        logger.error(f"Error in delete_habit: {e}")
        await update.message.reply_text("Произошла ошибка при удалении привычки.")





def main():
    application = Application.builder().token("7582444075:AAG9y-i3q7JTfSKYgfbbdTAkGpX7omJ7pwA").build()

    # ConversationHandler
    conversation_handler = ConversationHandler(
        entry_points=[MessageHandler(filters.TEXT & ~filters.COMMAND, handle_reply)],
        states={
            WAITING_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_name)],
            WAITING_DESCRIPTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_description)],
            WAITING_FREQUENCY: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_frequency)],
            WAITING_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, process_time)],
            WAITING_DELETE_HABIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, delete_habit)],
        },
        fallbacks=[CommandHandler("cancel", lambda update, context: ConversationHandler.END)]
    )

    application.add_handler(conversation_handler)
    application.add_handler(CommandHandler("start", start))

    application.run_polling()

if __name__ == "__main__":
    main()