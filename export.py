"""Excel-Export der Planung im gewohnten Format (Rolling Forecast).
Blatt 'Tage': Mitarbeiter x Projekt x Arbeitstag, Kopf mit Monat / KW / Datum.
Blatt 'Wochen': gleiche Zeilen, Summe je KW plus Auslastung.
Blatt 'Projekte': Budget, gebucht, geplant, offen je Projekt und Berater."""
from __future__ import annotations

import datetime as dt
import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter as L

import logic

NAVY, MID, LIGHT, LILAC, GREY, XL = "000055", "6688BB", "BBCCEE", "E4E4F6", "999999", "EBEBEB"
ALERT = "B3261E"
F_HEAD = Font(name="Calibri", bold=True, color="FFFFFF", size=10)
F_BOLD = Font(name="Calibri", bold=True, color=NAVY, size=10)
F_TXT = Font(name="Calibri", color=NAVY, size=10)
F_RED = Font(name="Calibri", bold=True, color=ALERT, size=10)
FILL = {k: PatternFill("solid", fgColor=v) for k, v in
        {"navy": NAVY, "mid": MID, "light": LIGHT, "lilac": LILAC, "xl": XL, "hol": "D9D9D9", "white": "FFFFFF"}.items()}
THIN = Side(style="thin", color="D2D2D2")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober",
          "November", "Dezember"]
H = logic.TAG_H


def _rows(cons: pd.DataFrame, projn: pd.DataFrame, ent: pd.DataFrame, mem: pd.DataFrame) -> list[dict]:
    """Zeilenstruktur: je Mitarbeiter seine Projekte (Budget oder Einträge), dann Intern / Abwesenheiten."""
    out = []
    for c in cons.itertuples():
        e = ent[ent["consultant_id"] == c.id] if not ent.empty else ent
        pids = set(mem.loc[mem["consultant_id"] == c.id, "project_id"]) if not mem.empty else set()
        if not e.empty:
            pids |= set(e.loc[e["project_id"].notna(), "project_id"].astype(int))
        pids = [p for p in pids if p in projn.index]
        pids.sort(key=lambda p: projn.at[p, "label"].lower())
        rows = [{"cid": c.id, "pid": p, "art": None, "label": projn.at[p, "label"]} for p in pids]
        arts = [a for a in list(logic.INTERN_ARTEN) + list(logic.ABWESEND_ARTEN)
                if not e.empty and (e["art"] == a).any()]
        for a in ["Intern", "Urlaub"] + [x for x in arts if x not in ("Intern", "Urlaub")]:
            rows.append({"cid": c.id, "pid": None, "art": a, "label": a})
        out.append({"cid": c.id, "kz": c.name, "name": (c.vollname if isinstance(c.vollname, str) and c.vollname
                                                         else c.name), "rows": rows})
    return out


