import streamlit as st
import pandas as pd
import sqlite3
import os
import io
import hashlib
from PIL import Image
from datetime import date, datetime
try:
    from translations import LANGUAGES
except ImportError:
    # Fallback داخلي حتى يعمل الملف منفردًا إذا لم يكن translations.py موجودًا
    LANGUAGES = {
        "العربية": {
            "title": "نظام إدارة العمليات والمخزون", "login": "تسجيل الدخول",
            "username": "اسم المستخدم", "password": "رمز الدخول", "login_btn": "دخول",
            "logout": "خروج من النظام", "prod_tab": "الإنتاج",
            "staff_tab": "وجبات الموظفين", "consume_tab": "صرف للإنتاج", "count_tab": "الجرد الدوري"
        },
        "English": {
            "title": "Operations & Inventory Management", "login": "Login",
            "username": "Username", "password": "PIN", "login_btn": "Sign in",
            "logout": "Logout", "prod_tab": "Production",
            "staff_tab": "Staff Meals", "consume_tab": "Production Issue", "count_tab": "Inventory Count"
        }
    }

# مكتبات توليد الـ PDF العريض (Landscape)
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Operations & Integrated Inventory Hub", layout="wide")

# 1. إعداد وتحديث جداول قاعدة البيانات
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("INVENTORY_DB_PATH", os.path.join(BASE_DIR, "inventory_data.db"))
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

# ترقية آمنة لقاعدة البيانات: تضيف أعمدة الرقابة دون حذف البيانات القديمة
def ensure_column(table_name, column_name, definition):
    cols = {row[1] for row in cursor.execute(f"PRAGMA table_info({table_name})").fetchall()}
    if column_name not in cols:
        cursor.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

