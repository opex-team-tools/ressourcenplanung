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
            name = st.selectbox("Kürzel", names, index=None, placeholder="Kürzel wählen")
            pw = st.text_input("Team-Passwort", type="password")
            if st.form_submit_button("Anmelden", type="primary"):
                if name and hmac.compare_digest(str(TEAM_PW), pw):
                    st.session_state.user = name
                    st.rerun()
                time.sleep(1.5)  # bremst Durchprobieren
                st.error("Kürzel oder Passwort falsch.")
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
        name = st.selectbox("Name", list(u.keys()), index=None)
        pw = st.text_input("Passwort", type="password")
        if st.form_submit_button("Anmelden", type="primary"):
            if name and hmac.compare_digest(str(u.get(name, "")), pw):
                st.session_state.user = name
                st.rerun()
            time.sleep(1.5)
            st.error("Name oder Passwort falsch.")
    return False


# ====================================================================== Gemeinsame Bausteine
def label_maps(proj: pd.DataFrame):
    """Zellenlabel <-> (art, project_id) für den Editor."""
    to_key, to_label = {}, {}
    for r in proj.itertuples():
        to_key[r.label] = ("Vor Ort", r.id)
        to_key[f"{r.label} (remote)"] = ("Remote", r.id)
        to_label[("Vor Ort", r.id)] = r.label
        to_label[("Remote", r.id)] = f"{r.label} (remote)"
    for a in logic.SONST_ARTEN:
        to_key[a] = (a, None)
        to_label[(a, None)] = a
    return to_key, to_label


def client_logo_map(proj_all: pd.DataFrame) -> dict:
    return {r.id: logo(r.kunde, r.domain, r.logo) for r in proj_all.itertuples()}


def week_days(ws: dt.date) -> list[dt.date]:
    return [ws + dt.timedelta(days=i) for i in range(5)]


# ====================================================================== Seite 1: Wochenmatrix
def render_matrix(ws: dt.date) -> str:
    today = heute()
    days = week_days(ws)
    cons = db.consultants()
    bk = db.bookings(days[0], days[-1])
    proj = db.projects(active_only=False).set_index("id")
    logos = client_logo_map(proj.reset_index())
    bmap = {(r.consultant_id, r.tag): r for r in bk.itertuples()}
    fact = logic.build_fact(days[0], days[-1], cons, bk)
    util = fact.groupby("consultant_id").apply(
        lambda g: g["projekt"].sum() / g["kapazitaet"].sum() if g["kapazitaet"].sum() else None,
        include_groups=False).to_dict() if not fact.empty else {}

    head = "<tr><th class='name'>Berater</th>"
    for d in days:
        cls = " class='today'" if d == today else ""
        head += f"<th{cls}>{logic.day_label(d)}</th>"
    head += "<th class='util'>Auslastung KW</th></tr>"

    rows = ""
    for c in cons.itertuples():
        rows += (f"<tr><td class='name'>{html.escape(c.name)}"
                 f"<span>{html.escape(_s(c.vollname) or _s(c.rolle))}</span></td>")
        for d in days:
            today_cls = " today-col" if d == today else ""
            hol = logic.feiertag_name(d)
            b = bmap.get((c.id, d))
            if b is None:
                if hol:
                    rows += f"<td class='c-hol{today_cls}' title='{html.escape(hol)}'>{html.escape(hol)}</td>"
                else:
                    rows += f"<td class='c-free{today_cls}'>frei</td>"
                continue
            tip = f"zuletzt: {b.updated_by or ''} {str(b.updated_at or '')[:16].replace('T', ' ')}"
            if b.art in logic.PROJEKT_ARTEN and pd.notna(b.project_id) and int(b.project_id) in proj.index:
                p = proj.loc[int(b.project_id)]
                cls = "c-onsite" if b.art == "Vor Ort" else "c-remote"
                art_txt = "" if b.art == "Vor Ort" else " · remote"
                rows += (f"<td class='{cls}{today_cls}' title='{html.escape(p['label'])} · {b.art} · {html.escape(tip)}'>"
                         f"<img class='lg' src='{logos[int(b.project_id)]}'>"
                         f"<span class='cl'>{html.escape(p['kunde'])}</span>"
                         f"<span class='pj'>{html.escape(p['name'])}{art_txt}</span></td>")
            elif b.art in logic.ABWESEND_ARTEN:
                rows += f"<td class='c-absent{today_cls}' title='{html.escape(tip)}'>{b.art}</td>"
            else:
                rows += f"<td class='c-intern{today_cls}' title='{html.escape(tip)}'>{b.art}</td>"
        u = util.get(c.id)
        w = 0 if u is None else min(u, 1) * 100
        rows += (f"<td class='util'><b>{fmt_pct(u)}</b><div class='ubar'><div style='width:{w:.0f}%'></div></div></td>"
                 "</tr>")
    legend = (f"<div class='legend'><span style='background:{WP['lilac']};border:1px solid {WP['light']}'>Vor Ort</span>"
              f"<span style='border:1px dashed {WP['mid']}'>Remote</span>"
              f"<span style='background:{WP['xlgrey']}'>Intern / Akquise</span>"
              f"<span style='background:#EEE'>Urlaub / Krank</span>"
              f"<span style='border:1px solid {WP['xlgrey']}'>frei</span></div>")
    return f"<table class='wpm'>{head}{rows}</table>{legend}"


