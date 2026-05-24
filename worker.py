import asyncio
import json
import os
import random
from datetime import datetime, date
from groq import Groq
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from duckduckgo_search import DDGS

TELEGRAM_TOKEN = "Token_bot"
GROQ_API_KEY = "your_key"
MODEL = "gpt-oss-120b"
DATA_FILE = "users_data.json"

SYSTEM_PROMPT = """Ты — тёплый, внимательный AI-психолог по имени Лия.
Твоя задача — помогать людям разобраться в своих чувствах, мыслях и переживаниях.

Принципы работы:
• Слушай активно: перефразируй сказанное, показывай, что понял.
• Задавай открытые вопросы (один за раз), побуждающие к рефлексии.
• Не давай советов сразу — сначала помоги человеку самому найти ответ.
• Используй техники КПТ, ACT и нарративной терапии, но не называй их вслух.
• Если человек в кризисе или упоминает суицид — мягко направь к живому специалисту и дай номер телефона доверия: 8-800-2000-122 (Россия, бесплатно).
• Не ставь диагнозы. Ты — поддержка, не замена врачу.
• Говори тепло, без канцелярита, на «ты».
• Ответы — 2–4 абзаца максимум, без списков и заголовков.
• Ты ТОЛЬКО психолог. Если тебя просят написать код, решить задачу или сделать что-то не связанное с психологией — вежливо откажись и верни разговор к переживаниям человека."""

SEARCH_SYSTEM_PROMPT = """Ты — тёплый AI-психолог по имени Лия.
Тебе дали результаты поиска по запросу пользователя. Твоя задача:
1. Кратко и тепло изложи найденную информацию своими словами (2-3 абзаца).
2. Если информация касается психологии или самочувствия — обязательно добавь пару слов поддержки.
3. Если это просто информационный запрос — ответь по делу, без лишнего.
4. Не копируй текст напрямую, говори как живой человек.
5. В конце можешь спросить, помогло ли это."""

EXERCISES = [
    {
        "name": "🫁 Дыхание 4-7-8",
        "text": (
            "Это упражнение быстро снимает тревогу.\n\n"
            "1. Вдох через нос — 4 секунды\n"
            "2. Задержи дыхание — 7 секунд\n"
            "3. Выдох через рот — 8 секунд\n\n"
            "Повтори 3–4 раза. Почувствуй как тело расслабляется с каждым циклом."
        ),
    },
    {
        "name": "🌿 Заземление 5-4-3-2-1",
        "text": (
            "Помогает вернуться в настоящий момент при тревоге или панике.\n\n"
            "Найди вокруг себя:\n"
            "👁 5 вещей которые видишь\n"
            "✋ 4 вещи которые можешь потрогать\n"
            "👂 3 звука которые слышишь\n"
            "👃 2 запаха которые чувствуешь\n"
            "👅 1 вкус во рту\n\n"
            "Называй их про себя не торопясь."
        ),
    },
    {
        "name": "💪 Прогрессивная релаксация",
        "text": (
            "Снимает физическое напряжение за 5 минут.\n\n"
            "Поочерёдно напрягай и расслабляй группы мышц:\n"
            "• Сожми кулаки — 5 сек — разожми\n"
            "• Напряги плечи к ушам — 5 сек — опусти\n"
            "• Зажмурь глаза — 5 сек — расслабь\n"
            "• Напряги живот — 5 сек — отпусти\n"
            "• Потяни носки на себя — 5 сек — расслабь\n\n"
            "После каждого расслабления замечай разницу в ощущениях."
        ),
    },
    {
        "name": "📝 Запись мыслей",
        "text": (
            "Техника из КПТ для работы с тревожными мыслями.\n\n"
            "Возьми листок и запиши:\n"
            "1. Ситуация — что произошло?\n"
            "2. Мысль — что ты подумал?\n"
            "3. Эмоция — что почувствовал? (0-10)\n"
            "4. Факты ЗА эту мысль\n"
            "5. Факты ПРОТИВ этой мысли\n"
            "6. Более реалистичная мысль\n\n"
            "Это помогает увидеть что мозг часто преувеличивает угрозу."
        ),
    },
    {
        "name": "🧘 Медитация на дыхание",
        "text": (
            "Простая медитация на 5 минут.\n\n"
            "• Сядь удобно, закрой глаза\n"
            "• Дыши естественно, не контролируй\n"
            "• Сосредоточь внимание на ощущении воздуха у ноздрей\n"
            "• Когда мысли уходят в сторону — просто мягко возвращай внимание к дыханию\n"
            "• Не осуждай себя за отвлечения — это нормально\n\n"
            "Даже 5 минут в день меняют качество жизни через несколько недель."
        ),
    },
]

