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
                    result.append(f"<blockquote>{'<br>'.join(group_lines)}</blockquote>")
            elif not subject and cabinet:
                result.append(f"🕒 <b>{hour}</b>: кабинет <b>{cabinet}</b>")
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