@st.fragment(run_every=60)
def matrix_live(ws: dt.date) -> None:
    st.markdown(render_matrix(ws), unsafe_allow_html=True)
    st.caption(f"Live-Ansicht, aktualisiert {dt.datetime.now():%H:%M:%S} (automatisch alle 60 Sekunden)")


def shift_week(n: int) -> None:
    st.session_state.kw_offset = 0 if n == 0 else st.session_state.get("kw_offset", 0) + n


def page_cockpit() -> None:
    today = heute()
    st.session_state.setdefault("kw_offset", 0)
    ws = logic.monday(today) + dt.timedelta(weeks=st.session_state.kw_offset)
    we = ws + dt.timedelta(days=4)
    header("Wochenmatrix", f"Wer ist in KW {ws.isocalendar().week:02d} bei welchem Kunden")

    cons = db.consultants()
    f_week = logic.build_fact(ws, we, cons, db.bookings(ws, we))
    m0 = logic.monday(today)
    f_4w = logic.build_fact(m0, m0 + dt.timedelta(days=27), cons, db.bookings(m0, m0 + dt.timedelta(days=27)))
    b_today = db.bookings(today, today)
    vor_ort_heute = int((b_today["art"] == "Vor Ort").sum())
    stats = logic.project_stats(db.projects(), db.bookings(project_only=True), today)
    u_w, u_4 = logic.kpi(f_week), logic.kpi(f_4w)

    k = st.columns(5)
    k[0].metric("Auslastung KW", fmt_pct(u_w),
                None if u_w is None else f"{(u_w - ZIEL) * 100:+.0f} pp vs. Ziel {ZIEL:.0%}")
    k[1].metric("Heute vor Ort", f"{vor_ort_heute} / {len(cons)}")
    k[2].metric("Auslastung nächste 4 Wochen", fmt_pct(u_4),
                None if u_4 is None else f"{(u_4 - ZIEL) * 100:+.0f} pp vs. Ziel")
    k[3].metric("Freie Beratertage 4 Wochen", f"{int(f_4w['frei'].sum()) if not f_4w.empty else 0}")
    k[4].metric("Ungeplante Projekttage", f"{int(stats['ungeplant'].clip(lower=0).sum())}",
                f"{int((stats['status'] == 'Überplant').sum())} Projekte überplant", delta_color="off")

    n = st.columns([1, 1, 1, 7])
    n[0].button("◀ Woche", on_click=shift_week, args=(-1,), width="stretch")
    n[1].button("Heute", on_click=shift_week, args=(0,), width="stretch")
    n[2].button("Woche ▶", on_click=shift_week, args=(1,), width="stretch")
    n[3].markdown(f"**KW {ws.isocalendar().week:02d}** &nbsp; {ws:%d.%m.} bis {we:%d.%m.%Y}")

    matrix_live(ws)

    c1, c2 = st.columns([3, 2])
    with c1:
        sub("Kundenpräsenz dieser Woche (Beratertage)")
        f = f_week[f_week["projekt"] == 1]
        if f.empty:
            st.caption("Keine Projekttage in dieser Woche.")
        else:
            proj = db.projects(active_only=False).set_index("id")
            f = f.assign(kunde=f["project_id"].astype(int).map(proj["kunde"]))
            g = f.groupby("kunde").agg(vor_ort=("vor_ort", "sum"), gesamt=("projekt", "sum")).reset_index()
            g["remote"] = g["gesamt"] - g["vor_ort"]
            g = g.sort_values("gesamt")
            fig = go.Figure([
                go.Bar(y=g["kunde"], x=g["vor_ort"], name="Vor Ort", orientation="h", marker_color=WP["navy"]),
                go.Bar(y=g["kunde"], x=g["remote"], name="Remote", orientation="h", marker_color=WP["light"])])
            fig.update_layout(barmode="stack")
            st.plotly_chart(plotly_layout(fig, height=60 + 32 * len(g)), width="stretch")
    with c2:
        sub("Letzte Änderungen")
        ch = db.recent_changes(12)
        if not ch.empty:
            ch["zeitpunkt"] = pd.to_datetime(ch["zeitpunkt"]).dt.strftime("%d.%m. %H:%M")
            ch["eintrag"] = ch["kunde"].fillna(ch["art"])
            st.dataframe(ch[["zeitpunkt", "von", "berater", "tag", "eintrag"]], hide_index=True,
                         width="stretch", height=300,
                         column_config={"tag": st.column_config.DateColumn("Tag", format="DD.MM.")})


