from flask import Flask, render_template_string, request
import requests
from bs4 import BeautifulSoup
import re
import os

app = Flask(__name__)

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
        klass = None
        subject = None
        cabinet = None
        while i < len(lines):
            # Название группы вместо предмета (строка начинается с #)
            if lines[i].startswith("#"):
                subject = lines[i][1:]
                i += 1
                continue
            # Класс (например, 3PD, 4PU, 7B, 8C, 6A, 6D)
            if re.match(r"^\d+[A-Z]+$", lines[i]):
                klass = lines[i]
                i += 1
                continue
            # Кабинет (номер с буквой, например 104, 104a, 115C, 9m)
            if re.match(r"^\d+\w*$", lines[i]) and not re.match(r"^\d+[A-Z]+$", lines[i]):
                cabinet = lines[i]
                i += 1
                continue
            # Предмет
            if not re.match(r"^\d+[A-Z]+$", lines[i]) and not re.match(r"^\d+\w*$", lines[i]) and not lines[i].startswith("#"):
                subject = lines[i]
                i += 1
                continue
            i += 1
        # Форматирование: всё в одной цитате
        block = f"🕒 <b>{hour}</b>"
        if subject:
            block += f": <b>{subject}</b>"
        if cabinet:
            block += f", кабинет <b>{cabinet}</b>"
        if klass:
            block += f"<br>Класс: <b>{klass}</b>"
        result.append(f"<blockquote>{block}</blockquote>")
    return "<br>".join(result) if result else "Нет занятий"

@app.route("/", methods=["GET", "POST"])
def index():
    selected_day = headers[0]
    if request.method == "POST":
        selected_day = request.form.get("day", headers[0])
    schedule_html = format_schedule(selected_day)
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Расписание</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <script src="https://telegram.org/js/telegram-web-app.js"></script>
        <style>
            body { font-family: Arial, sans-serif; background: #f7f7f7; }
            .container { max-width: 600px; margin: 30px auto; background: #fff; padding: 20px; border-radius: 10px; }
            select, button { font-size: 1em; padding: 5px 10px; margin: 10px 0; }
            .schedule { margin-top: 20px; }
            blockquote { background: #eee; border-left: 4px solid #888; margin: 8px 0; padding: 8px 16px; border-radius: 6px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h2>Расписание</h2>
            <form method="post">
                <label for="day">День недели:</label>
                <select name="day" id="day">
                    {% for d in headers %}
                        <option value="{{d}}" {% if d == selected_day %}selected{% endif %}>{{d}}</option>
                    {% endfor %}
                </select>
                <button type="submit">Показать</button>
            </form>
            <div class="schedule">
                {{schedule_html|safe}}
            </div>
        </div>
    </body>
    </html>
    """, headers=headers, selected_day=selected_day, schedule_html=schedule_html)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)