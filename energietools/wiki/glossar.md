# Glossar

Die zentralen Begriffe des österreichischen Strommarkts, kompakt erklärt - vom Arbeitspreis bis zur Überschusseinspeisung. Diese Seite ist der schnelle Nachschlage-Index; tiefere Erklärungen stehen auf den verlinkten Konzeptseiten. Konkrete Zahlen stehen nicht hier, sondern in den datierten Snapshots unter `energietools/data/`, auf die das Wiki verweist.

Mentales Grundmodell: Der österreichische Strompreis besteht aus vier Blöcken - (1) Energie (wettbewerblich), (2) Netzkosten (reguliert), (3) Steuern und Abgaben, (4) 20 % Umsatzsteuer. Nur Block 1 ist beim Anbieterwechsel beeinflussbar; Block 2-4 hängen am Wohnort bzw. am Gesetz. Wer die Begriffe unten kennt, kann jede österreichische Stromrechnung zerlegen.

---

## A

**Arbeitspreis (AP)**
Der verbrauchsabhängige Teil des Strompreises in ct/kWh - du zahlst ihn pro tatsächlich bezogener Kilowattstunde. Es gibt einen Arbeitspreis im Energieblock (Lieferant, wettbewerblich) und einen im Netzblock (Netznutzung, reguliert je [[netz/netzentgelte]]); beide sollte man nicht verwechseln. Varianten beim Netz-AP: AP (rund um die Uhr, der Haushaltswert), SNAP, DTAP/DNAP - für den Standardhaushalt zählt der einfache AP.

**Autarkiegrad**
Anteil des selbst gedeckten Strombedarfs an deinem Gesamtverbrauch (Autarkie = aus PV/Speicher gedeckt, statt aus dem Netz). Hoher Autarkiegrad senkt den Netzbezug und damit Energie-, Netz- und Abgabenkosten gleichzeitig. Wird aus Last- und Erzeugungsprofilen berechnet, siehe [[community/kennzahlen]].

---

## B

**Bilanzgruppe**
Ein virtueller Verbund von Einspeisern und Entnehmern, für den Erzeugung und Verbrauch über einen Bilanzgruppenverantwortlichen ausgeglichen (bilanziert) werden. Sie ist das marktorganisatorische Gerüst hinter jedem Liefervertrag und hinter [[community/energiegemeinschaften]] - der Endkunde sieht sie selten direkt, aber jede gelieferte kWh läuft über eine Bilanzgruppe.

---

## E

