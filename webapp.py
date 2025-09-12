from flask import Flask, render_template_string, request
import requests
from bs4 import BeautifulSoup
import re
import os
import pdfplumber

app = Flask(__name__)

PDF_URL = "https://drive.google.com/uc?export=download&id=11L7mjtdGHjuagx9sqvNbvOAEDTF5tQoB"

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

class_title_tag = soup.find(class_="tytulnapis")
current_class = class_title_tag.get_text(strip=True) if class_title_tag else ""

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
                # Исключение: если это wf, всегда добавляем
                if item == "wf":
                    lessons.append(item)
                    continue
                # Фильтр: пропускать инициалы учителей (две буквы)
                if re.fullmatch(r"[A-Za-zА-Яа-я]{2}", item):
                    continue
                lessons.append(item)
            lesson_text = "\n".join(lessons)
            schedule[day][hour] = lesson_text

def download_pdf(url, filename="substitutions.pdf"):
    response = requests.get(url)
    if response.headers.get("Content-Type") not in ["application/pdf", "application/octet-stream"]:
        raise Exception("Скачан не PDF-файл!")
    with open(filename, "wb") as f:
        f.write(response.content)
    return filename

def get_teachers():
    url = "https://dane.ek.zgora.pl/zse/plan/index_n.html"
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")
    teachers = []
    for a in soup.select("a"):
        href = a.get("href")
        name = a.text.strip()
        if href and href.startswith("plany/n") and name:
            teachers.append({"name": name, "url": "https://dane.ek.zgora.pl/zse/plan/" + href})
    return teachers

teachers_list = get_teachers()

def get_filtered_teachers(query):
    return [t for t in teachers_list if query.lower() in t["name"].lower()]

def get_all_classes(pdf_path):
    import re
    classes = set()
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            # Ищем шаблоны типа 8D, 4PU, 3Q2 и т.д.
            found = re.findall(r"\b\d+[A-Z]{1,3}\b", text)
            classes.update(found)
    return sorted(classes)

def parse_teacher_schedule(teacher_url):
    response = requests.get(teacher_url)
    soup = BeautifulSoup(response.content, "html.parser")
    table = soup.find("table", class_="tabela")
    rows = table.find_all("tr")
    header_row = None
    day_map = {
        "понедельник": "Poniedziałek",
        "вторник": "Wtorek",
        "среда": "Środa",
        "четверг": "Czwartek",
        "пятница": "Piątek"
    }
    for row in rows:
        cells = row.find_all(['th', 'td'])
        cell_texts = [cell.get_text(strip=True) for cell in cells]
        if set(day_map.values()).issubset(set(cell_texts)):
            header_row = row
            break
    if not header_row:
        return {}, []
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
                    if item == "wf":
                        lessons.append(item)
                        continue
                    if re.fullmatch(r"[A-Za-zА-Яа-я]{2}", item):
                        continue
                    lessons.append(item)
                lesson_text = "\n".join(lessons)
                schedule[day][hour] = lesson_text
    return schedule, headers

def format_teacher_schedule_day(schedule, day_name):
    result = []
    for hour, lesson in schedule.get(day_name, {}).items():
        if not lesson.strip():
            continue
        lines = [line for line in lesson.split('\n') if line.strip()]
        i = 0
        subject = None
        cabinet = None
        klass = None
        while i < len(lines):
            # Кабинет
            if re.match(r"^\d+\w*$", lines[i]) and not re.match(r"^\d+[A-Z]+$", lines[i]):
                cabinet = lines[i]
                i += 1
                continue
            # Класс
            if re.match(r"^\d+[A-Z]+$", lines[i]):
                klass = lines[i]
                i += 1
                continue
            # Предмет
            if (
                not re.match(r"^\d+[A-Z]+$", lines[i]) and
                not re.match(r"^\d+\w*$", lines[i]) and
                not lines[i].startswith("#") and
                not re.match(r"-?\d/\d", lines[i]) and
                not re.match(r"^s\d+$", lines[i])
            ):
                subject = lines[i]
                i += 1
                continue
            i += 1
        block = f"🕒 <b>{hour}</b>"
        if subject:
            block += f": <b>{subject}</b>"
        if cabinet:
            block += f", кабинет <b>{cabinet}</b>"
        if klass:
            block += f"<br>Класс: <b>{klass}</b>"
        result.append(f"<blockquote>{block}</blockquote>")
    return "<br>".join(result) if result else "Нет занятий"