def audit_action(table_name, record_id, action, branch, old_value="", new_value="", reason=""):
    cursor.execute(
        """INSERT INTO audit_log
           (table_name, record_id, action, branch, old_value, new_value, reason, changed_by)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (table_name, record_id, action, branch, str(old_value), str(new_value), reason, st.session_state.get("user", "system"))
    )

cursor.execute("""
CREATE TABLE IF NOT EXISTS operations_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entry_type TEXT,
    branch TEXT,
    to_branch TEXT,
    entry_date TEXT,
    item_type TEXT,
    item_sku TEXT,
    item_name TEXT,
    quantity REAL,
    unit TEXT,
    reason TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS purchases_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT,
    supplier_name TEXT,
    branch TEXT,
    invoice_date TEXT,
    item_sku TEXT,
    item_name TEXT,
    quantity REAL,
    cost_per_unit REAL,
    tax_percent REAL,
    total_with_tax REAL,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS cashier_closings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT,
    closing_date TEXT,
    cashier_name TEXT,
    cash_sales REAL,
    mada_sales REAL,
    visa_sales REAL,
    mastercard_sales REAL,
    bank_transfers REAL,
    hungerstation REAL,
    jahez REAL,
    ninja REAL,
    keeta REAL,
    expenses_notes TEXT,
    expenses_amount REAL,
    total_sales REAL,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS inventory_counts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT,
    count_date TEXT,
    count_id TEXT,
    item_sku TEXT,
    item_name TEXT,
    storage_qty REAL,
    ingredients_qty REAL,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS items_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_type TEXT,
    foodics_id TEXT,
    sku TEXT UNIQUE,
    name_ar TEXT,
    name_en TEXT,
    storage_unit TEXT,
    ingredient_unit TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS suppliers_master (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    foodics_id TEXT,
    name TEXT UNIQUE,
    code TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name TEXT NOT NULL,
    record_id INTEGER,
    action TEXT NOT NULL,
    branch TEXT,
    old_value TEXT,
    new_value TEXT,
    reason TEXT,
    changed_by TEXT,
    changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS transfers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transfer_date TEXT NOT NULL,
    from_branch TEXT NOT NULL,
    to_branch TEXT NOT NULL,
    item_type TEXT NOT NULL,
    item_sku TEXT NOT NULL,
    item_name TEXT,
    quantity_sent REAL NOT NULL,
    quantity_received REAL,
    unit TEXT,
    notes TEXT,
    status TEXT DEFAULT 'sent',
    created_by TEXT,
    received_by TEXT,
    received_date TEXT,
    received_at TIMESTAMP,
    entry_source TEXT DEFAULT 'direct_branch',
    updated_by TEXT,
    updated_at TIMESTAMP,
    cancel_reason TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS opening_balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT NOT NULL,
    period_month TEXT NOT NULL,
    item_sku TEXT NOT NULL,
    item_name TEXT,
    quantity REAL DEFAULT 0,
    source_count_date TEXT,
    created_by TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(branch, period_month, item_sku)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS period_closings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    branch TEXT NOT NULL,
    period_month TEXT NOT NULL,
    closing_date TEXT NOT NULL,
    status TEXT DEFAULT 'closed',
    notes TEXT,
    closed_by TEXT,
    closed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reopened_by TEXT,
    reopened_at TIMESTAMP,
    UNIQUE(branch, period_month)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS import_registry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    import_type TEXT NOT NULL,
    file_name TEXT,
    file_hash TEXT UNIQUE,
    branch TEXT,
    row_count INTEGER,
    imported_by TEXT,
    imported_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")


for _table in ["operations_log", "purchases_log", "cashier_closings", "inventory_counts"]:
    ensure_column(_table, "entry_source", "TEXT DEFAULT 'direct_branch'")
    ensure_column(_table, "status", "TEXT DEFAULT 'active'")
    ensure_column(_table, "updated_by", "TEXT")
    ensure_column(_table, "updated_at", "TIMESTAMP")
    ensure_column(_table, "cancel_reason", "TEXT")
ensure_column("operations_log", "movement_code", "TEXT")
ensure_column("transfers", "received_date", "TEXT")
ensure_column("items_master", "storage_to_ingredient_factor", "REAL")
# ترقية السجلات القديمة إلى أكواد حركة ثابتة لا تعتمد على لغة الواجهة
cursor.execute("UPDATE operations_log SET movement_code='PRODUCTION_ISSUE' WHERE movement_code IS NULL AND (entry_type LIKE '%منصرف%' OR entry_type LIKE '%صرف للإنتاج%')")
cursor.execute("UPDATE operations_log SET movement_code='STAFF_MEAL' WHERE movement_code IS NULL AND entry_type LIKE '%وجبات%'")
cursor.execute("UPDATE operations_log SET movement_code='WASTE' WHERE movement_code IS NULL AND entry_type LIKE '%هدر%'")
cursor.execute("UPDATE operations_log SET movement_code='PRODUCTION' WHERE movement_code IS NULL AND entry_type LIKE '%إنتاج%'")
conn.commit()

# تحميل الموردين والأصناف تلقائياً من الملفات
def load_seed_data():
    cursor.execute("SELECT COUNT(*) FROM items_master")
    if cursor.fetchone()[0] == 0:
        for f in os.listdir(BASE_DIR):
            if f.startswith("products_export") and f.endswith(".csv"):
                df_prod = pd.read_csv(os.path.join(BASE_DIR, f))
                for _, r in df_prod.iterrows():
                    cursor.execute("""
                    INSERT OR IGNORE INTO items_master (item_type, foodics_id, sku, name_ar, name_en, storage_unit, ingredient_unit)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, ('production', str(r.get('id')), str(r.get('sku')), str(r.get('name')), str(r.get('name_localized')), str(r.get('storage_unit')), str(r.get('ingredient_unit'))))
            elif f.startswith("inventory_items_export") and f.endswith(".csv"):
                df_inv = pd.read_csv(os.path.join(BASE_DIR, f))
                for _, r in df_inv.iterrows():
                    cursor.execute("""
                    INSERT OR IGNORE INTO items_master (item_type, foodics_id, sku, name_ar, name_en, storage_unit, ingredient_unit)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, ('inventory', str(r.get('id')), str(r.get('sku')), str(r.get('name')), str(r.get('name_localized')), str(r.get('storage_unit')), str(r.get('ingredient_unit'))))
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM suppliers_master")
    if cursor.fetchone()[0] == 0:
        for f in os.listdir(BASE_DIR):
            if "suppliers_export" in f and f.endswith(".csv"):
                df_sup = pd.read_csv(os.path.join(BASE_DIR, f))
                for _, r in df_sup.iterrows():
                    cursor.execute("INSERT OR IGNORE INTO suppliers_master (foodics_id, name, code) VALUES (?, ?, ?)",
                                   (str(r.get('id')), str(r.get('name')), str(r.get('code'))))
        conn.commit()

load_seed_data()

# مزامنة معامل التحويل من ملفات Foodics حتى لقواعد البيانات القديمة
for _f in os.listdir(BASE_DIR):
    if _f.startswith("inventory_items_export") and _f.endswith(".csv"):
        try:
            _idf = pd.read_csv(os.path.join(BASE_DIR, _f))
            if "storage_to_ingredient_factor" in _idf.columns:
                for _, _r in _idf.iterrows():
                    _factor = _r.get("storage_to_ingredient_factor")
                    if not pd.isna(_factor):
                        cursor.execute("UPDATE items_master SET storage_to_ingredient_factor=? WHERE sku=?", (float(_factor), str(_r.get("sku"))))
                conn.commit()
        except Exception:
            pass

BRANCH_LIST = ["ELarouba", "Malqa", "Alrawdah", "Laban"]

USERS = {
    "admin": {"pin": "9999", "role": "admin", "branch": "الكل", "name": "الإدارة العامة"},
    "accountant": {"pin": "5555", "role": "accountant", "branch": "الكل", "name": "المحاسب المالي"},
    "arouba": {"pin": "1001", "role": "cashier", "branch": "ELarouba", "name": "فرع العروبة"},
    "malqa": {"pin": "1002", "role": "cashier", "branch": "Malqa", "name": "فرع الملقا"},
    "rawdah": {"pin": "1003", "role": "cashier", "branch": "Alrawdah", "name": "فرع الروضة"},
    "laban": {"pin": "1004", "role": "cashier", "branch": "Laban", "name": "فرع لبن"}
}

if "auth" not in st.session_state:
    st.session_state.auth = False
    st.session_state.user = None
    st.session_state.role = None
    st.session_state.branch = None
    st.session_state.name = None
    st.session_state.active_branch = None

current_lang = st.sidebar.selectbox("🌐 Language / اختر اللغة", list(LANGUAGES.keys()))
t = LANGUAGES[current_lang]

if not st.session_state.auth:
    st.title(t.get("title", "نظام إدارة العمليات والمخزون"))
    st.subheader(t.get("login", "تسجيل الدخول"))
    c1, _ = st.columns([1, 2])
    with c1:
        u_input = st.text_input(t.get("username", "اسم المستخدم"), placeholder="اسم المستخدم").strip().lower()
        p_input = st.text_input(t.get("password", "رمز الدخول"), type="password", placeholder="PIN")
        if st.button(t.get("login_btn", "دخول"), use_container_width=True):
            if u_input in USERS and USERS[u_input]["pin"] == p_input:
                st.session_state.auth = True
                st.session_state.user = u_input
                st.session_state.role = USERS[u_input]["role"]
                st.session_state.branch = USERS[u_input]["branch"]
                st.session_state.name = USERS[u_input]["name"]
                st.session_state.active_branch = USERS[u_input]["branch"] if USERS[u_input]["role"] == "cashier" else BRANCH_LIST[0]
                st.rerun()
            else:
                st.error("اسم المستخدم أو رمز الدخول غير صحيح!")
    st.stop()

st.sidebar.markdown(f"**المستخدم:** {st.session_state.name}")

is_privileged = st.session_state.role in ["admin", "accountant"]
is_admin = st.session_state.role == "admin"
if is_privileged:
    workspace_mode = st.sidebar.radio("وضع العمل:", ["📊 لوحة الإدارة", "🏪 العمل داخل فرع"], key="workspace_mode")
    if workspace_mode == "🏪 العمل داخل فرع":
        st.session_state.active_branch = st.sidebar.selectbox(
            "الفرع الذي تعمل نيابةً عنه:", BRANCH_LIST,
            index=BRANCH_LIST.index(st.session_state.active_branch) if st.session_state.active_branch in BRANCH_LIST else 0,
            key="admin_active_branch"
        )
        st.sidebar.info("أي إدخال هنا سيُحفظ باسم الفرع المختار، مع تسجيل اسم مستخدم المكتب ومصدر الإدخال.")
else:
    workspace_mode = "🏪 العمل داخل فرع"
    st.session_state.active_branch = st.session_state.branch

active_branch = st.session_state.active_branch
entry_source = "office_paper" if is_privileged and workspace_mode == "🏪 العمل داخل فرع" else "direct_branch"
st.sidebar.markdown(f"**الفرع النشط:** `{active_branch if workspace_mode == '🏪 العمل داخل فرع' else 'جميع الفروع'}`")
st.sidebar.divider()


def month_key(d):
    return pd.to_datetime(d).strftime("%Y-%m")

def is_period_closed(branch, d):
    pm = month_key(d)
    row = cursor.execute("SELECT status FROM period_closings WHERE branch=? AND period_month=?", (branch, pm)).fetchone()
    return bool(row and row[0] == "closed")

def require_open_period(branch, d):
    if is_period_closed(branch, d):
        st.error(f"الفترة {month_key(d)} للفرع {branch} مغلقة. لا يمكن إضافة أو تعديل حركات داخلها قبل إعادة فتحها من الإدارة.")
        return False
    return True

def latest_count_series(branch, upto_date=None):
    params=[branch]
    q="SELECT * FROM inventory_counts WHERE branch=? AND COALESCE(status,'active')='active'"
    if upto_date:
        q += " AND count_date<=?"; params.append(str(upto_date))
    q += " ORDER BY count_date DESC, id DESC"
    df=pd.read_sql_query(q, conn, params=params)
    if df.empty: return pd.Series(dtype=float)
    df=df.drop_duplicates(subset=['item_sku'], keep='first')
    factors=pd.read_sql_query("SELECT sku, storage_to_ingredient_factor FROM items_master", conn).set_index('sku')['storage_to_ingredient_factor']
    df['factor']=df['item_sku'].map(factors)
    df['normalized_qty']=df['storage_qty'].fillna(0).astype(float)
    valid=df['factor'].fillna(0).astype(float)>0
    df.loc[valid,'normalized_qty'] += df.loc[valid,'ingredients_qty'].fillna(0).astype(float) / df.loc[valid,'factor'].astype(float)
    return df.set_index('item_sku')['normalized_qty']

def inventory_balance(branch, start_date=None, end_date=None):
    items=pd.read_sql_query("SELECT sku, name_ar, item_type, storage_unit FROM items_master ORDER BY name_ar", conn).set_index('sku')
    items['رصيد أول المدة']=0.0
    if start_date:
        pm=month_key(start_date)
        ob=pd.read_sql_query("SELECT item_sku, quantity FROM opening_balances WHERE branch=? AND period_month=?", conn, params=(branch,pm))
        if not ob.empty: items['رصيد أول المدة']=items.index.map(ob.set_index('item_sku')['quantity']).fillna(0)
    filters=[]; params=[]
    if start_date: filters.append('invoice_date>=?'); params.append(str(start_date))
    if end_date: filters.append('invoice_date<=?'); params.append(str(end_date))
    where=(' AND '+' AND '.join(filters)) if filters else ''
    p=pd.read_sql_query(f"SELECT item_sku,SUM(quantity) q FROM purchases_log WHERE branch=? AND COALESCE(status,'active')='active'{where} GROUP BY item_sku", conn, params=[branch]+params)
    pser=p.set_index('item_sku')['q'] if not p.empty else pd.Series(dtype=float)
    items['المشتريات (+)']=items.index.map(pser).fillna(0)

    of=[]; op=[]
    if start_date: of.append('entry_date>=?'); op.append(str(start_date))
    if end_date: of.append('entry_date<=?'); op.append(str(end_date))
    ow=(' AND '+' AND '.join(of)) if of else ''
    odf=pd.read_sql_query(f"SELECT * FROM operations_log WHERE branch=? AND COALESCE(status,'active')='active'{ow}", conn, params=[branch]+op)
    def sum_code(code):
        if odf.empty: return pd.Series(dtype=float)
        d=odf[odf['movement_code'].fillna('').eq(code)]
        return d.groupby('item_sku')['quantity'].sum() if not d.empty else pd.Series(dtype=float)
    issue=sum_code('PRODUCTION_ISSUE')
    waste=sum_code('WASTE')
    staff=sum_code('STAFF_MEAL')
    prod=sum_code('PRODUCTION')
    for name,ser in [('الصرف للإنتاج (-)',issue),('الهدر (-)',waste),('وجبات (-)',staff),('الإنتاج (+)',prod)]: items[name]=items.index.map(ser).fillna(0)

    tf=[]; tp=[]
    if start_date: tf.append('transfer_date>=?'); tp.append(str(start_date))
    if end_date: tf.append('transfer_date<=?'); tp.append(str(end_date))
    tw=(' AND '+' AND '.join(tf)) if tf else ''
    tout=pd.read_sql_query(f"SELECT item_sku,SUM(quantity_sent) q FROM transfers WHERE from_branch=? AND status IN ('sent','received'){tw} GROUP BY item_sku", conn, params=[branch]+tp)
    inf=[]; inp=[]
    if start_date: inf.append('COALESCE(received_date, DATE(received_at), transfer_date)>=?'); inp.append(str(start_date))
    if end_date: inf.append('COALESCE(received_date, DATE(received_at), transfer_date)<=?'); inp.append(str(end_date))
    inw=(' AND '+' AND '.join(inf)) if inf else ''
    tin=pd.read_sql_query(f"SELECT item_sku,SUM(COALESCE(quantity_received,quantity_sent)) q FROM transfers WHERE to_branch=? AND status='received'{inw} GROUP BY item_sku", conn, params=[branch]+inp)
    touts=tout.set_index('item_sku')['q'] if not tout.empty else pd.Series(dtype=float)
    tins=tin.set_index('item_sku')['q'] if not tin.empty else pd.Series(dtype=float)
    items['تحويل وارد (+)']=items.index.map(tins).fillna(0); items['تحويل صادر (-)']=items.index.map(touts).fillna(0)
    items['الرصيد الدفتري المتوقع']=items['رصيد أول المدة']+items['المشتريات (+)']+items['الإنتاج (+)']+items['تحويل وارد (+)']-items['الصرف للإنتاج (-)']-items['الهدر (-)']-items['وجبات (-)']-items['تحويل صادر (-)']
    actual=latest_count_series(branch,end_date)
    items['الجرد الفعلي']=items.index.map(actual)
    items['فارق الجرد (عجز/زيادة)']=items['الجرد الفعلي']-items['الرصيد الدفتري المتوقع']
    return items.reset_index()

# دالة توليد PDF بالوضع العرضي (Landscape)
def generate_pdf_report(df, title_text):
    pdf_buffer = io.BytesIO()
    doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(letter), rightMargin=20, leftMargin=20, topMargin=25, bottomMargin=25)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=14, alignment=1, spaceAfter=15)
    
    elements.append(Paragraph(title_text, title_style))
    elements.append(Spacer(1, 5))
    
    table_data = [list(df.columns)] + df.astype(str).values.tolist()
    
    t = Table(table_data)
    t.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2c3e50')),
        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE', (0,0), (-1,0), 9),
        ('BOTTOMPADDING', (0,0), (-1,0), 6),
        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#ecf0f1')),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('FONTSIZE', (0,1), (-1,-1), 7.5),
    ]))
    
    elements.append(t)
    doc.build(elements)
    pdf_buffer.seek(0)
    return pdf_buffer.getvalue()

