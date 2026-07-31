# energietools — Open-Source Toolkit für den österreichischen Energiemarkt
# SPDX-License-Identifier: MIT

"""Load Profile Analysis — Lastprofil-Analyse mit Metriken, Anomalie-Erkennung und Visualisierungen.

Ported from ~/Projekte/Load Profile Analysis. Key algorithms:
- Metrics: base load (15th percentile), peak, full load hours, monthly aggregation
- FDA Anomaly Detection: TVD-MSS (Huang & Sun 2019) with k-means clustering
- Savings: base load reduction, peak shaving, weekend/night optimization
- Visualizations: heatmap, duration curve, monthly chart
"""

from __future__ import annotations

import base64
import io
import logging
from datetime import date

import numpy as np
import pandas as pd

from energietools.models.load_profile import (
    AnomalyResult,
    ClusterInfo,
    LoadProfileAnalysis,
    LoadProfileMetrics,
    SavingsOpportunity,
)

log = logging.getLogger(__name__)

# --- Constants ---
QUANTILE_BASE_LOAD = 0.15
# Korrektheits-Fix 2026-07-20: vorher eine GLOBALE, fixe Q15-Annahme, die für
# JEDE Eingabe-Granularität benutzt wurde (kWh -> kW, period_hours, Monats-
# Resample, Anomalie-Erkennung, Jahresdauerlinie). Bei Tageswert-Serien
# (Slot-Abstand 1440 min statt 15 min) wurde eine Tages-kWh durch 0,25 h statt
# 24 h geteilt -> spitzenlast_kw/grundlast_kw ~96x zu hoch. Jetzt nur noch der
# FALLBACK, wenn sich aus den Zeitstempeln kein Abstand ableiten lässt (s.
# ``_intervall_stunden``) — die tatsächlich benutzte Slot-Länge wird JE SERIE
# aus den Zeitstempel-Abständen abgeleitet und durchgereicht.
DEFAULT_INTERVAL_HOURS = 0.25  # 15 min (Q15-Fallback)
# Ab so vielen Minuten Slot-Abstand gilt eine Serie als grob (Tageswerte o.ä.)
# -- dieselbe Schwelle wie
# ``energietools.capabilities.lastgang.granularitaet.GRANULARITAET_SCHWELLE_MIN``,
# hier dupliziert statt importiert: ``tools/`` hängt bewusst NICHT von
# ``capabilities/`` ab (umgekehrte Abhängigkeitsrichtung im Repo, s.
# ``capabilities/load_profile/capability.py`` — die Capability importiert
# lazy AUS diesem Modul, nicht umgekehrt).
GROBE_SERIE_SCHWELLE_MIN = 60
HOURS_PER_YEAR = 8760
NIGHT_START = 22
NIGHT_END = 4


def _intervall_stunden(index: pd.DatetimeIndex) -> tuple[float, float]:
    """Leitet die Slot-Länge DIESER Serie deterministisch aus den Zeitstempel-
    Abständen ab: Median der Abstände aufeinanderfolgender, sortierter,
    EINDEUTIGER Zeitstempel — robust gegen einzelne Lücken/Duplikate/einen
    einzelnen Ausreißer-Sprung (dieselbe Regel wie
    ``capabilities.lastgang.granularitaet.slot_abstand_minuten``).

    Liefert ``(interval_hours, interval_minuten)``. Fällt auf
    ``DEFAULT_INTERVAL_HOURS`` zurück, wenn kein Abstand bestimmbar ist
    (< 2 verschiedene Zeitstempel, oder — entartet — ein Median <= 0).
    """
    eindeutig = index.unique()
    if len(eindeutig) < 2:
        return DEFAULT_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS * 60
    deltas_minuten = eindeutig.to_series().diff().dropna().dt.total_seconds() / 60
    minuten = float(deltas_minuten.median()) if len(deltas_minuten) else 0.0
    if minuten <= 0:
        return DEFAULT_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS * 60
    return minuten / 60, minuten


