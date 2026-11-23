"""Собирает data.json для сайта.

Источник:
  - если задан GOOGLE_SERVICE_ACCOUNT (JSON ключ) и SHEET_ID, данные берутся
    из закрытой Google Таблицы через сервисный аккаунт (лист «Стихи»);
  - иначе из локального CSV (python scripts/build_data.py путь/к/файлу.csv).
Столбцы: Категория, Грех, Ссылка, Текст стиха.
"""
import csv, json, os, sys, datetime

def rows_from_sheet():
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s = AuthorizedSession(creds)
    sheet = os.environ.get("SHEET_NAME", "Стихи")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{os.environ['SHEET_ID']}/values/{sheet}"
    r = s.get(url, params={"valueRenderOption": "FORMATTED_VALUE"})
    r.raise_for_status()
    return r.json().get("values", [])

def rows_from_csv(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.reader(f))

def build(rows):
    header = [h.strip() for h in rows[0]]
    idx = {name: header.index(name) for name in ["Категория", "Грех", "Ссылка", "Текст стиха"]}
    cats = {}
    for row in rows[1:]:
        row = row + [""] * (len(header) - len(row))
        c, g, ref, text = (row[idx[k]].strip() for k in ["Категория", "Грех", "Ссылка", "Текст стиха"])
        if not (c and g and ref and text):
            continue
        cats.setdefault(c, {}).setdefault(g, []).append([ref, text])
    total = sum(len(v) for s in cats.values() for v in s.values())
    if total < 100:
        sys.exit(f"Слишком мало стихов ({total}), сайт не обновляю")
    return {
        "updated": datetime.date.today().isoformat(),
        "categories": [
            {"name": c, "sins": [{"name": g, "verses": v} for g, v in sins.items()]}
            for c, sins in cats.items()
        ],
    }

if __name__ == "__main__":
    rows = rows_from_csv(sys.argv[1]) if len(sys.argv) > 1 else rows_from_sheet()
    data = build(rows)
    with open("data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    n = sum(len(s["verses"]) for c in data["categories"] for s in c["sins"])
    print(f"Готово: {len(data['categories'])} категорий, "
          f"{sum(len(c['sins']) for c in data['categories'])} грехов, {n} стихов")