# ----------------- واجهة الكاشير / الفرع -----------------
if workspace_mode == "🏪 العمل داخل فرع":
    st.sidebar.markdown("### 🗂️ القائمة الرئيسية للفرع")
    c_mode = st.sidebar.radio("القسم:", [
        "العمليات والتشغيل اليومي", 
        "🗑️ الهدر والتالف (الإنتاج والمخزون)",
        "📝 تقرير الإغلاق المالي",
        "📥 التحويلات الواردة",
        t.get("count_tab", "الجرد الدوري")
    ])

    st.title(f"📍 بوابة الفرع - {st.session_state.name}")

    # 1. العمليات والتشغيل اليومي (متعدد الأصناف مع وحدة متغيرة ديناميكياً)
    if c_mode == "العمليات والتشغيل اليومي":
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚙️ نوع الحركة")
        tab_type = st.sidebar.radio("اختر العملية:", [
            t.get("prod_tab", "الإنتاج"), 
            t.get("staff_tab", "وجبات الموظفين"), 
            t.get("consume_tab", "منصرف المخزن"), 
            "🚚 إرسال تحويل لفرع"
        ])

        target_source = "production" if tab_type in [t.get("prod_tab", "الإنتاج"), t.get("staff_tab", "وجبات الموظفين")] else "inventory"
        movement_code = ("PRODUCTION" if tab_type == t.get("prod_tab", "الإنتاج") else "STAFF_MEAL" if tab_type == t.get("staff_tab", "وجبات الموظفين") else "PRODUCTION_ISSUE" if tab_type == t.get("consume_tab", "منصرف المخزن") else "TRANSFER")
        if tab_type == "🚚 إرسال تحويل لفرع":
            transfer_kind = st.radio("نوع الأصناف المحولة:", ["خامات/مواد مخزون", "منتجات نهائية"], horizontal=True, key="transfer_kind")
            target_source = "inventory" if transfer_kind == "خامات/مواد مخزون" else "production"
        df_items = pd.read_sql_query("SELECT sku, name_ar, name_en, storage_unit FROM items_master WHERE item_type=? ORDER BY name_ar ASC", conn, params=(target_source,))
        item_dict = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit']) for _, r in df_items.iterrows()}
        
        c_top1, c_top2 = st.columns(2)
        with c_top1: op_date = st.date_input("التاريخ:", value=date.today(), key="op_d")
        with c_top2: to_br = st.selectbox("تحويل إلى فرع:", [b for b in BRANCH_LIST if b != active_branch]) if tab_type == "🚚 إرسال تحويل لفرع" else "-"

        st.markdown(f"#### 📋 تسجيل حركة: `{tab_type}` (أدخل عدة أصناف معاً)")
        if "ops_rows" not in st.session_state:
            st.session_state.ops_rows = [{"item": list(item_dict.keys())[0] if item_dict else "", "qty": 1.0, "reason": ""}]

        for idx, row_val in enumerate(st.session_state.ops_rows):
            col_r = st.columns([4, 2, 2, 3, 1])
            sel_it = col_r[0].selectbox(f"صنف {idx+1}", list(item_dict.keys()) if item_dict else ["لا توجد أصناف"], index=list(item_dict.keys()).index(row_val["item"]) if row_val["item"] in item_dict else 0, key=f"op_it_{idx}")
            row_val["item"] = sel_it
            row_val["qty"] = col_r[1].number_input(f"كمية {idx+1}", min_value=0.1, step=0.5, value=row_val["qty"], key=f"op_q_{idx}")
            
            # جلب وتحديث وحدة الصنف ديناميكياً
            unit_dynamic = item_dict[sel_it][2] if sel_it in item_dict else "pcs"
            col_r[2].text_input(f"وحدة {idx+1}", value=str(unit_dynamic), disabled=True, key=f"op_u_{idx}")
            
            row_val["reason"] = col_r[3].text_input(f"سبب {idx+1}", value=row_val["reason"], placeholder="ملاحظة", key=f"op_r_{idx}")
            if col_r[4].button("❌", key=f"del_op_{idx}"):
                if len(st.session_state.ops_rows) > 1:
                    st.session_state.ops_rows.pop(idx)
                    st.rerun()

        if st.button("➕ إضافة سطر صنف آخر"):
            st.session_state.ops_rows.append({"item": list(item_dict.keys())[0] if item_dict else "", "qty": 1.0, "reason": ""})
            st.rerun()

        if st.button("💾 حفظ كافة العمليات المسجلة في النظام", type="primary", use_container_width=True):
            _selected=[r["item"] for r in st.session_state.ops_rows if r["item"] in item_dict]
            if len(_selected) != len(set(_selected)):
                st.error("يوجد نفس الصنف أكثر من مرة في النموذج. اجمع الكمية في سطر واحد لمنع التكرار."); st.stop()
            for r in st.session_state.ops_rows:
                if r["item"] in item_dict:
                    s_sku, s_name, s_unit = item_dict[r["item"]]
                    if not require_open_period(active_branch, op_date):
                        st.stop()
                    if tab_type == "🚚 إرسال تحويل لفرع":
                        cursor.execute("""INSERT INTO transfers
                            (transfer_date,from_branch,to_branch,item_type,item_sku,item_name,quantity_sent,unit,notes,status,created_by,entry_source)
                            VALUES (?,?,?,?,?,?,?,?,?,'sent',?,?)""",
                            (str(op_date),active_branch,to_br,target_source,s_sku,s_name,r["qty"],str(s_unit),r["reason"],st.session_state.user,entry_source))
                        audit_action("transfers", cursor.lastrowid, "create", active_branch, "", {"to":to_br,"sku":s_sku,"qty":r["qty"]}, "إرسال تحويل")
                    else:
                        cursor.execute("""
                        INSERT INTO operations_log (entry_type, branch, to_branch, entry_date, item_type, item_sku, item_name, quantity, unit, reason, created_by, entry_source, movement_code, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                        """, (tab_type, active_branch, to_br, str(op_date), target_source, s_sku, s_name, r["qty"], str(s_unit), r["reason"], st.session_state.user, entry_source, movement_code))
            conn.commit()
            st.success(f"تم حفظ الحركات بنجاح!")
            st.session_state.ops_rows = [{"item": list(item_dict.keys())[0] if item_dict else "", "qty": 1.0, "reason": ""}]

    # 2. الهدر والتالف (متعدد الأصناف وبوحدات متغيرة ديناميكياً)
    elif c_mode == "🗑️ الهدر والتالف (الإنتاج والمخزون)":
        st.subheader("🗑️ تسجيل الهدر والتالف اليومي (متعدد الأصناف)")
        waste_target = st.radio("حدد نوع التالف/الهدر:", ["هدر إنتاج (منتجات نهائية)", "هدر خامات مخزن"], horizontal=True)
        w_source = "production" if "إنتاج" in waste_target else "inventory"
        
        df_w_items = pd.read_sql_query("SELECT sku, name_ar, storage_unit FROM items_master WHERE item_type=? ORDER BY name_ar ASC", conn, params=(w_source,))
        w_item_dict = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit']) for _, r in df_w_items.iterrows()}
        
        w_date = st.date_input("تاريخ الهدر:", value=date.today())
        
        if "waste_rows" not in st.session_state:
            st.session_state.waste_rows = [{"item": list(w_item_dict.keys())[0] if w_item_dict else "", "qty": 1.0, "reason": ""}]

        st.markdown("#### 📋 جدول الأصناف التالفة:")
        for idx, w_row in enumerate(st.session_state.waste_rows):
            col_w = st.columns([4, 2, 2, 3, 1])
            sel_w_it = col_w[0].selectbox(f"صنف هدر {idx+1}", list(w_item_dict.keys()) if w_item_dict else ["لا توجد أصناف"], index=list(w_item_dict.keys()).index(w_row["item"]) if w_row["item"] in w_item_dict else 0, key=f"w_it_{idx}")
            w_row["item"] = sel_w_it
            w_row["qty"] = col_w[1].number_input(f"كمية هدر {idx+1}", min_value=0.1, step=0.5, value=w_row["qty"], key=f"w_q_{idx}")
            
            unit_w_dynamic = w_item_dict[sel_w_it][2] if sel_w_it in w_item_dict else "pcs"
            col_w[2].text_input(f"وحدة هدر {idx+1}", value=str(unit_w_dynamic), disabled=True, key=f"w_u_{idx}")
            
            w_row["reason"] = col_w[3].text_input(f"سبب {idx+1}", value=w_row["reason"], placeholder="سبب الهدر (إجباري)", key=f"w_r_{idx}")
            if col_w[4].button("❌", key=f"del_w_{idx}"):
                if len(st.session_state.waste_rows) > 1:
                    st.session_state.waste_rows.pop(idx)
                    st.rerun()

        if st.button("➕ إضافة صنف تالف آخر"):
            st.session_state.waste_rows.append({"item": list(w_item_dict.keys())[0] if w_item_dict else "", "qty": 1.0, "reason": ""})
            st.rerun()

        if st.button("💾 حفظ وترحيل كافة أصناف الهدر والتالف", type="primary", use_container_width=True):
            if not require_open_period(active_branch, w_date): st.stop()
            _selected=[r["item"] for r in st.session_state.waste_rows if r["item"] in w_item_dict]
            if len(_selected) != len(set(_selected)):
                st.error("يوجد نفس صنف الهدر أكثر من مرة. اجمع الكمية في سطر واحد."); st.stop()
            for wr in st.session_state.waste_rows:
                if wr["item"] in w_item_dict and wr["reason"].strip():
                    sk_w, nm_w, u_w = w_item_dict[wr["item"]]
                    cursor.execute("""
                    INSERT INTO operations_log (entry_type, branch, to_branch, entry_date, item_type, item_sku, item_name, quantity, unit, reason, created_by, entry_source, movement_code, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'WASTE', 'active')
                    """, ("الهدر والتالف", active_branch, "-", str(w_date), w_source, sk_w, nm_w, wr["qty"], str(u_w), wr["reason"], st.session_state.user, entry_source))
            conn.commit()
            st.success("تم تسجيل وترحيل كافة بنود الهدر والتالف بنجاح!")
            st.session_state.waste_rows = [{"item": list(w_item_dict.keys())[0] if w_item_dict else "", "qty": 1.0, "reason": ""}]

    # 3. تقرير الإغلاق المالي
    elif c_mode == "📝 تقرير الإغلاق المالي":
        st.subheader("📝 تقرير الإيرادات والمبيعات اليومية المستلمة (Daily Closing Sheet)")
        with st.form("cashier_closing_form"):
            c_f1, c_f2 = st.columns(2)
            with c_f1:
                cl_date = st.date_input("التاريخ (Date):", value=date.today())
                c_name = st.text_input("اسم الكاشير (Cashier Name):", value=st.session_state.name)
                c_cash = st.number_input("المبيعات النقدية (Cash Sales):", min_value=0.0, step=10.0)
                c_mada = st.number_input("شبكة مدى (Mada):", min_value=0.0, step=10.0)
                c_visa = st.number_input("فيزا (Visa):", min_value=0.0, step=10.0)
                c_master = st.number_input("ماستركارد (MasterCard):", min_value=0.0, step=10.0)
                c_trans = st.number_input("التحويلات البنكية (Bank Transfers):", min_value=0.0, step=10.0)
            with c_f2:
                c_hunger = st.number_input("هنقرستيشن (Hungerstation):", min_value=0.0, step=10.0)
                c_jahez = st.number_input("جاهز (Jahez):", min_value=0.0, step=10.0)
                c_ninja = st.number_input("نينجا (Ninja):", min_value=0.0, step=10.0)
                c_keeta = st.number_input("كيتا (Keeta):", min_value=0.0, step=10.0)
                c_exp_note = st.text_input("بيان المصروفات النثرية / العجز:", placeholder="مثال: فاتورة لبن المراعي كبير")
                c_exp_amt = st.number_input("مبلغ المصروفات النثرية (SAR):", min_value=0.0, step=1.0)
            c_total = c_cash + c_mada + c_visa + c_master + c_trans + c_hunger + c_jahez + c_ninja + c_keeta
            st.metric("إجمالي المبيعات اليومية المحسوبة", f"{c_total:,.2f} SAR")
            if st.form_submit_button("📤 إرسال واعتماد التقرير المالي للإدارة", type="primary", use_container_width=True):
                if not require_open_period(active_branch, cl_date): st.stop()
                cursor.execute("""
                INSERT INTO cashier_closings (branch, closing_date, cashier_name, cash_sales, mada_sales, visa_sales, mastercard_sales, bank_transfers, hungerstation, jahez, ninja, keeta, expenses_notes, expenses_amount, total_sales, created_by, entry_source, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """, (active_branch, str(cl_date), c_name, c_cash, c_mada, c_visa, c_master, c_trans, c_hunger, c_jahez, c_ninja, c_keeta, c_exp_note, c_exp_amt, c_total, st.session_state.user, entry_source))
                conn.commit()
                st.success("تم إرسال تقرير الإغلاق المالي بنجاح إلى الإدارة والمحاسب!")

    # 4. التحويلات الواردة
    elif c_mode == "📥 التحويلات الواردة":
        st.subheader(f"📥 التحويلات الواردة إلى {active_branch}")
        df_in = pd.read_sql_query("SELECT * FROM transfers WHERE to_branch=? AND status='sent' ORDER BY id DESC", conn, params=(active_branch,))
        if df_in.empty:
            st.info("لا توجد تحويلات معلقة للاستلام.")
        else:
            st.dataframe(df_in, use_container_width=True)
            tr_id = st.selectbox("اختر التحويل للاستلام:", df_in['id'].tolist())
            tr = df_in[df_in['id']==tr_id].iloc[0]
            received_qty = st.number_input("الكمية المستلمة فعليًا:", min_value=0.0, value=float(tr['quantity_sent']), step=0.1)
            receive_date = st.date_input("تاريخ الاستلام الفعلي:", value=date.today(), key="transfer_receive_date")
            receive_note = st.text_input("ملاحظة الاستلام/سبب الفرق إن وجد:")
            if st.button("✅ تأكيد الاستلام", type="primary", use_container_width=True):
                if not require_open_period(active_branch, receive_date): st.stop()
                if abs(float(received_qty)-float(tr['quantity_sent'])) > 1e-9 and not receive_note.strip():
                    st.error("يوجد فرق بين المرسل والمستلم؛ اكتب سبب الفرق قبل الاعتماد."); st.stop()
                cursor.execute("UPDATE transfers SET quantity_received=?, received_date=?, status='received', received_by=?, received_at=CURRENT_TIMESTAMP, notes=CASE WHEN ?='' THEN notes ELSE COALESCE(notes,'') || ' | استلام: ' || ? END WHERE id=? AND to_branch=? AND status='sent'", (received_qty,str(receive_date),st.session_state.user,receive_note,receive_note,int(tr_id),active_branch))
                audit_action("transfers", int(tr_id), "receive", active_branch, {"sent":float(tr['quantity_sent'])}, {"received":received_qty,"received_date":str(receive_date)}, receive_note or "استلام مطابق")
                conn.commit(); st.success("تم استلام التحويل وإضافته إلى مخزون الفرع."); st.rerun()

    # 5. الجرد الدوري (متعدد الأصناف في جدول واحد منظم)
    else:
        st.subheader("📋 الجرد الدوري الفعلي للمخزون (إدخال عدة أصناف معاً)")
        df_inv = pd.read_sql_query("SELECT sku, name_ar, storage_unit, ingredient_unit FROM items_master ORDER BY item_type, name_ar ASC", conn)
        cnt_map = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit'], r['ingredient_unit']) for _, r in df_inv.iterrows()}
        
        c_cnt1, c_cnt2 = st.columns(2)
        with c_cnt1: cnt_d = st.date_input("تاريخ الجرد:", value=date.today())
        with c_cnt2: cnt_id = st.text_input("معرف الجرد في فودكس (اختياري):", placeholder="رقم الجرد")

        if "count_rows" not in st.session_state:
            st.session_state.count_rows = [{"item": list(cnt_map.keys())[0] if cnt_map else "", "q_st": 0.0, "q_in": 0.0}]

        st.markdown("#### 📦 جدول جرد الأصناف:")
        for idx, c_row in enumerate(st.session_state.count_rows):
            col_c = st.columns([4, 2, 2, 1])
            sel_c_it = col_c[0].selectbox(f"صنف جرد {idx+1}", list(cnt_map.keys()) if cnt_map else ["لا توجد أصناف"], index=list(cnt_map.keys()).index(c_row["item"]) if c_row["item"] in cnt_map else 0, key=f"c_it_{idx}")
            c_row["item"] = sel_c_it
            
            u_st_dyn = cnt_map[sel_c_it][2] if sel_c_it in cnt_map else "pcs"
            u_in_dyn = cnt_map[sel_c_it][3] if sel_c_it in cnt_map else "pcs"
            
            c_row["q_st"] = col_c[1].number_input(f"تخزين ({u_st_dyn}) {idx+1}", min_value=0.0, step=1.0, value=c_row["q_st"], key=f"c_qst_{idx}")
            c_row["q_in"] = col_c[2].number_input(f"مكونات ({u_in_dyn}) {idx+1}", min_value=0.0, step=1.0, value=c_row["q_in"], key=f"c_qin_{idx}")
            
            if col_c[3].button("❌", key=f"del_c_{idx}"):
                if len(st.session_state.count_rows) > 1:
                    st.session_state.count_rows.pop(idx)
                    st.rerun()

        if st.button("➕ إضافة صنف آخر للجرد"):
            st.session_state.count_rows.append({"item": list(cnt_map.keys())[0] if cnt_map else "", "q_st": 0.0, "q_in": 0.0})
            st.rerun()

        if st.button("💾 حفظ وترحيل كافة أصناف الجرد للنظام", type="primary", use_container_width=True):
            if not require_open_period(active_branch, cnt_d): st.stop()
            _selected=[r["item"] for r in st.session_state.count_rows if r["item"] in cnt_map]
            if len(_selected) != len(set(_selected)):
                st.error("يوجد نفس الصنف أكثر من مرة في الجرد. يجب أن يظهر كل صنف مرة واحدة فقط."); st.stop()
            for cr in st.session_state.count_rows:
                if cr["item"] in cnt_map:
                    sk_c, nm_c, _, _ = cnt_map[cr["item"]]
                    cursor.execute("""
                        INSERT INTO inventory_counts (branch, count_date, count_id, item_sku, item_name, storage_qty, ingredients_qty, created_by, entry_source, status)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                    """, (active_branch, str(cnt_d), cnt_id.strip(), sk_c, nm_c, cr["q_st"], cr["q_in"], st.session_state.user, entry_source))
            conn.commit()
            st.success("تم حفظ وترحيل كافة بنود الجرد بنجاح!")
            st.session_state.count_rows = [{"item": list(cnt_map.keys())[0] if cnt_map else "", "q_st": 0.0, "q_in": 0.0}]