def analyze_load_profile(
    consumption_data: list[dict] | None = None,
    csv_text: str = "",
    price_per_kwh: float = 0.20,
    generate_visualizations: bool = True,
) -> LoadProfileAnalysis:
    """Vollständige Lastprofil-Analyse.

    Args:
        consumption_data: Liste von {timestamp: ISO-string, kwh: float} Einträgen.
        csv_text: Alternativ: CSV-Text mit Verbrauchsdaten (wird automatisch geparst).
                  Spalten werden anhand von Namens-Heuristiken erkannt.
        price_per_kwh: Strompreis in EUR/kWh (brutto) für Sparpotenzialkalkulation.
        generate_visualizations: Wenn False, werden die matplotlib-Base64-PNGs NICHT
                  gerendert (visualisierungen={}). Spart ~200KB pro Response und die
                  Render-Kosten — für JSON-Endpoints, die Charts client-seitig zeichnen.

    Returns:
        LoadProfileAnalysis mit Metriken, Anomalien, Sparpotenzialen und Visualisierungen.
    """
    try:
        # csv_text takes priority — handles the case where Claude passes both
        if csv_text:
            consumption_data = _parse_csv_text(csv_text)

        if not consumption_data:
            return LoadProfileAnalysis(
                metrics=_empty_metrics(),
                analyse_erfolgreich=False,
                fehler="Keine Daten übergeben. Bitte consumption_data oder csv_text angeben.",
            )

        df, interval_hours, interval_minuten = _prepare_dataframe(consumption_data)
        if df.empty or len(df) < 96:  # Minimum 1 Tag
            return LoadProfileAnalysis(
                metrics=_empty_metrics(),
                analyse_erfolgreich=False,
                fehler="Zu wenig Datenpunkte (mindestens 1 Tag à 96 Intervalle benötigt).",
            )

        metrics = _calculate_metrics(df, interval_hours, interval_minuten)
        anomalien, cluster = _detect_anomalies(df, interval_hours)
        einsparpotenziale = _estimate_savings(metrics, price_per_kwh)
        visualisierungen = (
            _generate_visualizations(df, metrics, interval_hours) if generate_visualizations else {}
        )

        sparpotenzial_kwh = sum(s.einsparung_kwh for s in einsparpotenziale)
        sparpotenzial_eur = sum(s.einsparung_eur for s in einsparpotenziale)

        return LoadProfileAnalysis(
            metrics=metrics,
            anomalien=anomalien,
            cluster=cluster,
            einsparpotenziale=einsparpotenziale,
            sparpotenzial_kwh=round(sparpotenzial_kwh, 1),
            sparpotenzial_eur=round(sparpotenzial_eur, 2),
            visualisierungen=visualisierungen,
        )
    except Exception as exc:
        log.exception("Lastprofil-Analyse fehlgeschlagen")
        return LoadProfileAnalysis(
            metrics=_empty_metrics(),
            analyse_erfolgreich=False,
            fehler=str(exc),
        )


# --- CSV Parsing ---


def _parse_csv_text(csv_text: str) -> list[dict]:
    """Parse raw CSV text into list of {timestamp, kwh} dicts.

    Handles various column names (German/English), separators, and date formats.
    Picks the separator that produces the most columns to avoid false matches.
    """
    if not csv_text or not csv_text.strip():
        raise ValueError("CSV-Text ist leer.")

    # Try all separators and pick the one that produces the most columns
    best_df: pd.DataFrame | None = None
    best_ncols = 0
    for sep in [";", ",", "\t"]:
        try:
            df = pd.read_csv(io.StringIO(csv_text), sep=sep)
            if len(df.columns) >= 2 and len(df.columns) > best_ncols:
                best_df = df
                best_ncols = len(df.columns)
        except Exception:
            continue

    if best_df is None:
        raise ValueError(
            "CSV konnte nicht geparst werden — kein Separator (;  ,  Tab) ergab mindestens 2 Spalten."
        )

    df = best_df

    # Drop completely empty rows
    df = df.dropna(how="all")

    # Normalize column names to lowercase
    col_map = {c: c.lower().strip() for c in df.columns}
    df = df.rename(columns=col_map)

    # Find timestamp column — prefer exact matches, then substring
    ts_col = _find_column(
        df.columns,
        exact=["timestamp", "zeitstempel", "datum", "date", "time", "zeit", "von"],
        substring=["timestamp", "zeitstempel", "datum", "date", "zeit", "von", "from", "time"],
    )
    if ts_col is None:
        # First column is likely the timestamp
        ts_col = df.columns[0]

    # Find value column — prefer exact matches, then substring, then first numeric
    val_col = _find_column(
        df.columns,
        exact=["kwh", "verbrauch", "consumption", "wert", "value", "menge", "energy", "kw"],
        substring=["kwh", "verbrauch", "consumption", "wert", "value", "menge", "energy"],
        exclude={ts_col},
    )
    if val_col is None:
        # Pick first column that can be parsed as numeric (not the timestamp)
        for c in df.columns:
            if c == ts_col:
                continue
            try:
                sample = df[c].dropna().head(10)
                if sample.empty:
                    continue
                if pd.api.types.is_numeric_dtype(sample):
                    val_col = c
                    break
                # Try German decimal comma conversion
                pd.to_numeric(sample.astype(str).str.replace(",", "."))
                val_col = c
                break
            except Exception:
                continue

    if val_col is None:
        cols_str = ", ".join(df.columns.tolist()[:10])
        raise ValueError(
            f"Keine Verbrauchsspalte in der CSV erkannt. Gefundene Spalten: {cols_str}"
        )

    # Parse values (handle German decimal comma)
    if not pd.api.types.is_numeric_dtype(df[val_col]):
        df[val_col] = pd.to_numeric(
            df[val_col].astype(str).str.replace(",", "."),
            errors="coerce",
        )
    else:
        df[val_col] = df[val_col].astype(float)

    # Drop rows where value couldn't be parsed
    df = df.dropna(subset=[val_col])

    if df.empty:
        raise ValueError("Keine gültigen numerischen Werte in der Verbrauchsspalte gefunden.")

    # Build result
    result = []
    for _, row in df.iterrows():
        result.append({"timestamp": str(row[ts_col]), "kwh": float(row[val_col])})

    log.info("CSV geparst: %d Datenpunkte, ts_col=%s, val_col=%s", len(result), ts_col, val_col)
    return result