**Eigenverbrauchsquote (SCR, Self-Consumption Rate)**
Anteil der selbst erzeugten Energie, die auch selbst verbraucht wird (statt eingespeist). Hohe SCR bedeutet: wenig [[#Ü]]berschuss, viel Eigennutzung - wirtschaftlich oft attraktiver als Einspeisung, da die vermiedene Bezugskosten höher sind als der Einspeiseerlös. Gegenstück zum Autarkiegrad; beide werden in [[community/kennzahlen]] berechnet.

**EAG-Förderbeitrag**
Bundesweit uniforme Abgabe nach dem Erneuerbaren-Ausbau-Gesetz (EAG), abgewickelt über die ÖMAG, die den Ökostromausbau finanziert. Besteht aus einem verbrauchsabhängigen Förderbeitrag in ct/kWh (auf Netznutzung und Netzverlust) plus einer fixen Förderpauschale in €/Jahr je Zählpunkt. Teil von Block 3 (Steuern und Abgaben), siehe [[netz/abgaben]].

**Elektrizitätsabgabe**
Die Stromsteuer des Bundes nach dem Elektrizitätsabgabegesetz (ElAbgG), erhoben in ct/kWh. Regelsatz 1,5 ct/kWh; für 2026 zur Krisenentlastung temporär gesenkt (Haushalte deutlich niedriger). Achtung: Die Senkung ist befristet - bei Auslaufen gilt wieder der Regelsatz; aktuelle Werte stehen in `data/netz/abgaben.json`.

**Energiegemeinschaft (EEG vs. BEG)**
Zusammenschluss zur gemeinsamen Erzeugung, Nutzung und Speicherung von erneuerbarer Energie. Die Erneuerbare-Energie-Gemeinschaft (EEG) ist räumlich gebunden (gleicher Netzbereich/Trafostation, dafür reduzierte Netzentgelte); die Bürgerenergiegemeinschaft (BEG) ist räumlich ungebunden (bundesweit, aber ohne Netzentgelt-Rabatt). Kennzahlen wie Eigenverbrauch und Reststrom berechnet [[community/kennzahlen]].

---

## G

**Gebrauchsabgabe**
Kommunale Abgabe (Landesrecht) für die Nutzung des öffentlichen Guts durch Stromleitungen im Gemeindegebiet - Satz und Bemessungsbasis variieren je Gemeinde (z. B. Wien mit einem Prozentsatz, viele Gemeinden 0 %). Teil von Block 3, aber im Gegensatz zu EAG und Elektrizitätsabgabe nicht bundesweit uniform; nur ansetzbar, wenn Satz und Basis belegt sind. Siehe [[netz/abgaben]].

**Grundgebühr / Grundpreis**
Der fixe, verbrauchsunabhängige Jahresbetrag in €/Jahr - du zahlst ihn auch ohne eine einzige bezogene kWh. Es gibt eine Grundgebühr im Energieblock (Lieferant) und eine Netz-Pauschale je Zählpunkt im Netzblock (reguliert, bundesweit einheitlich). Zusammen mit dem Arbeitspreis bestimmt sie die Jahreskosten; bei niedrigem Verbrauch dominiert die Grundgebühr.

---

## L

**Lastprofil**
Der zeitliche Verlauf des Stromverbrauchs (bzw. der Erzeugung), meist in Viertelstunden-Auflösung über ein Jahr. Haushalte ohne eigene Messung werden über synthetische Standardlastprofile abgebildet. Das Lastprofil ist Eingangsgröße für Eigenverbrauchsquote, Autarkie und für spotpreis-bezogene Auswertungen, siehe [[community/kennzahlen]].

---

## N

**Netzbereich**
Die regulatorische Tarifzone, für die ein einheitlicher NE-7-Netztarif gilt - in Österreich definiert die Systemnutzungsentgelte-Verordnung genau 14 davon (9 Bundesländer, 4 Stadtnetzbereiche, 1 Sonderfall). Deine PLZ/Gemeinde bestimmt den Netzbereich und damit die Netzkosten; sie sind nicht wechselbar. Zuordnung in `data/netz/plz_netzbereich.json`, Konzept in [[netz/netzentgelte]].

**Netzbetreiber (VNB)**
Verteilnetzbetreiber - das Unternehmen, das das lokale Stromnetz betreibt (in Österreich rund 119 juristische Einheiten). Wichtig: Unter der aktuellen Verordnung haben kleine Stadtwerke keine eigenen Tarife mehr, sondern verrechnen den Tarif ihres Netzbereichs; der Betreibername ist nur Attribution, nicht ein anderer Preis. Siehe [[netz/netzentgelte]].

**Netzebene (NE 3-NE 7)**
Die Spannungsebenen des Netzes, von Hochspannung (NE 3) bis Niederspannung (NE 7, 400 V). Je tiefer die Ebene, desto näher am Haushalt und desto höher das Entgelt pro kWh (Kosten höherer Ebenen werden nach unten gewälzt). Haushalte hängen an NE 7 als "nicht gemessene Leistung" - das ist die relevante Tarifzeile. Detail in [[netz/netzentgelte]].

**Netznutzungsentgelt**
Reguliertes Entgelt für die Nutzung des Netzes (§ 5 Systemnutzungsentgelte-Verordnung): Arbeitspreis in ct/kWh plus Netz-Pauschale in €/Jahr je Zählpunkt. Netzbereichsspezifisch und nicht wechselbar - es ist der größere der beiden reinen Netzkosten-Posten. Werte in `data/netz/netzkosten.json`, berechnet von [[netz/netzentgelte]].

**Netzverlustentgelt**
Reguliertes Entgelt zur Deckung der physikalischen Leitungsverluste (§ 6 Systemnutzungsentgelte-Verordnung), in ct/kWh, je Netzbereich. Achtung Verwechslungsfalle: Es gibt einen Entnehmer-Wert (für Verbraucher, je Netzbereich) und einen bundesweit uniformen Einspeiser-Wert - für die Haushaltskosten zählt der Entnehmer-Wert.

---

## P

**Profilkostenfaktor**
Maß dafür, wie teuer ein bestimmtes Verbrauchs- oder Erzeugungsprofil am Spotmarkt ist, weil es zeitlich nicht zum mittleren Marktpreis passt (z. B. PV-Überschuss zur Mittagszeit, wenn der Spotpreis niedrig ist). Er erklärt, warum die tatsächlich erzielte ct/kWh vom einfachen Jahresmittel des Spotpreises abweicht - relevant für Einspeise- und dynamische Tarife.

---

## R

**Reststrom**
Der Anteil des Verbrauchs, der trotz eigener Erzeugung und Speicher aus dem Netz bezogen werden muss (das Gegenstück zum Autarkiegrad). Auf Gemeinschaftsebene: die Energie, die eine [[community/energiegemeinschaften]] nicht intern decken kann und extern zukaufen muss. Wird in [[community/kennzahlen]] berechnet.

---

## S

**Smart Meter / Zählpunkt**
Der Zählpunkt ist die eindeutige Kennung deiner Verbrauchsstelle (33-stelliger Code) - alle Pauschalen werden je Zählpunkt verrechnet. Der Smart Meter ist das digitale Messgerät, das Viertelstundenwerte erfasst und damit dynamische Tarife, exakte Eigenverbrauchsberechnung und Energiegemeinschaften erst ermöglicht. Ohne Smart-Meter-Daten arbeitet man mit Standardlastprofilen.

**Spotpreis**
Der an der Strombörse (EPEX/EXAA) gebildete Großhandelspreis, üblicherweise stündlich für den Folgetag (Day-Ahead). Er ist die Basis dynamischer Tarife, deren Arbeitspreis dem Spotpreis (plus Aufschlag) folgt, sowie vieler Einspeisevergütungen. Schwankt stark nach Tageszeit und Last - siehe Profilkostenfaktor.

**Systemnutzungsentgelte-Verordnung (SNE-V)**
Die bundesweite Verordnung der E-Control (BGBl. II Nr. 305/2025), die die regulierten Netzkosten je Netzbereich und Netzebene festlegt - die autoritative Tarifliste für Netznutzung (§ 5), Netzverlust (§ 6) und Ausgleichszahlungen (§ 13). Wird jährlich novelliert; die Werte hier folgen der für das Tarifjahr maßgeblichen Novelle. Erklärung in [[netz/netzentgelte]] und [`NETZKOSTEN_UND_GEBUEHREN.md`](../../NETZKOSTEN_UND_GEBUEHREN.md).

---

## Ü

**Überschusseinspeisung**
Die ins Netz abgegebene Energie, die nicht selbst verbraucht oder gespeichert werden konnte (das Gegenstück zur Eigenverbrauchsquote). Sie wird zum Einspeisetarif vergütet - meist deutlich niedriger als die vermiedenen Bezugskosten, weshalb sich hoher Eigenverbrauch wirtschaftlich oft mehr lohnt als Einspeisung. Wird in [[community/kennzahlen]] berechnet.

---

## V

**Vollkosten / Gesamtkosten**
Die komplette Jahres-Stromrechnung brutto: Energie (Block 1) plus Netzkosten (Block 2) plus Steuern und Abgaben (Block 3) plus 20 % Umsatzsteuer (Block 4). Sie ist die einzig faire Vergleichsgröße für eine konkrete Adresse - ein reiner Energiepreisvergleich, der die ortsfesten Netzkosten ignoriert, vergleicht Äpfel mit Birnen. Berechnet von [[netz/gesamtkosten]].

---

## Siehe auch

- [[index]] - Einstieg und Übersicht des Wikis
- [[netz/netzentgelte]] - Netzkosten im Detail (Netzebenen, Netzbereiche, SNE-V)

## Berechnet von

Die hier definierten Größen werden von den energietools-Capabilities ermittelt, u. a. `netzkosten`, `gesamtkosten`, `grid_fees` (Netz/Abgaben), `tariff_compare`/`tarifvergleich_inkl_netz` (Tarife inkl. Netz), `community_metrics` (Eigenverbrauch/Autarkie/Reststrom/Überschuss) und `finance` (ROI/NPV/LCOE). Aufruf: `python -m energietools <name> --json '{...}'`.

## Quellen

- Preiszusammensetzung (Vier-Block-Modell, Begriffe): [`NETZKOSTEN_UND_GEBUEHREN.md`](../../NETZKOSTEN_UND_GEBUEHREN.md)
- Erhebung und Validierung der Zahlen: [`METHODIK.md`](../../METHODIK.md)
- Netzkosten: Systemnutzungsentgelte-Verordnung, BGBl. II Nr. 305/2025 (E-Control)
- Elektrizitätsabgabe: Elektrizitätsabgabegesetz (ElAbgG)
- EAG-Förderbeitrag: Erneuerbaren-Ausbau-Gesetz (EAG) / ÖMAG
- Daten-Snapshots: `energietools/data/netz/` (netzkosten.json, abgaben.json, plz_netzbereich.json, MANIFEST), `energietools/data/tariffs/`

Stand: 2026-06
