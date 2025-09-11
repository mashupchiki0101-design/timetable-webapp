import requests
from bs4 import BeautifulSoup
import re
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

day_map = {
    "понедельник": "Poniedziałek",
    "вторник": "Wtorek",
    "среда": "Środa",
    "четверг": "Czwartek",
    "пятница": "Piątek"
}

# --- парсинг расписания ---
url = "https://dane.ek.zgora.pl/zse/plan/plany/o37.html"
response = requests.get(url)
soup = BeautifulSoup(response.content, "html.parser")
with open("token.txt", "r") as file:
    token = file.read().strip()

TEACHERS_PER_PAGE = 10
search_query = ""
current_page = 0

table = soup.find("table", class_="tabela")
rows = table.find_all("tr")
header_row = None
for row in rows:
    cells = row.find_all(['th', 'td'])
    cell_texts = [cell.get_text(strip=True) for cell in cells]
    if set(day_map.values()).issubset(set(cell_texts)):
        header_row = row
        break

header_cells = header_row.find_all(['th', 'td'])
headers = [cell.get_text(strip=True) for cell in header_cells][2:]
schedule = {day: {} for day in headers}
header_index = rows.index(header_row)

for row in rows[header_index+1:]:
    cells = row.find_all("td")
    if len(cells) < 2:
        continue
    hour = cells[1].get_text(strip=True)
    for i, day in enumerate(headers):
        if i + 2 < len(cells):
            lesson_cell = cells[i+2]
            lessons = []
            for item in lesson_cell.stripped_strings:
                if re.fullmatch(r"[A-Za-zА-Яа-я]{2}", item):
                    continue
                lessons.append(item)
            lesson_text = "\n".join(lessons)
            schedule[day][hour] = lesson_text

def format_schedule(day_name):
    result = []
    for hour, lesson in schedule[day_name].items():
        if not lesson.strip():
            continue
        lines = [line for line in lesson.split('\n') if line.strip()]
        i = 0
        while i < len(lines):
            subject = None
            cabinet = None
            group_lines = []
            if re.match(r"^[a-zA-Zа-яА-Я._ ]+$", lines[i]) and not re.match(r"^\d+$", lines[i].strip()):
                subject = lines[i]
                i += 1
            if i < len(lines) and lines[i] and not re.match(r"-?(\d)/(\d)", lines[i]) and not lines[i].startswith("#") and not (re.match(r"^[a-zA-Zа-яА-Я._ ]+$", lines[i]) and not re.match(r"^\d+$", lines[i].strip())):
                cabinet = lines[i]
                i += 1
            while i < len(lines):
                if re.match(r"^[a-zA-Zа-яА-Я._ ]+$", lines[i]) and not re.match(r"^\d+$", lines[i].strip()):
                    break
                group_match = re.match(r"-?(\d)/(\d)", lines[i])
                if group_match:
                    group_num = group_match.group(1)
                    group_name = ""
                    group_cabinet = ""
                    if i+1 < len(lines) and lines[i+1].startswith("#"):
                        group_name = lines[i+1][1:]
                        i += 1
                    if i+1 < len(lines) and not lines[i+1].startswith("#") and not re.match(r"-?(\d)/(\d)", lines[i+1]):
                        group_cabinet = lines[i+1]
                        i += 1
                    info = f"        группа {group_num}"
                    if group_name:
                        info += f" ({group_name})"
                    if group_cabinet:
                        info += f", кабинет {group_cabinet}"
                    group_lines.append(info)
                    i += 1
                else:
                    i += 1
            while i < len(lines):
                if re.match(r"^[a-zA-Zа-яА-Я._ ]+$", lines[i]) and lines[i] == subject:
                    i += 1
                    if i < len(lines) and lines[i] and not re.match(r"-?(\d)/(\d)", lines[i]) and not lines[i].startswith("#") and not (re.match(r"^[a-zA-Zа-яА-Я._ ]+$", lines[i]) and not re.match(r"^\d+$", lines[i].strip())):
                        _ = lines[i]
                        i += 1
                    while i < len(lines):
                        if re.match(r"^[a-zA-Zа-яА-Я._ ]+$", lines[i]) and not re.match(r"^\d+$", lines[i].strip()):
                            break
                        group_match = re.match(r"-?(\d)/(\d)", lines[i])
                        if group_match:
                            group_num = group_match.group(1)
                            group_name = ""
                            group_cabinet = ""
                            if i+1 < len(lines) and lines[i+1].startswith("#"):
                                group_name = lines[i+1][1:]
                                i += 1
                            if i+1 < len(lines) and not lines[i+1].startswith("#") and not re.match(r"-?(\d)/(\d)", lines[i+1]):
                                group_cabinet = lines[i+1]
                                i += 1
                            info = f"        группа {group_num}"
                            if group_name:
                                info += f" ({group_name})"
                            if group_cabinet:
                                info += f", кабинет {group_cabinet}"
                            group_lines.append(info)
                            i += 1
                        else:
                            i += 1
                else:
                    break
            if subject:
                line = f"🕒 <b>{hour}</b>: <b>{subject}</b>"
                if cabinet and not group_lines:
                    line += f", кабинет <b>{cabinet}</b>"
                result.append(line)
                if group_lines:
                    result.append(f"<blockquote>{chr(10).join(group_lines)}</blockquote>")
            elif not subject and cabinet:
                result.append(f"🕒 <b>{hour}</b>: кабинет <b>{cabinet}</b>")
    return "\n".join(result) if result else "Нет занятий"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Открыть мини-приложение", web_app=WebAppInfo(url="https://plan-lo2.pl/"))]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Откройте мини-приложение для просмотра расписания.", reply_markup=reply_markup)

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # В боте больше нет кнопок для учителей, только мини-приложение
    await query.edit_message_text("Откройте мини-приложение для просмотра расписания.", reply_markup=InlineKeyboardMarkup([
        [InlineKeyboardButton("Открыть мини-приложение", web_app=WebAppInfo(url="https://plan-lo2.pl/"))]
    ]))

if __name__ == "__main__":
    app = ApplicationBuilder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(button))
    app.run_polling()