def _find_column(
    columns: pd.Index,
    exact: list[str],
    substring: list[str],
    exclude: set[str] | None = None,
) -> str | None:
    """Find best matching column name — exact match first, then substring."""
    exclude = exclude or set()
    cols = [c for c in columns if c not in exclude]

    # Exact match (highest priority)
    for candidate in exact:
        if candidate in cols:
            return candidate

    # Substring match (ordered by candidate priority)
    for candidate in substring:
        matches = [c for c in cols if candidate in c]
        if matches:
            return matches[0]

    return None


# --- Data Preparation ---


def _prepare_dataframe(data: list[dict]) -> tuple[pd.DataFrame, float, float]:
    """Rohdaten zu DataFrame mit DatetimeIndex und consumption_kw konvertieren.

    Liefert zusätzlich ``(interval_hours, interval_minuten)`` — die für DIESE
    Serie aus den Zeitstempel-Abständen abgeleitete Slot-Länge (Korrektheits-
    Fix 2026-07-20, s. ``_intervall_stunden``), NICHT mehr die vorher fixe
    Q15-Annahme.
    """
    df = pd.DataFrame(data)
    # utc=True handles mixed timezone offsets (e.g. CET/CEST from Austrian smart meter data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    # Convert to Europe/Vienna for correct hour-of-day analysis, then drop tz for downstream compat
    df["timestamp"] = df["timestamp"].dt.tz_convert("Europe/Vienna").dt.tz_localize(None)
    df = df.set_index("timestamp").sort_index()

    interval_hours, interval_minuten = _intervall_stunden(df.index)

    # kWh → kW über die ERKANNTE Slot-Länge dieser Serie (nicht mehr fix 15 min)
    if "kwh" in df.columns:
        df["consumption_kw"] = df["kwh"] / interval_hours
    elif "kw" in df.columns:
        df["consumption_kw"] = df["kw"]

    df = df[["consumption_kw"]].dropna()
    # Negative Werte entfernen
    df = df[df["consumption_kw"] >= 0]
    return df, interval_hours, interval_minuten


# --- Metrics Calculation ---