# ====================================================================== Seite 2: Erfassen
def tab_woche(user: str) -> None:
    today = heute()
    picked = st.date_input("Woche wählen (beliebiger Tag)", today, format="DD.MM.YYYY", key="edit_week")
    ws = logic.monday(picked)
    days = week_days(ws)
    cons = db.consultants()
    proj_active = db.projects()
    proj_all = db.projects(active_only=False)
    to_key, _ = label_maps(proj_active)
    _, to_label_all = label_maps(proj_all)
    bk = db.bookings(days[0], days[-1])
    bmap = {(r.consultant_id, r.tag): (r.art, None if pd.isna(r.project_id) else int(r.project_id))
            for r in bk.itertuples()}

    cols = {}
    for d in days:
        hol = logic.feiertag_name(d)
        cols[d] = logic.day_label(d) + (" (Feiertag)" if hol else "")
    data = {"Berater": cons["name"].tolist()}
    for d, lbl in cols.items():
        data[lbl] = [to_label_all.get(bmap.get((cid, d)), None) for cid in cons["id"]]
    original = pd.DataFrame(data)

    options = [""] + list(to_key.keys())
    extra = {v for c in cols.values() for v in original[c].dropna() if v not in to_key}
    options += sorted(extra)
    cfg = {"Berater": st.column_config.TextColumn(disabled=True, width="small")}
    for lbl in cols.values():
        cfg[lbl] = st.column_config.SelectboxColumn(lbl, options=options, width="medium")

    st.caption("Zelle anklicken, Kunde | Projekt wählen. Mehrere Zellen per Copy & Paste füllbar. "
               "Gespeichert werden nur geänderte Zellen, parallele Änderungen anderer bleiben erhalten.")
    key = f"editor_{ws.isoformat()}"
    edited = st.data_editor(original, column_config=cfg, hide_index=True, width="stretch",
                            num_rows="fixed", key=key, height=38 + 35 * len(original))

    if st.button("Änderungen speichern", type="primary"):
        key_all = {**{v: k for k, v in to_label_all.items()}, **to_key}
        changes = []
        for i, cid in enumerate(cons["id"]):
            for d, lbl in cols.items():
                old, new = original.at[i, lbl], edited.at[i, lbl]
                old = old if isinstance(old, str) and old else None
                new = new if isinstance(new, str) and new else None
                if old != new:
                    art, pid = key_all.get(new, (None, None)) if new else (None, None)
                    changes.append((int(cid), d, art, pid))
        if changes:
            db.write_cells(changes, user)
            st.session_state.pop(key, None)
            st.toast(f"{len(changes)} Zellen gespeichert")
            st.rerun()
        else:
            st.toast("Keine Änderungen")


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


