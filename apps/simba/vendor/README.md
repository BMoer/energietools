# vendored / pvtool

`pvtool/` ist eine **vendored** Kopie der Batteriespeicher-Engine von
**Jakob (GitHub: holzjfk-a11y)** aus `batterystorage-sim` (MIT, Zustimmung liegt
vor — siehe [`../../../CREDITS.md`](../../../CREDITS.md)).

Sie liegt hier **nur für die übergangsweise hybriden Teile** von Simba, die noch
nicht nach `energietools` portiert sind: die **Live-Connectoren** (aWATTar, ENTSO-E,
Solis, PVGIS-Stundenserie) und die **volle Wärmepumpen-Summary**. Diese werden im
Backend **lazy** importiert.

Der eigentliche Rechenkern (Batterie-Dispatch, Peak-Shaving, ROI, Netzentgelte,
Regelenergie-Auswertung) läuft **nicht** mehr über pvtool, sondern über die offene
`energietools`-Library. Ziel ist, auch die Connector-/HP-Logik nach `energietools`
zu ziehen und dieses Vendoring dann zu entfernen.

Nicht editieren — bei Bedarf aus der Quelle neu vendoren.