def build_excel(cons: pd.DataFrame, projn: pd.DataFrame, ent: pd.DataFrame, mem: pd.DataFrame,
                start: dt.date, end: dt.date, today: dt.date, titel: str = "AUSLASTUNG") -> bytes:
    days = [d for d in pd.date_range(start, end).date if d.weekday() < 5]
    weeks = sorted({logic.monday(d) for d in days})
    ms = logic.member_stats(ent, mem, today).set_index(["project_id", "consultant_id"]) if not mem.empty or not ent.empty \
        else pd.DataFrame()
    e = ent.copy()
    if not e.empty:
        e["key"] = [f"p{int(p)}" if pd.notna(p) else a for p, a in zip(e["project_id"], e["art"])]
    cell_h = e.groupby(["consultant_id", "key", "tag"])["stunden"].sum().to_dict() if not e.empty else {}
    cell_art = e.groupby(["consultant_id", "key", "tag"])["art"].first().to_dict() if not e.empty else {}
    people = _rows(cons, projn, ent, mem)

    wb = Workbook()
    # ------------------------------------------------------------------ Blatt Tage
    ws = wb.active
    ws.title = "Tage"
    first = 6  # erste Datenspalte (A Mitarbeiter, B Projekt, C Budget, D Offen, E Summe)
    ws["A1"] = f"{titel} | Rolling Forecast"
    ws["A1"].font = Font(name="Calibri", bold=True, size=14, color=NAVY)
    ws["A2"] = f"Stand {today:%d.%m.%Y} · Aktuelle KW {today.isocalendar().week} · Werte in Beratertagen (1 = 8 h)"
    ws["A2"].font = Font(name="Calibri", italic=True, size=10, color=MID)
    hdr = ["Mitarbeiter", "Projekt / Tätigkeit", "Budget BT", "Offen BT", "Σ Zeitraum"]
    for i, h in enumerate(hdr, start=1):
        ws.merge_cells(start_row=4, start_column=i, end_row=6, end_column=i)
        c = ws.cell(4, i, h)
        c.font, c.fill, c.alignment = F_HEAD, FILL["navy"], Alignment(horizontal="center", vertical="center", wrap_text=True)
    col_of = {}
    for j, d in enumerate(days):
        col = first + j
        col_of[d] = col
        c = ws.cell(6, col, d)
        c.number_format = "DD.MM."
        c.font, c.fill = F_HEAD, FILL["mid"]
        c.alignment = Alignment(horizontal="center", text_rotation=90)
        ws.column_dimensions[L(col)].width = 4.2
    # Monats- und KW-Köpfe (verbunden)
    for key_fn, row, fill in ((lambda d: (d.year, d.month), 4, "navy"),
                              (lambda d: logic.monday(d), 5, "mid")):
        j = 0
        while j < len(days):
            k = key_fn(days[j])
            k2 = j
            while k2 + 1 < len(days) and key_fn(days[k2 + 1]) == k:
                k2 += 1
            if k2 > j:
                ws.merge_cells(start_row=row, start_column=first + j, end_row=row, end_column=first + k2)
            txt = f"{MONATE[k[1] - 1]} {k[0]}" if row == 4 else f"KW {k.isocalendar().week}"
            c = ws.cell(row, first + j, txt)
            c.font, c.fill, c.alignment = F_HEAD, FILL[fill], Alignment(horizontal="center")
            j = k2 + 1
    r = 7
    for p in people:
        # Kopfzeile Mitarbeiter: Summe gebuchter Tage je Tag (rot bei Überbuchung)
        ws.cell(r, 1, p["name"]).font = F_BOLD
        ws.cell(r, 2, f"Summe ({p['kz']})").font = F_BOLD
        tot_period = 0.0
        for d, col in col_of.items():
            if logic.feiertag_name(d):
                c = ws.cell(r, col, "x")
                c.fill = FILL["hol"]
                continue
            h = sum(v for (cid, key, tag), v in cell_h.items() if cid == p["cid"] and tag == d)
            if h:
                c = ws.cell(r, col, round(h / H, 2))
                c.font = F_RED if h > H + 1e-9 else F_BOLD
                tot_period += h / H
        ws.cell(r, 5, round(tot_period, 2)).font = F_BOLD
        for col in range(1, first + len(days)):
            ws.cell(r, col).fill = FILL["lilac"] if ws.cell(r, col).value != "x" else FILL["hol"]
            ws.cell(r, col).border = BOX
        r += 1
        for row in p["rows"]:
            key = f"p{row['pid']}" if row["pid"] is not None else row["art"]
            ws.cell(r, 2, row["label"]).font = F_TXT
            if row["pid"] is not None and not ms.empty and (row["pid"], p["cid"]) in ms.index:
                b = ms.loc[(row["pid"], p["cid"])]
                ws.cell(r, 3, round(float(b["budget"]), 1)).font = F_TXT
                c = ws.cell(r, 4, round(float(b["offen"]), 1))
                c.font = F_RED if b["offen"] < -0.01 else F_TXT
            tot = 0.0
            for d, col in col_of.items():
                c = ws.cell(r, col)
                c.border = BOX
                if logic.feiertag_name(d):
                    c.value, c.fill = "x", FILL["hol"]
                    continue
                h = cell_h.get((p["cid"], key, d), 0.0)
                if h:
                    c.value = round(h / H, 2)
                    art = cell_art.get((p["cid"], key, d))
                    c.fill = FILL["lilac"] if art == "Vor Ort" else FILL["white"] if art == "Remote" else FILL["xl"]
                    c.font = F_TXT
                    tot += h / H
            ws.cell(r, 5, round(tot, 2)).font = F_TXT
            for col in range(1, 6):
                ws.cell(r, col).border = BOX
            r += 1
        r += 1
    for col, w in zip("ABCDE", (22, 42, 10, 10, 10)):
        ws.column_dimensions[col].width = w
    for col in (3, 4, 5):
        for rr in range(7, r):
            ws.cell(rr, col).number_format = "0.0"
    ws.freeze_panes = ws.cell(7, first)
    ws.cell(r + 1, 1, "Legende:").font = F_BOLD
    for i, (t, f) in enumerate((("Vor Ort", "lilac"), ("Remote", "white"), ("Intern / Abwesend", "xl"),
                                ("Feiertag (x)", "hol"))):
        c = ws.cell(r + 1, 2 + i, t)
        c.fill, c.border, c.font = FILL[f], BOX, F_TXT
    ws.cell(r + 2, 1, "Rote Werte = überbucht (mehr als 1 Tag bzw. 8 h) · Offen negativ = mehr geplant als budgetiert").font = \
        Font(name="Calibri", italic=True, size=9, color=MID)

    # ------------------------------------------------------------------ Blatt Wochen
    w2 = wb.create_sheet("Wochen")
    w2["A1"] = f"{titel} | Wochenübersicht (Beratertage)"
    w2["A1"].font = Font(name="Calibri", bold=True, size=14, color=NAVY)
    heads = ["Mitarbeiter", "Projekt / Tätigkeit"] + [f"KW {w.isocalendar().week}\n{w:%d.%m.}" for w in weeks]
    for i, h in enumerate(heads, start=1):
        c = w2.cell(3, i, h)
        c.font, c.fill = F_HEAD, FILL["navy"]
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        if i > 2:
            w2.column_dimensions[L(i)].width = 8
    w2.row_dimensions[3].height = 30
    fact = logic.build_fact(start, end, cons, ent)
    r = 4
    for p in people:
        w2.cell(r, 1, p["name"]).font = F_BOLD
        w2.cell(r, 2, "Auslastung").font = F_BOLD
        f = fact[fact["consultant_id"] == p["cid"]]
        for i, w in enumerate(weeks):
            fw = f[f["tag"].map(logic.monday) == w]
            u = logic.kpi(fw)
            c = w2.cell(r, 3 + i, u if u is not None else "")
            c.number_format = "0%"
            c.font = F_RED if (u or 0) > 1.0001 else F_BOLD
            c.fill, c.border = FILL["lilac"], BOX
        w2.cell(r, 1).fill = w2.cell(r, 2).fill = FILL["lilac"]
        r += 1
        for row in p["rows"]:
            key = f"p{row['pid']}" if row["pid"] is not None else row["art"]
            w2.cell(r, 2, row["label"]).font = F_TXT
            for i, w in enumerate(weeks):
                h = sum(cell_h.get((p["cid"], key, w + dt.timedelta(days=k)), 0.0) for k in range(5))
                c = w2.cell(r, 3 + i, round(h / H, 2) if h else None)
                c.number_format, c.border, c.font = "0.0", BOX, F_TXT
            r += 1
        r += 1
    w2.column_dimensions["A"].width, w2.column_dimensions["B"].width = 22, 42
    w2.freeze_panes = "C4"

    # ------------------------------------------------------------------ Blatt Projekte
    w3 = wb.create_sheet("Projekte")
    w3["A1"] = f"{titel} | Projekte und Budgets (Beratertage)"
    w3["A1"].font = Font(name="Calibri", bold=True, size=14, color=NAVY)
    heads = ["Kunde", "Projekt", "Berater", "Budget BT", "Gebucht bis heute", "Geplant ab morgen", "Offen BT",
             "Start", "Ende"]
    for i, h in enumerate(heads, start=1):
        c = w3.cell(3, i, h)
        c.font, c.fill = F_HEAD, FILL["navy"]
    stats = logic.project_stats(projn.reset_index(), ent, mem, today)
    cmap = dict(zip(cons["id"], cons["name"]))
    r = 4
    for s in stats.sort_values(["kunde", "name"]).itertuples():
        vals = [s.kunde, s.name if s.name != s.kunde else "", "Gesamt", s.budget, s.gebucht, s.geplant, s.offen,
                s.start if pd.notna(s.start) else None, s.ende if pd.notna(s.ende) else None]
        for i, v in enumerate(vals, start=1):
            c = w3.cell(r, i, v)
            c.font, c.fill, c.border = F_BOLD, FILL["lilac"], BOX
        w3.cell(r, 7).font = F_RED if s.offen < -0.01 else F_BOLD
        r += 1
        if not ms.empty:
            sub = ms.reset_index()
            for m in sub[sub["project_id"] == s.id].itertuples():
                vals = ["", "", cmap.get(m.consultant_id, ""), m.budget, m.gebucht, m.geplant, m.offen]
                for i, v in enumerate(vals, start=1):
                    c = w3.cell(r, i, v)
                    c.font, c.border = F_TXT, BOX
                w3.cell(r, 7).font = F_RED if m.offen < -0.01 else F_TXT
                r += 1
    for col, w in zip("ABCDEFGHI", (26, 34, 10, 11, 16, 16, 10, 12, 12)):
        w3.column_dimensions[col].width = w
    for rr in range(4, r):
        for col in (4, 5, 6, 7):
            w3.cell(rr, col).number_format = "0.0"
        for col in (8, 9):
            w3.cell(rr, col).number_format = "DD.MM.YYYY"
    w3.freeze_panes = "A4"

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
