# Messung

Messung ist die Grundlage jeder Abrechnung und jeder fundierten Analyse: Wie viel Strom wann verbraucht (oder eingespeist) wird, misst der Zähler an deinem **Zählpunkt**. Mit dem **Smart Meter** werden daraus zeitlich aufgelöste Daten - die Voraussetzung für Spot-Tarife, Eigenverbrauchs-Optimierung und Energiegemeinschaften.

## Worum es geht

- **Smart Meter:** Intelligenter Zähler, der den Verbrauch automatisch und zeitlich fein erfasst (Österreich-weiter Rollout). Ersetzt die jährliche Ablesung und liefert die Datenbasis für zeitvariable Tarife.
- **Zählpunkt:** Die eindeutige Kennung deiner Verbrauchsstelle (33-stellige Zählpunktnummer). An ihn hängen Pauschalen (z. B. Netz-Pauschale, EAG-Förderpauschale) und die Zuordnung zum Netzbereich.
- **Lastprofile & 15-min-Werte:** Smart Meter erfassen Viertelstundenwerte. Das Lastprofil zeigt, wann du Strom brauchst - entscheidend für Spot-Tarife, Batterie-Auslegung und die Berechnung von Eigenverbrauch und Autarkie.
- **Datenzugang:** Die Messdaten gehören dir. Du beziehst sie über die **Netzbetreiber-Portale** (z. B. Wiener Netze, Netz NÖ) - meist als CSV/Export im Web-Portal, teils per API. energietools liest diese Exporte für die Lastprofil- und Community-Analyse.

## Siehe auch

- [[tarife/index]] - Spot-/Floater-Tarife, die Viertelstundenwerte nutzen
- [[wirtschaftlichkeit/index]] - Eigenverbrauch, Autarkie und Batterie-Wirtschaftlichkeit aus Lastprofilen
- [[netz/index]] - Zählpunkt, Netzbereich und die zählpunktbezogenen Pauschalen
- [[markt/index]] - Bilanzgruppen und das Viertelstundenraster des Marktes
- [[glossar]]

## Berechnet von

- Tool `load_profile` - Lastprofil-Analyse aus Smart-Meter-Daten (FDA-Anomalieerkennung, Heatmaps)
- Tool `smartmeter` - Smart-Meter-Datenzugriff (benötigt Live-Zugangsdaten; Wiener Netze implementiert, Netz NÖ in Arbeit)
- Capability `community_metrics` - Eigenverbrauchs-/Autarkie-Kennzahlen aus Erzeugungs- und Verbrauchsreihen

## Quellen

- ElWOG / Intelligente-Messgeräte-Einführungsverordnung (IMA-VO) - Smart-Meter-Rollout und Datenzugang
- Netzbetreiber-Portale (Wiener Netze, Netz NÖ u. a.) - Export der eigenen Messdaten
- Erhebung & Validierung: [`METHODIK.md`](../../METHODIK.md)

Stand: 2026-06
