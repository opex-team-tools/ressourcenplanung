"""Ressourcenplanung | Operations Team
Start: streamlit run app.py
"""
from __future__ import annotations

import base64
import datetime as dt
import hmac
import html
import os
import time

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import db
import logic

st.set_page_config(page_title="Ressourcenplanung", page_icon="📅", layout="wide")

BASE = os.path.dirname(os.path.abspath(__file__))
LOGO_PATH = os.path.join(BASE, "assets", "wp_logo.png")

# Farbcode (Corporate Design)
WP = dict(navy="#000055", mid="#6688BB", light="#BBCCEE", lilac="#E4E4F6",
          grey="#999999", lgrey="#D2D2D2", xlgrey="#EBEBEB", dark="#00295F", alert="#B3261E")
SERIES = ["#000055", "#6688BB", "#BBCCEE", "#999999", "#00295F", "#63686A",
          "#D2D2D2", "#8FA6CF", "#4D4D8F", "#B8B8B8"]
FONT = "Calibri, Carlito, 'Segoe UI', Arial, sans-serif"


def secret(section: str, key: str, default=None):
    try:
        return st.secrets[section][key]
    except Exception:
        return default


ZIEL = float(secret("app", "zielauslastung", 0.80))
LOGO_TOKEN = secret("app", "logo_dev_token", None) or None
# Markenname nur in den Secrets, nicht im (ggf. öffentlichen) Code
MARKE = secret("app", "marke", "Ressourcenplanung")


def _list_secret(section: str, key: str) -> list[str]:
    v = secret(section, key, None)
    if isinstance(v, str):
        v = [v]
    return [str(x).strip() for x in (v or []) if str(x).strip()]


TEAM_PW = secret("auth", "team_passwort", None)
SELBSTREG = str(secret("auth", "selbstregistrierung", "false")).lower() in ("1", "true", "ja", "yes")
ADMINS = {a.lower() for a in _list_secret("auth", "admins")}
TEAM_SEED = _list_secret("app", "team")
ROLLEN = ["Consultant", "Senior Consultant", "Projektleiter/in", "Manager", "Partner", "Werkstudent/in"]


def is_admin() -> bool:
    """Ohne konfigurierte Admins (Demo) darf jeder alles."""
    if not ADMINS:
        return True
    return str(st.session_state.get("user", "")).lower() in ADMINS


def _s(v) -> str:
    return "" if v is None or (not isinstance(v, str) and pd.isna(v)) else str(v)


@st.cache_data(ttl=7 * 24 * 3600, show_spinner=False)
def _fetch_logo(url: str, name: str) -> str:
    """Logo serverseitig laden und als Data URI cachen (schnell, kein Tracking pro Aufruf).
    Fallback: Initialen-Badge im Mittelblau."""
    if url.startswith("data:"):
        return url
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=4) as r:
            data = r.read()
            mime = r.headers.get_content_type() or "image/png"
        if len(data) < 200 or not mime.startswith("image/"):
            raise ValueError("kein brauchbares Logo")
        return f"data:{mime};base64,{base64.b64encode(data).decode()}"
    except Exception:
        return db.initials_svg(name)


def logo(name, domain, logo_blob) -> str:
    return _fetch_logo(db.logo_src(name, domain, logo_blob, LOGO_TOKEN), name)


@st.cache_resource(show_spinner="Datenbank wird vorbereitet ...")
def init_once() -> bool:
    """Schema und ggf. Demo-Daten genau einmal pro Serverprozess."""
    db.init_db(team=TEAM_SEED or None)
    return True


def heute() -> dt.date:
    return dt.date.today()


# ====================================================================== Styling
def inject_css() -> None:
    st.markdown(f"""
<style>
html, body, [class*="css"], .stMarkdown, .stDataFrame {{ font-family: {FONT}; }}
h1, h2, h3, h4 {{ color: {WP['navy']}; font-family: {FONT}; }}
.wp-title {{ font-size: 1.55rem; color: {WP['navy']}; margin: 0 0 .15rem 0; }}
.wp-title b {{ font-weight: 700; }}
.wp-line {{ border: 0; border-top: 2px solid {WP['navy']}; margin: .2rem 0 1rem 0; }}
.wp-sub {{ font-style: italic; color: {WP['mid']}; border-bottom: 1px solid {WP['mid']};
          padding-bottom: 2px; margin: 1.2rem 0 .6rem 0; font-size: 1.05rem; }}
.wp-wordmark {{ font-family: 'Goudy Old Style', Garamond, Georgia, serif; color: {WP['navy']};
               font-size: 1.25rem; line-height: 1.15; padding: .2rem 0 .8rem 0; }}
.wp-wordmark small {{ display:block; font-family:{FONT}; font-size:.75rem; color:{WP['mid']};
                     letter-spacing:.06em; text-transform:uppercase; margin-top:.25rem; }}
div[data-testid="stMetric"] {{ background: #F5F6FB; border-left: 4px solid {WP['navy']};
                               padding: .6rem .9rem; border-radius: 2px; }}
div[data-testid="stMetricLabel"] p {{ color: {WP['mid']}; font-size: .85rem; }}
div[data-testid="stMetricValue"] {{ color: {WP['navy']}; }}

table.wpm {{ width: 100%; border-collapse: separate; border-spacing: 4px; table-layout: fixed; }}
table.wpm th {{ color: {WP['navy']}; font-weight: 600; font-size: .85rem; text-align: center;
               padding: 4px 2px; border-bottom: 2px solid {WP['navy']}; }}
table.wpm th.today {{ background: {WP['navy']}; color: #fff; border-radius: 3px 3px 0 0; }}
table.wpm th.name, table.wpm td.name {{ text-align: left; width: 13%; }}
table.wpm th.util, table.wpm td.util {{ width: 11%; }}
table.wpm td {{ height: 62px; vertical-align: middle; text-align: center; border-radius: 4px;
               font-size: .78rem; color: {WP['navy']}; padding: 3px; overflow: hidden; }}
table.wpm td.name {{ font-weight: 600; font-size: .92rem; background: transparent; }}
table.wpm td.name span {{ display:block; font-weight:400; font-size:.72rem; color:{WP['grey']}; }}
td.c-onsite {{ background: {WP['lilac']}; border: 1px solid {WP['light']}; }}
td.c-remote {{ background: #FFFFFF; border: 1px dashed {WP['mid']}; }}
td.c-intern {{ background: {WP['xlgrey']}; color: #555 !important; }}
td.c-absent {{ background: repeating-linear-gradient(45deg,#F2F2F2,#F2F2F2 6px,#E6E6E6 6px,#E6E6E6 12px);
              color: {WP['grey']} !important; }}
td.c-free {{ background: #FFFFFF; border: 1px solid {WP['xlgrey']}; color: {WP['lgrey']} !important; }}
td.c-hol {{ background: {WP['xlgrey']}; color: {WP['grey']} !important; font-style: italic; }}
td.today-col {{ box-shadow: inset 0 0 0 2px {WP['navy']}; }}
td img.lg {{ height: 26px; max-width: 70%; object-fit: contain; display:block; margin: 0 auto 2px auto; }}
td .cl {{ display:block; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
td .pj {{ display:block; font-size:.68rem; color:{WP['mid']}; white-space:nowrap; overflow:hidden;
         text-overflow:ellipsis; }}
.ubar {{ background:{WP['xlgrey']}; height: 8px; border-radius: 4px; overflow:hidden; margin-top:4px; }}
.ubar > div {{ height: 100%; background:{WP['navy']}; }}
.legend span {{ display:inline-block; padding: 2px 10px; margin-right: 8px; border-radius: 3px;
               font-size: .78rem; color:{WP['navy']}; }}
</style>""", unsafe_allow_html=True)


def header(titel: str, kernsatz: str) -> None:
    st.markdown(f"<div class='wp-title'><b>{html.escape(titel)}</b> | {html.escape(kernsatz)}</div>"
                f"<hr class='wp-line'>", unsafe_allow_html=True)


def sub(text: str) -> None:
    st.markdown(f"<div class='wp-sub'>{html.escape(text)}</div>", unsafe_allow_html=True)


def branding() -> None:
    if os.path.exists(LOGO_PATH):
        st.logo(LOGO_PATH, size="large")
    else:
        st.sidebar.markdown(f"<div class='wp-wordmark'>{html.escape(MARKE)}"
                            "<small>Ressourcenplanung Operations</small></div>", unsafe_allow_html=True)