def _calculate_metrics(
    df: pd.DataFrame, interval_hours: float, interval_minuten: float
) -> LoadProfileMetrics:
    """Kennzahlen berechnen.

    ``interval_hours``/``interval_minuten``: die für DIESE Serie erkannte
    Slot-Länge (``_intervall_stunden``, Korrektheits-Fix 2026-07-20) — bei
    Q15-Daten identisch zur alten fixen Annahme (0,25 h/15 min), bei gröberer
    Eingabe (z.B. Tageswerten: 24 h/1440 min) NICHT mehr fälschlich 0,25 h.
    """
    kw = df["consumption_kw"]
    period_hours = len(kw) * interval_hours  # tatsächlich abgedeckte Stunden des Uploads
    total_kwh = float(kw.sum() * interval_hours)
    grundlast_kw = float(np.percentile(kw, QUANTILE_BASE_LOAD * 100))
    spitzenlast_kw = float(kw.max())

    # Volllaststunden ist eine JAHRESkennzahl (Jahresenergie / Spitzenlast). Ein Upload
    # deckt selten ein volles Jahr ab → erst auf 8760 h hochrechnen, sonst ist die Zahl
    # bei Teilzeiträumen bedeutungslos (vorher: nur Teilzeitraum-kWh → ~halbiert).
    annual_kwh = total_kwh / period_hours * HOURS_PER_YEAR if period_hours > 0 else 0.0
    volllaststunden = annual_kwh / spitzenlast_kw if spitzenlast_kw > 0 else 0
    # Grundlast-Anteil = Energie der Dauerlast IM Zeitraum / Gesamtenergie IM Zeitraum.
    # period_hours statt HOURS_PER_YEAR: vorher wurde eine Jahres-Dauerlast gegen eine
    # evtl. Teilzeitraum-Summe gerechnet → systematisch überhöht (Faktor 8760/period).
    grundlast_anteil = (grundlast_kw * period_hours) / total_kwh * 100 if total_kwh > 0 else 0

    # Monatsaggregation
    monthly = df.resample("ME").apply(lambda x: float(x.sum() * interval_hours))
    monthly_kwh = {
        ts.strftime("%Y-%m"): round(val, 1)
        for ts, val in monthly["consumption_kw"].items()
    }

    # Nachtverbrauch (22:00-04:00)
    night_mask = (df.index.hour >= NIGHT_START) | (df.index.hour < NIGHT_END)
    nacht_mean = float(kw[night_mask].mean()) if night_mask.any() else 0.0

    # Wochenendverbrauch
    weekend_mask = df.index.dayofweek >= 5
    wochenende_mean = float(kw[weekend_mask].mean()) if weekend_mask.any() else 0.0

    # Design-Entscheidung (Fix 2, statt stiller Verweigerung): bei grober
    # Auflösung (>= GROBE_SERIE_SCHWELLE_MIN) sind grundlast_kw/spitzenlast_kw
    # rechnerisch korrekt (kWh/interval_hours), aber KEINE echte Intraday-
    # Spitze, sondern eine Intervall-Mittel-Leistung (bei Tageswerten:
    # Tagesmittel-Leistung) — das Result macht das über granularitaet_hinweis
    # explizit, statt die Analyse zu verweigern (total_kwh/monthly_kwh/
    # Sparpotenziale bleiben auch bei grober Auflösung sinnvoll).
    granularitaet_hinweis = None
    if interval_minuten >= GROBE_SERIE_SCHWELLE_MIN:
        granularitaet_hinweis = (
            f"Erkanntes Intervall: {interval_minuten:.0f} min (Median der "
            "Zeitstempel-Abstände) — grundlast_kw/spitzenlast_kw sind bei dieser "
            f"Granularität eine Intervall-Mittel-Leistung (kWh / {interval_hours:.2f} h), "
            "KEINE echte Intraday-Spitze. Für eine echte Spitzenlast wird eine "
            "feinere Auflösung (z.B. 15-min) benötigt."
        )

    return LoadProfileMetrics(
        mean_kw=round(float(kw.mean()), 3),
        median_kw=round(float(kw.median()), 3),
        min_kw=round(float(kw.min()), 3),
        max_kw=round(spitzenlast_kw, 3),
        std_kw=round(float(kw.std()), 3),
        grundlast_kw=round(grundlast_kw, 3),
        spitzenlast_kw=round(spitzenlast_kw, 3),
        volllaststunden=round(volllaststunden, 0),
        grundlast_anteil_pct=round(grundlast_anteil, 1),
        total_kwh=round(total_kwh, 1),
        monthly_kwh=monthly_kwh,
        nacht_mean_kw=round(nacht_mean, 3),
        wochenende_mean_kw=round(wochenende_mean, 3),
        interval_minuten=round(interval_minuten, 1),
        granularitaet_hinweis=granularitaet_hinweis,
    )


# --- Anomaly Detection ---

# Mindestzahl Tage, ab der eine Verteilung der Tagesabstände schätzbar ist.
# Darunter ist jede Schwelle geraten.
_MIN_TAGE_FUER_SCHWELLE = 14

# Skalierungsfaktor MAD → Standardabweichung bei Normalverteilung.
_MAD_ZU_SIGMA = 1.4826

# Wie viele robuste Sigma ein Tag vom typischen Tag entfernt sein muss.
_ANOMALIE_K = 3.0


def _ueber_robuster_schwelle(abstaende: np.ndarray, k: float) -> set[int]:
    """Indizes, deren Abstand ungewöhnlich groß ist (Median + k·MAD).

    Robust: Median und MAD statt Mittelwert und Sigma — fünf Extremtage ziehen
    die Schwelle nicht so hoch, dass sie sich selbst verstecken.

    **Null ist ein mögliches Ergebnis.** Bei gleichförmigen Tagen kommt nichts
    heraus. Eine feste Quantils-Schwelle ("die obersten 5 %") meldete
    stattdessen immer 5 %, auch wenn es nichts zu melden gibt.

    Ist die MAD null (über die Hälfte der Werte identisch), greift die
    Standardabweichung als Ersatzmaßstab; ohne diesen Guard läge die Schwelle
    exakt auf dem Median und jeder minimal abweichende Tag wäre ein Ausreißer.
    """
    median_abstand = float(np.median(abstaende))
    mad = float(np.median(np.abs(abstaende - median_abstand)))
    streuung = mad * _MAD_ZU_SIGMA if mad > 0 else float(np.std(abstaende))
    if streuung <= 0:
        return set()
    schwelle = median_abstand + k * streuung
    return set(np.flatnonzero(abstaende > schwelle).tolist())


