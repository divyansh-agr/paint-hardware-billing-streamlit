import streamlit as st
import sqlite3, os, io, html, hashlib, json
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER

DB_PATH = "billing.db"

st.set_page_config(page_title="Paint & Hardware Billing", page_icon="🧾", layout="wide")


def db():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db(); cur = con.cursor()
    cur.execute("CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), shop_name TEXT, address TEXT, gstin TEXT, phone TEXT, state TEXT, state_code TEXT, declaration TEXT, username TEXT, password TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS customers (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, phone TEXT, address TEXT, gstin TEXT, state TEXT, state_code TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS invoices (id INTEGER PRIMARY KEY AUTOINCREMENT, invoice_no TEXT UNIQUE, invoice_date TEXT, customer_name TEXT, customer_address TEXT, customer_gstin TEXT, customer_state TEXT, customer_state_code TEXT, taxable REAL, cgst REAL, sgst REAL, igst REAL DEFAULT 0, total REAL, items_json TEXT)")
    cols=[r[1] for r in cur.execute('PRAGMA table_info(invoices)').fetchall()]
    if 'igst' not in cols: cur.execute('ALTER TABLE invoices ADD COLUMN igst REAL DEFAULT 0')
    if cur.execute("SELECT COUNT(*) FROM settings").fetchone()[0] == 0:
        cur.execute("INSERT INTO settings VALUES (1,?,?,?,?,?,?,?,?,?)", ("Agarwal Paint & Hardware Store", "Jattari, Aligarh, Uttar Pradesh", "", "", "Uttar Pradesh", "09", "Goods once sold will not be taken back unless agreed.", "admin", "admin123"))
    con.commit(); con.close()


def settings():
    return dict(db().execute("SELECT * FROM settings WHERE id=1").fetchone())


def next_invoice():
    row = db().execute("SELECT invoice_no FROM invoices ORDER BY id DESC LIMIT 1").fetchone()
    if not row: return "INV-0001"
    try: return f"INV-{int(row['invoice_no'].split('-')[-1])+1:04d}"
    except: return f"INV-{row['invoice_no']}-1"


def money(x): return f"₹ {Decimal(str(x)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"


def num_words(n):
    # compact Indian number-to-words
    ones=["zero","one","two","three","four","five","six","seven","eight","nine","ten","eleven","twelve","thirteen","fourteen","fifteen","sixteen","seventeen","eighteen","nineteen"]
    tens=["","","twenty","thirty","forty","fifty","sixty","seventy","eighty","ninety"]
    def under1000(x):
        if x<20:return ones[x]
        if x<100:return tens[x//10]+(" "+ones[x%10] if x%10 else "")
        return ones[x//100]+" hundred"+(" "+under1000(x%100) if x%100 else "")
    n=int(round(float(n))); parts=[]
    for div,name in [(10000000,"crore"),(100000,"lakh"),(1000,"thousand"),(1,"")]:
        q=n//div; n%=div
        if q: parts.append(under1000(q)+(" "+name if name else ""))
    return " ".join(parts).title() if parts else "Zero"


def make_pdf(inv, items, s):
    buf=io.BytesIO(); doc=SimpleDocTemplate(buf,pagesize=A4,rightMargin=28,leftMargin=28,topMargin=25,bottomMargin=25)
    styles=getSampleStyleSheet(); small=ParagraphStyle('small', parent=styles['Normal'], fontSize=7.5, leading=9); right=ParagraphStyle('right', parent=small, alignment=TA_RIGHT); center=ParagraphStyle('center', parent=small, alignment=TA_CENTER)
    story=[]
    story += [Paragraph('<b>TAX INVOICE</b>', ParagraphStyle('title',parent=styles['Title'],fontSize=15,alignment=TA_CENTER)), Spacer(1,6)]
    seller=f"<b>{html.escape(s['shop_name'])}</b><br/>{html.escape(s['address'])}<br/>GSTIN: {html.escape(s['gstin'] or '—')}<br/>Phone: {html.escape(s['phone'] or '—')}"
    meta=f"<b>Invoice No.:</b> {inv['invoice_no']}<br/><b>Invoice Date:</b> {inv['invoice_date']}<br/><b>State:</b> {html.escape(s['state'])} ({html.escape(s['state_code'])})"
    t=Table([[Paragraph(seller,small),Paragraph(meta,small)]],colWidths=[350,160]); t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.6,colors.black),('INNERGRID',(0,0),(-1,-1),.4,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5)])); story += [t,Spacer(1,5)]
    buyer=f"<b>Bill To</b><br/>{html.escape(inv['customer_name'])}<br/>{html.escape(inv['customer_address'] or '')}<br/>GSTIN: {html.escape(inv['customer_gstin'] or '—')}<br/>State: {html.escape(inv['customer_state'] or '')} ({html.escape(inv['customer_state_code'] or '')})"
    bt=Table([[Paragraph(buyer,small)]],colWidths=[510]); bt.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.6,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)])); story += [bt,Spacer(1,6)]
    data=[["S.No.","Description of Goods","HSN/SAC","Qty","Rate","Disc. %","Amount"]]
    for i,it in enumerate(items,1): data.append([str(i),it['description'],it['hsn'],str(it['qty']),money(it['rate']),f"{it['discount']:.2f}",money(it['amount'])])
    data.append(["","","","","","Taxable",money(inv['taxable'])])
    data.append(["","","","","","CGST",money(inv['cgst'])])
    data.append(["","","","","","SGST",money(inv['sgst'])])
    if float(inv.get('igst',0)): data.append(["","","","","","IGST",money(inv['igst'])])
    data.append(["","","","","","TOTAL",money(inv['total'])])
    tt=Table(data,colWidths=[30,180,60,40,65,55,80],repeatRows=1)
    tt.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.45,colors.black),('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(-2,-4),(-1,-1),'Helvetica-Bold'),('ALIGN',(0,0),(-1,-1),'CENTER'),('ALIGN',(1,1),(1,-1),'LEFT'),('ALIGN',(-1,1),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('FONTSIZE',(0,0),(-1,-1),7.2),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)])); story += [tt,Spacer(1,6)]
    story += [Paragraph(f"<b>Amount in Words:</b> Rupees {num_words(inv['total'])} Only",small), Paragraph(f"<b>Tax Amount in Words:</b> Rupees {num_words(inv['cgst']+inv['sgst']+inv.get('igst',0))} Only",small), Spacer(1,12)]
    bottom=Table([[Paragraph(f"<b>Declaration</b><br/>{html.escape(s['declaration'])}",small),Paragraph("For <b>"+html.escape(s['shop_name'])+"</b><br/><br/><br/>Authorized Signatory",right)]],colWidths=[340,170]); bottom.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.6,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6)])); story += [bottom,Spacer(1,5),Paragraph("This is a computer generated invoice",center)]
    doc.build(story); buf.seek(0); return buf.getvalue()