def plotly_layout(fig: go.Figure, height: int = 380, pct: bool = False) -> go.Figure:
    fig.update_layout(
        height=height, margin=dict(l=10, r=10, t=30, b=10), plot_bgcolor="#FFFFFF",
        paper_bgcolor="#FFFFFF", font=dict(family=FONT, color=WP["navy"], size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        hoverlabel=dict(font_family=FONT))
    fig.update_xaxes(showgrid=False, linecolor=WP["lgrey"])
    fig.update_yaxes(gridcolor=WP["xlgrey"], zeroline=False)
    if pct:
        fig.update_yaxes(tickformat=".0%")
    return fig


def fmt_pct(v) -> str:
    return "n/a" if v is None or pd.isna(v) else f"{v:.0%}"


# ====================================================================== Login
def users() -> dict:
    try:
        return dict(st.secrets["users"])
    except Exception:
        return {}


def login_gate() -> bool:
    if st.session_state.get("user"):
        return True
    header("Ressourcenplanung", "Anmeldung Operations Team")
    names = db.consultants()["name"].tolist()
    if TEAM_PW:
        with st.form("login"):
            vn = st.text_input("Vor- und Nachname", placeholder="z. B. Max Mustermann")
            pw = st.text_input("Team-Passwort", type="password")
            if st.form_submit_button("Anmelden", type="primary"):
                ok = bool(vn.strip()) and hmac.compare_digest(str(TEAM_PW), pw)
                person = db.find_consultant(vn) if ok else None
                if ok and person is None and SELBSTREG and len(vn.split()) >= 2:
                    kz = db.suggest_kuerzel(vn)
                    db.create_consultant(kz, vn.strip())
                    person = db.find_consultant(vn)
                if person is not None:
                    st.session_state.user = person["name"]
                    st.session_state.user_label = _s(person.get("vollname")) or person["name"]
                    st.rerun()
                time.sleep(1.5)  # bremst Durchprobieren
                if ok:
                    st.error("Name nicht im Team gefunden. Bitte Schreibweise prüfen oder den Admin bitten, "
                             "dich anzulegen.")
                else:
                    st.error("Name oder Passwort falsch.")
        return False
    u = users()
    if not u:
        st.info("Demo-Modus: kein Passwort in den Secrets hinterlegt. Name wählen genügt.")
        name = st.selectbox("Wer bist du?", names, index=None)
        if st.button("Weiter", type="primary", disabled=not name):
            st.session_state.user = name
            st.rerun()
        return False
    with st.form("login"):
        eingabe = st.text_input("Benutzername", placeholder="Kürzel, z. B. abc")
        pw = st.text_input("Passwort", type="password")
        if st.form_submit_button("Anmelden", type="primary"):
            # Groß/Kleinschreibung und Leerzeichen beim Benutzernamen egal
            name = next((k for k in u if k.strip().lower() == eingabe.strip().lower()), None)
            if name and hmac.compare_digest(str(u.get(name, "")), pw):
                st.session_state.user = name
                st.rerun()
            time.sleep(1.5)
            st.error("Benutzername oder Passwort falsch.")
    return False


# ====================================================================== Gemeinsame Bausteine
SONST = ["Urlaub", "Intern", "Akquise", "Krank"]
ORT_ICON = {"Vor Ort": "🏢", "Remote": "🏠"}
ART_ICON = {"Urlaub": "🌴", "Intern": "🏛️", "Akquise": "🎯", "Krank": "🤒", "Löschen": "🧽"}
H = logic.TAG_H


def extra_css() -> None:
    st.markdown(f"""
<style>
.dh {{ display:flex; justify-content:space-between; align-items:center; font-weight:700; color:{WP['navy']};
      font-size:.88rem; margin-bottom:4px; }}
.dh.today > span:first-child {{ background:{WP['navy']}; color:#fff; padding:1px 7px; border-radius:4px; }}
.hb {{ font-size:.72rem; padding:1px 7px; border-radius:10px; font-weight:600; white-space:nowrap; }}
.hb.ok {{ background:{WP['lilac']}; color:{WP['navy']}; }}
.hb.low {{ background:#F2F2F2; color:{WP['grey']}; }}
.hb.over {{ background:#FBE3E1; color:{WP['alert']}; }}
.ent2 {{ display:flex; gap:6px; align-items:center; font-size:.76rem; line-height:1.2; color:{WP['navy']};
        padding:4px 5px; border-radius:4px; overflow:hidden; }}
.ent2 > div {{ overflow:hidden; min-width:0; }}
.ent2 b, .ent2 small, .ent2 i {{ display:block; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
.ent2 small {{ color:{WP['navy']}; font-size:.72rem; }}
.ent2 i {{ color:{WP['mid']}; font-size:.68rem; font-style:normal; }}
.ent2 img {{ height:20px; width:20px; object-fit:contain; flex:0 0 20px; }}
.ent2.onsite {{ background:{WP['lilac']}; border-left:4px solid {WP['navy']}; }}
.ent2.remote {{ background:#FFFFFF; border:1px dashed {WP['mid']}; border-left:4px dashed {WP['mid']}; }}
.ent2.intern {{ background:{WP['xlgrey']}; }}
.ent2.absent {{ background:repeating-linear-gradient(45deg,#F4F4F4,#F4F4F4 6px,#EAEAEA 6px,#EAEAEA 12px); color:#777; }}
.brush {{ background:{WP['lilac']}; border:1px solid {WP['light']}; border-radius:6px; padding:8px 12px;
         color:{WP['navy']}; margin:4px 0 8px 0; }}
.brush b {{ font-size:1.02rem; }}
.wk {{ color:{WP['mid']}; font-size:.85rem; }}
.kpis {{ display:flex; gap:22px; flex-wrap:wrap; }}
.kpis div b {{ display:block; font-size:1.3rem; color:{WP['navy']}; line-height:1.1; }}
.kpis div span {{ font-size:.74rem; color:{WP['mid']}; }}
.kpis div b.neg {{ color:{WP['alert']}; }}
.bar {{ height:9px; background:{WP['xlgrey']}; border-radius:5px; overflow:hidden; display:flex; margin-top:8px; }}
.bar .g {{ background:{WP['navy']}; }} .bar .p {{ background:{WP['mid']}; }} .bar .o {{ background:{WP['alert']}; }}
.ptitle b {{ font-size:1.05rem; color:{WP['navy']}; }} .ptitle span {{ color:{WP['mid']}; font-size:.85rem; }}
td .ent {{ display:flex; align-items:center; justify-content:center; gap:4px; font-size:.7rem; white-space:nowrap;
          overflow:hidden; text-overflow:ellipsis; line-height:1.25; }}
td .ent img {{ height:16px; width:16px; object-fit:contain; }}
td.over {{ box-shadow: inset 0 0 0 2px {WP['alert']} !important; }}
.legend2 span {{ display:inline-block; padding:2px 10px; margin-right:8px; border-radius:3px; font-size:.78rem;
               color:{WP['navy']}; }}
</style>""", unsafe_allow_html=True)


def bt(v) -> str:
    """Beratertage hübsch: 12 / 12,5"""
    v = round(float(v or 0), 1)
    return f"{v:g}".replace(".", ",")


def hh(v) -> str:
    return f"{float(v):g}".replace(".", ",") + " h"


def client_logo_map(proj_all: pd.DataFrame) -> dict:
    return {r.id: logo(r.kunde, r.domain, r.logo) for r in proj_all.itertuples()}


def week_days(ws: dt.date) -> list[dt.date]:
    return [ws + dt.timedelta(days=i) for i in range(5)]


def person_label(cons: pd.DataFrame) -> dict:
    return {r.name: (f"{_s(r.vollname)} ({r.name})" if _s(r.vollname) else r.name) for r in cons.itertuples()}


def entry_html(e, projn: pd.DataFrame, logos: dict) -> str:
    h = hh(e.stunden)
    if pd.notna(e.project_id) and int(e.project_id) in projn.index:
        pid = int(e.project_id)
        p = projn.loc[pid]
        cls = "onsite" if e.art == "Vor Ort" else "remote"
        return (f"<div class='ent2 {cls}' title='{html.escape(p['label'])} · {e.art} · {h}'>"
                f"<img src='{logos[pid]}'><div><b>{html.escape(p['kunde'])}</b>"
                f"<small>{ORT_ICON.get(e.art, '')} {e.art} · {h}</small><i>{html.escape(p['name'])}</i></div></div>")
    cls = "absent" if e.art in logic.ABWESEND_ARTEN else "intern"
    return (f"<div class='ent2 {cls}'><div><b>{ART_ICON.get(e.art, '')} {e.art}</b>"
            f"<small>{h}</small></div></div>")


def day_header_html(d: dt.date, tot: float, today: dt.date, abw: float = 0.0) -> str:
    t = " today" if d == today else ""
    if logic.feiertag_name(d):
        badge = ""
    elif abw > 0 and tot - abw <= 0:
        badge = "<span class='hb low'>abwesend</span>"
    elif tot <= 0:
        badge = "<span class='hb low'>frei</span>"
    elif tot > H:
        badge = f"<span class='hb over'>⚠ {hh(tot)}</span>"
    elif tot < H:
        badge = f"<span class='hb low'>{hh(tot)} · {hh(H - tot)} frei</span>"
    else:
        badge = "<span class='hb ok'>8 h ✓</span>"
    return f"<div class='dh{t}'><span>{logic.WOTAG[d.weekday()]} {d:%d.%m.}</span>{badge}</div>"


# ====================================================================== Seite: Mein Kalender
def current_brush():
    """('p', project_id) | ('a', 'Urlaub' ...) | ('a', 'Löschen') | None"""
    ss = st.session_state
    other = ss.get("k_other")
    if other and other in ss.get("k_other_map", {}):
        return ("p", int(ss["k_other_map"][other]))
    b = ss.get("k_brush")
    if not b:
        return None
    return ("p", int(b[1:])) if b.startswith("p") else ("a", b)


def _valid_days(days) -> list[dt.date]:
    return [d for d in days if d.weekday() < 5 and not logic.feiertag_name(d)]


def apply_brush(cid: int, days: list[dt.date]) -> None:
    ss = st.session_state
    br = current_brush()
    days = _valid_days(days)
    if br is None:
        st.toast("Bitte zuerst oben auswählen, was eingetragen werden soll.")
        return
    if not days:
        return
    if br == ("a", "Löschen"):
        n = db.clear_days(cid, days)
        st.toast(f"🧽 {n} Einträge entfernt")
        return
    h = float(ss.get("k_h") or H)
    if br[0] == "p":
        ort = ss.get("k_ort") or "Vor Ort"
        rows = [(cid, d, ort, br[1], h) for d in days]
        db.add_member(br[1], cid)  # taucht damit unter "Meine Projekte" auf
    else:
        rows = [(cid, d, br[1], None, h) for d in days]
    db.upsert_entries(rows, ss.get("user", ""))
    e = db.entries(min(days), max(days), consultant_id=cid)
    tot = e.groupby("tag")["stunden"].sum() if not e.empty else pd.Series(dtype=float)
    over = [d for d in days if tot.get(d, 0) > H]
    msg = f"✓ {len(rows)} Tag{'e' if len(rows) != 1 else ''} eingetragen"
    if over:
        msg += " · ⚠ überbucht am " + ", ".join(f"{d:%d.%m.}" for d in over[:5])
    st.toast(msg)


def del_entry_cb(entry_id: int) -> None:
    db.delete_entry(entry_id)
    st.toast("Eintrag entfernt")


def clear_range_cb(cid: int, von: dt.date, bis: dt.date) -> None:
    n = db.clear_range([cid], von, bis)
    st.toast(f"🧽 {n} Einträge im Zeitraum entfernt")


def _shift_k(n: int) -> None:
    st.session_state.k_off = 0 if n == 0 else st.session_state.get("k_off", 0) + n


def _clear_other() -> None:
    st.session_state.k_other = None


def page_kalender() -> None:
    today = heute()
    ss = st.session_state
    user = ss.user
    cons = db.consultants()
    names = cons["name"].tolist()
    header("Mein Kalender", "Auswählen, was eingetragen wird, dann Tage anklicken")
    if not names:
        st.info("Noch keine Mitarbeiter angelegt (Verwaltung).")
        return
    plab = person_label(cons)
    c1, _ = st.columns([2, 4])
    wer = c1.selectbox("Planung für", names, index=names.index(user) if user in names else 0, key="k_wer",
                       format_func=lambda n: plab.get(n, n),
                       help="Standard: du selbst. Projektleiter können hier für Kollegen planen.")
    cid = int(cons.loc[cons["name"] == wer, "id"].iloc[0])

    proj = db.projects()
    pmap = proj.set_index("id")
    mem = db.members()
    ms = logic.member_stats(db.entries(consultant_id=cid, project_only=True),
                            mem[mem["consultant_id"] == cid], today).set_index("project_id")
    mine = [pid for pid in pmap.index if pid in ms.index]
    others = [pid for pid in pmap.index if pid not in ms.index]

    # ---------------- 1 | Pinsel
    sub("1 | Was trage ich ein?")

    def lab(o: str) -> str:
        if o.startswith("p"):
            pid = int(o[1:])
            t = f"{pmap.at[pid, 'kunde']} · {pmap.at[pid, 'name']}"
            if pid in ms.index:
                b = ms.loc[pid]
                t += f"  ({bt(b['offen'])} von {bt(b['budget'])} BT offen)" if b["budget"] > 0 else "  (kein Budget)"
            return t
        return f"{ART_ICON.get(o, '')} {o}"

    opts = [f"p{p}" for p in mine] + SONST + ["Löschen"]
    if ss.get("k_brush") not in opts:
        ss.k_brush = opts[0]
    st.pills("Meine Projekte und Abwesenheiten", opts, format_func=lab, key="k_brush",
             selection_mode="single", on_change=_clear_other)
    other_map = {f"{pmap.at[p, 'kunde']} · {pmap.at[p, 'name']}": p for p in others}
    ss["k_other_map"] = other_map
    cc = st.columns([3, 2, 2])
    cc[0].selectbox("… oder ein anderes Projekt", list(other_map), index=None, key="k_other",
                    placeholder="Projekt suchen, bei dem ich noch nicht eingeplant bin")
    br = current_brush()
    is_p = br is not None and br[0] == "p"
    cc[1].segmented_control("Ort", ["Vor Ort", "Remote"], default="Vor Ort", key="k_ort",
                            format_func=lambda x: f"{ORT_ICON[x]} {x}", disabled=not is_p)
    cc[2].segmented_control("Stunden pro Tag", [2, 4, 6, 8], default=8, key="k_h",
                            format_func=lambda x: f"{x} h", disabled=br == ("a", "Löschen"))
    h_sel = float(ss.get("k_h") or H)
    if br is None:
        st.markdown("<div class='brush'>Bitte oben auswählen, was eingetragen werden soll.</div>",
                    unsafe_allow_html=True)
        short = "eintragen"
    elif br == ("a", "Löschen"):
        st.markdown("<div class='brush'>🧽 <b>Radiergummi</b>: angeklickte Tage werden geleert.</div>",
                    unsafe_allow_html=True)
        short = "🧽 leeren"
    elif is_p:
        ort = ss.get("k_ort") or "Vor Ort"
        p = pmap.loc[br[1]]
        st.markdown(f"<div class='brush'>Pinsel: <b>{ORT_ICON[ort]} {html.escape(p['kunde'])}</b> · "
                    f"{html.escape(p['name'])} · {ort} · {hh(h_sel)} pro Tag</div>", unsafe_allow_html=True)
        short = f"＋ {p['kunde'][:14]}"
    else:
        st.markdown(f"<div class='brush'>Pinsel: <b>{ART_ICON.get(br[1], '')} {br[1]}</b> · {hh(h_sel)} pro Tag</div>",
                    unsafe_allow_html=True)
        short = f"＋ {br[1]}"

    # ---------------- 2 | Kalender
    sub("2 | Tage anklicken")
    ss.setdefault("k_off", 0)
    nb = st.columns([1.2, 1, 1.2, 2, 3])
    nb[0].button("◀ Früher", on_click=_shift_k, args=(-1,), width="stretch")
    nb[1].button("Heute", on_click=_shift_k, args=(0,), width="stretch")
    nb[2].button("Später ▶", on_click=_shift_k, args=(1,), width="stretch")
    n_w = nb[3].selectbox("Wochen", [2, 3, 4, 6], index=1, key="k_nw", label_visibility="collapsed",
                          format_func=lambda x: f"{x} Wochen anzeigen")
    start = logic.monday(today) + dt.timedelta(weeks=ss.k_off)
    weeks = [start + dt.timedelta(weeks=i) for i in range(n_w)]
    end = weeks[-1] + dt.timedelta(days=4)
    ent = db.entries(start, end, consultant_id=cid)
    projn = db.projects(active_only=False).set_index("id")
    logos = client_logo_map(projn.reset_index())
    by_day = {d: g for d, g in ent.groupby("tag")} if not ent.empty else {}
    st.markdown("<div class='legend2'><span style='background:#E4E4F6;border-left:4px solid #000055'>🏢 Vor Ort</span>"
                "<span style='border:1px dashed #6688BB'>🏠 Remote</span>"
                "<span style='background:#FBE3E1;color:#B3261E'>⚠ mehr als 8 h = überbucht</span></div>",
                unsafe_allow_html=True)

    for ws in weeks:
        wd = week_days(ws)
        we = ent[ent["tag"].isin(wd)] if not ent.empty else ent
        f = logic.build_fact(ws, wd[-1], cons[cons["id"] == cid], we)
        hc = st.columns([4, 1.3, 1.3], vertical_alignment="bottom")
        hc[0].markdown(f"**KW {ws.isocalendar().week:02d}** &nbsp; {ws:%d.%m.} bis {wd[-1]:%d.%m.} &nbsp; "
                       f"<span class='wk'>{hh(f['gebucht'].sum())} geplant von {hh(f['kapazitaet'].sum())}</span>",
                       unsafe_allow_html=True)
        hc[1].button("Mo bis Do", key=f"w4_{cid}_{ws}", on_click=apply_brush, args=(cid, wd[:4]),
                     disabled=br is None, width="stretch", help="Auswahl für Mo bis Do dieser Woche eintragen")
        hc[2].button("Mo bis Fr", key=f"w5_{cid}_{ws}", on_click=apply_brush, args=(cid, wd),
                     disabled=br is None, width="stretch", help="Auswahl für die ganze Woche eintragen")
        cols = st.columns(5, gap="small")
        for i, d in enumerate(wd):
            with cols[i].container(border=True):
                es = by_day.get(d)
                tot = float(es["stunden"].sum()) if es is not None else 0.0
                abw = float(es.loc[es["art"].isin(logic.ABWESEND_ARTEN), "stunden"].sum()) if es is not None else 0.0
                st.markdown(day_header_html(d, tot, today, abw), unsafe_allow_html=True)
                hol = logic.feiertag_name(d)
                if hol:
                    st.caption(f"Feiertag: {hol}")
                    continue
                if es is not None:
                    for e in es.sort_values(["project_id", "art"]).itertuples():
                        ec = st.columns([6, 1], vertical_alignment="center", gap="small")
                        ec[0].markdown(entry_html(e, projn, logos), unsafe_allow_html=True)
                        ec[1].button("✕", key=f"del_{e.id}", on_click=del_entry_cb, args=(int(e.id),),
                                     type="tertiary", help="Eintrag entfernen")
                st.button(short, key=f"add_{cid}_{d}", on_click=apply_brush, args=(cid, [d]),
                          disabled=br is None, width="stretch")
        st.write("")

    with st.expander("Serie eintragen (z. B. Mo bis Do jede Woche bis Projektende) oder Zeitraum leeren"):
        s1, s2, s3, s4 = st.columns(4)
        von = s1.date_input("Von", today, format="DD.MM.YYYY", key="k_s_von")
        bis = s2.date_input("Bis", today + dt.timedelta(weeks=8), format="DD.MM.YYYY", key="k_s_bis")
        wt = s3.multiselect("Wochentage", logic.WOTAG[:5], default=logic.WOTAG[:4], key="k_s_wt")
        rh = s4.selectbox("Rhythmus", list(logic.RHYTHMEN), key="k_s_rh")
        sdays = logic.plan_days(von, bis, wt, logic.RHYTHMEN[rh])
        st.caption(f"{len(sdays)} Tage mit der aktuellen Auswahl oben ({short.replace('＋ ', '')}, {hh(h_sel)}). "
                   "Bestehende Einträge anderer Projekte bleiben erhalten, Feiertage werden übersprungen.")
        b1, b2, _ = st.columns([1, 1, 3])
        b1.button("Serie eintragen", type="primary", on_click=apply_brush, args=(cid, sdays),
                  disabled=not sdays or br is None, key="k_s_go")
        b2.button("Zeitraum leeren", on_click=clear_range_cb, args=(cid, von, bis), disabled=von > bis,
                  key="k_s_clear", help="Löscht alle Einträge dieser Person zwischen Von und Bis")

    # ---------------- 3 | Budget
    sub("Meine Projekte und Budgets")
    if ms.empty:
        st.caption("Noch keinem Projekt zugeordnet.")
        return
    lmap = dict(zip(cons["id"], cons["name"]))
    rows = []
    for pid, b in ms.iterrows():
        if pid not in projn.index:
            continue
        p = projn.loc[pid]
        rows.append({"logo": logos[pid], "Projekt": p["label"], "Budget BT": b["budget"], "Gebucht": b["gebucht"],
                     "Geplant": b["geplant"], "Offen": b["offen"], "Ende": p["ende"],
                     "Leitung": lmap.get(int(p["leiter_id"]), "") if pd.notna(p.get("leiter_id")) else ""})
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
        "logo": st.column_config.ImageColumn("", width="small"),
        "Budget BT": st.column_config.NumberColumn(format="%.1f"),
        "Gebucht": st.column_config.NumberColumn("Gebucht (bis heute)", format="%.1f"),
        "Geplant": st.column_config.NumberColumn("Geplant (ab morgen)", format="%.1f"),
        "Offen": st.column_config.NumberColumn(format="%.1f"),
        "Ende": st.column_config.DateColumn(format="DD.MM.YYYY")})
    st.caption("Budget anpassen: Menü **Projekte**, beim Projekt auf **Team & Budget** klicken. "
               "Negativ offen bedeutet, dass mehr geplant ist als budgetiert.")