def tages_ausreisser_typisiert(
    tage: np.ndarray,
    k: float = _ANOMALIE_K,
) -> dict[int, str]:
    """Ungewöhnliche Tage als ``{index: "magnitude" | "shape" | "both"}``.

    ``tage`` ist eine Matrix (n_tage × n_slots) mit einem Tagesprofil je Zeile.

    Warum zwei Kennzahlen statt einer (Befund 31.07.2026, nachgemessen an 937
    Tagesprofilen):

    Der Vorgänger verglich das **Maximum** der Slot-Abweichungen eines Tages
    gegen die **punktweise** Streuung über alle Tage. Bei 96 Slots reißt dieses
    Maximum eine 2–2,5-Sigma-Grenze fast beliebig oft: gemessen 542 von 937
    Tagen (57,8 %), bei einem Median der Kennzahl von 2,68 gegen eine Schwelle
    von 2,5 — die Schwelle lag *unter* dem Median. Geprüft wurde faktisch "hat
    dieser Tag irgendeinen ungewöhnlichen Moment", und das hat jeder Tag.

    Eine einzelne Abstandskennzahl über die rohen Profile behebt das nur halb:
    sie ist nach unten gedeckelt (weniger als null Verbrauch geht nicht) und
    nach oben offen. In der Messung markierte sie 91 Tage — und **keinen
    einzigen der 39 Urlaubstage**, obwohl Abwesenheit die aussagekräftigste
    Anomalie eines Haushalts ist. Hohe Tage verdrängten die niedrigen aus der
    Verteilung.

    Deshalb getrennt, entlang der Unterscheidung, die ``AnomalyResult.typ``
    ohnehin behauptet:

    * **magnitude** — das Tagesniveau. Abstand der logarithmierten Tagessumme
      zum Median; der Logarithmus macht Halbierung und Verdopplung
      gleich weit, sonst gewönne die offene Seite immer.
    * **shape** — die Tagesform. Abstand des auf Tagessumme 1 normierten
      Profils zum normierten Median-Tag; unabhängig davon, wie viel an dem Tag
      verbraucht wurde.

    Gemessen an derselben Serie: 43 von 937 Tagen (4,6 %), darunter alle 39
    Urlaubstage.
    """
    if tage.ndim != 2 or len(tage) < _MIN_TAGE_FUER_SCHWELLE:
        return {}

    tagessummen = tage.sum(axis=1)
    niveau_abstand = np.abs(np.log1p(tagessummen) - np.log1p(np.median(tagessummen)))
    magnitude = _ueber_robuster_schwelle(niveau_abstand, k)

    # Form: jedes Profil auf Tagessumme 1 normiert. Tage ohne jeden Verbrauch
    # haben keine Form — sie bleiben auf null und fallen der Niveau-Prüfung zu.
    summen_spalte = tagessummen.reshape(-1, 1)
    formen = np.divide(
        tage, summen_spalte, out=np.zeros_like(tage, dtype=float), where=summen_spalte > 0
    )
    form_abstand = np.sqrt(np.mean((formen - np.median(formen, axis=0)) ** 2, axis=1))
    shape = _ueber_robuster_schwelle(form_abstand, k)

    typen: dict[int, str] = {}
    for i in sorted(magnitude | shape):
        if i in magnitude and i in shape:
            typen[i] = "both"
        else:
            typen[i] = "magnitude" if i in magnitude else "shape"
    return typen


def tages_ausreisser(tage: np.ndarray, k: float = _ANOMALIE_K) -> list[int]:
    """Indizes ungewöhnlicher Tage, aufsteigend (s. ``tages_ausreisser_typisiert``)."""
    return sorted(tages_ausreisser_typisiert(tage, k=k))


