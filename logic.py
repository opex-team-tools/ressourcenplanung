"""Kalender-, Aggregations- und Auswertungslogik (UI-unabhängig, testbar)."""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import holidays as _hol
import pandas as pd

MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
WOTAG = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]

TAG_H = 8.0  # 8 Stunden = 1 Beratertag = 100 %
PROJEKT_ARTEN = ("Vor Ort", "Remote")
INTERN_ARTEN = ("Intern", "Akquise")
ABWESEND_ARTEN = ("Urlaub", "Krank", "Elternzeit")
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


# ---------------------------------------------------------------- Faktentabelle (Stunden)
FACT_COLS = ["consultant_id", "name", "tag", "kapazitaet", "projekt", "vor_ort", "intern", "abwesend",
             "gebucht", "frei"]
_HCOLS = ["projekt", "vor_ort", "intern", "abwesend"]


def build_fact(start: dt.date, end: dt.date, cons: pd.DataFrame, ent: pd.DataFrame) -> pd.DataFrame:
    """Ein Datensatz je Berater und Arbeitstag, alle Werte in Stunden.
    Kapazität = 8 h minus Abwesenheit. Mehr als 8 h gebucht = überbucht (frei bleibt 0)."""
    days = workdays(start, end)
    if cons.empty or not days:
        return pd.DataFrame(columns=FACT_COLS)
    grid = pd.MultiIndex.from_product([cons["id"].tolist(), days],
                                      names=["consultant_id", "tag"]).to_frame(index=False)
    grid = grid.merge(cons[["id", "name"]].rename(columns={"id": "consultant_id"}), on="consultant_id")
    if ent is None or ent.empty:
        f = grid.assign(**{c: 0.0 for c in _HCOLS})
    else:
        e = ent[["consultant_id", "tag", "art", "stunden"]].copy()
        h = e["stunden"].astype(float)
        e["projekt"] = h.where(e["art"].isin(PROJEKT_ARTEN), 0.0)
        e["vor_ort"] = h.where(e["art"] == "Vor Ort", 0.0)
        e["intern"] = h.where(e["art"].isin(INTERN_ARTEN), 0.0)
        e["abwesend"] = h.where(e["art"].isin(ABWESEND_ARTEN), 0.0)
        agg = e.groupby(["consultant_id", "tag"], as_index=False)[_HCOLS].sum()
        f = grid.merge(agg, on=["consultant_id", "tag"], how="left")
        f[_HCOLS] = f[_HCOLS].fillna(0.0)
    f["kapazitaet"] = (TAG_H - f["abwesend"]).clip(lower=0)
    f["gebucht"] = f["projekt"] + f["intern"]
    f["frei"] = (f["kapazitaet"] - f["gebucht"]).clip(lower=0)
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
    g["frei_tage"] = g["frei"] / TAG_H
    return g.sort_values(keys).reset_index(drop=True)


def kpi(f: pd.DataFrame, col: str = "projekt") -> float | None:
    if f.empty or f["kapazitaet"].sum() == 0:
        return None
    return f[col].sum() / f["kapazitaet"].sum()