# ====================================================================== Seite: Team (Wochenmatrix)
def render_matrix(ws: dt.date) -> str:
    today = heute()
    days = week_days(ws)
    cons = db.consultants()
    ent = db.entries(days[0], days[-1])
    projn = db.projects(active_only=False).set_index("id")
    logos = client_logo_map(projn.reset_index())
    by = {k: g for k, g in ent.groupby(["consultant_id", "tag"])} if not ent.empty else {}
    fact = logic.build_fact(days[0], days[-1], cons, ent)

    head = "<tr><th class='name'>Berater</th>"
    for d in days:
        head += f"<th{' class=today' if d == today else ''}>{logic.day_label(d)}</th>"
    head += "<th class='util'>Auslastung KW</th></tr>"
    rows = ""
    for c in cons.itertuples():
        rows += (f"<tr><td class='name'>{html.escape(c.name)}"
                 f"<span>{html.escape(_s(c.vollname) or _s(c.rolle))}</span></td>")
        for d in days:
            tc = " today-col" if d == today else ""
            hol = logic.feiertag_name(d)
            g = by.get((c.id, d))
            if g is None:
                rows += (f"<td class='c-hol{tc}'>{html.escape(hol)}</td>" if hol
                         else f"<td class='c-free{tc}'>frei</td>")
                continue
            tot = float(g["stunden"].sum())
            arts = set(g["art"])
            cls = ("c-onsite" if "Vor Ort" in arts else "c-remote" if "Remote" in arts
                   else "c-absent" if arts <= set(logic.ABWESEND_ARTEN) else "c-intern")
            over = " over" if tot > H else ""
            inner = ""
            for e in g.sort_values("stunden", ascending=False).head(2).itertuples():
                if pd.notna(e.project_id) and int(e.project_id) in projn.index:
                    p = projn.loc[int(e.project_id)]
                    inner += (f"<div class='ent' title='{html.escape(p['label'])} · {e.art} · {hh(e.stunden)}'>"
                              f"<img src='{logos[int(e.project_id)]}'>{ORT_ICON.get(e.art, '')} "
                              f"<b>{html.escape(p['kunde'][:16])}</b>&nbsp;{hh(e.stunden)}</div>")
                else:
                    inner += f"<div class='ent'>{ART_ICON.get(e.art, '')} {e.art} {hh(e.stunden)}</div>"
            if len(g) > 2:
                inner += f"<div class='ent'>+ {len(g) - 2} weitere</div>"
            if tot > H:
                inner += f"<div class='ent' style='color:{WP['alert']};font-weight:700'>⚠ {hh(tot)}</div>"
            rows += f"<td class='{cls}{tc}{over}'>{inner}</td>"
        fc = fact[fact["consultant_id"] == c.id]
        u = logic.kpi(fc)
        w = 0 if u is None else min(u, 1) * 100
        rows += (f"<td class='util'><b>{fmt_pct(u)}</b><div class='ubar'><div style='width:{w:.0f}%'></div></div>"
                 "</td></tr>")
    legend = (f"<div class='legend'><span style='background:{WP['lilac']};border:1px solid {WP['light']}'>🏢 Vor Ort</span>"
              f"<span style='border:1px dashed {WP['mid']}'>🏠 Remote</span>"
              f"<span style='background:{WP['xlgrey']}'>Intern / Akquise</span>"
              f"<span style='background:#EEE'>Urlaub / Krank</span>"
              f"<span style='box-shadow: inset 0 0 0 2px {WP['alert']}'>⚠ überbucht</span></div>")
    return f"<table class='wpm'>{head}{rows}</table>{legend}"


