# Ressourcenplanung | Operations Team

Streamlit App: Wer ist wann bei welchem Kunden, Auslastung 4 Monate voraus, offene Projekttage.

## Start lokal
```
pip install -r requirements.txt
streamlit run app.py
```
Beim ersten Start wird `data/capa.db` mit Demo-Daten angelegt. Für einen sauberen Start: `data/` löschen und in `db.py` `init_db(seed=False)` setzen.

## Pilot auf Streamlit Community Cloud mit Supabase
1. Supabase Projekt anlegen (Region Frankfurt), unter "Connect" den **Session pooler** Connection String kopieren.
2. Privates GitHub Repo, Inhalt dieses Ordners hochladen (ohne secrets.toml).
3. share.streamlit.io: Deploy from GitHub, Main file `app.py`, Python 3.12, Secrets aus `.streamlit/secrets.toml.example` befüllen.
4. Nach dem Deploy: Settings > Sharing > nur eingeladene Personen.
Echtbetrieb mit `DEMO_DATEN = "false"` und neuer leerer Datenbank (oder Tabellen in Supabase leeren).

## Zugänge
`.streamlit/secrets.toml.example` nach `.streamlit/secrets.toml` kopieren, Namen und Passwörter eintragen. Ohne Datei läuft Demo-Modus.

## Firmenlogo
Logo als `assets/wp_logo.png` ablegen, es erscheint automatisch oben links. Ohne Datei wird eine Wortmarke angezeigt.

## Kundenlogos
Reihenfolge: hochgeladenes Logo (Stammdaten) > logo.dev (Token in secrets) > Favicon über Domain > Initialen-Badge. Logos werden serverseitig 7 Tage gecacht.

## Struktur
- `app.py`    Oberfläche (Wochenmatrix, Erfassen, Auslastung, Projekte, Stammdaten)
- `logic.py`  Kalender (Feiertage Bayern), Aggregation Tag/Woche/Monat/Hybrid, Projektkennzahlen
- `db.py`     Persistenz (SQLite). Für Mehrbenutzerbetrieb auf Server: auf Postgres umstellen, nur diese Datei betroffen.