def tab_zeitraum(user: str) -> None:
    today = heute()
    cons = db.consultants()
    names = cons["name"].tolist()
    sel = st.multiselect("Berater", names, default=[user] if user in names else [])
    c1, c2, c3, c4 = st.columns([2, 2, 3, 2])
    von = c1.date_input("Von", today, format="DD.MM.YYYY", key="z_von")
    bis = c2.date_input("Bis", today + dt.timedelta(days=27), format="DD.MM.YYYY", key="z_bis")
    wt = c3.multiselect("Wochentage", logic.WOTAG[:5], default=logic.WOTAG[:4], key="z_wt")
    rh = c4.selectbox("Rhythmus", list(logic.RHYTHMEN), key="z_rh")
    art = st.radio("Art", ["Vor Ort", "Remote", "Intern", "Akquise", "Urlaub"], horizontal=True)

    cid, new_name, dom, projekt = None, None, None, None
    if art in logic.PROJEKT_ARTEN:
        cid, new_name, dom = client_picker("z")
        if cid or new_name:
            p = db.projects()
            plist = p[p["client_id"] == cid]["name"].tolist() if cid else []
            projekt = st.selectbox("Projekt", plist, index=0 if plist else None, accept_new_options=True,
                                   placeholder="Projektname tippen", key="z_proj")
    overwrite = st.checkbox("Bestehende Einträge überschreiben", value=True)

    days = logic.plan_days(von, bis, wt, logic.RHYTHMEN[rh])
    n = len(days) * len(sel)
    st.caption(f"{len(days)} Arbeitstage × {len(sel)} Berater = {n} Einträge "
               f"(Rhythmus: {rh}, Feiertage Bayern ausgenommen)")
    ready = n > 0 and (art not in logic.PROJEKT_ARTEN or ((cid or new_name) and projekt))
    if st.button("Buchen", type="primary", disabled=not ready):
        if new_name:
            cid = db.create_client(new_name, dom)
        pid = db.ensure_project(cid, projekt) if art in logic.PROJEKT_ARTEN else None
        ids = cons[cons["name"].isin(sel)]["id"].tolist()
        written = db.bulk_book(ids, days, art, pid, user, overwrite)
        st.success(f"{written} Einträge gebucht.")


def tab_freigeben() -> None:
    cons = db.consultants()
    sel = st.multiselect("Berater", cons["name"].tolist(), key="f_sel")
    c1, c2 = st.columns(2)
    von = c1.date_input("Von", heute(), format="DD.MM.YYYY", key="f_von")
    bis = c2.date_input("Bis", heute() + dt.timedelta(days=4), format="DD.MM.YYYY", key="f_bis")
    if st.button("Zeitraum freigeben", disabled=not sel or von > bis):
        n = db.clear_range(cons[cons["name"].isin(sel)]["id"].tolist(), von, bis)
        st.success(f"{n} Einträge entfernt.")