# ---------------------------------------------------------------- Projekte & Budgets (Beratertage)
def member_stats(ent: pd.DataFrame, mem: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Je Projekt und Berater: Budget, gebucht (bis heute), geplant (ab morgen), offen. Alles in BT."""
    cols = ["project_id", "consultant_id", "budget", "gebucht", "geplant", "offen"]
    pe = ent[ent["project_id"].notna() & ent["art"].isin(PROJEKT_ARTEN)].copy() if not ent.empty else ent
    if pe is not None and not pe.empty:
        pe["project_id"] = pe["project_id"].astype(int)
        pe["vergangen"] = pe["tag"] <= today
        g = pe.groupby(["project_id", "consultant_id"]).apply(
            lambda x: pd.Series({"gebucht": x.loc[x["vergangen"], "stunden"].sum() / TAG_H,
                                 "geplant": x.loc[~x["vergangen"], "stunden"].sum() / TAG_H}),
            include_groups=False).reset_index()
    else:
        g = pd.DataFrame(columns=["project_id", "consultant_id", "gebucht", "geplant"])
    m = mem[["project_id", "consultant_id", "budget_tage"]].rename(columns={"budget_tage": "budget"}) \
        if not mem.empty else pd.DataFrame(columns=["project_id", "consultant_id", "budget"])
    for d in (g, m):
        for c in ("project_id", "consultant_id"):
            d[c] = d[c].astype(int)
    out = m.merge(g, on=["project_id", "consultant_id"], how="outer")
    for c in ("budget", "gebucht", "geplant"):
        out[c] = pd.to_numeric(out[c]).fillna(0.0).astype(float)
    out["offen"] = out["budget"] - out["gebucht"] - out["geplant"]
    return out[cols] if not out.empty else pd.DataFrame(columns=cols)


def project_stats(proj: pd.DataFrame, ent: pd.DataFrame, mem: pd.DataFrame, today: dt.date) -> pd.DataFrame:
    """Je Projekt: Budget (Summe der Beraterbudgets), gebucht, geplant, offen, Team."""
    df = proj.copy()
    ms = member_stats(ent, mem, today)
    agg = ms.groupby("project_id")[["budget", "gebucht", "geplant"]].sum() if not ms.empty \
        else pd.DataFrame(columns=["budget", "gebucht", "geplant"])
    df = df.merge(agg, left_on="id", right_index=True, how="left")
    for c in ("budget", "gebucht", "geplant"):
        df[c] = pd.to_numeric(df[c]).fillna(0.0).astype(float)
    df["verteilt"] = df["budget"]  # Summe der Beraterbudgets
    if "budget_tage" in df:  # Projektbudget gesamt (aus Projektanlage), sonst Summe der Berater
        ges = pd.to_numeric(df["budget_tage"]).fillna(0.0)
        df["budget"] = ges.where(ges > 0, df["budget"])
    df["budget_tage"] = df["budget"]
    df["nicht_verteilt"] = df["budget"] - df["verteilt"]
    df["verbraucht"] = df["gebucht"]
    df["eingeplant"] = df["geplant"]
    df["offen"] = df["budget"] - df["gebucht"] - df["geplant"]
    df["ungeplant"] = df["offen"]
    df["fortschritt"] = ((df["gebucht"] + df["geplant"]) / df["budget"].where(df["budget"] > 0)).fillna(0)

    def status(r):
        if r["budget"] <= 0:
            return "Kein Budget"
        if r["offen"] < -0.01:
            return "Überplant"
        if r["offen"] > 0.01:
            return "Rest offen"
        return "Voll eingeplant"

    df["status"] = df.apply(status, axis=1) if not df.empty else pd.Series(dtype=str)
    return df


def week_fill_plan(target_h: float, mine: dict, other: dict, days: list) -> dict:
    """Stundenverteilung eines Projekts innerhalb einer Woche auf Zielstunden bringen.
    mine/other: {tag: stunden}. Rückgabe: {tag: neue_stunden} für alle geänderten Tage.
    Mehr: erst Tage mit freier Kapazität (Mo -> Fr), dann bis 8 h je Tag. Weniger: von Fr -> Mo abbauen."""
    cur = {d: float(mine.get(d, 0.0)) for d in days}
    diff = target_h - sum(cur.values())
    new = dict(cur)
    if diff > 1e-9:
        for respect_other in (True, False):
            for d in days:
                if diff <= 1e-9:
                    break
                room = TAG_H - new[d] - (other.get(d, 0.0) if respect_other else 0.0)
                put = min(max(room, 0.0), diff)
                if put > 1e-9:
                    new[d] += put
                    diff -= put
    elif diff < -1e-9:
        for d in reversed(days):
            if diff >= -1e-9:
                break
            take = min(new[d], -diff)
            new[d] -= take
            diff += take
    return {d: round(h, 4) for d, h in new.items() if abs(h - cur[d]) > 1e-9}