init_db()

if 'logged' not in st.session_state: st.session_state.logged=False
if not st.session_state.logged:
    st.markdown("# 🧾 Paint & Hardware Billing")
    st.caption("GST billing — no e-invoice QR, IRN or acknowledgement fields")
    with st.form("login"):
        u=st.text_input("Username"); p=st.text_input("Password",type="password")
        if st.form_submit_button("Login",use_container_width=True):
            s=settings()
            if u==s['username'] and p==s['password']: st.session_state.logged=True; st.rerun()
            else: st.error("Invalid username or password")
    st.info("Default login: admin / admin123. Change it in Settings.")
    st.stop()

s=settings()
with st.sidebar:
    st.title("🧾 Billing")
    page=st.radio("Menu",["New Invoice","Invoice History","Customers","Settings"])
    if st.button("Logout"): st.session_state.logged=False; st.rerun()

if page=="New Invoice":
    st.title("New GST Invoice")
    c1,c2=st.columns(2)
    with c1: inv_no=st.text_input("Invoice No.",value=next_invoice())
    with c2: inv_date=st.date_input("Invoice Date",date.today())
    st.subheader("Customer")
    customers=db().execute("SELECT * FROM customers ORDER BY name").fetchall()
    names=["New Customer"]+[x['name'] for x in customers]
    selected=st.selectbox("Customer",names)
    cust=next((dict(x) for x in customers if x['name']==selected),None)
    cc=st.columns(2)
    with cc[0]: cname=st.text_input("Customer Name",value=cust['name'] if cust else "")
    with cc[1]: cgstin=st.text_input("GSTIN (optional)",value=cust['gstin'] if cust else "")
    ca=st.text_input("Address",value=cust['address'] if cust else "")
    cs1,cs2=st.columns(2)
    with cs1: cstate=st.text_input("State",value=cust['state'] if cust else "")
    with cs2: ccode=st.text_input("State Code",value=cust['state_code'] if cust else "")
    st.subheader("Items")
    if 'items' not in st.session_state: st.session_state["items"]=[]
    with st.form("add_item",clear_on_submit=True):
        a,b,c,d,e,f=st.columns([3,1.2,1,1.3,1.2,1])
        desc=a.text_input("Description"); hsn=b.text_input("HSN/SAC"); qty=c.number_input("Qty",min_value=0.01,value=1.0); rate=d.number_input("Rate",min_value=0.0,value=0.0); disc=e.number_input("Disc %",min_value=0.0,max_value=100.0,value=0.0); gst=f.selectbox("GST %",[0,5,12,18,28])
        add=st.form_submit_button("+ Add Item")
        if add and desc:
            gross=qty*rate; amount=gross*(1-disc/100)
            st.session_state["items"].append({'description':desc,'hsn':hsn,'qty':qty,'rate':rate,'discount':disc,'gst':gst,'amount':amount})
            st.rerun()
    if st.session_state["items"]:
        for i,it in enumerate(st.session_state["items"]):
            x=st.columns([4,1,1,1,1,1])
            x[0].write(it['description']); x[1].write(it['qty']); x[2].write(money(it['rate'])); x[3].write(f"{it['gst']}%"); x[4].write(money(it['amount']))
            if x[5].button("Remove",key=f"rm{i}"): st.session_state["items"].pop(i); st.rerun()
        taxable=sum(x['amount'] for x in st.session_state["items"])
        same_state = bool(cstate.strip()) and cstate.strip().lower() == s['state'].strip().lower()
        cgst=sum(x['amount']*x['gst']/200 for x in st.session_state["items"]) if same_state else 0
        sgst=cgst
        igst=sum(x['amount']*x['gst']/100 for x in st.session_state["items"]) if not same_state else 0
        total=taxable+cgst+sgst+igst
        st.markdown(f"**Taxable:** {money(taxable)}  |  **CGST:** {money(cgst)}  |  **SGST:** {money(sgst)}  |  **IGST:** {money(igst)}  |  **TOTAL:** {money(total)}")
        if st.button("Generate & Save Invoice",type="primary",use_container_width=True):
            con=db()
            try:
                con.execute("INSERT INTO invoices(invoice_no,invoice_date,customer_name,customer_address,customer_gstin,customer_state,customer_state_code,taxable,cgst,sgst,igst,total,items_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",(inv_no,str(inv_date),cname,ca,cgstin,cstate,ccode,taxable,cgst,sgst,igst,total,json.dumps(st.session_state["items"])))
                con.commit(); st.success(f"Invoice {inv_no} saved.")
                inv={'invoice_no':inv_no,'invoice_date':str(inv_date),'customer_name':cname,'customer_address':ca,'customer_gstin':cgstin,'customer_state':cstate,'customer_state_code':ccode,'taxable':taxable,'cgst':cgst,'sgst':sgst,'igst':igst,'total':total}
                pdf=make_pdf(inv,st.session_state["items"],s)
                st.download_button("⬇️ Download PDF",pdf,file_name=f"{inv_no}.pdf",mime="application/pdf")
                st.session_state["items"]=[]
            except sqlite3.IntegrityError: st.error("Invoice number already exists.")
            finally: con.close()