def page_erfassen() -> None:
    header("Erfassen", "Einsätze in Sekunden eintragen, jeder für jeden")
    user = st.session_state.user
    t1, t2, t3 = st.tabs(["Woche bearbeiten", "Zeitraum buchen", "Zeitraum freigeben"])
    with t1:
        tab_woche(user)
    with t2:
        tab_zeitraum(user)
    with t3:
        tab_freigeben()


# ====================================================================== Seite: Anlegen
def anlegen_projekt(user: str) -> None:
    today = heute()
    cons = db.consultants()
    names = cons["name"].tolist()
    sub("1 | Kunde und Projekt")
    cid, new_name, dom = client_picker("np")
    c1, c2 = st.columns([3, 1])
    pname = c1.text_input("Projektname", key="np_name", placeholder="z. B. Footprint Analyse")
    budget = c2.number_input("Budget (Beratertage)", min_value=0, step=5, value=0, key="np_budget")
    c3, c4 = st.columns(2)
    start = c3.date_input("Start", today, format="DD.MM.YYYY", key="np_start")
    ende = c4.date_input("Ende", today + dt.timedelta(days=90), format="DD.MM.YYYY", key="np_ende")

    sub("2 | Team direkt einplanen (optional)")
    sel = st.multiselect("Berater", names, default=[user] if user in names else [], key="np_sel")
    c5, c6, c7 = st.columns([3, 2, 2])
    wt = c5.multiselect("Wochentage", logic.WOTAG[:5], default=logic.WOTAG[:4], key="np_wt")
    rh = c6.selectbox("Rhythmus", list(logic.RHYTHMEN), key="np_rh")
    art = c7.radio("Art", ["Vor Ort", "Remote"], horizontal=True, key="np_art")
    overwrite = st.checkbox("Bestehende Einträge überschreiben", value=False, key="np_ow",
                            help="Aus: bereits belegte Tage (z. B. Urlaub, anderes Projekt) bleiben unverändert.")

    days = logic.plan_days(start, ende, wt, logic.RHYTHMEN[rh]) if sel else []
    n = len(days) * len(sel)
    if start > ende:
        st.error("Das Ende liegt vor dem Start.")
    elif sel:
        txt = f"{len(days)} Tage je Berater × {len(sel)} Berater = **{n} Beratertage** (Rhythmus: {rh})"
        if budget:
            diff = budget - n
            txt += (f" · Budget {budget} BT, davon **{diff} BT noch offen**" if diff >= 0
                    else f" · **{-diff} BT über Budget**")
        st.markdown(txt)

    ready = bool((cid or new_name) and pname.strip() and start <= ende)
    label = "Projekt anlegen und einplanen" if n else "Projekt anlegen"
    if st.button(label, type="primary", disabled=not ready, key="np_go"):
        if new_name:
            cid = db.create_client(new_name, dom)
        pid = db.ensure_project(cid, pname)
        db.update_project_meta(pid, float(budget) if budget else None, start, ende)
        written = 0
        if n:
            ids = cons[cons["name"].isin(sel)]["id"].tolist()
            written = db.bulk_book(ids, days, art, pid, user, overwrite)
        for k in ("np_kunde", "np_dom", "np_name", "np_budget"):
            st.session_state.pop(k, None)
        st.session_state["np_done"] = f"Projekt **{pname.strip()}** angelegt" + (f", {written} Tage eingeplant." if n else ".")
        if n and written < n:
            st.session_state["np_skip"] = (f"{n - written} Tage waren bereits belegt (z. B. Urlaub oder anderes Projekt) "
                                           "und wurden nicht überschrieben. Bei Bedarf mit Haken "
                                           "\"Bestehende Einträge überschreiben\" erneut einplanen.")
        st.rerun()
    if st.session_state.get("np_done"):
        st.success(st.session_state.pop("np_done"))
    if st.session_state.get("np_skip"):
        st.warning(st.session_state.pop("np_skip"))


