"""py build_master_seed.py  Project_List.xlsx  [portal/data/master_seed.json]  -  turns the Project Master workbook (v2) into the seed file that
   py manage.py import_master  loads into the portal."""
import openpyxl, json, datetime, re, sys
SRC=sys.argv[1]
OUT=sys.argv[2] if len(sys.argv)>2 else 'portal/data/master_seed.json'
wb=openpyxl.load_workbook(SRC,data_only=True)
def iso(v):
    if isinstance(v,datetime.datetime): return v.date().isoformat()
    if isinstance(v,datetime.date): return v.isoformat()
    return None
def clean(v):
    if v is None: return None
    if isinstance(v,float) and v==int(v) and abs(v)<1e12: pass
    if isinstance(v,str):
        v=v.strip()
        return v or None
    return v
def sheet(name,hrow=4,first=5):
    ws=wb[name]; h=[(c.value or '').strip() if isinstance(c.value,str) else c.value for c in ws[hrow]]
    out={}
    for r in ws.iter_rows(min_row=first,values_only=True):
        pid=r[0]
        if pid and str(pid).strip().startswith('DH'):
            out[str(pid).strip()]={h[i]:r[i] for i in range(len(h)) if h[i]}
    return out
M=sheet('Project Master'); E=sheet('Equipment-Serials'); K=sheet('KSEB-PMSG Tracker'); C=sheet('Contractor Payouts'); H=sheet('Handover-Warranty')
def num(v):
    return float(v) if isinstance(v,(int,float)) and not isinstance(v,bool) else None
def phone(v):
    if v is None: return None
    if isinstance(v,float): v=int(v)
    d=re.sub(r'\D','',str(v)); return d[-10:] if len(d)>=10 else (str(v).strip() or None)
seed={}
for pid,m in M.items():
    r={}
    def put(k,v):
        v=clean(v)
        if v is not None: r[k]=v
    put('name',m.get('Customer Name')); put('booking_date',iso(m.get('Booking Date')))
    put('phone',phone(m.get('Phone'))); put('alt_phone',phone(m.get('Alternate Phone'))); put('email',m.get('Email'))
    put('site_address',m.get('Site Address'))
    pc=m.get('Pincode'); put('pincode',str(int(pc)) if isinstance(pc,(int,float)) else pc)
    put('district',m.get('District')); put('region',m.get('Region')); put('map_link',m.get('Google Map Link'))
    cn=m.get('KSEB Consumer No.'); put('consumer_no',str(int(cn)) if isinstance(cn,(int,float)) else cn)
    put('load_change',m.get('Load Change Required?')); put('scheme',m.get('Scheme')); put('segment',m.get('Segment')); put('sales_person',m.get('Sales In-Charge'))
    for k,col in (('quote_value','Quote Value (Rs)'),('panel_wp','Panel Wattage (Wp)'),('panel_count','No. of Panels'),('dc_kwp','DC Capacity (kWp)'),('ac_kw','AC / Inverter Capacity (kW)')):
        n=num(m.get(col)); 
        if n is not None: r[k]=n
    put('system',m.get('System Type')); put('almm',m.get('ALMM'))
    kw=m.get('Capacity (kW)'); 
    if kw is not None: r['kw']=('%g'%kw) if isinstance(kw,(int,float)) else str(kw).strip()
    put('panel_make',m.get('Panel Brand')); put('inverter_make',m.get('Inverter Brand')); put('stage',m.get('Project Stage')); put('engineer',m.get('Site In-Charge / Engineer')); put('remarks',m.get('Remarks'))
    e=E.get(pid,{})
    put('panel_serials',e.get('Panel Serial Numbers (separate with comma)')); put('inverter_model',e.get('Inverter Model')); put('inverter_phase',e.get('Inverter Phase'))
    put('inverter_serial',e.get('Inverter Serial No.')); put('energy_meter_make',e.get('Energy Meter Make')); put('energy_meter_serial',e.get('Energy Meter Serial No.'))
    put('net_meter_make',e.get('Net Meter Make')); put('net_meter_serial',e.get('Net Meter Serial No.')); put('roof_type',e.get('Roof Type'))
    for k,col in (('panel_at_site','Panel Material at Site?'),('inverter_at_site','Inverter Material at Site?')): put(k,e.get(col))
    k_=K.get(pid,{}); ks={}
    for key,col in (('portal_app','Portal Application Date'),('docs','Documents Submitted to KSEB'),('feasibility','Feasibility Approval Date'),('reg_paid','Registration Fee Paid Date'),
                    ('work_start','Work Start Date'),('work_done','Work Completion Date'),('netmeter_app','Install Details Submitted / Net Meter Applied'),('inspection','KSEB Inspection Date'),
                    ('agreement','Net Metering Agreement Date'),('meter_fix','Net Meter Fix Date'),('programming','Meter Programming / Sync Date'),('commissioning','Commissioning Certificate Date (Portal)'),
                    ('subsidy','Subsidy Credited Date')):
        d=iso(k_.get(col))
        if d: ks[key]=d
    if ks: r['kseb']=ks
    put('arn',k_.get('PM Surya Ghar Application No. (ARN)')); put('kseb_ref',k_.get('KSEB Application / Ref. No.')); put('docs_status',k_.get('Documents Status'))
    put('reg_receipt',k_.get('Reg. Fee Receipt No.')); put('inspection_status',k_.get('Inspection Status')); put('programming_notes',k_.get('Programming Notes (settings, CT ratio, MF, initial reading)'))
    put('bank_details',k_.get('Bank Details Submitted on Portal')); put('subsidy_status',k_.get('Subsidy Status')); put('kseb_notes',k_.get('Blocker / Notes'))
    c=C.get(pid,{})
    put('electrical_contractor',c.get('Electrical Contractor')); put('structure_contractor',c.get('Structure Contractor'))
    for k,col in (('electrical_amount','Electrical Amount (Rs)'),('electrical_paid','Electrical Paid (Rs)'),('structure_amount','Structure Amount (Rs)'),('structure_paid','Structure Paid (Rs)')):
        n=num(c.get(col)); 
        if n: r[k]=n
    h=H.get(pid,{})
    put('invoice_no',h.get('Invoice No.')); put('invoice_date',iso(h.get('Invoice Date'))); n=num(h.get('Invoice Value (Rs)'))
    if n: r['invoice_value']=n
    put('handover_status',h.get('Handover Status')); put('handover_date',iso(h.get('Handover Date'))); put('handover_mode',h.get('Handover Mode')); put('handed_over_by',h.get('Handed Over By'))
    put('warranty_start',iso(h.get('Warranty Start Date (blank = commissioning date)')))
    for k,col in (('panel_warranty_yrs','Panel Product Warranty (yrs)'),('panel_perf_yrs','Panel Performance Warranty (yrs)'),('inverter_warranty_yrs','Inverter Warranty (yrs)'),('workmanship_yrs','Workmanship Warranty (yrs) - blank = 5 (Settings)')):
        n=num(h.get(col))
        if n: r[k]=n
    seed[pid]=r
json.dump(seed,open(OUT,'w',encoding='utf-8'),ensure_ascii=False,indent=0,sort_keys=True)
print(len(seed))