elif page=="Invoice History":
    st.title("Invoice History")
    rows=db().execute("SELECT * FROM invoices ORDER BY id DESC").fetchall()
    for r in rows:
        cols=st.columns([1.2,1.2,3,1.5,1.2])
        cols[0].write(r['invoice_no']); cols[1].write(r['invoice_date']); cols[2].write(r['customer_name']); cols[3].write(money(r['total']))
        if cols[4].button("PDF",key=f"pdf{r['id']}"):
            items=__import__('json').loads(r['items_json']); st.download_button("Download",make_pdf(dict(r),items,s),file_name=f"{r['invoice_no']}.pdf",mime="application/pdf",key=f"dl{r['id']}")

elif page=="Customers":
    st.title("Customers")
    with st.form("customer"):
        n=st.text_input("Name"); ph=st.text_input("Phone"); ad=st.text_input("Address"); g=st.text_input("GSTIN"); stt=st.text_input("State"); sc=st.text_input("State Code")
        if st.form_submit_button("Save Customer"):
            if n:
                con=db(); con.execute("INSERT INTO customers(name,phone,address,gstin,state,state_code) VALUES(?,?,?,?,?,?)",(n,ph,ad,g,stt,sc)); con.commit(); con.close(); st.success("Customer saved."); st.rerun()
    for r in db().execute("SELECT * FROM customers ORDER BY name").fetchall(): st.write(f"**{r['name']}** — {r['gstin'] or 'No GSTIN'} — {r['phone'] or ''}")

else:
    st.title("Shop Settings")
    s=settings()
    with st.form("settings"):
        name=st.text_input("Shop Name",s['shop_name']); address=st.text_area("Address",s['address']); gstin=st.text_input("GSTIN",s['gstin']); phone=st.text_input("Phone",s['phone']); state=st.text_input("State",s['state']); code=st.text_input("State Code",s['state_code']); dec=st.text_area("Declaration",s['declaration']); user=st.text_input("Login Username",s['username']); pw=st.text_input("Login Password",s['password'],type="password")
        if st.form_submit_button("Save Settings"):
            con=db(); con.execute("UPDATE settings SET shop_name=?,address=?,gstin=?,phone=?,state=?,state_code=?,declaration=?,username=?,password=? WHERE id=1",(name,address,gstin,phone,state,code,dec,user,pw)); con.commit(); con.close(); st.success("Settings saved. Reload the page to see changes.")