def _detect_anomalies(
    df: pd.DataFrame, interval_hours: float
) -> tuple[list[AnomalyResult], list[ClusterInfo]]:
    """FDA-basierte Anomalie-Erkennung (fallback auf statistische Methode).

    ``_build_daily_profiles`` verlangt >=90 Slots/Tag (Q15-Annahme, 96 Slots
    ~= 1 Tag) — bei gröberer Eingabe (z.B. Tageswerten: 1 Slot/Tag) liefert
    das bewusst IMMER ``{}`` und damit hier ``([], [])``: Anomalie-Erkennung
    braucht ein echtes Intraday-Profil, das eine Tageswert-Serie nicht hat.
    Kein Fix nötig (kein falscher Wert, nur ein sauber geguardetes Feature),
    NICHT Teil dieses Korrektheits-Fixes (Scope: kW-Metriken/period_hours).
    """
    daily_profiles = _build_daily_profiles(df)
    if len(daily_profiles) < 14:
        return [], []

    try:
        return _fda_anomaly_detection(daily_profiles, interval_hours)
    except ImportError:
        log.info("scikit-fda nicht installiert, verwende statistische Anomalie-Erkennung")
        return _statistical_anomaly_detection(daily_profiles, interval_hours)
    except Exception as exc:
        log.warning("FDA-Anomalie-Erkennung fehlgeschlagen: %s", exc)
        return _statistical_anomaly_detection(daily_profiles, interval_hours)


def _build_daily_profiles(df: pd.DataFrame) -> dict[date, np.ndarray]:
    """Tagesprofile als 96-Punkt Arrays extrahieren."""
    profiles: dict[date, np.ndarray] = {}
    for day, group in df.groupby(df.index.date):
        if len(group) >= 90:  # Mindestens ~94% vollständig
            values = group["consumption_kw"].values[:96]
            if len(values) == 96:
                profiles[day] = values
    return profiles


