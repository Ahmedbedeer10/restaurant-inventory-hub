import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from PIL import Image
from datetime import date
from translations import LANGUAGES

# مكتبات توليد الـ PDF العريض (Landscape)
from reportlab.lib.pagesizes import letter, landscape
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors

st.set_page_config(page_title="Operations & Integrated Inventory Hub", layout="wide")

# 1. إعداد وتحديث جداول قاعدة البيانات
conn = sqlite3.connect("inventory_data.db", check_same_thread=False)
cursor = conn.cursor()

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
conn.commit()

# تحميل الموردين والأصناف تلقائياً من الملفات
def load_seed_data():
    cursor.execute("SELECT COUNT(*) FROM items_master")
    if cursor.fetchone()[0] == 0:
        for f in os.listdir("."):
            if f.startswith("products_export") and f.endswith(".csv"):
                df_prod = pd.read_csv(f)
                for _, r in df_prod.iterrows():
                    cursor.execute("""
                    INSERT OR IGNORE INTO items_master (item_type, foodics_id, sku, name_ar, name_en, storage_unit, ingredient_unit)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, ('production', str(r.get('id')), str(r.get('sku')), str(r.get('name')), str(r.get('name_localized')), str(r.get('storage_unit')), str(r.get('ingredient_unit'))))
            elif f.startswith("inventory_items_export") and f.endswith(".csv"):
                df_inv = pd.read_csv(f)
                for _, r in df_inv.iterrows():
                    cursor.execute("""
                    INSERT OR IGNORE INTO items_master (item_type, foodics_id, sku, name_ar, name_en, storage_unit, ingredient_unit)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, ('inventory', str(r.get('id')), str(r.get('sku')), str(r.get('name')), str(r.get('name_localized')), str(r.get('storage_unit')), str(r.get('ingredient_unit'))))
        conn.commit()

    cursor.execute("SELECT COUNT(*) FROM suppliers_master")
    if cursor.fetchone()[0] == 0:
        for f in os.listdir("."):
            if "suppliers_export" in f and f.endswith(".csv"):
                df_sup = pd.read_csv(f)
                for _, r in df_sup.iterrows():
                    cursor.execute("INSERT OR IGNORE INTO suppliers_master (foodics_id, name, code) VALUES (?, ?, ?)",
                                   (str(r.get('id')), str(r.get('name')), str(r.get('code'))))
        conn.commit()

load_seed_data()

BRANCH_LIST = ["ELarouba", "Malqa", "Alrawdah", "Laban"]

