"""Kalender-, Aggregations- und Auswertungslogik (UI-unabhängig, testbar)."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import holidays as _hol
import pandas as pd

MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
WOTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

PROJEKT_ARTEN = ("Vor Ort", "Remote")
INTERN_ARTEN = ("Intern", "Akquise")
ABWESEND_ARTEN = ("Urlaub", "Krank")
SONST_ARTEN = INTERN_ARTEN + ABWESEND_ARTEN

RHYTHMEN = {"Jede Woche": 1, "Alle 2 Wochen": 2, "Alle 3 Wochen": 3, "Alle 4 Wochen": 4}

GRANULARITAETEN = {
    "Hybrid": "Hybrid: Wochen bis Ende Folgemonat, danach Monate",
    "Tag": "Tag",
    "Woche": "Woche",
    "Monat": "Monat",
}


# ---------------------------------------------------------------- Kalender
@lru_cache(maxsize=16)
def feiertage(year: int) -> dict:
    """Gesetzliche Feiertage Bayern."""
    return dict(_hol.Germany(subdiv="BY", years=year))


def feiertag_name(d: dt.date) -> str | None:
    return feiertage(d.year).get(d)


def workdays(start: dt.date, end: dt.date) -> list[dt.date]:
    out, d = [], start
    while d <= end:
        if d.weekday() < 5 and d not in feiertage(d.year):
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def plan_days(von: dt.date, bis: dt.date, wochentage: list[str], rhythmus: int = 1) -> list[dt.date]:
    """Arbeitstage im Zeitraum, gefiltert nach Wochentagen und Wochenrhythmus.
    Rhythmus 2 = Startwoche, dann jede zweite Woche usw. Feiertage Bayern sind ausgenommen."""
    if von > bis:
        return []
    base = monday(von)
    return [d for d in workdays(von, bis)
            if WOTAG[d.weekday()] in wochentage and ((monday(d) - base).days // 7) % max(rhythmus, 1) == 0]


def monday(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def month_start(d: dt.date, add: int = 0) -> dt.date:
    m = d.month - 1 + add
    return dt.date(d.year + m // 12, m % 12 + 1, 1)


def month_end(d: dt.date, add: int = 0) -> dt.date:
    return month_start(d, add + 1) - dt.timedelta(days=1)


def day_label(d: dt.date) -> str:
    return f"{WOTAG[d.weekday()]} {d:%d.%m.}"


def week_label(d: dt.date) -> str:
    return f"KW {d.isocalendar().week:02d}"


def month_label(d: dt.date) -> str:
    return f"{MONATE[d.month - 1]} {d:%y}"


def period(d: dt.date, gran: str, today: dt.date) -> tuple[dt.date, str]:
    """Ordnet einen Tag einer Periode zu: (Periodenstart, Label)."""
    if gran == "Tag":
        return d, day_label(d)
    if gran == "Woche":
        m = monday(d)
        return m, week_label(m)
    if gran == "Monat":
        m = month_start(d)
        return m, month_label(m)
    # Hybrid: aktueller + Folgemonat auf Wochenebene, danach Monate
    cutoff = month_start(today, 2)
    m = monday(d)
    if m < cutoff:
        return m, week_label(m)
    ms = month_start(d)
    return ms, month_label(ms)


# ---------------------------------------------------------------- Faktentabelle
FACT_COLS = ["consultant_id", "name", "tag", "art", "project_id",
             "kapazitaet", "projekt", "vor_ort", "intern", "frei"]


def build_fact(start: dt.date, end: dt.date, cons: pd.DataFrame, book: pd.DataFrame) -> pd.DataFrame:
    """Ein Datensatz je Berater und Arbeitstag, inkl. Kennzahlen 0/1."""
    days = workdays(start, end)
    if cons.empty or not days:
        return pd.DataFrame(columns=FACT_COLS)
    grid = pd.MultiIndex.from_product([cons["id"].tolist(), days],
                                      names=["consultant_id", "tag"]).to_frame(index=False)
    grid = grid.merge(cons[["id", "name"]].rename(columns={"id": "consultant_id"}), on="consultant_id")
    if book.empty:
        b = pd.DataFrame(columns=["consultant_id", "tag", "art", "project_id"])
    else:
        b = book[["consultant_id", "tag", "art", "project_id"]]
    f = grid.merge(b, on=["consultant_id", "tag"], how="left")
    f["kapazitaet"] = (~f["art"].isin(ABWESEND_ARTEN)).astype(int)
    f["projekt"] = f["art"].isin(PROJEKT_ARTEN).astype(int)
    f["vor_ort"] = (f["art"] == "Vor Ort").astype(int)
    f["intern"] = f["art"].isin(INTERN_ARTEN).astype(int)
    f["frei"] = f["kapazitaet"] - f["projekt"] - f["intern"]
    return f[FACT_COLS]


def aggregate(f: pd.DataFrame, gran: str, today: dt.date, by_consultant: bool = True) -> pd.DataFrame:
    if f.empty:
        return pd.DataFrame()
    per = [period(d, gran, today) for d in f["tag"]]
    f = f.assign(p_start=[p[0] for p in per], p_label=[p[1] for p in per])
    keys = ["p_start", "p_label"] + (["name"] if by_consultant else [])
    g = f.groupby(keys, as_index=False)[["kapazitaet", "projekt", "vor_ort", "intern", "frei"]].sum()
    kap = g["kapazitaet"].where(g["kapazitaet"] > 0)
    g["auslastung"] = g["projekt"] / kap
    g["vor_ort_quote"] = g["vor_ort"] / kap
    return g.sort_values(keys).reset_index(drop=True)


def kpi(f: pd.DataFrame, col: str = "projekt") -> float | None:
    if f.empty or f["kapazitaet"].sum() == 0:
        return None
    return f[col].sum() / f["kapazitaet"].sum()


# ---------------------------------------------------------------- Projekte
def project_stats(proj: pd.DataFrame, bk: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Budget vs. verbraucht vs. eingeplant je Projekt."""
    df = proj.copy()
    if bk.empty:
        for c in ["verbraucht", "eingeplant", "vor_ort", "gesamt"]:
            df[c] = 0
        df["letzte"] = pd.NaT
        df["team"] = ""
    else:
        b = bk[bk["project_id"].notna() & bk["art"].isin(PROJEKT_ARTEN)].copy()
        b["project_id"] = b["project_id"].astype(int)
        b["vergangen"] = b["tag"] <= today
        agg = b.groupby("project_id").agg(
            verbraucht=("vergangen", "sum"),
            gesamt=("tag", "count"),
            vor_ort=("art", lambda s: int((s == "Vor Ort").sum())),
            letzte=("tag", "max"),
            team=("name", lambda s: ", ".join(sorted(s.unique()))),
        )
        df = df.merge(agg, left_on="id", right_index=True, how="left")
        for c in ["verbraucht", "gesamt", "vor_ort"]:
            df[c] = df[c].fillna(0).astype(int)
        df["team"] = df["team"].fillna("")
        df["eingeplant"] = df["gesamt"] - df["verbraucht"]
    df["budget_tage"] = df["budget_tage"].fillna(0)
    df["ungeplant"] = df["budget_tage"] - df["verbraucht"] - df["eingeplant"]
    df["fortschritt"] = (df["verbraucht"] / df["budget_tage"].where(df["budget_tage"] > 0)).fillna(0)

    def status(r):
        if r["budget_tage"] <= 0:
            return "Kein Budget"
        if r["ungeplant"] < 0:
            return "Überplant"
        if r["ungeplant"] > 0:
            return "Rest ungeplant"
        return "Voll eingeplant"

    df["status"] = df.apply(status, axis=1)
    return df
