// Geteilte energietools-Laufzeit für die hosted-Tools.
// Lädt Pyodide (CDN, vom Browser über Tools hinweg gecacht), installiert die
// MIT-Library energietools aus dem gebündelten Wheel + minimale Abhängigkeiten,
// und gibt die Pyodide-Instanz zurück. Pro Seite einmal (memoisiert).
const PYODIDE_VERSION = "0.27.7";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const WHEEL = "/wheels/energietools-0.3.0-py3-none-any.whl";

let _promise = null;

export function loadEnergietools(onStatus) {
  if (_promise) return _promise;
  _promise = (async () => {
    const say = (m) => onStatus && onStatus(m);
    say("Lade Laufzeit …");
    const { loadPyodide } = await import(`${PYODIDE_URL}pyodide.mjs`);
    const py = await loadPyodide({ indexURL: PYODIDE_URL });
    say("Lade Pakete …");
    await py.loadPackage(["micropip", "numpy"]);
    const micropip = py.pyimport("micropip");
    await micropip.install(["pydantic"]);
    say("Lade energietools …");
    await micropip.install(window.location.origin + WHEEL, { deps: false });
    say("");
    return py;
  })();
  return _promise;
}

// Komfort: deutsches Euro-/Zahlenformat.
export function eur(x) {
  return new Intl.NumberFormat("de-AT", {
    style: "currency",
    currency: "EUR",
  }).format(x);
}