USERS = {
    "admin": {"pin": "9999", "role": "admin", "branch": "الكل", "name": "الإدارة العامة"},
    "accountant": {"pin": "5555", "role": "admin", "branch": "الكل", "name": "المحاسب المالي"},
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
                st.rerun()
            else:
                st.error("اسم المستخدم أو رمز الدخول غير صحيح!")
    st.stop()

st.sidebar.markdown(f"**المستخدم:** {st.session_state.name}")
st.sidebar.markdown(f"**الفرع:** `{st.session_state.branch}`")
st.sidebar.divider()

# دالة توليد PDF بالوضع العرضي (Landscape) لتظهر كافة الأعمدة بوضوح تام
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
if st.session_state.role == "cashier":
    st.sidebar.markdown("### 🗂️️ القائمة الرئيسية للفرع")
    c_mode = st.sidebar.radio("القسم:", [
        "العمليات والتشغيل اليومي", 
        "🗑️ الهدر والتالف (الإنتاج والمخزون)",
        "📝 تقرير الإغلاق المالي", 
        t.get("count_tab", "الجرد الدوري")
    ])

    st.title(f"📍 بوابة الفرع - {st.session_state.name}")

    if c_mode == "العمليات والتشغيل اليومي":
        st.sidebar.markdown("---")
        st.sidebar.markdown("### ⚙️ نوع الحركة")
        tab_type = st.sidebar.radio("اختر العملية:", [
            t.get("prod_tab", "الإنتاج"), 
            t.get("staff_tab", "وجبات الموظفين"), 
            t.get("consume_tab", "منصرف المخزن"), 
            t.get("transfer_tab", "التحويلات")
        ])

        target_source = "production" if tab_type in [t.get("prod_tab", "الإنتاج"), t.get("staff_tab", "وجبات الموظفين")] else "inventory"
        df_items = pd.read_sql_query("SELECT sku, name_ar, name_en, storage_unit FROM items_master WHERE item_type=? ORDER BY name_ar ASC", conn, params=(target_source,))
        item_dict = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit']) for _, r in df_items.iterrows()}
        
        c_top1, c_top2 = st.columns(2)
        with c_top1: op_date = st.date_input("التاريخ:", value=date.today(), key="op_d")
        with c_top2: to_br = st.selectbox("تحويل إلى فرع:", [b for b in BRANCH_LIST if b != st.session_state.branch]) if tab_type == t.get("transfer_tab", "التحويلات") else "-"

        st.markdown(f"#### 📋 تسجيل حركة: `{tab_type}` (أدخل عدة أصناف معاً)")
        if "ops_rows" not in st.session_state:
            st.session_state.ops_rows = [{"item": list(item_dict.keys())[0], "qty": 1.0, "reason": ""}]

        for idx, row_val in enumerate(st.session_state.ops_rows):
            col_r = st.columns([4, 2, 2, 3, 1])
            sel_it = col_r[0].selectbox(f"صنف {idx+1}", list(item_dict.keys()), index=list(item_dict.keys()).index(row_val["item"]) if row_val["item"] in item_dict else 0, key=f"op_it_{idx}")
            row_val["item"] = sel_it
            row_val["qty"] = col_r[1].number_input(f"كمية {idx+1}", min_value=0.1, step=0.5, value=row_val["qty"], key=f"op_q_{idx}")
            unit_fixed = item_dict[sel_it][2]
            col_r[2].text_input(f"وحدة {idx+1}", value=str(unit_fixed), disabled=True, key=f"op_u_{idx}")
            row_val["reason"] = col_r[3].text_input(f"سبب {idx+1}", value=row_val["reason"], placeholder="ملاحظة", key=f"op_r_{idx}")
            if col_r[4].button("❌", key=f"del_op_{idx}"):
                if len(st.session_state.ops_rows) > 1:
                    st.session_state.ops_rows.pop(idx)
                    st.rerun()

        if st.button("➕ إضافة سطر صنف آخر"):
            st.session_state.ops_rows.append({"item": list(item_dict.keys())[0], "qty": 1.0, "reason": ""})
            st.rerun()

        if st.button("💾 حفظ كافة العمليات المسجلة في النظام", type="primary", use_container_width=True):
            for r in st.session_state.ops_rows:
                s_sku, s_name, s_unit = item_dict[r["item"]]
                cursor.execute("""
                INSERT INTO operations_log (entry_type, branch, to_branch, entry_date, item_type, item_sku, item_name, quantity, unit, reason, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (tab_type, st.session_state.branch, to_br, str(op_date), target_source, s_sku, s_name, r["qty"], str(s_unit), r["reason"], st.session_state.user))
            conn.commit()
            st.success(f"تم حفظ الحركات بنجاح!")
            st.session_state.ops_rows = [{"item": list(item_dict.keys())[0], "qty": 1.0, "reason": ""}]

    elif c_mode == "🗑️ الهدر والتالف (الإنتاج والمخزون)":
        st.subheader("🗑️ تسجيل الهدر والتالف اليومي (منتجات نهائية أو خامات مخزن)")
        waste_target = st.radio("حدد نوع التالف/الهدر:", ["هدر إنتاج (منتجات نهائية)", "هدر خامات مخزن"], horizontal=True)
        w_source = "production" if "إنتاج" in waste_target else "inventory"
        
        df_w_items = pd.read_sql_query("SELECT sku, name_ar, storage_unit FROM items_master WHERE item_type=? ORDER BY name_ar ASC", conn, params=(w_source,))
        w_item_dict = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit']) for _, r in df_w_items.iterrows()}
        
        with st.form("waste_form"):
            w_date = st.date_input("تاريخ الهدر:", value=date.today())
            selected_w_item = st.selectbox("اختر الصنف التالف:", list(w_item_dict.keys()) if w_item_dict else ["لا توجد أصناف"])
            w_qty = st.number_input("الكمية التالفة:", min_value=0.1, step=0.5, value=1.0)
            w_reason = st.text_input("سبب التالف / الهدر (إجباري):", placeholder="مثال: احتراق أثناء الشوي / انتهاء صلاحية")
            
            if st.form_submit_button("💾 تسجيل وترحيل الهدر والتالف للنظام", type="primary", use_container_width=True):
                if selected_w_item and selected_w_item != "لا توجد أصناف":
                    sk_w, nm_w, u_w = w_item_dict[selected_w_item]
                    cursor.execute("""
                    INSERT INTO operations_log (entry_type, branch, to_branch, entry_date, item_type, item_sku, item_name, quantity, unit, reason, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, ("الهدر والتالف", st.session_state.branch, "-", str(w_date), w_source, sk_w, nm_w, w_qty, str(u_w), w_reason, st.session_state.user))
                    conn.commit()
                    st.success(f"تم تسجيل هدر التالف للصنف ({nm_w}) بكمية {w_qty} بنجاح!")
                else:
                    st.warning("يرجى اختيار صنف صحيح!")

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
                cursor.execute("""
                INSERT INTO cashier_closings (branch, closing_date, cashier_name, cash_sales, mada_sales, visa_sales, mastercard_sales, bank_transfers, hungerstation, jahez, ninja, keeta, expenses_notes, expenses_amount, total_sales, created_by)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (st.session_state.branch, str(cl_date), c_name, c_cash, c_mada, c_visa, c_master, c_trans, c_hunger, c_jahez, c_ninja, c_keeta, c_exp_note, c_exp_amt, c_total, st.session_state.user))
                conn.commit()
                st.success("تم إرسال تقرير الإغلاق المالي بنجاح إلى الإدارة والمحاسب!")
    else:
        st.subheader("📋 الجرد الدوري الفعلي للمخزون")
        df_inv = pd.read_sql_query("SELECT sku, name_ar, storage_unit, ingredient_unit FROM items_master WHERE item_type='inventory' ORDER BY name_ar ASC", conn)
        cnt_map = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit'], r['ingredient_unit']) for _, r in df_inv.iterrows()}
        ca, cb = st.columns(2)
        with ca:
            cnt_d = st.date_input("تاريخ الجرد:", value=date.today())
            sel_cnt = st.selectbox("الصنف:", list(cnt_map.keys()))
            cnt_id = st.text_input("معرف الجرد في فودكس:", placeholder="اختياري")
        with cb:
            sk_c, nm_c, u_st, u_in = cnt_map[sel_cnt]
            q_st = st.number_input(f"كمية التخزين ({u_st}):", min_value=0.0, step=1.0)
            q_in = st.number_input(f"كمية المكونات ({u_in}):", min_value=0.0, step=1.0)
        if st.button("حفظ الجرد للصنف", type="primary"):
            cursor.execute("INSERT INTO inventory_counts (branch, count_date, count_id, item_sku, item_name, storage_qty, ingredients_qty, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (st.session_state.branch, str(cnt_d), cnt_id.strip(), sk_c, nm_c, q_st, q_in, st.session_state.user))
            conn.commit()
            st.success("تم حفظ الجرد بنجاح!")

# ----------------- واجهة الإدارة والمحاسب -----------------
elif st.session_state.role == "admin":
    st.title("📊 لوحة تحكم الإدارة العامة والمحاسبة المالية")
    
    admin_section = st.sidebar.radio("🗂️ أقسام الإدارة:", [
        "📥 استيراد مشتريات فودكس (سريع)",
        "📊 تقرير المدفوعات والمبيعات (مطابق للـ PDF)",
        "🛒 إدخال المشتريات اليدوية",
        "📑 تقارير إغلاق الكاشيرات والطباعة",
        "⚖️ ميزان المخزون والجرد",
        "🍗 تحليل استهلاك الخامات الذكي",
        "🚀 تصدير قوالب فودكس",
        "📋 سجل العمليات اليومية"
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
                if st.button("🚀 ترحيل وحفظ المشتريات في قاعدة البيانات السحابية", type="primary", use_container_width=True):
                    count = 0
                    for index, row in df_purchases.iterrows():
                        date_val = str(row.get('Business Date', row.get('Date', date.today())))
                        inv_num_val = str(row.get('Invoice Number', row.get('Invoice', 'FOODICS-IMP')))
                        supplier_val = str(row.get('Supplier Name', row.get('Supplier', 'مورد فودكس')))
                        item_name_val = str(row.get('Item Name', row.get('Name', 'صنف فودكس')))
                        item_sku_val = str(row.get('SKU', '0000'))
                        qty_val = float(row.get('Quantity', row.get('Qty', 1.0)))
                        cost_val = float(row.get('Total Cost', row.get('Cost', 0.0)))
                        tot_tax_val = cost_val * 1.15
                        cursor.execute("""
                            INSERT INTO purchases_log (invoice_number, supplier_name, branch, invoice_date, item_sku, item_name, quantity, cost_per_unit, tax_percent, total_with_tax, created_by)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (inv_num_val, supplier_val, imp_branch, date_val, item_sku_val, item_name_val, qty_val, cost_val, 15.0, tot_tax_val, st.session_state.user))
                        count += 1
                    conn.commit()
                    st.success(f"تم ترحيل وحفظ {count} بند مشتريات بنجاح من ملف فودكس!")
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
                
                # أزرار التحميل بكافة الصيغ المطلوبة (PDF Landscape, Excel, CSV)
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
            st.session_state.pur_rows = [{"item": list(inv_item_dict.keys())[0], "qty": 1.0, "price": 10.0}]

        grand_total = 0.0
        for p_idx, p_row in enumerate(st.session_state.pur_rows):
            col_p = st.columns([4, 2, 2, 2, 2, 1])
            p_sel = col_p[0].selectbox(f"صنف {p_idx+1}", list(inv_item_dict.keys()), key=f"pur_it_{p_idx}")
            p_row["item"] = p_sel
            p_row["qty"] = col_p[1].number_input(f"كمية {p_idx+1}", min_value=0.1, step=1.0, value=p_row["qty"], key=f"pur_q_{p_idx}")
            col_p[2].text_input(f"وحدة {p_idx+1}", value=inv_item_dict[p_sel][2], disabled=True, key=f"pur_u_{p_idx}")
            p_row["price"] = col_p[3].number_input(f"سعر {p_idx+1}", min_value=0.0, step=0.5, value=p_row["price"], key=f"pur_p_{p_idx}")
            row_tot = (p_row["qty"] * p_row["price"]) * 1.15
            grand_total += row_tot
            col_p[4].write(f"{row_tot:,.2f} SAR")
            if col_p[5].button("❌", key=f"del_pur_{p_idx}"):
                if len(st.session_state.pur_rows) > 1:
                    st.session_state.pur_rows.pop(p_idx)
                    st.rerun()

        if st.button("➕ إضافة صنف آخر"):
            st.session_state.pur_rows.append({"item": list(inv_item_dict.keys())[0], "qty": 1.0, "price": 10.0})
            st.rerun()

        st.metric("الإجمالي شامل الضريبة", f"{grand_total:,.2f} SAR")
        if st.button("💾 حفظ الفاتورة", type="primary", use_container_width=True):
            if inv_number.strip():
                for pr in st.session_state.pur_rows:
                    p_sku, p_name, _ = inv_item_dict[pr["item"]]
                    tot_r = (pr["qty"] * pr["price"]) * 1.15
                    cursor.execute("INSERT INTO purchases_log (invoice_number, supplier_name, branch, invoice_date, item_sku, item_name, quantity, cost_per_unit, tax_percent, total_with_tax, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (inv_number.strip(), inv_supplier, inv_branch, str(inv_date), p_sku, p_name, pr["qty"], pr["price"], 15.0, tot_r, st.session_state.user))
                conn.commit()
                st.success("تم حفظ الفاتورة بنجاح!")
                st.session_state.pur_rows = [{"item": list(inv_item_dict.keys())[0], "qty": 1.0, "price": 10.0}]

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
        p_s = pd.read_sql_query("SELECT item_sku, SUM(quantity) as p_qty FROM purchases_log WHERE branch=? GROUP BY item_sku", conn, params=(r_b,)).set_index("item_sku")["p_qty"]
        op_s = pd.read_sql_query("SELECT item_sku, SUM(CASE WHEN entry_type LIKE '%منصرف%' THEN quantity ELSE 0 END) as c_qty, SUM(CASE WHEN entry_type LIKE '%هدر%' THEN quantity ELSE 0 END) as w_qty, SUM(CASE WHEN entry_type LIKE '%وجبات%' THEN quantity ELSE 0 END) as s_qty, SUM(CASE WHEN entry_type LIKE '%تحويل%' AND branch=? THEN quantity ELSE 0 END) as t_qty, SUM(CASE WHEN entry_type LIKE '%إنتاج%' THEN quantity ELSE 0 END) as pr_qty FROM operations_log WHERE branch=? GROUP BY item_sku", conn, params=(r_b, r_b)).set_index("item_sku")
        act_s = pd.read_sql_query("SELECT item_sku, storage_qty FROM inventory_counts WHERE branch=? GROUP BY item_sku HAVING id = MAX(id)", conn, params=(r_b,)).set_index("item_sku")["storage_qty"]
        
        m_items = pd.read_sql_query("SELECT sku, name_ar, item_type, storage_unit FROM items_master", conn).set_index("sku")
        m_items["المشتريات (+)"] = m_items.index.map(p_s).fillna(0)
        m_items["الجرد الفعلي"] = m_items.index.map(act_s).fillna(0)
        for col_name, src_col in [("المنصرف (-)", "c_qty"), ("الهدر (-)", "w_qty"), ("وجبات (-)", "s_qty"), ("تحويل صادر (-)", "t_qty"), ("الإنتاج (+)", "pr_qty")]:
            m_items[col_name] = m_items.index.map(op_s[src_col]).fillna(0) if src_col in op_s.columns else 0.0

        m_items["الرصيد الدفتري المتوقع"] = m_items["المشتريات (+)"] + m_items["الإنتاج (+)"] - m_items["المنصرف (-)"] - m_items["الهدر (-)"] - m_items["وجبات (-)"] - m_items["تحويل صادر (-)"]
        m_items["فارق الجرد (عجز/زيادة)"] = m_items["الجرد الفعلي"] - m_items["الرصيد الدفتري المتوقع"]
        df_bal = m_items.reset_index()
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

    else:
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

# زر تسجيل الخروج في أسفل القائمة الجانبية للجميع
st.sidebar.divider()
if st.sidebar.button(t.get("logout", "خروج من النظام"), use_container_width=True):
    st.session_state.auth = False
    st.rerun()