def anlegen_kunde() -> None:
    c1, c2 = st.columns(2)
    name = c1.text_input("Kundenname", key="nk_name", placeholder="z. B. Musterwerk GmbH")
    guess = db.guess_domain(name) if name else ""
    dom = c2.text_input("Website / Domain (für das Logo)", key="nk_dom", placeholder=guess or "kunde.de")
    ali = st.text_input("Aliasse (optional, Komma getrennt)", key="nk_ali",
                        help="Kurzformen, unter denen Kollegen den Kunden eintippen, z. B. MW, Musterwerk")
    domain = (dom or guess).strip()
    treffer = db.match_client(name) if name.strip() else None
    if name.strip():
        c3, c4 = st.columns([1, 12])
        if treffer is not None:
            c3.image(logo(treffer["name"], treffer["domain"], treffer["logo"]), width=36)
            c4.info(f"Existiert bereits als **{treffer['name']}**. Kein neuer Kunde nötig.")
        else:
            c3.image(logo(name, domain, None), width=36)
            c4.caption("Logo-Vorschau. Passt das Logo nicht, Domain anpassen oder später unter Stammdaten ein Logo hochladen.")
    if st.button("Kunde anlegen", type="primary", disabled=not name.strip() or treffer is not None, key="nk_go"):
        db.create_client(name, domain, ali)
        for k in ("nk_name", "nk_dom", "nk_ali"):
            st.session_state.pop(k, None)
        st.session_state["nk_done"] = f"Kunde **{name.strip()}** angelegt."
        st.rerun()
    if st.session_state.get("nk_done"):
        st.success(st.session_state.pop("nk_done"))


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


def page_anlegen() -> None:
    header("Anlegen", "Neue Projekte, Kunden und Mitarbeiter in einem Schritt")
    user = st.session_state.user
    t1, t2, t3 = st.tabs(["Neues Projekt", "Neuer Kunde", "Mitarbeiter"])
    with t1:
        anlegen_projekt(user)
    with t2:
        anlegen_kunde()
    with t3:
        anlegen_mitarbeiter()


# ====================================================================== Seite 3: Auslastung
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


def page_auslastung() -> None:
    today = heute()
    header("Auslastung", "Wie voll ist das Team in den nächsten Monaten")
    c1, c2, c3 = st.columns([3, 2, 3])
    gran = c1.radio("Granularität", list(logic.GRANULARITAETEN), format_func=logic.GRANULARITAETEN.get,
                    horizontal=True)
    monate = c2.slider("Horizont (Monate)", 1, 6, 4)
    metrik = c3.radio("Kennzahl", ["Auslastung", "Vor-Ort-Quote", "Freie Tage"], horizontal=True)

    start = logic.monday(today) if gran != "Monat" else logic.month_start(today)
    end = logic.month_end(today, monate - 1)
    cons = db.consultants()
    fact = logic.build_fact(start, end, cons, db.bookings(start, end))
    if fact.empty:
        st.info("Keine Daten im Zeitraum.")
        return
    team = logic.aggregate(fact, gran, today, by_consultant=False)
    pers = logic.aggregate(fact, gran, today, by_consultant=True)
    col = {"Auslastung": "auslastung", "Vor-Ort-Quote": "vor_ort_quote", "Freie Tage": "frei"}[metrik]
    pct = col != "frei"
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
        sty = pv.style.format("{:.0f}", na_rep="")
    st.dataframe(sty, width="stretch", height=38 + 35 * len(pv))

    sub("Freie Kapazität für Staffing (nächste 8 Wochen)")
    m0 = logic.monday(today)
    f8 = fact[(fact["tag"] >= today) & (fact["tag"] < m0 + dt.timedelta(weeks=8))]
    rows = []
    for name, g in f8.groupby("name", sort=False):
        frei = g[g["frei"] > 0]
        rows.append({"Berater": name, "Verfügbar": int(g["kapazitaet"].sum()),
                     "Projekt": int(g["projekt"].sum()), "Frei": int(g["frei"].sum()),
                     "Auslastung": logic.kpi(g),
                     "Nächster freier Tag": frei["tag"].min() if not frei.empty else None,
                     "Freie Tage KW": ", ".join(sorted({f"{d.isocalendar().week:02d}" for d in frei["tag"]})[:6])})
    cap = pd.DataFrame(rows).sort_values("Frei", ascending=False)
    st.dataframe(cap, hide_index=True, width="stretch", column_config={
        "Auslastung": st.column_config.ProgressColumn(format="percent", min_value=0, max_value=1),
        "Nächster freier Tag": st.column_config.DateColumn(format="DD.MM.YYYY")})

    st.download_button("Rohdaten als CSV", fact.to_csv(index=False, sep=";").encode("utf-8-sig"),
                       file_name=f"auslastung_{today:%Y%m%d}.csv", mime="text/csv")


