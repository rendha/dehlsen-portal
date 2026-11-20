"""py build_master_seed_v3.py  Dehlsen_Project_Master_All_Years.xlsx  [portal/data/master_seed.json]
Turns the all-years Project Master workbook (633 projects) into the seed file that  py manage.py import_master  loads.
Keeps what the old seed file already holds for a project (KSEB dates, contractor amounts, invoices...) and lets the workbook's values replace the same keys."""
import openpyxl, json, datetime, re, sys
from pathlib import Path
SRC = sys.argv[1]
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "portal/data/master_seed.json")
wb = openpyxl.load_workbook(SRC, data_only=True)
def iso(v):
    return v.date().isoformat() if isinstance(v, datetime.datetime) else (v.isoformat() if isinstance(v, datetime.date) else None)
def clean(v):
    if isinstance(v, str):
        v = v.strip()
        return v or None
    return v
def num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
def phone(v):
    if v is None: return None
    if isinstance(v, float): v = int(v)
    d = re.sub(r"\D", "", str(v)); return d[-10:] if len(d) >= 10 else (str(v).strip() or None)
def sheet(name):
    rows = list(wb[name].iter_rows(values_only=True)); h = rows[3]
    return {str(r[0]).strip(): {h[i]: r[i] for i in range(len(h)) if h[i]} for r in rows[4:] if r[0] and str(r[0]).strip().startswith("DH")}
M, E = sheet("Project Master"), sheet("Equipment-Serials")
old = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
seed = {}
for pid, m in M.items():
    r = {}
    def put(k, v):
        v = clean(v)
        if v is not None: r[k] = v
    put("name", m.get("Customer Name")); put("booking_date", iso(m.get("Booking Date")))
    put("phone", phone(m.get("Phone"))); put("alt_phone", phone(m.get("Alternate Phone"))); put("email", m.get("Email"))
    put("site_address", m.get("Site Address"))
    pc = m.get("Pincode"); put("pincode", str(int(pc)) if isinstance(pc, (int, float)) else pc)
    put("district", m.get("District")); put("region", m.get("Region (sales)")); put("map_link", m.get("Google Map Link"))
    cn = m.get("KSEB Consumer No."); put("consumer_no", str(int(cn)) if isinstance(cn, (int, float)) else cn)
    put("load_change", m.get("Load Change Required?")); put("scheme", m.get("Scheme")); put("segment", m.get("Segment")); put("sales_person", m.get("Sales In-Charge"))
    for k, col in (("quote_value", "Quote Value (Rs)"), ("panel_wp", "Panel Wattage (Wp)"), ("panel_count", "No. of Panels"), ("dc_kwp", "DC Capacity (kWp)"), ("ac_kw", "Inverter Capacity (kW)")):
        n = num(m.get(col))
        if n is not None: r[k] = n
    put("system", m.get("System Type")); put("almm", m.get("ALMM"))
    kw = m.get("Capacity (kW)")
    if kw is not None: r["kw"] = ("%g" % kw) if isinstance(kw, (int, float)) else str(kw).strip()
    put("panel_make", m.get("Panel Brand")); put("inverter_make", m.get("Inverter Brand")); put("inverter_phase", m.get("Inverter Phase"))
    put("stage", m.get("Project Stage")); put("engineer", m.get("Site In-Charge")); put("remarks", m.get("Remarks")); put("roof_type", m.get("Roof Type"))
    put("handover_status", m.get("Handover Status (invoice + warranty given)"))
    put("panel_at_site", m.get("Panel Material at Site")); put("inverter_at_site", m.get("Inverter Material at Site"))
    com = iso(m.get("Commissioning Date"))
    e = E.get(pid, {})
    put("panel_serials", e.get("Panel Serial Numbers (separate with comma)")); put("inverter_model", e.get("Inverter Model")); put("inverter_serial", e.get("Inverter Serial No."))
    put("energy_meter_make", e.get("Energy Meter Make")); put("energy_meter_serial", e.get("Energy Meter Serial No.")); put("net_meter_make", e.get("Net Meter Make")); put("net_meter_serial", e.get("Net Meter Serial No."))
    kseb = dict((old.get(pid) or {}).get("kseb") or {})
    if com and "commissioning" not in kseb: kseb["commissioning"] = com
    if kseb: r["kseb"] = kseb
    merged = dict(old.get(pid) or {}); merged.update(r)
    if "kseb" in r: merged["kseb"] = r["kseb"]
    seed[pid] = merged
for pid in old:                       # never drop a project the old seed had
    seed.setdefault(pid, old[pid])
OUT.write_text(json.dumps(seed, indent=1, sort_keys=True, ensure_ascii=False), encoding="utf-8")
print("%d projects written to %s  (%d from the workbook, %d only in the old seed)" % (len(seed), OUT, len(M), len(set(old) - set(M))))