@st.fragment(run_every=60)
def matrix_live(ws: dt.date) -> None:
    st.markdown(render_matrix(ws), unsafe_allow_html=True)
    st.caption(f"Live-Ansicht, aktualisiert {dt.datetime.now():%H:%M:%S} (automatisch jede Minute)")


def shift_week(n: int) -> None:
    st.session_state.kw_offset = 0 if n == 0 else st.session_state.get("kw_offset", 0) + n


def page_team() -> None:
    today = heute()
    st.session_state.setdefault("kw_offset", 0)
    ws = logic.monday(today) + dt.timedelta(weeks=st.session_state.kw_offset)
    we = ws + dt.timedelta(days=4)
    header("Team", f"Wer ist in KW {ws.isocalendar().week:02d} bei welchem Kunden")
    cons = db.consultants()
    ent_w = db.entries(ws, we)
    f_week = logic.build_fact(ws, we, cons, ent_w)
    m0 = logic.monday(today)
    e4 = m0 + dt.timedelta(days=27)
    f_4w = logic.build_fact(m0, e4, cons, db.entries(m0, e4))
    e_today = db.entries(today, today)
    vor_ort_heute = e_today.loc[e_today["art"] == "Vor Ort", "consultant_id"].nunique() if not e_today.empty else 0
    u_w, u_4 = logic.kpi(f_week), logic.kpi(f_4w)
    over_days = int((f_4w.assign(t=f_4w["gebucht"] + (H - f_4w["kapazitaet"]))["t"] > H).sum()) if not f_4w.empty else 0

    k = st.columns(5)
    k[0].metric("Auslastung KW", fmt_pct(u_w),
                None if u_w is None else f"{(u_w - ZIEL) * 100:+.0f} pp vs. Ziel {ZIEL:.0%}")
    k[1].metric("Heute vor Ort", f"{vor_ort_heute} / {len(cons)}")
    k[2].metric("Auslastung 4 Wochen", fmt_pct(u_4),
                None if u_4 is None else f"{(u_4 - ZIEL) * 100:+.0f} pp vs. Ziel")
    k[3].metric("Frei 4 Wochen (BT)", bt(f_4w["frei"].sum() / H) if not f_4w.empty else "0")
    k[4].metric("Überbucht 4 Wochen", f"{over_days} Tage")

    n = st.columns([1, 1, 1, 7])
    n[0].button("◀ Woche", on_click=shift_week, args=(-1,), width="stretch")
    n[1].button("Heute", on_click=shift_week, args=(0,), width="stretch")
    n[2].button("Woche ▶", on_click=shift_week, args=(1,), width="stretch")
    n[3].markdown(f"**KW {ws.isocalendar().week:02d}** &nbsp; {ws:%d.%m.} bis {we:%d.%m.%Y}")
    matrix_live(ws)

    c1, c2 = st.columns([3, 2])
    with c1:
        sub("Kundenpräsenz dieser Woche (Beratertage)")
        pe = ent_w[ent_w["art"].isin(logic.PROJEKT_ARTEN) & ent_w["project_id"].notna()] if not ent_w.empty else ent_w
        if pe.empty:
            st.caption("Keine Projekttage in dieser Woche.")
        else:
            projn = db.projects(active_only=False).set_index("id")
            pe = pe.assign(kunde=pe["project_id"].astype(int).map(projn["kunde"]),
                           vo=pe["stunden"].where(pe["art"] == "Vor Ort", 0) / H,
                           re=pe["stunden"].where(pe["art"] == "Remote", 0) / H)
            g = pe.groupby("kunde")[["vo", "re"]].sum().reset_index()
            g = g.assign(t=g["vo"] + g["re"]).sort_values("t")
            fig = go.Figure([
                go.Bar(y=g["kunde"], x=g["vo"], name="🏢 Vor Ort", orientation="h", marker_color=WP["navy"]),
                go.Bar(y=g["kunde"], x=g["re"], name="🏠 Remote", orientation="h", marker_color=WP["light"])])
            fig.update_layout(barmode="stack")
            st.plotly_chart(plotly_layout(fig, height=60 + 32 * len(g)), width="stretch")
    with c2:
        sub("Letzte Änderungen")
        ch = db.recent_changes(12)
        if not ch.empty:
            ch["zeitpunkt"] = pd.to_datetime(ch["zeitpunkt"]).dt.strftime("%d.%m. %H:%M")
            ch["eintrag"] = ch["kunde"].fillna(ch["art"]) + " · " + ch["stunden"].map(lambda v: hh(v))
            st.dataframe(ch[["zeitpunkt", "von", "berater", "tag", "eintrag"]], hide_index=True,
                         width="stretch", height=300,
                         column_config={"tag": st.column_config.DateColumn("Tag", format="DD.MM.")})


