#!/usr/bin/env python3
# energietools demo gallery — build script
# SPDX-License-Identifier: MIT
"""Baut die statische marimo/WASM-Demo-Gallery für GitHub Pages (energietools.at).

Schritte:
  1. energietools-Wheel frisch aus dem Repo bauen.
  2. Jede Demo nach ``site/<slug>/`` als selbst-enthaltenes WASM-Bundle exportieren.
  3. EIN gemeinsames Wheel nach ``site/wheels/`` (root-relative von jeder App geladen).
  4. Landing-Page ``site/index.html`` + ``CNAME`` + ``.nojekyll`` schreiben.

Aufruf:  python demos/build_site.py  [--outdir site]  [--skip-wheel]
Die Demos laden ausschließlich die MIT-Library energietools + ihre Daten-Snapshots —
kein Server, kein proprietärer gridbert-Code.
"""

from __future__ import annotations

import argparse
import glob
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
DEMOS = REPO / "demos"
WHEEL_VERSION = "0.3.0"
DOMAIN = "energietools.at"

# Reihenfolge = Anzeigereihenfolge auf der Landing-Page.
# ``author`` macht sichtbar, dass verschiedene Autor:innen Apps in dieselbe Gallery
# publizieren können — neue Autor:innen brauchen nur einen Eintrag + ihre marimo-Datei.
APPS = [
    {
        "slug": "rechnung",
        "file": "rechnung.py",
        "emoji": "🧾",
        "title": "Rechnungs-Röntgen",
        "tagline": "Stromrechnung in Energie / Netz / Abgaben / USt zerlegt — mit Tarifvergleich.",
        "author": "Ben Mörzinger",
    },
    {
        "slug": "spot",
        "file": "spot.py",
        "emoji": "⚡",
        "title": "Spot-Eignungs-Check",
        "tagline": "Lohnt sich ein dynamischer Tarif für dein Lastprofil? Backtest gegen EPEX 2025.",
        "author": "Ben Mörzinger",
    },
    {
        "slug": "speicher",
        "file": "speicher.py",
        "emoji": "🔋",
        "title": "Speicher-Sizing",
        "tagline": "PV-Batteriegröße mit echtem Dispatch und auditierbarem ROI (NPV/Amortisation).",
        "author": "Ben Mörzinger",
    },
    {
        "slug": "netzkosten",
        "file": "netzkosten.py",
        "emoji": "🔌",
        "title": "Netzkosten-Lokalisator",
        "tagline": "Regulierte Netzkosten PLZ-scharf — lückenloser Rechenweg mit Preisblatt-Quelle.",
        "author": "Ben Mörzinger",
    },
    # Externe App (eigener Server): Simba läuft als FastAPI-Container (Beschaffung
    # via pvtool, Rechenkern auf energietools re-wired). Keine WASM-Karte, sondern
    # eine externe Link-Karte — demonstriert, dass verschiedene Autor:innen
    # publishen. ``href`` setzen + ``external: True`` ⇒ kein marimo-Export.
    {
        "slug": "simba",
        "emoji": "🔆",
        "title": "Simba — PV-Speicher-Simulator",
        "tagline": "PV + Batterie + Wärmepumpe simulieren: Eigenverbrauch, Spot, Arbitrage, Peak-Shaving.",
        "author": "Jakob Kreisel",
        "href": "https://simba.energietools.at",
        "external": True,
    },
]


def run(cmd: list[str], **kw) -> None:
    print("·", " ".join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)


def build_wheel(outdir: Path) -> Path:
    wheel_dir = outdir / "_wheel"
    if wheel_dir.exists():
        shutil.rmtree(wheel_dir)
    run([sys.executable, "-m", "build", "--wheel", "--outdir", str(wheel_dir)], cwd=REPO)
    wheels = glob.glob(str(wheel_dir / f"energietools-{WHEEL_VERSION}-*.whl"))
    if not wheels:
        raise SystemExit(f"Wheel energietools-{WHEEL_VERSION} nicht gebaut — Version prüfen.")
    return Path(wheels[0])


def export_app(app: dict, outdir: Path) -> None:
    target = outdir / app["slug"]
    if target.exists():
        shutil.rmtree(target)
    run([
        sys.executable, "-m", "marimo", "export", "html-wasm",
        str(DEMOS / app["file"]), "-o", str(target), "--mode", "run",
    ])


def _card(a: dict) -> str:
    ext = a.get("external")
    href = a.get("href", f"./{a['slug']}/")
    attrs = ' target="_blank" rel="noopener"' if ext else ""
    badge = '<span class="ext">externer Server ↗</span>' if ext else ""
    go = "öffnen ↗" if ext else "öffnen →"
    return (
        f'      <a class="card" href="{href}"{attrs}>\n'
        f'        <div class="emoji">{a["emoji"]}</div>\n'
        f'        <h3>{a["title"]}{badge}</h3>\n'
        f'        <p>{a["tagline"]}</p>\n'
        f'        <span class="author">von {a["author"]}</span>\n'
        f'        <span class="go">{go}</span>\n'
        f"      </a>"
    )


def landing_html() -> str:
    cards = "\n".join(_card(a) for a in APPS)
    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>energietools — auditierbare Energie-Rechner</title>