MOODS = ["😢 Очень плохо", "😔 Плохо", "😐 Нейтрально", "🙂 Хорошо", "😄 Отлично"]

client = Groq(api_key=GROQ_API_KEY)
user_histories: dict[int, list[dict]] = {}
MAX_HISTORY = 20


# ─── БАЗА ДАННЫХ ──────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_user_data(user_id: int) -> dict:
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "first_seen": date.today().isoformat(),
            "last_seen": date.today().isoformat(),
            "days_streak": 1,
            "total_days": 1,
            "mood_diary": [],
        }
        save_data(data)
    return data[uid]


def update_user_streak(user_id: int):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        get_user_data(user_id)
        return
    today = date.today().isoformat()
    last = data[uid].get("last_seen", today)
    if last == today:
        return
    from datetime import timedelta
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    if last == yesterday:
        data[uid]["days_streak"] = data[uid].get("days_streak", 1) + 1
    else:
        data[uid]["days_streak"] = 1
    data[uid]["total_days"] = data[uid].get("total_days", 1) + 1
    data[uid]["last_seen"] = today
    save_data(data)


def save_mood(user_id: int, mood_index: int, note: str = ""):
    data = load_data()
    uid = str(user_id)
    if uid not in data:
        get_user_data(user_id)
        data = load_data()
    entry = {
        "date": datetime.now().strftime("%d.%m.%Y %H:%M"),
        "mood": MOODS[mood_index],
        "note": note,
    }
    data[uid].setdefault("mood_diary", []).append(entry)
    save_data(data)


# ─── ПОИСК ───────────────────────────────────────────────────────────────────
def search_web(query: str, max_results: int = 5) -> str:
    """Поиск через DuckDuckGo, возвращает текст с результатами."""
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return "По этому запросу ничего не найдено."
        lines = []
        for r in results:
            title = r.get("title", "")
            body = r.get("body", "")
            href = r.get("href", "")
            lines.append(f"• {title}\n  {body}\n  {href}")
        return "\n\n".join(lines)
    except Exception as e:
        return f"Ошибка поиска: {e}"


# ─── GROQ ─────────────────────────────────────────────────────────────────────
def get_history(user_id: int) -> list[dict]:
    return user_histories.setdefault(user_id, [])


def add_message(user_id: int, role: str, content: str):
    history = get_history(user_id)
    history.append({"role": role, "content": content})
    if len(history) > MAX_HISTORY:
        user_histories[user_id] = history[-MAX_HISTORY:]


async def ask_groq(user_id: int, user_text: str) -> str:
    add_message(user_id, "user", user_text)
    history = get_history(user_id)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=MODEL,
        messages=messages,
        max_tokens=1024,
        temperature=0.8,
    )
    reply = response.choices[0].message.content
    add_message(user_id, "assistant", reply)
    return reply


