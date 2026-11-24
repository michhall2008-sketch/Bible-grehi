"""Собирает data.json (русский) и data-sk.json (словацкий) для сайта.

Источник:
  - если задан GOOGLE_SERVICE_ACCOUNT (JSON ключ) и SHEET_ID, данные берутся
    из закрытой Google Таблицы через сервисный аккаунт:
      «Стихи» + «Словарь»          -> data.json
      «Verše SK» + «Slovník SK»    -> data-sk.json
  - иначе из локальных файлов:
      python scripts/build_data.py стихи.csv [slovak.xlsx]
    (русский словарь берётся из scripts/slovar.tsv, словацкие листы из xlsx).
Столбец «Для пастора» на сайт НЕ попадает никогда.
"""
import csv, json, os, sys, datetime
from urllib.parse import quote

TODAY = datetime.date.today().isoformat()

RU = dict(verses=("Категория", "Грех", "Ссылка", "Текст стиха", None),
          slovar=("Грех", "Что это значит", "Пример из жизни"), syn="Синонимы")
SK = dict(verses=("Kategória", "Hriech", "Odkaz", "Text verša", "Odkaz na mojabiblia.sk"),
          slovar=("Hriech", "Čo to znamená", "Príklad zo života"), syn="Synonymá")
# Необязательный столбец синонимов в листе словаря: слова и фразы через запятую, для поиска на сайте.


def sheet_rows(sheet):
    from google.oauth2 import service_account
    from google.auth.transport.requests import AuthorizedSession
    info = json.loads(os.environ["GOOGLE_SERVICE_ACCOUNT"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"])
    s = AuthorizedSession(creds)
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{os.environ['SHEET_ID']}/values/{quote(sheet)}"
    r = s.get(url, params={"valueRenderOption": "FORMATTED_VALUE"})
    r.raise_for_status()
    return r.json().get("values", [])


def xlsx_rows(path, sheet):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    return [["" if v is None else str(v) for v in r] for r in wb[sheet].iter_rows(values_only=True)]


def tsv_rows(path):
    with open(path, encoding="utf-8") as f:
        return [line.rstrip("\n").split("\t") for line in f if line.strip()]


def csv_rows(path):
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def build(rows, slovar, cols):
    vc, sc = cols["verses"], cols["slovar"]
    meaning, syn = {}, {}
    if slovar:
        h = [x.strip() for x in slovar[0]]
        gi, mi, ei = (h.index(n) for n in sc)
        si = h.index(cols["syn"]) if cols["syn"] in h else None
        for r in slovar[1:]:
            r = r + [""] * (len(h) - len(r))
            g = r[gi].strip()
            if not g:
                continue
            if r[mi].strip():
                meaning[g] = (r[mi].strip(), r[ei].strip())
            if si is not None:
                words = [w.strip() for w in r[si].split(",") if w.strip()]
                if words:
                    syn[g] = words
    header = [h.strip() for h in rows[0]]
    idx = [header.index(n) if n else None for n in vc]
    cats = {}
    for row in rows[1:]:
        row = row + [""] * (len(header) - len(row))
        c, g, ref, text = (row[i].strip() for i in idx[:4])
        if not (c and g and ref and text):
            continue
        v = [ref, text]
        if idx[4] is not None and row[idx[4]].strip():
            v.append(row[idx[4]].strip())
        cats.setdefault(c, {}).setdefault(g, []).append(v)
    total = sum(len(v) for s in cats.values() for v in s.values())
    if total < 100:
        raise ValueError(f"Слишком мало стихов ({total})")
    return {
        "updated": TODAY,
        "categories": [
            {"name": c, "sins": [dict({"name": g, "verses": v},
                                      **({"meaning": meaning[g][0], "example": meaning[g][1]} if g in meaning else {}),
                                      **({"syn": syn[g]} if g in syn else {}))
                                 for g, v in sins.items()]}
            for c, sins in cats.items()
        ],
    }


def save(data, path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
    n = sum(len(s["verses"]) for c in data["categories"] for s in c["sins"])
    m = sum(1 for c in data["categories"] for s in c["sins"] if "meaning" in s)
    print(f"{path}: {len(data['categories'])} категорий, "
          f"{sum(len(c['sins']) for c in data['categories'])} грехов, {n} стихов, {m} пояснений")


if __name__ == "__main__":
    here = os.path.dirname(__file__)
    if len(sys.argv) > 1:
        save(build(csv_rows(sys.argv[1]), tsv_rows(os.path.join(here, "slovar.tsv")), RU), "data.json")
        if len(sys.argv) > 2:
            save(build(xlsx_rows(sys.argv[2], "Verše SK"), xlsx_rows(sys.argv[2], "Slovník SK"), SK), "data-sk.json")
        sys.exit(0)

    # Русский обязателен: если не получилось, сайт не трогаем.
    try:
        ru_slovar = sheet_rows("Словарь")
    except Exception as e:
        print("Лист «Словарь» не прочитан, беру scripts/slovar.tsv:", e)
        ru_slovar = tsv_rows(os.path.join(here, "slovar.tsv"))
    try:
        save(build(sheet_rows(os.environ.get("SHEET_NAME", "Стихи")), ru_slovar, RU), "data.json")
    except ValueError as e:
        sys.exit(f"{e}, сайт не обновляю")

    # Словацкий: при ошибке оставляем прежний data-sk.json.
    try:
        save(build(sheet_rows("Verše SK"), sheet_rows("Slovník SK"), SK), "data-sk.json")
    except Exception as e:
        print("Словацкие листы не обновлены, оставляю прежний data-sk.json:", e)