def _fda_anomaly_detection(
    profiles: dict[date, np.ndarray], interval_hours: float
) -> tuple[list[AnomalyResult], list[ClusterInfo]]:
    """FDA TVD-MSS Anomalie-Erkennung mit scikit-fda."""
    import skfda
    from skfda.ml.clustering import KMeans as FDAKMeans

    dates = sorted(profiles.keys())
    data_matrix = np.array([profiles[d] for d in dates])

    fd = skfda.FDataGrid(data_matrix, grid_points=np.linspace(0, 24, 96))

    # K-Means Clustering
    n_clusters = min(4, max(2, len(dates) // 15))
    kmeans = FDAKMeans(n_clusters=n_clusters, random_state=42)
    labels = kmeans.fit_predict(fd)
    centroids = kmeans.cluster_centers_.data_matrix.squeeze()

    # Anomalien: Tage, die innerhalb IHRES Clusters ungewöhnlich weit vom
    # typischen Tag entfernt sind. Die Schwelle je Cluster einzeln bestimmen —
    # ein Wochenend-Cluster streut anders als ein Werktags-Cluster, und eine
    # gemeinsame Schwelle bestrafte den streuenderen von beiden.
    anomalien: list[AnomalyResult] = []
    for cluster_id in range(n_clusters):
        cluster_mask = labels == cluster_id
        cluster_idx = np.flatnonzero(cluster_mask)
        if len(cluster_idx) == 0:
            continue
        cluster_data = data_matrix[cluster_mask]
        centroid = centroids[cluster_id]

        for lokal, typ in tages_ausreisser_typisiert(cluster_data).items():
            global_idx = int(cluster_idx[lokal])
            d = dates[global_idx]
            diff = data_matrix[global_idx] - centroid
            anomalien.append(AnomalyResult(
                datum=d,
                wochentag=_wochentag(d),
                typ=typ,
                cluster_id=cluster_id,
                abweichung_kwh=round(float(np.sum(np.maximum(diff, 0)) * interval_hours), 2),
                spitzen_abweichung_kw=round(float(np.max(np.abs(diff))), 3),
            ))
    anomalien.sort(key=lambda a: a.datum)

    # Cluster-Info
    cluster_info: list[ClusterInfo] = []
    for cid in range(n_clusters):
        mask = labels == cid
        cluster_dates = [dates[i] for i in range(len(dates)) if mask[i]]
        cluster_data = data_matrix[mask]
        cluster_info.append(ClusterInfo(
            cluster_id=cid,
            tage=int(mask.sum()),
            mean_daily_kwh=round(float(cluster_data.sum(axis=1).mean() * interval_hours), 1),
            typische_wochentage=_typical_weekdays(cluster_dates),
        ))

    return anomalien, cluster_info


def _statistical_anomaly_detection(
    profiles: dict[date, np.ndarray], interval_hours: float
) -> tuple[list[AnomalyResult], list[ClusterInfo]]:
    """Statistische Anomalie-Erkennung ohne Clustering (Fallback).

    Das ist der Pfad, der **produktiv läuft**: ``scikit-fda`` ist im
    Gateway-Container nicht installiert, ``_detect_anomalies`` fängt den
    ImportError und landet hier. Der Befund vom 31.07.2026 (57,8 % der Tage
    als Anomalie) stammt von hier, nicht aus dem FDA-Pfad.

    Ohne Cluster ist der Maßstab die Gesamtheit der Tage; die Schwelle selbst
    steckt in ``tages_ausreisser`` und ist dieselbe wie im FDA-Pfad.
    """
    dates = sorted(profiles.keys())
    data_matrix = np.array([profiles[d] for d in dates])

    typischer_tag = np.median(data_matrix, axis=0)

    anomalien: list[AnomalyResult] = []
    for i, typ in tages_ausreisser_typisiert(data_matrix).items():
        diff = data_matrix[i] - typischer_tag
        anomalien.append(AnomalyResult(
            datum=dates[i],
            wochentag=_wochentag(dates[i]),
            typ=typ,
            abweichung_kwh=round(float(np.sum(np.maximum(diff, 0)) * interval_hours), 2),
            spitzen_abweichung_kw=round(float(np.max(np.abs(diff))), 3),
        ))

    return anomalien, []


def _wochentag(d: date) -> str:
    """Deutschen Wochentag-Namen zurückgeben."""
    tage = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
    return tage[d.weekday()]


def _typical_weekdays(dates: list[date]) -> list[str]:
    """Häufigste Wochentage in einer Datumsliste."""
    from collections import Counter
    if not dates:
        return []
    counts = Counter(_wochentag(d) for d in dates)
    return [day for day, _ in counts.most_common(3)]


# --- Savings Estimation ---


def _estimate_savings(metrics: LoadProfileMetrics, price: float) -> list[SavingsOpportunity]:
    """Einsparpotenziale berechnen."""
    opportunities: list[SavingsOpportunity] = []

    # 1. Grundlast-Reduktion (10% realistisch)
    if metrics.grundlast_kw > 0:
        reduction_kw = metrics.grundlast_kw * 0.10
        savings_kwh = reduction_kw * HOURS_PER_YEAR
        savings_eur = savings_kwh * price
        if savings_eur >= 10:
            opportunities.append(SavingsOpportunity(
                kategorie="base_load",
                beschreibung=(
                    f"Grundlast-Reduktion von {metrics.grundlast_kw:.2f} kW "
                    f"um 10% ({reduction_kw:.2f} kW)"
                ),
                einsparung_kwh=round(savings_kwh, 1),
                einsparung_eur=round(savings_eur, 2),
                konfidenz="medium",
            ))

    # 2. Peak Shaving (nur bei peak_ratio > 2.5)
    if metrics.spitzenlast_kw > 0 and metrics.mean_kw > 0:
        peak_ratio = metrics.spitzenlast_kw / metrics.mean_kw
        if peak_ratio > 2.5:
            peak_reduction = (metrics.spitzenlast_kw - 2.5 * metrics.mean_kw) * 0.15
            peak_hours = HOURS_PER_YEAR * 0.05
            savings_kwh = peak_reduction * peak_hours * 0.20
            savings_eur = savings_kwh * price
            if savings_eur >= 10:
                opportunities.append(SavingsOpportunity(
                    kategorie="peak_shaving",
                    beschreibung=(
                        f"Spitzenlast-Reduktion (Peak/Mean Ratio: {peak_ratio:.1f}x)"
                    ),
                    einsparung_kwh=round(savings_kwh, 1),
                    einsparung_eur=round(savings_eur, 2),
                    konfidenz="low",
                ))

    # 3. Wochenend-Optimierung
    if metrics.wochenende_mean_kw > metrics.grundlast_kw * 1.2:
        excess = metrics.wochenende_mean_kw - metrics.grundlast_kw
        reducible = excess * 0.50
        weekend_hours = 104 * 24  # 104 Wochenendtage × 24h
        savings_kwh = reducible * weekend_hours
        savings_eur = savings_kwh * price
        if savings_eur >= 10:
            opportunities.append(SavingsOpportunity(
                kategorie="weekend",
                beschreibung=(
                    f"Wochenend-Verbrauch ({metrics.wochenende_mean_kw:.2f} kW) "
                    f"liegt 20%+ über Grundlast ({metrics.grundlast_kw:.2f} kW)"
                ),
                einsparung_kwh=round(savings_kwh, 1),
                einsparung_eur=round(savings_eur, 2),
                konfidenz="medium",
            ))

    # 4. Nacht-Optimierung
    if metrics.nacht_mean_kw > metrics.grundlast_kw * 1.1:
        excess = metrics.nacht_mean_kw - metrics.grundlast_kw
        reducible = excess * 0.30
        night_hours = 8 * 365
        savings_kwh = reducible * night_hours
        savings_eur = savings_kwh * price
        if savings_eur >= 10:
            opportunities.append(SavingsOpportunity(
                kategorie="night",
                beschreibung=(
                    f"Nachtverbrauch ({metrics.nacht_mean_kw:.2f} kW) "
                    f"liegt 10%+ über Grundlast ({metrics.grundlast_kw:.2f} kW)"
                ),
                einsparung_kwh=round(savings_kwh, 1),
                einsparung_eur=round(savings_eur, 2),
                konfidenz="low",
            ))

    return opportunities


# --- Visualizations ---


def _generate_visualizations(
    df: pd.DataFrame, metrics: LoadProfileMetrics, interval_hours: float
) -> dict[str, str]:
    """Visualisierungen als base64 PNG generieren."""
    viz: dict[str, str] = {}

    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        viz["heatmap"] = _generate_heatmap(df, plt)
        viz["jahresdauerlinie"] = _generate_duration_curve(df, plt, interval_hours)
        viz["monatsverbrauch"] = _generate_monthly_chart(df, metrics, plt)
    except ImportError:
        log.info("matplotlib nicht installiert — keine Visualisierungen erstellt")

    return viz


def _fig_to_base64(fig) -> str:
    """Matplotlib Figure → base64 PNG string."""
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    buf.seek(0)
    result = base64.b64encode(buf.read()).decode("utf-8")
    fig.clear()
    return result


def _generate_heatmap(df: pd.DataFrame, plt) -> str:
    """Heatmap: Stunde × Tag Carpet Plot."""
    pivot = df.copy()
    pivot["hour"] = pivot.index.hour + pivot.index.minute / 60
    pivot["date"] = pivot.index.date

    heatmap_data = pivot.pivot_table(
        values="consumption_kw", index="hour", columns="date", aggfunc="mean"
    )

    fig, ax = plt.subplots(figsize=(14, 6))
    im = ax.pcolormesh(
        range(heatmap_data.shape[1]),
        heatmap_data.index,
        heatmap_data.values,
        cmap="YlOrRd",
        shading="auto",
    )
    ax.set_ylabel("Stunde")
    ax.set_xlabel("Tag")
    ax.set_title("Lastprofil Heatmap (kW)")
    fig.colorbar(im, ax=ax, label="kW")
    result = _fig_to_base64(fig)
    plt.close(fig)
    return result


def _generate_duration_curve(df: pd.DataFrame, plt, interval_hours: float) -> str:
    """Jahresdauerlinie (sortiertes Lastprofil)."""
    sorted_kw = np.sort(df["consumption_kw"].values)[::-1]
    hours = np.arange(len(sorted_kw)) * interval_hours

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.fill_between(hours, sorted_kw, alpha=0.3, color="#22c55e")
    ax.plot(hours, sorted_kw, color="#16a34a", linewidth=1)
    ax.set_xlabel("Stunden")
    ax.set_ylabel("Leistung (kW)")
    ax.set_title("Jahresdauerlinie")
    ax.axhline(y=float(np.median(sorted_kw)), color="gray", linestyle="--", alpha=0.5, label="Median")
    ax.legend()
    result = _fig_to_base64(fig)
    plt.close(fig)
    return result


def _generate_monthly_chart(df: pd.DataFrame, metrics: LoadProfileMetrics, plt) -> str:
    """Monatsverbrauch als Balkendiagramm."""
    months = list(metrics.monthly_kwh.keys())
    values = list(metrics.monthly_kwh.values())

    fig, ax = plt.subplots(figsize=(10, 5))
    bars = ax.bar(months, values, color="#22c55e", alpha=0.8)
    ax.set_xlabel("Monat")
    ax.set_ylabel("Verbrauch (kWh)")
    ax.set_title(f"Monatsverbrauch (Gesamt: {metrics.total_kwh:,.0f} kWh)")
    plt.xticks(rotation=45, ha="right")

    for bar, val in zip(bars, values):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 5,
                f"{val:.0f}", ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    result = _fig_to_base64(fig)
    plt.close(fig)
    return result


def _empty_metrics() -> LoadProfileMetrics:
    """Leere Metriken für Fehlerfälle."""
    return LoadProfileMetrics(
        mean_kw=0, median_kw=0, min_kw=0, max_kw=0, std_kw=0,
        grundlast_kw=0, spitzenlast_kw=0, volllaststunden=0,
        grundlast_anteil_pct=0, total_kwh=0,
    )