<meta name="description" content="Open-Source-Rechner für den österreichischen Energiemarkt. Jede Zahl mit Rechenweg, komplett im Browser.">
<style>
  :root {{ --bg:#0b0e14; --card:#141a24; --line:#222c3a; --fg:#e6edf3; --muted:#9aa7b4; --accent:#4ade80; }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg); font:16px/1.6 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif; }}
  .wrap {{ max-width:980px; margin:0 auto; padding:64px 24px 96px; }}
  header h1 {{ font-size:2.6rem; margin:0 0 .3em; letter-spacing:-.02em; }}
  header .accent {{ color:var(--accent); }}
  header p.lead {{ font-size:1.2rem; color:var(--muted); max-width:62ch; margin:.2em 0 0; }}
  .badges {{ margin:22px 0 0; display:flex; gap:10px; flex-wrap:wrap; }}
  .badge {{ font-size:.82rem; color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:5px 12px; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(280px,1fr)); gap:18px; margin:44px 0 0; }}
  .card {{ display:block; background:var(--card); border:1px solid var(--line); border-radius:16px; padding:22px; text-decoration:none; color:inherit; transition:border-color .15s, transform .15s; }}
  .card:hover {{ border-color:var(--accent); transform:translateY(-2px); }}
  .card .emoji {{ font-size:1.9rem; }}
  .card h3 {{ margin:.5em 0 .25em; font-size:1.2rem; }}
  .card p {{ color:var(--muted); font-size:.95rem; margin:0 0 .6em; }}
  .card .author {{ display:block; color:#6b7785; font-size:.78rem; margin:0 0 1em; }}
  .card .ext {{ font-size:.62rem; color:var(--muted); border:1px solid var(--line); border-radius:999px; padding:2px 7px; margin-left:8px; vertical-align:middle; font-weight:400; }}
  .card .go {{ color:var(--accent); font-size:.9rem; font-weight:600; }}
  .principle {{ margin:56px 0 0; padding:24px; border:1px solid var(--line); border-radius:16px; background:#0f141d; }}
  .principle h2 {{ margin:0 0 .4em; font-size:1.1rem; }}
  .principle p {{ color:var(--muted); margin:.4em 0 0; font-size:.95rem; }}
  code {{ background:#0a0d13; border:1px solid var(--line); border-radius:6px; padding:1px 6px; font-size:.85em; }}
  footer {{ margin:56px 0 0; color:var(--muted); font-size:.85rem; }}
  a {{ color:var(--accent); }}
</style>
</head>
<body>
  <div class="wrap">
    <header>
      <h1><span class="accent">energie</span>tools</h1>
      <p class="lead">Auditierbare Rechner für den österreichischen Energiemarkt. Jede Zahl trägt
      ihren <strong>Rechenweg</strong> und ihre <strong>Quelle</strong> — und läuft komplett in deinem Browser.</p>
      <div class="badges">
        <span class="badge">Open Source · MIT</span>
        <span class="badge">Kein Server · 100&nbsp;% im Browser</span>
        <span class="badge">Datierte, gequellte Daten-Snapshots</span>
        <span class="badge">Österreich</span>
      </div>
    </header>

    <main class="grid">
{cards}
    </main>

    <section class="principle">
      <h2>Warum „auditierbar"?</h2>
      <p>Diese Demos rechnen <strong>im Browser</strong> auf der quelloffenen Library
      <a href="https://github.com/BMoer/energietools"><code>energietools</code></a> — du siehst den
      Code, den Rechenweg jeder Zahl und das Stand-Datum jeder Datenquelle. Fehlt eine Eingabe oder
      ist eine PLZ uneindeutig, wird <strong>bewusst nicht geschätzt</strong>. Die Beschaffung der
      Daten (Scraper, Backend) ist proprietär; hier liegt nur der reproduzierbare Kern.</p>
    </section>

    <footer>
      <a href="https://github.com/BMoer/energietools">GitHub: BMoer/energietools</a> ·
      gebaut mit <a href="https://marimo.io">marimo</a> &amp; Pyodide ·
      Netto-Listenpreise, ohne Gewähr.
    </footer>
  </div>
</body>
</html>
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", default=str(REPO / "site"))
    ap.add_argument("--skip-wheel", action="store_true", help="vorhandenes Wheel in site/wheels/ wiederverwenden")
    ap.add_argument("--no-cname", action="store_true", help="kein CNAME schreiben (z.B. für lokalen Test)")
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)
    wheels_dir = out / "wheels"
    wheels_dir.mkdir(parents=True, exist_ok=True)

    if not args.skip_wheel:
        wheel = build_wheel(out)
        for old in glob.glob(str(wheels_dir / "energietools-*.whl")):
            Path(old).unlink()
        shutil.copy(wheel, wheels_dir / wheel.name)
        print(f"  wheel → {wheels_dir / wheel.name}")

    for app in APPS:
        if app.get("external"):
            print(f"  app  → {app['slug']} (extern: {app['href']}) — kein WASM-Export")
            continue
        export_app(app, out)
        print(f"  app  → {out / app['slug']}/")

    (out / "index.html").write_text(landing_html(), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    if not args.no_cname:
        (out / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")

    # _wheel-Build-Artefakt aufräumen
    if (out / "_wheel").exists():
        shutil.rmtree(out / "_wheel")

    print(f"\n✓ Gallery gebaut: {out}")
    print(f"  lokal testen:  python -m http.server --directory {out} 8000  →  http://localhost:8000/")


if __name__ == "__main__":
    main()