# ====================================================================== Seite 4: Projekte
def page_projekte() -> None:
    today = heute()
    header("Projekte", "Wie viele Beratertage sind je Projekt noch offen")
    proj = db.projects()
    stats = logic.project_stats(proj, db.bookings(project_only=True), today)
    if stats.empty:
        st.info("Noch keine Projekte angelegt.")
        return
    stats["logo_url"] = [logo(r.kunde, r.domain, r.logo) for r in stats.itertuples()]

    k = st.columns(4)
    k[0].metric("Budget gesamt", f"{int(stats['budget_tage'].sum())} BT")
    k[1].metric("Verbraucht", f"{int(stats['verbraucht'].sum())} BT")
    k[2].metric("Eingeplant (Zukunft)", f"{int(stats['eingeplant'].sum())} BT")
    k[3].metric("Ungeplant (offen)", f"{int(stats['ungeplant'].clip(lower=0).sum())} BT",
                f"{int(-stats['ungeplant'].clip(upper=0).sum())} BT überplant", delta_color="inverse")

    s = stats.sort_values("ungeplant")
    fig = go.Figure([
        go.Bar(y=s["label"], x=s["verbraucht"], name="Verbraucht", orientation="h", marker_color=WP["navy"]),
        go.Bar(y=s["label"], x=s["eingeplant"], name="Eingeplant", orientation="h", marker_color=WP["mid"]),
        go.Bar(y=s["label"], x=s["ungeplant"].clip(lower=0), name="Ungeplant", orientation="h",
               marker_color=WP["light"]),
        go.Bar(y=s["label"], x=-s["ungeplant"].clip(upper=0), name="Überplant", orientation="h",
               marker_color=WP["alert"])])
    fig.update_layout(barmode="stack", xaxis_title="Beratertage")
    st.plotly_chart(plotly_layout(fig, 80 + 38 * len(s)), width="stretch")

    sub("Projektübersicht")
    view = stats[["logo_url", "kunde", "name", "budget_tage", "verbraucht", "eingeplant", "ungeplant",
                  "fortschritt", "ende", "status", "team"]]
    st.dataframe(view.sort_values(["status", "kunde"]), hide_index=True, width="stretch",
                 column_config={
                     "logo_url": st.column_config.ImageColumn("", width="small"),
                     "kunde": "Kunde", "name": "Projekt",
                     "budget_tage": st.column_config.NumberColumn("Budget BT", format="%d"),
                     "verbraucht": st.column_config.NumberColumn("Verbraucht", format="%d"),
                     "eingeplant": st.column_config.NumberColumn("Eingeplant", format="%d"),
                     "ungeplant": st.column_config.NumberColumn("Offen", format="%d"),
                     "fortschritt": st.column_config.ProgressColumn("Burn", format="percent",
                                                                    min_value=0, max_value=1),
                     "ende": st.column_config.DateColumn("Ende", format="DD.MM.YYYY"),
                     "status": "Status", "team": "Team"})

    sub("Staffing je Projekt und Woche (Beratertage, nächste 12 Wochen)")
    m0 = logic.monday(today)
    bk = db.bookings(m0, m0 + dt.timedelta(weeks=12) - dt.timedelta(days=1), project_only=True)
    if not bk.empty:
        bk["woche"] = [logic.monday(d) for d in bk["tag"]]
        lab = proj.set_index("id")["label"]
        bk["projekt"] = bk["project_id"].astype(int).map(lab)
        pv = bk.pivot_table(index="projekt", columns="woche", values="tag", aggfunc="count").fillna(0)
        pv.columns = [logic.week_label(c) for c in pv.columns]
        mx = max(pv.values.max(), 1)
        st.dataframe(pv.style.format("{:.0f}").map(lambda v: util_css(v / mx * 1.1) if v else ""),
                     width="stretch")