async def ask_groq_with_search(query: str, search_results: str) -> str:
    """Отдельный запрос к Groq с результатами поиска — без влияния на историю диалога."""
    user_content = (
        f"Пользователь искал: «{query}»\n\n"
        f"Результаты поиска:\n{search_results}\n\n"
        f"Перескажи это тепло и по делу."
    )
    messages = [
        {"role": "system", "content": SEARCH_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
    response = await asyncio.to_thread(
        client.chat.completions.create,
        model=MODEL,
        messages=messages,
        max_tokens=800,
        temperature=0.7,
    )
    return response.choices[0].message.content


# ─── КОМАНДЫ ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_histories.pop(user.id, None)
    context.user_data.clear()
    get_user_data(user.id)
    update_user_streak(user.id)
    await update.message.reply_text(
        f"Привет, {user.first_name} 👋\n\n"
        "Я Лия — твой личный AI-психолог. Здесь безопасно, и я никуда не тороплюсь.\n\n"
        "Расскажи, что сейчас на душе? Или просто напиши пару слов о том, что тебя привело сюда."
    )


async def cmd_reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_histories.pop(update.effective_user.id, None)
    context.user_data.clear()
    await update.message.reply_text(
        "История нашего разговора очищена. Можем начать с чистого листа 🌱\n"
        "Что сейчас у тебя на сердце?"
    )


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Доступные команды:\n\n"
        "/start — начать новый разговор\n"
        "/reset — очистить историю\n"
        "/exercise — получить упражнение\n"
        "/mood — записать настроение в дневник\n"
        "/diary — посмотреть дневник настроения\n"
        "/stats — моя статистика\n"
        "/search <запрос> — найти информацию в интернете\n"
        "/help — эта справка\n\n"
        "⚠️ Линия психологической помощи: 8-800-2000-122 (бесплатно, круглосуточно)"
    )


async def cmd_exercise(update: Update, context: ContextTypes.DEFAULT_TYPE):
    exercise = random.choice(EXERCISES)
    await update.message.reply_text(f"{exercise['name']}\n\n{exercise['text']}")


async def cmd_mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    context.user_data["waiting_mood"] = True
    mood_list = "\n".join([f"{i+1}. {m}" for i, m in enumerate(MOODS)])
    await update.message.reply_text(
        f"Как ты себя чувствуешь сейчас?\n\n{mood_list}\n\nОтветь цифрой от 1 до 5"
    )


async def cmd_diary(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    diary = data.get("mood_diary", [])
    if not diary:
        await update.message.reply_text(
            "Дневник пока пустой. Используй /mood чтобы записать своё настроение 📖"
        )
        return
    last_entries = diary[-10:]
    text = "📖 Твой дневник настроения (последние записи):\n\n"
    for entry in reversed(last_entries):
        text += f"📅 {entry['date']}\n"
        text += f"   {entry['mood']}\n"
        if entry.get("note"):
            text += f"   💬 {entry['note']}\n"
        text += "\n"
    await update.message.reply_text(text)


async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    data = get_user_data(user_id)
    streak = data.get("days_streak", 1)
    total = data.get("total_days", 1)
    first = data.get("first_seen", date.today().isoformat())
    mood_count = len(data.get("mood_diary", []))
    streak_emoji = "🔥" if streak >= 3 else "✨"
    await update.message.reply_text(
        f"📊 Твоя статистика:\n\n"
        f"{streak_emoji} Дней подряд: {streak}\n"
        f"📅 Всего дней с ботом: {total}\n"
        f"🗓 Первый визит: {first}\n"
        f"📖 Записей в дневнике: {mood_count}"
    )


async def cmd_search(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда /search <запрос> — ищет в интернете и отвечает в стиле Лии."""
    query = " ".join(context.args)
    if not query:
        await update.message.reply_text(
            "Напиши что искать, например:\n/search как справиться с тревогой"
        )
        return

    await context.bot.send_chat_action(
        chat_id=update.effective_chat.id, action="typing"
    )

    # Сообщение-заглушка пока идёт поиск
    searching_msg = await update.message.reply_text(f"🔍 Ищу «{query}»...")

    try:
        # Поиск в отдельном потоке
        search_results = await asyncio.to_thread(search_web, query)
        # Формируем ответ через Groq
        reply = await ask_groq_with_search(query, search_results)
        await searching_msg.delete()
        await update.message.reply_text(reply)
    except Exception as e:
        await searching_msg.delete()
        await update.message.reply_text(
            "Не удалось выполнить поиск. Попробуй чуть позже 🙏"
        )
        print(f"[SEARCH ERROR] {e}")


# ─── ОБРАБОТКА СООБЩЕНИЙ ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    update_user_streak(user_id)

    if context.user_data.get("waiting_mood"):
        if text in ["1", "2", "3", "4", "5"]:
            mood_index = int(text) - 1
            context.user_data["waiting_mood"] = False
            context.user_data["mood_index"] = mood_index
            context.user_data["waiting_note"] = True
            await update.message.reply_text(
                f"Записал: {MOODS[mood_index]}\n\n"
                "Хочешь добавить заметку? Напиши пару слов или отправь «-» чтобы пропустить."
            )
        else:
            await update.message.reply_text(
                "Пожалуйста, отправь цифру от 1 до 5.\n\n"
                "Или напиши /reset чтобы выйти из режима дневника."
            )
        return

    if context.user_data.get("waiting_note"):
        note = "" if text == "-" else text
        mood_index = context.user_data.get("mood_index", 2)
        save_mood(user_id, mood_index, note)
        context.user_data.clear()
        await update.message.reply_text(
            "✅ Настроение записано в дневник!\n\n"
            "Хочешь поговорить о том, как ты себя чувствуешь?"
        )
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")

    try:
        reply = await ask_groq(user_id, text)
        await update.message.reply_text(reply)
    except Exception as e:
        await update.message.reply_text(
            "Упс, что-то пошло не так. Попробуй ещё раз или напиши /reset."
        )
        print(f"[ERROR] user={user_id}: {e}")


# ─── ЗАПУСК ──────────────────────────────────────────────────────────────────
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("reset", cmd_reset))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("exercise", cmd_exercise))
    app.add_handler(CommandHandler("mood", cmd_mood))
    app.add_handler(CommandHandler("diary", cmd_diary))
    app.add_handler(CommandHandler("stats", cmd_stats))
    app.add_handler(CommandHandler("search", cmd_search))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Бот запущен. Ctrl+C для остановки.")
    app.run_polling()


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