def extract_substitutions_for_day(class_name, day_name, pdf_path):
    result = []
    current_day = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                # Обновляем текущий день
                if day_name in line:
                    current_day = day_name
                # Если строка содержит класс и текущий день — добавляем
                if current_day == day_name and class_name in line:
                    result.append(line)
    return result

def format_schedule(day_name):
    result = []
    for hour, lesson in schedule[day_name].items():
        if not lesson.strip():
            continue
        lines = [line for line in lesson.split('\n') if line.strip()]
        i = 0
        subject = None
        cabinet = None
        while i < len(lines):
            # Кабинет (номер с буквой, например 104, 104a, 115C, 9m)
            if re.match(r"^\d+\w*$", lines[i]) and not re.match(r"^\d+[A-Z]+$", lines[i]):
                cabinet = lines[i]
                i += 1
                continue
            # Предмет (строка, не кабинет, не группа)
            if (
                not re.match(r"^\d+[A-Z]+$", lines[i]) and
                not re.match(r"^\d+\w*$", lines[i]) and
                not lines[i].startswith("#") and
                not re.match(r"-?\d/\d", lines[i]) and
                not re.match(r"^s\d+$", lines[i])
            ):
                # Любая строка, не распознанная как класс/кабинет/группа, это предмет
                subject = lines[i]
                i += 1
                continue
            # Пропустить все группы и классы
            i += 1

        # Специальная логика для кабинетов по классу
        if current_class == "4PU" and subject:
            subj_norm = subject.replace(" ", "").lower()
            if subj_norm == "j.niem.ii":
                cabinet = "215b"
            elif subj_norm == "j.ang.i":
                cabinet = "103"

        # Форматирование: всё в одной цитате
        block = f"🕒 <b>{hour}</b>"
        if subject:
            block += f": <b>{subject}</b>"
        if cabinet:
            block += f", кабинет <b>{cabinet}</b>"
        if current_class:
            block += f"<br>Класс: <b>{current_class}</b>"
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
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-4">
            <h2 class="mb-4">Расписание</h2>
            <a href="/teachers" class="btn btn-primary mb-3">Поиск по учителям</a>
            <a href="/substitutions" class="btn btn-warning mb-3">Показать замены</a>
            <form method="post" class="mb-4">
                <div class="row g-2 align-items-center">
                    <div class="col-auto">
                        <label for="day" class="form-label mb-0">День недели:</label>
                    </div>
                    <div class="col-auto">
                        <select name="day" id="day" class="form-select">
                            {% for d in headers %}
                                <option value="{{d}}" {% if d == selected_day %}selected{% endif %}>{{d}}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-auto">
                        <button type="submit" class="btn btn-success">Показать</button>
                    </div>
                </div>
            </form>
            <div class="schedule">
                {{schedule_html|safe}}
            </div>
        </div>
    </body>
    </html>
    """, headers=headers, selected_day=selected_day, schedule_html=schedule_html)

@app.route("/teachers", methods=["GET", "POST"])
def teachers():
    results = []
    query = ""
    if request.method == "POST":
        query = request.form.get("search", "").strip()
        results = get_filtered_teachers(query)
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Поиск по учителям</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-4">
            <h2 class="mb-4">Поиск по учителям</h2>
            <form method="post" class="mb-4">
                <div class="input-group">
                    <input type="text" name="search" class="form-control" placeholder="Введите имя или фамилию учителя" value="{{query}}">
                    <button type="submit" class="btn btn-primary">Поиск</button>
                </div>
            </form>
            {% if results %}
                <div class="list-group">
                {% for t in results %}
                    <div class="list-group-item mb-2">
                        <div class="fw-bold mb-2">{{t.name}}</div>
                        <form method="get" action="/teacher_schedule">
                            <input type="hidden" name="url" value="{{t.url}}">
                            <button type="submit" class="btn btn-outline-success">Показать расписание</button>
                        </form>
                    </div>
                {% endfor %}
                </div>
            {% elif query %}
                <div class="alert alert-warning mt-3">Учитель не найден.</div>
            {% endif %}
            <br><a href="/" class="btn btn-secondary">Назад к расписанию класса</a>
        </div>
    </body>
    </html>
    """, results=results, query=query)