# ====================================================================== Seite 5: Stammdaten
def page_stammdaten() -> None:
    header("Stammdaten", "Team, Kunden, Logos und Projektbudgets")
    t1, t2, t3 = st.tabs(["Kunden & Logos", "Projekte", "Team"])

    with t1:
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

    with t2:
        p = db.projects(active_only=False)
        cl = db.clients(active_only=False)
        p["aktiv"] = p["aktiv"].astype(bool)
        view = p[["id", "kunde", "name", "budget_tage", "start", "ende", "aktiv"]]
        ed = st.data_editor(view, hide_index=True, width="stretch", num_rows="dynamic",
                            key="ed_projects", column_config={
                                "id": None,
                                "kunde": st.column_config.SelectboxColumn("Kunde", options=cl["name"].tolist(),
                                                                          required=True),
                                "name": st.column_config.TextColumn("Projekt", required=True),
                                "budget_tage": st.column_config.NumberColumn("Budget (BT)", min_value=0, step=5),
                                "start": st.column_config.DateColumn("Start", format="DD.MM.YYYY"),
                                "ende": st.column_config.DateColumn("Ende", format="DD.MM.YYYY"),
                                "aktiv": st.column_config.CheckboxColumn("Aktiv")})
        if st.button("Projekte speichern", type="primary"):
            cmap = dict(zip(cl["name"], cl["id"]))
            ed = ed.dropna(subset=["kunde", "name"]).copy()
            ed["client_id"] = ed["kunde"].map(cmap)
            ed["aktiv"] = ed["aktiv"].fillna(True).astype(int)
            db.save_table("projects", ["name", "client_id", "budget_tage", "start", "ende", "aktiv"], ed, p)
            st.session_state.pop("ed_projects", None)
            st.rerun()

    with t3:
        if is_admin():
            team_editor()
        else:
            st.info("Das Team pflegt der Admin.")
            st.dataframe(db.consultants()[["name", "vollname", "rolle"]].map(_s), hide_index=True, width="stretch",
                         column_config={"name": "Kürzel", "vollname": "Name", "rolle": "Rolle"})


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
                 "(Supabase: Session Pooler Connection String verwenden).")
        st.exception(e)
        st.stop()
    inject_css()
    branding()
    if not login_gate():
        st.stop()
    pg = st.navigation([
        st.Page(page_cockpit, title="Wochenmatrix", icon=":material/grid_view:", default=True),
        st.Page(page_anlegen, title="Anlegen", icon=":material/add_circle:"),
        st.Page(page_erfassen, title="Erfassen", icon=":material/edit_calendar:"),
        st.Page(page_auslastung, title="Auslastung", icon=":material/monitoring:"),
        st.Page(page_projekte, title="Projekte", icon=":material/work:"),
        st.Page(page_stammdaten, title="Stammdaten", icon=":material/settings:"),
    ])
    with st.sidebar:
        st.caption(f"Angemeldet als **{st.session_state.user}**{' (Admin)' if is_admin() and ADMINS else ''}"
                   f"  \nDatenbank: {db.backend()}")
        if st.button("Abmelden"):
            st.session_state.clear()
            st.rerun()
    pg.run()


main()