# ----------------- واجهة الإدارة والمحاسب -----------------
elif is_privileged and workspace_mode == "📊 لوحة الإدارة":
    st.title("📊 لوحة تحكم الإدارة العامة والمحاسبة المالية")
    
    admin_section = st.sidebar.radio("🗂️ أقسام الإدارة:", [
        "📥 استيراد مشتريات فودكس (سريع)",
        "📊 تقرير المدفوعات والمبيعات (مطابق للـ PDF)",
        "🛒 إدخال المشتريات اليدوية",
        "📑 تقارير إغلاق الكاشيرات والطباعة",
        "⚖️ ميزان المخزون والجرد",
        "🍗 تحليل استهلاك الخامات الذكي",
        "🚀 تصدير قوالب فودكس",
        "📋 سجل العمليات اليومية",
        "🔁 متابعة التحويلات",
        "📅 إقفال وفتح الفترات",
        "🛡️ النسخ الاحتياطي والرقابة",
        "✏️ تعديل وإلغاء الحركات"
    ])

    if admin_section == "📥 استيراد مشتريات فودكس (سريع)":
        st.subheader("📥 استيراد تقرير المشتريات من فودكس دفعة واحدة")
        purchased_file = st.file_uploader("اختر ملف المشتريات (CSV)", type=["csv"], key="purchases_csv_uploader")
        if purchased_file is not None:
            try:
                df_purchases = pd.read_csv(purchased_file)
                st.success("تم قراءة الملف بنجاح! معاينة سريعة:")
                st.dataframe(df_purchases.head(5))
                imp_branch = st.selectbox("حدد الفرع المخصص لهذه الفاتورة المستوردة:", BRANCH_LIST, key="imp_br")
                file_bytes = purchased_file.getvalue()
                file_hash = hashlib.sha256(file_bytes).hexdigest()
                already = cursor.execute("SELECT id, imported_at, branch FROM import_registry WHERE file_hash=?", (file_hash,)).fetchone()
                if already:
                    st.error(f"هذا الملف تم استيراده سابقًا (سجل #{already[0]} - الفرع {already[2]} - {already[1]}). تم منع التكرار.")
                if st.button("🚀 ترحيل وحفظ المشتريات في قاعدة البيانات السحابية", type="primary", use_container_width=True, disabled=bool(already)):
                    import_dates = [pd.to_datetime(r.get('Business Date', r.get('Date', date.today()))).date() for _, r in df_purchases.iterrows()]
                    closed_months = sorted({month_key(d) for d in import_dates if is_period_closed(imp_branch, d)})
                    if closed_months:
                        st.error("الملف يحتوي حركات داخل فترات مغلقة: " + ", ".join(closed_months) + ". أعد فتح الفترة أو استخدم ملفًا صحيحًا."); st.stop()
                    count = 0
                    for index, row in df_purchases.iterrows():
                        date_val = str(row.get('Business Date', row.get('Date', date.today())))
                        inv_num_val = str(row.get('Invoice Number', row.get('Invoice', 'FOODICS-IMP')))
                        supplier_val = str(row.get('Supplier Name', row.get('Supplier', 'مورد فودكس')))
                        item_name_val = str(row.get('Item Name', row.get('Name', 'صنف فودكس')))
                        item_sku_val = str(row.get('SKU', '0000'))
                        qty_val = float(row.get('Quantity', row.get('Qty', 1.0)) or 0)
                        total_cost_raw = float(row.get('Total Cost', row.get('Total', 0.0)) or 0)
                        unit_cost_raw = row.get('Unit Cost', row.get('Cost Per Unit', row.get('Cost', None)))
                        cost_val = float(unit_cost_raw) if unit_cost_raw not in (None, '') and not pd.isna(unit_cost_raw) else (total_cost_raw / qty_val if qty_val else 0.0)
                        subtotal_val = total_cost_raw if total_cost_raw else cost_val * qty_val
                        tot_tax_val = subtotal_val * 1.15
                        cursor.execute("""
                            INSERT INTO purchases_log (invoice_number, supplier_name, branch, invoice_date, item_sku, item_name, quantity, cost_per_unit, tax_percent, total_with_tax, created_by, entry_source, status)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'foodics_import', 'active')
                        """, (inv_num_val, supplier_val, imp_branch, date_val, item_sku_val, item_name_val, qty_val, cost_val, 15.0, tot_tax_val, st.session_state.user))
                        count += 1
                    cursor.execute("INSERT INTO import_registry(import_type,file_name,file_hash,branch,row_count,imported_by) VALUES(?,?,?,?,?,?)", ("purchases", purchased_file.name, file_hash, imp_branch, count, st.session_state.user))
                    conn.commit()
                    st.success(f"تم ترحيل وحفظ {count} بند مشتريات بنجاح من ملف فودكس، وتم تسجيل بصمة الملف لمنع استيراده مرتين.")
            except Exception as e:
                st.error(f"حدث خطأ أثناء معالجة الملف: {e}")

    elif admin_section == "📊 تقرير المدفوعات والمبيعات (مطابق للـ PDF)":
        st.subheader("📊 تحليل واستيراد ملف المدفوعات والمبيعات (مطابق تماماً لتقرير الـ PDF)")
        st.write("قم برفع ملف الـ CSV الخاص بالمدفوعات لتوليد تقرير موحد ومقسّم حسب الفروع وقنوات الدفع مع إمكانية التحميل بكافة الصيغ (PDF Landscape, Excel, CSV).")
        
        uploaded_payment_file = st.file_uploader("اختر ملف المدفوعات المصدر من فودكس (CSV)", type=["csv"], key="pdf_like_report_uploader")
        
        if uploaded_payment_file is not None:
            try:
                df = pd.read_csv(uploaded_payment_file)
                branch_mapping = {'ELarouba': 'Alarouba', 'Malqa': 'Malqa', 'Alrawdah': 'AlRawdah', 'AlRawdah': 'AlRawdah', 'Laban': 'Laban'}
                df['Branch_Clean'] = df['الفرع'].map(branch_mapping).fillna(df['الفرع'])
                
                pivot_df = df.pivot_table(index='Branch_Clean', columns='طريقة الدفع', values='المبلغ الصافي', aggfunc='sum', fill_value=0.0)
                expected_cols = ['Cash', 'MADA', 'Bank Trancefer', 'Jahez', 'KEETA', 'Hungerstion', 'Ninja', 'The Chefz']
                for col in expected_cols:
                    if col not in pivot_df.columns: pivot_df[col] = 0.0
                
                pos_bank_cols = [c for c in ['MADA', 'Bank Trancefer', 'Visa', 'MasterCard'] if c in pivot_df.columns]
                pivot_df['Pos Bank'] = pivot_df[pos_bank_cols].sum(axis=1) if pos_bank_cols else 0.0
                pivot_df['Cash Sales'] = pivot_df.get('Cash', 0.0)
                pivot_df['Total Sales Cash'] = pivot_df['Cash Sales'] + pivot_df['Pos Bank']
                pivot_df['Keeta'] = pivot_df.get('KEETA', 0.0)
                pivot_df['Jahez'] = pivot_df.get('Jahez', 0.0)
                pivot_df['Hungerstion'] = pivot_df.get('Hungerstion', 0.0)
                pivot_df['Ninja'] = pivot_df.get('Ninja', 0.0)
                pivot_df['The Chefz'] = pivot_df.get('The Chefz', 0.0)
                
                credit_cols = ['Keeta', 'Jahez', 'Hungerstion', 'Ninja', 'The Chefz']
                pivot_df['Total Sales Credit'] = pivot_df[credit_cols].sum(axis=1)
                pivot_df['Total Sales'] = pivot_df['Total Sales Cash'] + pivot_df['Total Sales Credit']
                
                final_report = pivot_df[['Cash Sales', 'Pos Bank', 'Total Sales Cash', 'Keeta', 'Jahez', 'Hungerstion', 'Ninja', 'The Chefz', 'Total Sales Credit', 'Total Sales']].reset_index()
                totals = final_report.select_dtypes(include=['number']).sum()
                totals['Branch_Clean'] = 'Total Sales Biet Elhaneeth'
                final_report = pd.concat([final_report, pd.DataFrame([totals])], ignore_index=True)
                final_report.columns = ['Branch Name', 'Cash', 'Pos Bank', 'Total Sales Cash', 'Keeta', 'Jahez', 'Hungerstion', 'Ninja', 'The Chefz', 'Total Sales Credit', 'Total Sales']
                
                st.success("✨ تم تحليل ملف المدفوعات وتوليد التقرير بنجاح مطابَقاً لنموذج الـ PDF!")
                st.dataframe(final_report.style.format({c: "{:,.2f}" for c in final_report.columns if c != 'Branch Name'}), use_container_width=True)
                
                col_d1, col_d2, col_d3 = st.columns(3)
                with col_d1:
                    pdf_data = generate_pdf_report(final_report, "Daily Sales & Payments Report")
                    st.download_button("📥 تحميل PDF عريض", pdf_data, "Daily_Sales_Report.pdf", "application/pdf")
                with col_d2:
                    excel_buffer = io.BytesIO()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        final_report.to_excel(writer, index=False, sheet_name='Daily Sales')
                    st.download_button("📥 تحميل Excel", excel_buffer.getvalue(), "Daily_Sales_Report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                with col_d3:
                    st.download_button("📥 تحميل CSV", final_report.to_csv(index=False).encode('utf-8-sig'), "Daily_Sales_Report.csv", "text/csv")

            except Exception as e:
                st.error(f"حدث خطأ أثناء معالجة ملف المدفوعات: {e}")

    elif admin_section == "🛒 إدخال المشتريات اليدوية":
        st.subheader("🛒 تسجيل فواتير المشتريات اليدوية")
        df_sups = pd.read_sql_query("SELECT name FROM suppliers_master ORDER BY name ASC", conn)
        sup_list = df_sups['name'].tolist() if not df_sups.empty else ["مورد عام"]
        df_inv_it = pd.read_sql_query("SELECT sku, name_ar, storage_unit FROM items_master WHERE item_type='inventory' ORDER BY name_ar ASC", conn)
        inv_item_dict = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit']) for _, r in df_inv_it.iterrows()}

        h1, h2, h3, h4 = st.columns(4)
        with h1: inv_number = st.text_input("رقم الفاتورة:", placeholder="INV-001")
        with h2: inv_supplier = st.selectbox("المورد:", sup_list)
        with h3: inv_branch = st.selectbox("الفرع:", BRANCH_LIST)
        with h4: inv_date = st.date_input("التاريخ:", value=date.today())

        if "pur_rows" not in st.session_state:
            st.session_state.pur_rows = [{"item": list(inv_item_dict.keys())[0] if inv_item_dict else "", "qty": 1.0, "price": 10.0}]

        grand_total = 0.0
        for p_idx, p_row in enumerate(st.session_state.pur_rows):
            col_p = st.columns([4, 2, 2, 2, 2, 1])
            p_sel = col_p[0].selectbox(f"صنف {p_idx+1}", list(inv_item_dict.keys()) if inv_item_dict else ["لا توجد أصناف"], key=f"pur_it_{p_idx}")
            p_row["item"] = p_sel
            p_row["qty"] = col_p[1].number_input(f"كمية {p_idx+1}", min_value=0.1, step=1.0, value=p_row["qty"], key=f"pur_q_{p_idx}")
            
            unit_p_dyn = inv_item_dict[p_sel][2] if p_sel in inv_item_dict else "pcs"
            col_p[2].text_input(f"وحدة {p_idx+1}", value=unit_p_dyn, disabled=True, key=f"pur_u_{p_idx}")
            
            p_row["price"] = col_p[3].number_input(f"سعر {p_idx+1}", min_value=0.0, step=0.5, value=p_row["price"], key=f"pur_p_{p_idx}")
            row_tot = (p_row["qty"] * p_row["price"]) * 1.15
            grand_total += row_tot
            col_p[4].write(f"{row_tot:,.2f} SAR")
            if col_p[5].button("❌", key=f"del_pur_{p_idx}"):
                if len(st.session_state.pur_rows) > 1:
                    st.session_state.pur_rows.pop(p_idx)
                    st.rerun()

        if st.button("➕ إضافة صنف آخر"):
            st.session_state.pur_rows.append({"item": list(inv_item_dict.keys())[0] if inv_item_dict else "", "qty": 1.0, "price": 10.0})
            st.rerun()

        st.metric("الإجمالي شامل الضريبة", f"{grand_total:,.2f} SAR")
        if st.button("💾 حفظ الفاتورة", type="primary", use_container_width=True):
            if not require_open_period(inv_branch, inv_date): st.stop()
            _selected=[r["item"] for r in st.session_state.pur_rows if r["item"] in inv_item_dict]
            if len(_selected) != len(set(_selected)):
                st.error("يوجد نفس الصنف أكثر من مرة في الفاتورة. اجمع الكمية في سطر واحد."); st.stop()
            if inv_number.strip():
                for pr in st.session_state.pur_rows:
                    if pr["item"] in inv_item_dict:
                        p_sku, p_name, _ = inv_item_dict[pr["item"]]
                        tot_r = (pr["qty"] * pr["price"]) * 1.15
                        cursor.execute("INSERT INTO purchases_log (invoice_number, supplier_name, branch, invoice_date, item_sku, item_name, quantity, cost_per_unit, tax_percent, total_with_tax, created_by, entry_source, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'office_manual', 'active')", (inv_number.strip(), inv_supplier, inv_branch, str(inv_date), p_sku, p_name, pr["qty"], pr["price"], 15.0, tot_r, st.session_state.user))
                conn.commit()
                st.success("تم حفظ الفاتورة بنجاح!")
                st.session_state.pur_rows = [{"item": list(inv_item_dict.keys())[0] if inv_item_dict else "", "qty": 1.0, "price": 10.0}]

    elif admin_section == "📑 تقارير إغلاق الكاشيرات والطباعة":
        st.subheader("📑 تقارير إغلاق الكاشيرات ومطابقة الدفاتر")
        b_c_fil = st.selectbox("تصفية حسب الفرع:", ["الكل"] + BRANCH_LIST)
        q_clos = "SELECT * FROM cashier_closings WHERE 1=1"
        p_clos = []
        if b_c_fil != "الكل":
            q_clos += " AND branch=?"
            p_clos.append(b_c_fil)
        df_closings = pd.read_sql_query(q_clos, conn, params=p_clos)
        st.dataframe(df_closings, use_container_width=True)

        if not df_closings.empty:
            sel_report_id = st.selectbox("اختر رقم التقرير للطباعة والمراجعة:", df_closings['id'].tolist())
            r_data = df_closings[df_closings['id'] == sel_report_id].iloc[0]
            
            col_b1, col_b2, col_b3 = st.columns(3)
            with col_b1:
                pdf_cls = generate_pdf_report(pd.DataFrame([r_data]), f"Cashier Closing Report - Branch {r_data['branch']}")
                st.download_button("📥 تحميل التقرير PDF", pdf_cls, f"Closing_{r_data['branch']}.pdf", "application/pdf")
            with col_b2:
                ex_cls = io.BytesIO()
                with pd.ExcelWriter(ex_cls, engine='openpyxl') as wr: pd.DataFrame([r_data]).to_excel(wr, index=False)
                st.download_button("📥 تحميل التقرير Excel", ex_cls.getvalue(), f"Closing_{r_data['branch']}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            with col_b3:
                st.download_button("📥 تحميل التقرير CSV", pd.DataFrame([r_data]).to_csv(index=False).encode('utf-8-sig'), f"Closing_{r_data['branch']}.csv", "text/csv")

    elif admin_section == "⚖️ ميزان المخزون والجرد":
        st.subheader("⚖️ ميزان المخزون ومطابقة فروقات الجرد")
        r_b = st.selectbox("اختر الفرع:", BRANCH_LIST)
        d1,d2=st.columns(2)
        with d1: bal_start=st.date_input("من تاريخ:", value=date.today().replace(day=1), key="bal_start")
        with d2: bal_end=st.date_input("إلى تاريخ:", value=date.today(), key="bal_end")
        df_bal = inventory_balance(r_b, bal_start, bal_end)
        st.dataframe(df_bal, use_container_width=True)
        
        cb1, cb2, cb3 = st.columns(3)
        with cb1:
            st.download_button("📥 تحميل الميزان PDF", generate_pdf_report(df_bal, f"Inventory Balance - {r_b}"), f"Balance_{r_b}.pdf", "application/pdf")
        with cb2:
            bx = io.BytesIO()
            with pd.ExcelWriter(bx, engine='openpyxl') as wr: df_bal.to_excel(wr, index=False)
            st.download_button("📥 تحميل الميزان Excel", bx.getvalue(), f"Balance_{r_b}.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with cb3:
            st.download_button("📥 تحميل الميزان CSV", df_bal.to_csv(index=False).encode('utf-8-sig'), f"Balance_{r_b}.csv", "text/csv")

    elif admin_section == "🍗 تحليل استهلاك الخامات الذكي":
        st.subheader("🍗 تحليل استهلاك الخامات من تقرير فودكس")
        p_file = st.file_uploader("ارفع ملف المبيعات (XLS / CSV):", type=["xls", "csv", "xlsx"])
        if p_file:
            dfs_raw = pd.read_csv(p_file) if p_file.name.endswith(".csv") else pd.read_html(p_file)[0]
            st.dataframe(dfs_raw.head())

    elif admin_section == "🚀 تصدير قوالب فودكس":
        st.subheader("🚀 تصدير ملفات فودكس المعتمدة")
        ex_b = st.selectbox("الفرع:", BRANCH_LIST, key="ex_b_admin")
        ex_d = st.date_input("التاريخ:", value=date.today(), key="ex_d_admin")
        c_p, c_t, c_i = st.columns(3)
        with c_p:
            df_p = pd.read_sql_query("SELECT item_name AS name, item_sku AS sku, quantity AS storage_quantity, 0 AS ingredients_quantity FROM operations_log WHERE branch=? AND entry_date=? AND entry_type LIKE '%إنتاج%'", conn, params=(ex_b, str(ex_d)))
            if not df_p.empty: st.download_button("📥 تحميل production.csv", df_p.to_csv(index=False).encode('utf-8'), "production.csv")
            else: st.warning("لا يوجد إنتاج")
        with c_t:
            df_t = pd.read_sql_query("SELECT item_name AS name, item_sku AS sku, quantity AS storage_quantity, 0 AS ingredients_quantity FROM operations_log WHERE branch=? AND entry_date=? AND entry_type LIKE '%تحويل%'", conn, params=(ex_b, str(ex_d)))
            if not df_t.empty: st.download_button("📥 تحميل transfer_sending.csv", df_t.to_csv(index=False).encode('utf-8'), "transfer_sending.csv")
            else: st.warning("لا توجد تحويلات")
        with c_i:
            df_cnt = pd.read_sql_query("SELECT item_name AS 'Inventory Item Name', item_sku AS 'Inventory Item SKU', storage_qty AS 'Storage quantity', ingredients_qty AS 'Ingredients quantity', count_id AS 'Inventory Count ID' FROM inventory_counts WHERE branch=? AND count_date=?", conn, params=(ex_b, str(ex_d)))
            if not df_cnt.empty:
                b_io = io.BytesIO()
                with pd.ExcelWriter(b_io, engine='openpyxl') as wr: df_cnt.to_excel(wr, index=False)
                st.download_button("📥 تحميل inventory-count.xlsx", b_io.getvalue(), "inventory-count.xlsx")
            else: st.warning("لا يوجد جرد")

    elif admin_section == "📋 سجل العمليات اليومية":
        st.subheader("📋 سجل العمليات اليومية لكافة الفروع")
        df_ops = pd.read_sql_query("SELECT * FROM operations_log ORDER BY id DESC", conn)
        st.dataframe(df_ops, use_container_width=True)
        
        co1, co2, co3 = st.columns(3)
        with co1:
            st.download_button("📥 تحميل السجل PDF", generate_pdf_report(df_ops, "Operations Log"), "Operations_Log.pdf", "application/pdf")
        with co2:
            ox = io.BytesIO()
            with pd.ExcelWriter(ox, engine='openpyxl') as wr: df_ops.to_excel(wr, index=False)
            st.download_button("📥 تحميل السجل Excel", ox.getvalue(), "Operations_Log.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        with co3:
            st.download_button("📥 تحميل السجل CSV", df_ops.to_csv(index=False).encode('utf-8-sig'), "Operations_Log.csv", "text/csv")


    elif admin_section == "🔁 متابعة التحويلات":
        st.subheader("🔁 متابعة التحويلات بين الفروع")
        tr_status=st.selectbox("الحالة:",["الكل","sent","received","cancelled"])
        q="SELECT * FROM transfers"; pp=[]
        if tr_status!="الكل": q+=" WHERE status=?"; pp=[tr_status]
        q+=" ORDER BY id DESC"
        dftr=pd.read_sql_query(q,conn,params=pp); st.dataframe(dftr,use_container_width=True)
        if not dftr.empty:
            xid=st.selectbox("رقم التحويل للمراجعة:",dftr['id'].tolist(),key="admin_tr_id")
            xr=dftr[dftr.id==xid].iloc[0]
            if xr['status']=='sent':
                rs=st.text_input("سبب إلغاء التحويل:",key="tr_cancel_reason")
                if st.button("إلغاء التحويل المعلق",use_container_width=True):
                    if not rs.strip(): st.error("اكتب سبب الإلغاء.")
                    else:
                        cursor.execute("UPDATE transfers SET status='cancelled',cancel_reason=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND status='sent'",(rs,st.session_state.user,int(xid)))
                        audit_action('transfers',int(xid),'cancel',xr['from_branch'],xr.to_dict(),{'status':'cancelled'},rs); conn.commit(); st.rerun()

    elif admin_section == "📅 إقفال وفتح الفترات":
        st.subheader("📅 إقفال الشهر وترحيل الجرد كرصيد افتتاحي")
        pc_branch=st.selectbox("الفرع:",BRANCH_LIST,key="pc_branch")
        pc_month=st.text_input("الشهر YYYY-MM:",value=date.today().strftime('%Y-%m'),key="pc_month")
        pc_note=st.text_input("ملاحظات الإقفال:")
        current_pc=cursor.execute("SELECT status FROM period_closings WHERE branch=? AND period_month=?",(pc_branch,pc_month)).fetchone()
        st.info(f"حالة الفترة: {current_pc[0] if current_pc else 'مفتوحة'}")
        if st.button("🔒 إقفال الشهر وإنشاء رصيد الشهر التالي",type="primary",use_container_width=True):
            cnt=pd.read_sql_query("SELECT * FROM inventory_counts WHERE branch=? AND count_date LIKE ? AND COALESCE(status,'active')='active' ORDER BY count_date DESC,id DESC",conn,params=(pc_branch,pc_month+'%'))
            if cnt.empty: st.error("لا يمكن الإقفال بدون جرد فعلي داخل الشهر.")
            else:
                cnt=cnt.drop_duplicates('item_sku',keep='first')
                required=pd.read_sql_query("SELECT sku,name_ar,storage_to_ingredient_factor FROM items_master",conn)
                missing=required[~required['sku'].isin(cnt['item_sku'])]
                if not missing.empty:
                    st.error(f"لا يمكن إقفال الشهر: يوجد {len(missing)} صنفًا لم يتم جردها.")
                    st.dataframe(missing[['sku','name_ar']],use_container_width=True); st.stop()
                factors=required.set_index('sku')['storage_to_ingredient_factor']
                cnt['factor']=cnt['item_sku'].map(factors)
                cnt['normalized_qty']=cnt['storage_qty'].fillna(0).astype(float)
                valid=cnt['factor'].fillna(0).astype(float)>0
                cnt.loc[valid,'normalized_qty'] += cnt.loc[valid,'ingredients_qty'].fillna(0).astype(float)/cnt.loc[valid,'factor'].astype(float)
                next_month=(pd.Period(pc_month,freq='M')+1).strftime('%Y-%m')
                for _,r in cnt.iterrows():
                    cursor.execute("INSERT INTO opening_balances(branch,period_month,item_sku,item_name,quantity,source_count_date,created_by) VALUES(?,?,?,?,?,?,?) ON CONFLICT(branch,period_month,item_sku) DO UPDATE SET quantity=excluded.quantity,source_count_date=excluded.source_count_date,created_by=excluded.created_by",(pc_branch,next_month,r['item_sku'],r['item_name'],float(r['normalized_qty']),r['count_date'],st.session_state.user))
                cursor.execute("INSERT INTO period_closings(branch,period_month,closing_date,status,notes,closed_by) VALUES(?,?,?,'closed',?,?) ON CONFLICT(branch,period_month) DO UPDATE SET status='closed',closing_date=excluded.closing_date,notes=excluded.notes,closed_by=excluded.closed_by,closed_at=CURRENT_TIMESTAMP",(pc_branch,pc_month,str(date.today()),pc_note,st.session_state.user))
                audit_action('period_closings',0,'close',pc_branch,'',{'period':pc_month,'next_opening':next_month},pc_note); conn.commit(); st.success(f"تم الإقفال. جرد {pc_month} أصبح رصيد أول {next_month}."); st.rerun()
        if current_pc and current_pc[0]=='closed':
            if is_admin:
                reopen_reason=st.text_input("سبب إعادة الفتح (Admin فقط):",key="reopen_reason")
                if st.button("🔓 إعادة فتح الفترة",use_container_width=True):
                    if not reopen_reason.strip(): st.error("اكتب سبب إعادة الفتح.")
                    else:
                        cursor.execute("UPDATE period_closings SET status='open',reopened_by=?,reopened_at=CURRENT_TIMESTAMP WHERE branch=? AND period_month=?",(st.session_state.user,pc_branch,pc_month)); audit_action('period_closings',0,'reopen',pc_branch,{'status':'closed'},{'status':'open'},reopen_reason); conn.commit(); st.rerun()
            else: st.warning("إعادة فتح فترة مغلقة متاحة للإدارة فقط.")

    elif admin_section == "🛡️ النسخ الاحتياطي والرقابة":
        st.subheader("🛡️ النسخ الاحتياطي ومؤشرات الرقابة")
        pending = cursor.execute("SELECT COUNT(*) FROM transfers WHERE status='sent'").fetchone()[0]
        cancelled_ops = cursor.execute("SELECT COUNT(*) FROM operations_log WHERE COALESCE(status,'active')='cancelled'").fetchone()[0]
        closed_periods = cursor.execute("SELECT COUNT(*) FROM period_closings WHERE status='closed'").fetchone()[0]
        c1,c2,c3 = st.columns(3)
        c1.metric("تحويلات بانتظار الاستلام", pending)
        c2.metric("حركات ملغاة محفوظة", cancelled_ops)
        c3.metric("فترات مغلقة", closed_periods)

        st.markdown("### تحويلات بها فروق استلام")
        diff_tr = pd.read_sql_query("SELECT * FROM transfers WHERE status='received' AND ABS(COALESCE(quantity_received,0)-quantity_sent)>0.000001 ORDER BY id DESC", conn)
        if diff_tr.empty: st.success("لا توجد فروق استلام مسجلة.")
        else: st.dataframe(diff_tr, use_container_width=True)

        st.markdown("### آخر سجل رقابي")
        audit_df = pd.read_sql_query("SELECT * FROM audit_log ORDER BY id DESC LIMIT 200", conn)
        st.dataframe(audit_df, use_container_width=True)

        st.markdown("### نسخة احتياطية من قاعدة البيانات")
        st.caption("حمّل نسخة دورية قبل أي تحديث كبير. في الاستضافة السحابية يظل الأفضل نقل قاعدة البيانات لاحقًا إلى خدمة دائمة مثل PostgreSQL/Supabase.")
        try:
            conn.commit()
            with open(DB_PATH, "rb") as dbf:
                st.download_button("⬇️ تحميل نسخة قاعدة البيانات", dbf.read(), file_name=f"inventory_backup_{date.today().isoformat()}.db", mime="application/octet-stream", use_container_width=True)
        except Exception as e:
            st.warning(f"تعذر تجهيز النسخة الاحتياطية: {e}")

    elif admin_section == "✏️ تعديل وإلغاء الحركات":
        st.subheader("✏️ تعديل وإلغاء الحركات مع سجل رقابي")
        st.caption("الإلغاء لا يمحو السجل من قاعدة البيانات؛ يتم الاحتفاظ به للمراجعة، ولا يدخل في ميزان المخزون.")
        manage_branch = st.selectbox("الفرع:", BRANCH_LIST, key="manage_branch")
        show_cancelled = st.checkbox("إظهار الحركات الملغاة", value=False)
        q_manage = "SELECT * FROM operations_log WHERE branch=?"
        params_manage = [manage_branch]
        if not show_cancelled:
            q_manage += " AND COALESCE(status,'active')='active'"
        q_manage += " ORDER BY id DESC"
        df_manage = pd.read_sql_query(q_manage, conn, params=params_manage)
        st.dataframe(df_manage, use_container_width=True)

        if not df_manage.empty:
            manage_id = st.selectbox("رقم الحركة المراد مراجعتها:", df_manage["id"].tolist())
            current = df_manage[df_manage["id"] == manage_id].iloc[0]
            with st.form("edit_operation_form"):
                e1, e2 = st.columns(2)
                with e1:
                    edit_date = st.date_input("التاريخ:", value=pd.to_datetime(current["entry_date"]).date())
                    edit_qty = st.number_input("الكمية:", min_value=0.0, value=float(current["quantity"]), step=0.1)
                with e2:
                    edit_reason = st.text_input("البيان / السبب:", value=str(current.get("reason") or ""))
                    change_reason = st.text_input("سبب التعديل (إجباري):", placeholder="مثال: خطأ في قراءة التقرير الورقي")
                if st.form_submit_button("💾 حفظ التعديل", type="primary", use_container_width=True):
                    if not change_reason.strip():
                        st.error("يجب كتابة سبب التعديل.")
                    elif is_period_closed(manage_branch, current["entry_date"]):
                        st.error("لا يمكن تعديل حركة داخل فترة مغلقة. أعد فتح الفترة أولًا.")
                    else:
                        old_snapshot = current.to_dict()
                        cursor.execute(
                            """UPDATE operations_log
                               SET entry_date=?, quantity=?, reason=?, updated_by=?, updated_at=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (str(edit_date), edit_qty, edit_reason, st.session_state.user, int(manage_id))
                        )
                        new_snapshot = {"entry_date": str(edit_date), "quantity": edit_qty, "reason": edit_reason}
                        audit_action("operations_log", int(manage_id), "edit", manage_branch, old_snapshot, new_snapshot, change_reason.strip())
                        conn.commit()
                        st.success("تم تعديل الحركة وحفظ أثر التعديل في سجل الرقابة.")
                        st.rerun()

            if str(current.get("status") or "active") == "active":
                cancel_reason = st.text_input("سبب الإلغاء:", key=f"cancel_reason_{manage_id}", placeholder="مثال: إدخال مكرر")
                if st.button("🗑️ إلغاء الحركة مع الاحتفاظ بالسجل", type="secondary", use_container_width=True):
                    if not cancel_reason.strip():
                        st.error("يجب كتابة سبب الإلغاء.")
                    elif is_period_closed(manage_branch, current["entry_date"]):
                        st.error("لا يمكن إلغاء حركة داخل فترة مغلقة. أعد فتح الفترة أولًا.")
                    else:
                        cursor.execute(
                            """UPDATE operations_log
                               SET status='cancelled', cancel_reason=?, updated_by=?, updated_at=CURRENT_TIMESTAMP
                               WHERE id=?""",
                            (cancel_reason.strip(), st.session_state.user, int(manage_id))
                        )
                        audit_action("operations_log", int(manage_id), "cancel", manage_branch, current.to_dict(), {"status": "cancelled"}, cancel_reason.strip())
                        conn.commit()
                        st.success("تم إلغاء الحركة دون حذفها من سجل المراجعة.")
                        st.rerun()

        st.divider()
        st.markdown("### 🗂️ إدارة بقية السجلات")
        other_kind = st.selectbox("نوع السجل:", ["المشتريات", "الجرد", "إغلاق الكاشير"], key="other_manage_kind")
        cfg = {
            "المشتريات": ("purchases_log", "invoice_date", ["quantity", "cost_per_unit", "total_with_tax"]),
            "الجرد": ("inventory_counts", "count_date", ["storage_qty", "ingredients_qty"]),
            "إغلاق الكاشير": ("cashier_closings", "closing_date", ["total_sales", "expenses_amount"]),
        }
        tbl, date_col, numeric_cols = cfg[other_kind]
        odf = pd.read_sql_query(f"SELECT * FROM {tbl} WHERE branch=? ORDER BY id DESC LIMIT 500", conn, params=(manage_branch,))
        st.dataframe(odf, use_container_width=True)
        if not odf.empty:
            oid=st.selectbox("رقم السجل:",odf['id'].tolist(),key="other_record_id")
            orow=odf[odf.id==oid].iloc[0]
            vals={}
            with st.form("other_edit_form"):
                new_date=st.date_input("التاريخ:",value=pd.to_datetime(orow[date_col]).date(),key="other_date")
                for col in numeric_cols:
                    vals[col]=st.number_input(col,value=float(orow[col] or 0),step=0.1,key=f"other_{col}")
                why=st.text_input("سبب التعديل:",key="other_edit_reason")
                if st.form_submit_button("حفظ تعديل السجل",use_container_width=True):
                    if not why.strip(): st.error("سبب التعديل إجباري.")
                    elif is_period_closed(manage_branch,orow[date_col]): st.error("الفترة مغلقة. أعد فتحها أولًا.")
                    else:
                        sets=[f"{date_col}=?"]+[f"{c}=?" for c in numeric_cols]+["updated_by=?","updated_at=CURRENT_TIMESTAMP"]
                        args=[str(new_date)]+[vals[c] for c in numeric_cols]+[st.session_state.user,int(oid)]
                        cursor.execute(f"UPDATE {tbl} SET "+','.join(sets)+" WHERE id=?",args)
                        audit_action(tbl,int(oid),'edit',manage_branch,orow.to_dict(),{date_col:str(new_date),**vals},why); conn.commit(); st.success("تم الحفظ مع سجل رقابي."); st.rerun()
            if str(orow.get('status') or 'active')=='active':
                owhy=st.text_input("سبب إلغاء السجل:",key=f"other_cancel_{tbl}_{oid}")
                if st.button("إلغاء السجل دون حذفه",key="other_cancel_btn",use_container_width=True):
                    if not owhy.strip(): st.error("سبب الإلغاء إجباري.")
                    elif is_period_closed(manage_branch,orow[date_col]): st.error("الفترة مغلقة. أعد فتحها أولًا.")
                    else:
                        cursor.execute(f"UPDATE {tbl} SET status='cancelled',cancel_reason=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=?",(owhy,st.session_state.user,int(oid)))
                        audit_action(tbl,int(oid),'cancel',manage_branch,orow.to_dict(),{'status':'cancelled'},owhy); conn.commit(); st.rerun()

        st.markdown("### 🧾 سجل التعديلات والإلغاءات")
        df_audit = pd.read_sql_query("SELECT * FROM audit_log ORDER BY id DESC LIMIT 500", conn)
        st.dataframe(df_audit, use_container_width=True)

# زر تسجيل الخروج في أسفل القائمة الجانبية للجميع
st.sidebar.divider()
if st.sidebar.button(t.get("logout", "خروج من النظام"), use_container_width=True):
    st.session_state.auth = False
    st.rerun()