@app.route("/teacher_schedule", methods=["GET", "POST"])
def teacher_schedule():
    url = request.args.get("url")
    if not url:
        return "Нет данных"
    schedule, headers = parse_teacher_schedule(url)
    selected_day = headers[0]
    if request.method == "POST":
        selected_day = request.form.get("day", headers[0])
    schedule_html = format_teacher_schedule_day(schedule, selected_day)
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Расписание учителя</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-4">
            <h2 class="mb-4">Расписание учителя</h2>
            <form method="post" class="mb-4">
                <div class="row g-2 align-items-center">
                    <div class="col-auto">
                        <label for="day" class="form-label mb-0">День недели:</label>
                    </div>
                    <div class="col-auto">
                        <select name="day" id="day" class="form-select">
                            {% for d in headers %}
                                <option value="{{d}}" {% if d == selected_day %}selected{% endif %}>{{d}}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-auto">
                        <button type="submit" class="btn btn-success">Показать</button>
                    </div>
                </div>
            </form>
            <div class="schedule">
                {{schedule_html|safe}}
            </div>
            <br><a href="/teachers" class="btn btn-secondary">Назад к поиску</a>
        </div>
    </body>
    </html>
    """, headers=headers, selected_day=selected_day, schedule_html=schedule_html)

def extract_substitutions(class_name, pdf_path):
    day_keywords = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek"]
    result = {day: [] for day in day_keywords}
    current_day = None
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            for line in text.split('\n'):
                for day in day_keywords:
                    if day in line:
                        current_day = day
                if class_name.lower() in line.lower() and current_day:
                    result[current_day].append(line)
    return result

@app.route("/substitutions", methods=["GET", "POST"])
def substitutions():
    error = None
    classes = []
    days = ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek"]
    selected_class = ""
    selected_day = days[0]
    result = []
    try:
        pdf_path = download_pdf(PDF_URL)
        classes = get_all_classes(pdf_path)
    except Exception as e:
        error = str(e)
    if request.method == "POST":
        selected_class = request.form.get("class_name", "")
        selected_day = request.form.get("day_name", days[0])
        try:
            result = extract_substitutions_for_day(selected_class, selected_day, pdf_path)
        except Exception as e:
            error = str(e)
    return render_template_string("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Замены для класса</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    </head>
    <body class="bg-light">
        <div class="container py-4">
            <h2 class="mb-4">Проверить замены для класса и дня</h2>
            <form method="post" class="mb-4">
                <div class="row g-2 align-items-center">
                    <div class="col-auto">
                        <label for="class_name" class="form-label mb-0">Класс:</label>
                    </div>
                    <div class="col-auto">
                        <select name="class_name" id="class_name" class="form-select">
                            {% for c in classes %}
                                <option value="{{c}}" {% if c == selected_class %}selected{% endif %}>{{c}}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-auto">
                        <label for="day_name" class="form-label mb-0">День недели:</label>
                    </div>
                    <div class="col-auto">
                        <select name="day_name" id="day_name" class="form-select">
                            {% for d in days %}
                                <option value="{{d}}" {% if d == selected_day %}selected{% endif %}>{{d}}</option>
                            {% endfor %}
                        </select>
                    </div>
                    <div class="col-auto">
                        <button type="submit" class="btn btn-primary">Показать замены</button>
                    </div>
                </div>
            </form>
            {% if error %}
                <div class="alert alert-danger mt-3">Ошибка: {{error}}</div>
            {% endif %}
            {% if result %}
                <ul class="list-group mb-3">
                {% for item in result %}
                    <li class="list-group-item">{{item}}</li>
                {% endfor %}
                </ul>
            {% elif selected_class and selected_day and not error %}
                <div class="alert alert-warning mt-3">Нет замен для выбранного класса и дня.</div>
            {% endif %}
            <br><a href="/" class="btn btn-secondary">Назад</a>
        </div>
    </body>
    </html>
    """, classes=classes, days=days, selected_class=selected_class, selected_day=selected_day, result=result, error=error)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)