# ====================================================================== Seite: Projekte
def kpi_html(budget: float, gebucht: float, geplant: float, offen: float) -> str:
    neg = " class='neg'" if offen < -0.01 else ""
    tot = max(budget, gebucht + geplant, 0.01)
    over = max(gebucht + geplant - budget, 0)
    return (f"<div class='kpis'><div><b>{bt(budget)}</b><span>Budget BT</span></div>"
            f"<div><b>{bt(gebucht)}</b><span>gebucht bis heute</span></div>"
            f"<div><b>{bt(geplant)}</b><span>geplant ab morgen</span></div>"
            f"<div><b{neg}>{bt(offen)}</b><span>{'offen' if offen >= -0.01 else 'über Budget'}</span></div></div>"
            f"<div class='bar'><div class='g' style='width:{min(gebucht, budget or gebucht) / tot * 100:.1f}%'></div>"
            f"<div class='p' style='width:{max(min(geplant, budget - gebucht), 0) / tot * 100:.1f}%'></div>"
            f"<div class='o' style='width:{over / tot * 100:.1f}%'></div></div>")


@st.dialog("Neues Projekt anlegen", width="large")
def dialog_neues_projekt() -> None:
    today = heute()
    user = st.session_state.user
    cons = db.consultants()
    names = cons["name"].tolist()
    plab = person_label(cons)
    cid_k, new_name, dom = client_picker("dlg")
    c1, c2 = st.columns([3, 2])
    pname = c1.text_input("Projektname", key="dlg_name", placeholder="z. B. Footprint Analyse")
    leiter = c2.selectbox("Projektleitung", names, index=names.index(user) if user in names else 0,
                          format_func=lambda n: plab.get(n, n), key="dlg_leiter")
    c3, c4 = st.columns(2)
    start = c3.date_input("Start", today, format="DD.MM.YYYY", key="dlg_start")
    ende = c4.date_input("Ende", today + dt.timedelta(days=90), format="DD.MM.YYYY", key="dlg_ende")

    st.markdown("**Team und Budget je Berater (Beratertage, 1 BT = 8 h)**")
    base = pd.DataFrame({"Mitarbeiter": [user] if user in names else [None], "Budget BT": [0.0]})
    ed = st.data_editor(base, num_rows="dynamic", hide_index=True, width="stretch", key="dlg_team",
                        column_config={
                            "Mitarbeiter": st.column_config.SelectboxColumn(options=names, required=True),
                            "Budget BT": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.1f")})
    team = ed.dropna(subset=["Mitarbeiter"]).drop_duplicates("Mitarbeiter")
    st.caption(f"Projektbudget gesamt: **{bt(team['Budget BT'].fillna(0).sum())} BT** "
               "(Summe der Berater). Jeder kann sein Budget später selbst anpassen.")

    plan = st.toggle("Team direkt einplanen (optional)", key="dlg_plan")
    if plan:
        p1, p2, p3, p4 = st.columns(4)
        wt = p1.multiselect("Wochentage", logic.WOTAG[:5], default=logic.WOTAG[:4], key="dlg_wt")
        rh = p2.selectbox("Rhythmus", list(logic.RHYTHMEN), key="dlg_rh")
        ort = p3.segmented_control("Ort", ["Vor Ort", "Remote"], default="Vor Ort", key="dlg_ort",
                                   format_func=lambda x: f"{ORT_ICON[x]} {x}")
        std = p4.segmented_control("Stunden", [2, 4, 6, 8], default=8, key="dlg_h", format_func=lambda x: f"{x} h")
        pdays = logic.plan_days(start, ende, wt, logic.RHYTHMEN[rh])
        st.caption(f"{len(pdays)} Tage je Berater, {len(pdays) * len(team)} Einträge. "
                   "Bereits geplante andere Projekte bleiben erhalten.")
    ok = bool((cid_k or new_name) and pname.strip() and start <= ende and len(team))
    if st.button("Projekt anlegen", type="primary", disabled=not ok, key="dlg_go"):
        if new_name:
            cid_k = db.create_client(new_name, dom)
        pid = db.ensure_project(cid_k, pname)
        lid = int(cons.loc[cons["name"] == leiter, "id"].iloc[0])
        db.update_project_meta(pid, start=start, ende=ende, leiter_id=lid, aktiv=True)
        idmap = dict(zip(cons["name"], cons["id"]))
        db.set_members(pid, [(idmap[r["Mitarbeiter"]], float(r["Budget BT"] or 0)) for _, r in team.iterrows()])
        n = 0
        if plan and pdays:
            rows = [(idmap[m], d, ort or "Vor Ort", pid, float(std or 8)) for m in team["Mitarbeiter"] for d in pdays]
            n = db.upsert_entries(rows, user)
        for k_ in ("dlg_kunde", "dlg_dom", "dlg_name", "dlg_team", "dlg_plan"):
            st.session_state.pop(k_, None)
        st.session_state["proj_msg"] = f"Projekt **{pname.strip()}** angelegt" + (f", {n} Tage eingeplant." if n else ".")
        st.rerun()


def page_projekte() -> None:
    today = heute()
    user = st.session_state.user
    header("Projekte", "Budget, Planung und offene Beratertage je Projekt")
    cons = db.consultants(active_only=False)
    names = db.consultants()["name"].tolist()
    plab = person_label(cons)
    me = cons.loc[cons["name"] == user, "id"]
    me = int(me.iloc[0]) if len(me) else None

    c = st.columns([1.4, 1.6, 1.8, 4])
    if c[0].button("＋ Neues Projekt", type="primary", width="stretch"):
        dialog_neues_projekt()
    nur_meine = c[1].toggle("Nur meine Projekte", value=me is not None, key="p_mine", disabled=me is None)
    alle = c[2].toggle("Abgeschlossene zeigen", value=False, key="p_closed")
    if st.session_state.get("proj_msg"):
        st.success(st.session_state.pop("proj_msg"))

    proj = db.projects(active_only=not alle)
    if proj.empty:
        st.info("Noch keine Projekte. Oben auf **＋ Neues Projekt** klicken.")
        return
    ent = db.entries(project_only=True)
    mem = db.members()
    stats = logic.project_stats(proj, ent, mem, today).set_index("id")
    ms = logic.member_stats(ent, mem, today)
    lmap = dict(zip(cons["id"], cons["name"]))
    if nur_meine and me is not None:
        mine = set(ms.loc[ms["consultant_id"] == me, "project_id"])
        stats = stats[stats.index.isin(mine) | (stats["leiter_id"] == me)]
    if stats.empty:
        st.info("Keine Projekte mit dir. Schalter **Nur meine Projekte** ausschalten, um alle zu sehen.")
        return

    for pid, r in stats.sort_values(["kunde", "name"]).iterrows():
        with st.container(border=True):
            a, b, c3 = st.columns([0.6, 4, 6], vertical_alignment="center")
            a.image(logo(r["kunde"], r["domain"], r["logo"]), width=44)
            leit = plab.get(lmap.get(int(r["leiter_id"])), "") if pd.notna(r.get("leiter_id")) else ""
            zeit = (f"{r['start']:%d.%m.%Y} bis {r['ende']:%d.%m.%Y}"
                    if pd.notna(r["start"]) and pd.notna(r["ende"]) else "ohne Zeitraum")
            b.markdown(f"<div class='ptitle'><b>{html.escape(r['kunde'])}</b> · {html.escape(r['name'])}<br>"
                       f"<span>{zeit}{' · Leitung: ' + html.escape(leit) if leit else ''}"
                       f"{'' if r['aktiv'] else ' · abgeschlossen'}</span></div>", unsafe_allow_html=True)
            c3.markdown(kpi_html(r["budget"], r["gebucht"], r["geplant"], r["offen"]), unsafe_allow_html=True)

            with st.expander("Team & Budget"):
                m = ms[ms["project_id"] == pid]
                df = pd.DataFrame({
                    "Mitarbeiter": [lmap.get(int(x)) for x in m["consultant_id"]],
                    "Budget BT": m["budget"].astype(float).values,
                    "Gebucht": m["gebucht"].astype(float).values,
                    "Geplant": m["geplant"].astype(float).values,
                    "Offen": m["offen"].astype(float).values})
                ed = st.data_editor(df, num_rows="dynamic", hide_index=True, width="stretch", key=f"pm_{pid}",
                                    column_config={
                                        "Mitarbeiter": st.column_config.SelectboxColumn(
                                            options=sorted(set(names) | set(df["Mitarbeiter"].dropna())), required=True),
                                        "Budget BT": st.column_config.NumberColumn(min_value=0.0, step=0.5, format="%.1f"),
                                        "Gebucht": st.column_config.NumberColumn("Gebucht (bis heute)", format="%.1f"),
                                        "Geplant": st.column_config.NumberColumn("Geplant (ab morgen)", format="%.1f"),
                                        "Offen": st.column_config.NumberColumn(format="%.1f")},
                                    disabled=["Gebucht", "Geplant", "Offen"])
                m1, m2, m3 = st.columns(3)
                s_ = m1.date_input("Start", r["start"] if pd.notna(r["start"]) else today, format="DD.MM.YYYY",
                                   key=f"ps_{pid}")
                e_ = m2.date_input("Ende", r["ende"] if pd.notna(r["ende"]) else today, format="DD.MM.YYYY",
                                   key=f"pe_{pid}")
                lnames = names if names else [""]
                cur = lmap.get(int(r["leiter_id"])) if pd.notna(r.get("leiter_id")) else None
                l_ = m3.selectbox("Projektleitung", lnames, index=lnames.index(cur) if cur in lnames else 0,
                                  format_func=lambda n: plab.get(n, n), key=f"pl_{pid}")
                bb1, bb2, _ = st.columns([1, 1.4, 3])
                if bb1.button("Speichern", type="primary", key=f"psave_{pid}"):
                    idmap = dict(zip(cons["name"], cons["id"]))
                    rows = [(idmap[x["Mitarbeiter"]], float(x["Budget BT"] or 0))
                            for _, x in ed.dropna(subset=["Mitarbeiter"]).drop_duplicates("Mitarbeiter").iterrows()
                            if x["Mitarbeiter"] in idmap]
                    db.set_members(int(pid), rows)
                    db.update_project_meta(int(pid), start=s_, ende=e_,
                                           leiter_id=idmap.get(l_) if l_ else None)
                    st.session_state.pop(f"pm_{pid}", None)
                    st.session_state["proj_msg"] = f"**{r['label']}** gespeichert."
                    st.rerun()
                if bb2.button("Projekt abschließen" if r["aktiv"] else "Wieder aktivieren", key=f"pa_{pid}"):
                    db.update_project_meta(int(pid), aktiv=not bool(r["aktiv"]))
                    st.rerun()


# ====================================================================== Seite: Auswertung
def auswertung_projekte() -> None:
    today = heute()
    proj = db.projects()
    stats = logic.project_stats(proj, db.entries(project_only=True), db.members(), today)
    if stats.empty:
        st.info("Noch keine Projekte angelegt.")
        return
    k = st.columns(4)
    k[0].metric("Budget gesamt", f"{bt(stats['budget'].sum())} BT")
    k[1].metric("Gebucht bis heute", f"{bt(stats['gebucht'].sum())} BT")
    k[2].metric("Geplant ab morgen", f"{bt(stats['geplant'].sum())} BT")
    k[3].metric("Offen", f"{bt(stats['offen'].clip(lower=0).sum())} BT",
                f"{bt(-stats['offen'].clip(upper=0).sum())} BT über Budget", delta_color="inverse")
    s = stats.sort_values("offen")
    fig = go.Figure([
        go.Bar(y=s["label"], x=s["gebucht"], name="Gebucht", orientation="h", marker_color=WP["navy"]),
        go.Bar(y=s["label"], x=s["geplant"], name="Geplant", orientation="h", marker_color=WP["mid"]),
        go.Bar(y=s["label"], x=s["offen"].clip(lower=0), name="Offen", orientation="h", marker_color=WP["light"]),
        go.Bar(y=s["label"], x=-s["offen"].clip(upper=0), name="Über Budget", orientation="h",
               marker_color=WP["alert"])])
    fig.update_layout(barmode="stack", xaxis_title="Beratertage")
    st.plotly_chart(plotly_layout(fig, 80 + 38 * len(s)), width="stretch")

    sub("Staffing je Projekt und Woche (Beratertage, nächste 12 Wochen)")
    m0 = logic.monday(today)
    e = db.entries(m0, m0 + dt.timedelta(weeks=12) - dt.timedelta(days=1), project_only=True)
    if not e.empty:
        e["woche"] = [logic.monday(d) for d in e["tag"]]
        e["projekt"] = e["project_id"].astype(int).map(db.projects(active_only=False).set_index("id")["label"])
        e["bt"] = e["stunden"] / H
        pv = e.pivot_table(index="projekt", columns="woche", values="bt", aggfunc="sum").fillna(0)
        pv.columns = [logic.week_label(c) for c in pv.columns]
        mx = max(pv.values.max(), 1)
        st.dataframe(pv.style.format("{:.1f}").map(lambda v: util_css(v / mx * 1.1) if v else ""),
                     width="stretch")


def page_auswertung() -> None:
    header("Auswertung", "Auslastung und Projektbudgets im Überblick")
    t1, t2 = st.tabs(["Auslastung", "Projekte & Budget"])
    with t1:
        auswertung_auslastung()
    with t2:
        auswertung_projekte()


# ====================================================================== Seite: Verwaltung
def page_verwaltung() -> None:
    header("Verwaltung", "Team, Kunden und Logos")
    t1, t2 = st.tabs(["Team", "Kunden & Logos"])
    with t1:
        anlegen_mitarbeiter()
    with t2:
        kunden_logos()


# ====================================================================== Wiederverwendete Bausteine
def client_picker(prefix: str):
    """Kunde tippen: bestehende Kunden werden erkannt, neue mit Logo-Vorschau angelegt.
    Rückgabe: (client_id | None, neuer_name | None, domain | None)."""
    cl = db.clients()
    kunde = st.selectbox("Kunde", cl["name"].tolist(), index=None, accept_new_options=True,
                         placeholder="Kundenname tippen", key=f"{prefix}_kunde")
    if not kunde:
        return None, None, None
    exact = cl[cl["name"] == kunde]
    if not exact.empty:
        r = exact.iloc[0]
    else:
        r = db.match_client(kunde)
    if r is not None:
        c1, c2 = st.columns([1, 12])
        c1.image(logo(r["name"], r["domain"], r["logo"]), width=36)
        if r["name"] != kunde:
            c2.success(f"Erkannt als **{r['name']}**")
        if not r["aktiv"]:
            db.save_table("clients", ["aktiv"], pd.DataFrame([{"id": r["id"], "aktiv": 1}]), pd.DataFrame({"id": []}))
        return int(r["id"]), None, None
    st.warning(f"Neuer Kunde: **{kunde}**. Domain prüfen, das Logo wird daraus gezogen.")
    c1, c2 = st.columns([1, 8])
    dom = c2.text_input("Website / Domain", db.guess_domain(kunde), key=f"{prefix}_dom")
    c1.image(logo(kunde, dom, None), width=36)
    return None, kunde, dom
STOPS = [(0.0, (255, 255, 255)), (0.5, (228, 228, 246)), (0.8, (187, 204, 238)),
         (1.0, (102, 136, 187)), (1.2, (0, 0, 85))]
def util_css(v) -> str:
    if v is None or pd.isna(v):
        return f"background-color:#F7F7F7;color:{WP['grey']}"
    v = max(0.0, min(float(v), 1.2))
    for (a, ca), (b, cb) in zip(STOPS, STOPS[1:]):
        if v <= b:
            t = (v - a) / (b - a) if b > a else 0
            rgb = tuple(int(ca[i] + (cb[i] - ca[i]) * t) for i in range(3))
            break
    txt = "#FFFFFF" if v >= 0.95 else WP["navy"]
    return f"background-color:rgb{rgb};color:{txt}"
def auswertung_auslastung() -> None:
    today = heute()
    c1, c2, c3 = st.columns([3, 2, 3])
    gran = c1.radio("Granularität", list(logic.GRANULARITAETEN), format_func=logic.GRANULARITAETEN.get,
                    horizontal=True)
    monate = c2.slider("Horizont (Monate)", 1, 6, 4)
    metrik = c3.radio("Kennzahl", ["Auslastung", "Vor-Ort-Quote", "Freie Tage"], horizontal=True)

    start = logic.monday(today) if gran != "Monat" else logic.month_start(today)
    end = logic.month_end(today, monate - 1)
    cons = db.consultants()
    fact = logic.build_fact(start, end, cons, db.entries(start, end))
    if fact.empty:
        st.info("Keine Daten im Zeitraum.")
        return
    team = logic.aggregate(fact, gran, today, by_consultant=False)
    pers = logic.aggregate(fact, gran, today, by_consultant=True)
    col = {"Auslastung": "auslastung", "Vor-Ort-Quote": "vor_ort_quote", "Freie Tage": "frei_tage"}[metrik]
    pct = col != "frei_tage"
    order = team["p_label"].tolist()

    auswahl = st.multiselect("Einzelne Berater einblenden", cons["name"].tolist(), placeholder="Team gesamt")
    fig = go.Figure()
    for i, name in enumerate(auswahl):
        d = pers[pers["name"] == name]
        fig.add_trace(go.Scatter(x=d["p_label"], y=d[col], name=name, mode="lines+markers",
                                 line=dict(color=SERIES[(i + 1) % len(SERIES)], width=2), marker=dict(size=5)))
    fig.add_trace(go.Scatter(x=team["p_label"], y=team[col], name="Team", mode="lines+markers",
                             line=dict(color=WP["navy"], width=4), marker=dict(size=8)))
    if col == "auslastung":
        fig.add_hline(y=ZIEL, line_dash="dash", line_color=WP["grey"],
                      annotation_text=f"Ziel {ZIEL:.0%}", annotation_font_color=WP["grey"])
    fig.update_xaxes(categoryorder="array", categoryarray=order)
    fig.update_yaxes(rangemode="tozero")
    st.plotly_chart(plotly_layout(fig, 400, pct), width="stretch")

    sub(f"{metrik} je Berater")
    pv = pers.pivot(index="name", columns="p_label", values=col)
    pv.index.name = "Berater"
    pv = pv.reindex(index=cons["name"].tolist(), columns=order)
    pv.index.name = "Berater"
    if pct:
        pv["Ø"] = [logic.kpi(fact[fact["name"] == n]) if col == "auslastung"
                   else logic.kpi(fact[fact["name"] == n], "vor_ort") for n in pv.index]
        sty = pv.style.map(util_css).format(lambda v: "Urlaub" if pd.isna(v) else fmt_pct(v))
    else:
        pv["Σ"] = pv.sum(axis=1)
        sty = pv.style.format("{:.1f}", na_rep="")
    st.dataframe(sty, width="stretch", height=38 + 35 * len(pv))

    sub("Freie Kapazität für Staffing (nächste 8 Wochen)")
    m0 = logic.monday(today)
    f8 = fact[(fact["tag"] >= today) & (fact["tag"] < m0 + dt.timedelta(weeks=8))]
    rows = []
    for name, g in f8.groupby("name", sort=False):
        frei = g[g["frei"] > 0]
        rows.append({"Berater": name, "Verfügbar BT": round(g["kapazitaet"].sum() / H, 1),
                     "Projekt BT": round(g["projekt"].sum() / H, 1), "Frei BT": round(g["frei"].sum() / H, 1),
                     "Auslastung": logic.kpi(g),
                     "Nächster freier Tag": frei["tag"].min() if not frei.empty else None,
                     "Freie Tage KW": ", ".join(sorted({f"{d.isocalendar().week:02d}" for d in frei["tag"]})[:6])})
    cap = pd.DataFrame(rows).sort_values("Frei BT", ascending=False)
    st.dataframe(cap, hide_index=True, width="stretch", column_config={
        "Auslastung": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "Nächster freier Tag": st.column_config.DateColumn(format="DD.MM.YYYY")})

    st.download_button("Rohdaten als CSV", fact.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name=f"auslastung_{today:%Y%m%d}.csv", mime="text/csv")
def kunden_logos() -> None:
    cl = db.clients(active_only=False)
    cl.insert(1, "vorschau", [logo(r.name, r.domain, r.logo) for r in cl.itertuples()])
    cl["aktiv"] = cl["aktiv"].astype(bool)
    ed = st.data_editor(cl.drop(columns=["logo"]), hide_index=True, width="stretch",
                        num_rows="dynamic", key="ed_clients", column_config={
                            "id": None,
                            "vorschau": st.column_config.ImageColumn("Logo", width="small"),
                            "name": st.column_config.TextColumn("Kunde", required=True),
                            "domain": st.column_config.TextColumn("Domain (für Logo)"),
                            "aliases": st.column_config.TextColumn("Aliasse (Komma getrennt)"),
                            "aktiv": st.column_config.CheckboxColumn("Aktiv")},
                        disabled=["vorschau"])
    if st.button("Kunden speichern", type="primary"):
        db.save_table("clients", ["name", "domain", "aliases", "aktiv"],
                      ed.assign(aktiv=ed["aktiv"].fillna(True).astype(int)), cl)
        st.session_state.pop("ed_clients", None)
        st.rerun()

    sub("Eigenes Logo hochladen (überschreibt automatisches Logo)")
    c1, c2 = st.columns(2)
    wahl = c1.selectbox("Kunde", cl["name"].tolist(), index=None, key="logo_kunde")
    up = c2.file_uploader("PNG, JPG oder SVG", type=["png", "jpg", "jpeg", "svg"])
    b1, b2 = st.columns([1, 5])
    if b1.button("Logo setzen", disabled=not (wahl and up)):
        mime = "image/svg+xml" if up.name.lower().endswith(".svg") else up.type
        db.set_logo(int(cl[cl["name"] == wahl]["id"].iloc[0]),
                    f"data:{mime};base64,{base64.b64encode(up.getvalue()).decode()}")
        st.rerun()
    if b2.button("Automatisches Logo wiederherstellen", disabled=not wahl):
        db.set_logo(int(cl[cl["name"] == wahl]["id"].iloc[0]), None)
        st.rerun()


def anlegen_mitarbeiter() -> None:
    cons_all = db.consultants(active_only=False)
    if not is_admin():
        admins = ", ".join(sorted(ADMINS)) or "Admin"
        st.info(f"Neue Mitarbeiter legt der Admin an ({admins}).")
        st.dataframe(db.consultants()[["name", "vollname", "rolle"]].map(_s), hide_index=True, width="stretch",
                     column_config={"name": "Kürzel", "vollname": "Name", "rolle": "Rolle"})
        return
    sub("Neuen Mitarbeiter anlegen")
    c1, c2, c3 = st.columns([1, 2, 2])
    kz = c1.text_input("Kürzel (Login)", key="nm_kz", max_chars=12, placeholder="z. B. abc")
    vn = c2.text_input("Vollständiger Name", key="nm_vn")
    ro = c3.selectbox("Rolle", ROLLEN, index=0, accept_new_options=True, key="nm_ro")
    exists = kz.strip().lower() in {str(x).lower() for x in cons_all["name"]}
    if exists:
        st.caption("Kürzel existiert bereits. Anlegen reaktiviert bzw. aktualisiert den Eintrag.")
    if st.button("Mitarbeiter anlegen", type="primary", disabled=not kz.strip(), key="nm_go"):
        _, neu = db.create_consultant(kz, vn.strip(), ro or "")
        for k in ("nm_kz", "nm_vn"):
            st.session_state.pop(k, None)
        st.session_state["nm_done"] = (f"**{kz.strip()}** {'angelegt' if neu else 'reaktiviert'}. "
                                       "Login ab sofort mit dem Team-Passwort möglich.")
        st.rerun()
    if st.session_state.get("nm_done"):
        st.success(st.session_state.pop("nm_done"))

    sub("Team bearbeiten")
    team_editor()

    with st.expander("Admin: Planungsdaten zurücksetzen (z. B. Demo-Daten vor dem Echtstart löschen)"):
        st.warning("Löscht **alle Buchungen, Projekte und Kunden** unwiderruflich. Das Team bleibt erhalten.")
        ok = st.text_input("Zur Bestätigung LÖSCHEN eintippen", key="reset_ok")
        if st.button("Alles zurücksetzen", disabled=ok != "LÖSCHEN", key="reset_go"):
            db.reset_planning()
            st.session_state.pop("reset_ok", None)
            st.success("Planungsdaten gelöscht.")
def team_editor() -> None:
    c = db.consultants(active_only=False)
    c["aktiv"] = c["aktiv"].astype(bool)
    c = c[["id", "name", "vollname", "rolle", "sort", "aktiv"]]
    for col in ("vollname", "rolle"):
        c[col] = c[col].map(_s)
    ed = st.data_editor(c, hide_index=True, width="stretch", num_rows="dynamic", key="ed_team",
                        column_config={"id": None,
                                       "name": st.column_config.TextColumn("Kürzel (Login)", required=True),
                                       "vollname": "Name",
                                       "rolle": st.column_config.SelectboxColumn("Rolle", options=ROLLEN),
                                       "sort": st.column_config.NumberColumn("Reihenfolge", step=1),
                                       "aktiv": st.column_config.CheckboxColumn("Aktiv")})
    if st.button("Team speichern", type="primary", key="team_save"):
        db.save_table("consultants", ["name", "vollname", "rolle", "sort", "aktiv"],
                      ed.assign(aktiv=ed["aktiv"].fillna(True).astype(int)), c)
        st.session_state.pop("ed_team", None)
        st.rerun()

# ====================================================================== Main
def main() -> None:
    try:
        init_once()
    except Exception as e:
        st.error("Datenbank nicht erreichbar. Bitte DATABASE_URL in den Secrets prüfen "
                 "(Supabase: Session Pooler Connection String verwenden; pausiertes Projekt wieder starten).")
        st.exception(e)
        st.stop()
    inject_css()
    extra_css()
    branding()
    if not login_gate():
        st.stop()
    pg = st.navigation([
        st.Page(page_kalender, title="Mein Kalender", icon=":material/calendar_month:", default=True),
        st.Page(page_team, title="Team", icon=":material/grid_view:"),
        st.Page(page_projekte, title="Projekte", icon=":material/work:"),
        st.Page(page_auswertung, title="Auswertung", icon=":material/monitoring:"),
        st.Page(page_verwaltung, title="Verwaltung", icon=":material/settings:"),
    ])
    with st.sidebar:
        st.caption(f"Angemeldet als **{st.session_state.get('user_label', st.session_state.user)}**"
                   f"{' (Admin)' if is_admin() and ADMINS else ''}"
                   f"  \nDatenbank: {db.backend()}")
        if st.button("Abmelden"):
            st.session_state.clear()
            st.rerun()
    pg.run()


main()
