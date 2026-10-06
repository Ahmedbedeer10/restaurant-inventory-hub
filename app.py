import streamlit as st
import pandas as pd
import sqlite3
import os
import io
from PIL import Image
from datetime import date
from translations import LANGUAGES

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
    # تحميل الأصناف
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

    # تحميل الموردين
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

# إدارة الجلسة واللغات
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
if st.sidebar.button(t.get("logout", "خروج")):
    st.session_state.auth = False
    st.rerun()

# ----------------- واجهة الكاشير / الفرع -----------------
if st.session_state.role == "cashier":
    st.title(f"📍 {t.get('role_cashier', 'بوابة الفرع')} - {st.session_state.name}")
    c_mode = st.radio("القسم:", ["العمليات والتشغيل اليومي", "📝 تقرير الإغلاق المالي اليومي للكاشير", t.get("count_tab", "الجرد الدوري")], horizontal=True)

    # 1. إدخال العمليات التشغيلية (يدعم سطور متعددة)
    if c_mode == "العمليات والتشغيل اليومي":
        tab_type = st.radio("نوع العملية:", [
            t.get("prod_tab", "الإنتاج"), t.get("staff_tab", "وجبات الموظفين"), 
            t.get("consume_tab", "منصرف المخزن"), t.get("waste_tab", "الهدر"), t.get("transfer_tab", "التحويلات")
        ], horizontal=True)

        target_source = "production" if tab_type in [t.get("prod_tab", "الإنتاج"), t.get("staff_tab", "وجبات الموظفين")] else "inventory"
        df_items = pd.read_sql_query("SELECT sku, name_ar, name_en, storage_unit FROM items_master WHERE item_type=? ORDER BY name_ar ASC", conn, params=(target_source,))
        
        item_dict = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit']) for _, r in df_items.iterrows()}
        
        c_top1, c_top2 = st.columns(2)
        with c_top1:
            op_date = st.date_input("التاريخ:", value=date.today(), key="op_d")
        with c_top2:
            to_br = st.selectbox("تحويل إلى فرع:", [b for b in BRANCH_LIST if b != st.session_state.branch]) if tab_type == t.get("transfer_tab", "التحويلات") else "-"

        st.markdown("#### 📋 جدول تسجيل الأصناف (أدخل عدة أصناف معاً):")
        if "ops_rows" not in st.session_state:
            st.session_state.ops_rows = [{"item": list(item_dict.keys())[0], "qty": 1.0, "reason": ""}]

        cols_head = st.columns([4, 2, 2, 3, 1])
        cols_head[0].write("**الصنف**")
        cols_head[1].write("**الكمية**")
        cols_head[2].write("**الوحدة**")
        cols_head[3].write("**السبب / الملاحظة**")
        cols_head[4].write("**حذف**")

        for idx, row_val in enumerate(st.session_state.ops_rows):
            col_r = st.columns([4, 2, 2, 3, 1])
            sel_it = col_r[0].selectbox(f"صنف {idx+1}", list(item_dict.keys()), index=list(item_dict.keys()).index(row_val["item"]) if row_val["item"] in item_dict else 0, key=f"op_it_{idx}", label_visibility="collapsed")
            row_val["item"] = sel_it
            row_val["qty"] = col_r[1].number_input(f"كمية {idx+1}", min_value=0.1, step=0.5, value=row_val["qty"], key=f"op_q_{idx}", label_visibility="collapsed")
            unit_fixed = item_dict[sel_it][2]
            col_r[2].text_input(f"وحدة {idx+1}", value=str(unit_fixed), disabled=True, key=f"op_u_{idx}", label_visibility="collapsed")
            row_val["reason"] = col_r[3].text_input(f"سبب {idx+1}", value=row_val["reason"], placeholder="ملاحظة", key=f"op_r_{idx}", label_visibility="collapsed")
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
            st.success(f"تم حفظ {len(st.session_state.ops_rows)} حركة بنجاح!")
            st.session_state.ops_rows = [{"item": list(item_dict.keys())[0], "qty": 1.0, "reason": ""}]

    # 2. تقرير إغلاق الكاشير اليومي (مطابق للصورة تماماً)
    elif c_mode == "📝 تقرير الإغلاق المالي اليومي للكاشير":
        st.subheader("📝 تقرير الإيرادات والمبيعات اليومية المستلمة (Daily Closing Sheet)")
        with st.form("cashier_closing_form", clear_on_submit=False):
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

    # 3. الجرد الفعلي الدوري
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
            cursor.execute("INSERT INTO inventory_counts (branch, count_date, count_id, item_sku, item_name, storage_qty, ingredients_qty, created_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                           (st.session_state.branch, str(cnt_d), cnt_id.strip(), sk_c, nm_c, q_st, q_in, st.session_state.user))
            conn.commit()
            st.success("تم حفظ الجرد بنجاح!")

# ----------------- واجهة الإدارة والمحاسب -----------------
elif st.session_state.role == "admin":
    st.title("📊 لوحة تحكم الإدارة العامة والمحاسبة المالية")
    admin_tabs = st.tabs([
        "🛒 إدارة المشتريات (متعدد الأصناف)",
        "📑 تقارير إغلاق الكاشيرات اليومية والطباعة",
        "⚖️ ميزان المخزون ومطابقة فروقات الجرد",
        "🍗 تحليل استهلاك الخامات الذكي",
        "🚀 تصدير قوالب فودكس المعتمدة",
        "سجل العمليات اليومية من الفروع"
    ])

    # 1. المشتريات متعددة الأصناف
    with admin_tabs[0]:
        st.subheader("🛒 تسجيل فواتير المشتريات (إدخال عدة أصناف في الفاتورة)")
        
        df_sups = pd.read_sql_query("SELECT name FROM suppliers_master ORDER BY name ASC", conn)
        sup_list = df_sups['name'].tolist() if not df_sups.empty else ["مورد عام", "المراعي", "نادك"]
        
        df_inv_it = pd.read_sql_query("SELECT sku, name_ar, storage_unit FROM items_master WHERE item_type='inventory' ORDER BY name_ar ASC", conn)
        inv_item_dict = {f"{r['name_ar']} ({r['sku']})": (r['sku'], r['name_ar'], r['storage_unit']) for _, r in df_inv_it.iterrows()}

        # بيانات رأس الفاتورة
        h1, h2, h3, h4 = st.columns(4)
        with h1: inv_number = st.text_input("رقم الفاتورة:", placeholder="INV-001")
        with h2: inv_supplier = st.selectbox("اختر المورد (من فودكس):", sup_list)
        with h3: inv_branch = st.selectbox("الفرع المستلم:", BRANCH_LIST)
        with h4: inv_date = st.date_input("تاريخ الفاتورة:", value=date.today())

        st.markdown("#### 📦 بنود الفاتورة:")
        if "pur_rows" not in st.session_state:
            st.session_state.pur_rows = [{"item": list(inv_item_dict.keys())[0], "qty": 1.0, "price": 10.0, "tax": 15.0}]

        cols_ph = st.columns([4, 2, 2, 2, 2, 1])
        cols_ph[0].write("**الصنف المشترى**")
        cols_ph[1].write("**الكمية**")
        cols_ph[2].write("**الوحدة**")
        cols_ph[3].write("**سعر الوحدة**")
        cols_ph[4].write("**الإجمالي بالضريبة**")
        cols_ph[5].write("**حذف**")

        grand_total = 0.0
        for p_idx, p_row in enumerate(st.session_state.pur_rows):
            col_p = st.columns([4, 2, 2, 2, 2, 1])
            p_sel = col_p[0].selectbox(f"صنف {p_idx+1}", list(inv_item_dict.keys()), index=list(inv_item_dict.keys()).index(p_row["item"]) if p_row["item"] in inv_item_dict else 0, key=f"pur_it_{p_idx}", label_visibility="collapsed")
            p_row["item"] = p_sel
            p_row["qty"] = col_p[1].number_input(f"كمية {p_idx+1}", min_value=0.1, step=1.0, value=p_row["qty"], key=f"pur_q_{p_idx}", label_visibility="collapsed")
            col_p[2].text_input(f"وحدة {p_idx+1}", value=inv_item_dict[p_sel][2], disabled=True, key=f"pur_u_{p_idx}", label_visibility="collapsed")
            p_row["price"] = col_p[3].number_input(f"سعر {p_idx+1}", min_value=0.0, step=0.5, value=p_row["price"], key=f"pur_p_{p_idx}", label_visibility="collapsed")
            row_tot = (p_row["qty"] * p_row["price"]) * 1.15
            grand_total += row_tot
            col_p[4].write(f"{row_tot:,.2f} SAR")
            if col_p[5].button("❌", key=f"del_pur_{p_idx}"):
                if len(st.session_state.pur_rows) > 1:
                    st.session_state.pur_rows.pop(p_idx)
                    st.rerun()

        if st.button("➕ إضافة صنف آخر للفاتورة"):
            st.session_state.pur_rows.append({"item": list(inv_item_dict.keys())[0], "qty": 1.0, "price": 10.0, "tax": 15.0})
            st.rerun()

        st.metric("الإجمالي الكلي للفاتورة شامل الضريبة", f"{grand_total:,.2f} SAR")

        if st.button("💾 حفظ الفاتورة بالكامل في المخزون", type="primary", use_container_width=True):
            if inv_number.strip():
                for pr in st.session_state.pur_rows:
                    p_sku, p_name, _ = inv_item_dict[pr["item"]]
                    tot_r = (pr["qty"] * pr["price"]) * 1.15
                    cursor.execute("""
                    INSERT INTO purchases_log (invoice_number, supplier_name, branch, invoice_date, item_sku, item_name, quantity, cost_per_unit, tax_percent, total_with_tax, created_by)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (inv_number.strip(), inv_supplier, inv_branch, str(inv_date), p_sku, p_name, pr["qty"], pr["price"], 15.0, tot_r, st.session_state.user))
                conn.commit()
                st.success(f"تم حفظ فاتورة {inv_supplier} بعدد {len(st.session_state.pur_rows)} صنفاً بنجاح!")
                st.session_state.pur_rows = [{"item": list(inv_item_dict.keys())[0], "qty": 1.0, "price": 10.0, "tax": 15.0}]
            else:
                st.warning("يرجى كتابة رقم الفاتورة أولاً!")

        st.divider()
        purchases_df = pd.read_sql_query("SELECT invoice_number AS 'رقم الفاتورة', supplier_name AS 'المورد', branch AS 'الفرع', invoice_date AS 'التاريخ', item_sku AS 'الكود', item_name AS 'الصنف', quantity AS 'الكمية', cost_per_unit AS 'السعر', total_with_tax AS 'الإجمالي' FROM purchases_log ORDER BY id DESC", conn)
        st.dataframe(purchases_df, use_container_width=True)

    # 2. تقارير إغلاق الكاشيرات اليومية والطباعة
    with admin_tabs[1]:
        st.subheader("📑 تقارير إغلاق الكاشيرات ومطابقة الدفاتر (Daily Cashier Sheets)")
        b_c_fil = st.selectbox("تصفية حسب الفرع:", ["الكل"] + BRANCH_LIST, key="clos_fil")
        
        q_clos = "SELECT * FROM cashier_closings WHERE 1=1"
        p_clos = []
        if b_c_fil != "الكل":
            q_clos += " AND branch=?"
            p_clos.append(b_c_fil)
        q_clos += " ORDER BY id DESC"
        
        df_closings = pd.read_sql_query(q_clos, conn, params=p_clos)
        st.dataframe(df_closings, use_container_width=True)

        if not df_closings.empty:
            st.divider()
            st.markdown("### 🖨️ طباعة نموذج تقرير إغلاق الكاشير المعتمد (Printable Voucher)")
            sel_report_id = st.selectbox("اختر رقم التقرير للطباعة والمراجعة:", df_closings['id'].tolist())
            r_data = df_closings[df_closings['id'] == sel_report_id].iloc[0]

            voucher_html = f"""
            <div style="border: 2px solid #000; padding: 20px; font-family: Cairo, Tahoma, Arial; background-color: #fff; color: #000; border-radius: 8px;">
                <h2 style="text-align: center; margin-bottom: 5px;">Kitchen and Restaurant - Al-Haneeth House - {r_data['branch']}</h2>
                <h4 style="text-align: center; margin-top: 0; color: #555;">تقرير الإيرادات اليومية المستلمة المعتمد</h4>
                <hr style="border: 1px solid #000;"/>
                <table style="width: 100%; font-size: 16px; margin-bottom: 15px;">
                    <tr><td><b>التاريخ:</b> {r_data['closing_date']}</td><td><b>اسم الكاشير:</b> {r_data['cashier_name']}</td><td><b>الفرع:</b> {r_data['branch']}</td></tr>
                </table>
                <table style="width: 100%; border-collapse: collapse; text-align: right; font-size: 15px;" border="1">
                    <tr style="background-color: #f2f2f2;"><th>بيان الإيراد / القناة</th><th>المبلغ (SAR)</th></tr>
                    <tr><td>المبيعات النقدية (Cash Sales)</td><td>{r_data['cash_sales']:,.2f}</td></tr>
                    <tr><td>شبكة مدى (Mada)</td><td>{r_data['mada_sales']:,.2f}</td></tr>
                    <tr><td>فيزا (Visa)</td><td>{r_data['visa_sales']:,.2f}</td></tr>
                    <tr><td>ماستركارد (MasterCard)</td><td>{r_data['mastercard_sales']:,.2f}</td></tr>
                    <tr><td>التحويلات البنكية (Bank Transfers)</td><td>{r_data['bank_transfers']:,.2f}</td></tr>
                    <tr><td>هنقرستيشن (Hungerstation)</td><td>{r_data['hungerstation']:,.2f}</td></tr>
                    <tr><td>جاهز (Jahez)</td><td>{r_data['jahez']:,.2f}</td></tr>
                    <tr><td>نينجا (Ninja)</td><td>{r_data['ninja']:,.2f}</td></tr>
                    <tr><td>كيتا (Keeta)</td><td>{r_data['keeta']:,.2f}</td></tr>
                    <tr style="background-color: #fee;"><td><b>المصروفات النثرية / العجز ({r_data['expenses_notes']})</b></td><td><b>{r_data['expenses_amount']:,.2f}</b></td></tr>
                    <tr style="background-color: #e2f0d9; font-size: 18px;"><td><b>إجمالي المبيعات اليومية (Total Sales)</b></td><td><b>{r_data['total_sales']:,.2f} SAR</b></td></tr>
                </table>
                <br/><br/>
                <table style="width: 100%; text-align: center; font-size: 14px;">
                    <tr>
                        <td><b>توقيع الكاشير</b><br/><br/>______________</td>
                        <td><b>توقيع المحاسب</b><br/><br/>______________</td>
                        <td><b>اعتماد المدير المالي</b><br/><br/>______________</td>
                    </tr>
                </table>
            </div>
            """
            st.components.v1.html(voucher_html, height=520, scrolling=True)
            st.download_button("📥 تحميل التقرير كملف Excel للمحاسب", df_closings.to_csv(index=False).encode('utf-8-sig'), f"Cashier_Closing_{b_c_fil}.csv", "text/csv")

    # 3. ميزان المخزون
    with admin_tabs[2]:
        st.subheader("⚖️ ميزان المخزون ومطابقة فروقات الجرد")
        r_b = st.selectbox("اختر الفرع:", BRANCH_LIST, key="rec_b")
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

        act_b = m_items[(m_items["المشتريات (+)"] > 0) | (m_items["المنصرف (-)"] > 0) | (m_items["الجرد الفعلي"] > 0) | (m_items["الهدر (-)"] > 0)].reset_index()
        if not act_b.empty:
            st.dataframe(act_b.style.map(lambda v: 'background-color: #ffcccc; color: #900;' if v < 0 else ('background-color: #ccffcc;' if v > 0 else ''), subset=['فارق الجرد (عجز/زيادة)']), use_container_width=True)
        else:
            st.info("لا توجد حركات مسجلة لهذا الفرع.")

    # 4. تحليل استهلاك الخامات الذكي
    with admin_tabs[3]:
        st.subheader("🍗 تحليل استهلاك الخامات (دجاج / لحوم / مشروبات) من تقرير فودكس")
        p_file = st.file_uploader("ارفع ملف المبيعات حسب الفرع (XLS / CSV):", type=["xls", "csv", "xlsx"], key="dep_u")
        if p_file:
            dfs_raw = pd.read_csv(p_file) if p_file.name.endswith(".csv") else pd.read_html(p_file)[0]
            if isinstance(dfs_raw.columns, pd.MultiIndex): dfs_raw.columns = dfs_raw.columns.get_level_values(-1)
            dfs_raw = dfs_raw[dfs_raw['الفرع'].notna() & (~dfs_raw['الفرع'].isin(['Title', 'النطاق الزمني', 'تجميع بـ']))].reset_index(drop=True)
            dfs_raw['صافي الكمية'] = pd.to_numeric(dfs_raw['صافي الكمية'], errors='coerce').fillna(0)

            dep_list = []
            for _, rw in dfs_raw.iterrows():
                br = str(rw['الفرع']).strip()
                pn = str(rw['المنتج']).strip()
                sq = float(rw['صافي الكمية'])
                if 'دجاج' in pn:
                    ch_q = (sq * 0.5) if pn.startswith('نص') else (sq * 1.0)
                    dep_list.append({'الفرع': br, 'الفئة': 'دجاج كامل', 'الصنف': pn, 'الكمية المباعة': sq, 'الوحدة': 'حبة دجاج', 'الكمية المستهلكة': ch_q})
                elif 'تيس' in pn or 'لحم' in pn:
                    if 'ربع' in pn: nf = sq * 4.0
                    elif 'نص' in pn: nf = sq * 8.0
                    elif 'تيس' in pn and 'راس' not in pn and 'نفر' not in pn: nf = sq * 16.0
                    else: nf = sq * 1.0
                    dep_list.append({'الفرع': br, 'الفئة': 'لحم تيس', 'الصنف': pn, 'الكمية المباعة': sq, 'الوحدة': 'أنفار', 'الكمية المستهلكة': nf})
                elif any(dk in pn for dk in ['بيبسي', 'سفن', 'مشروبات غازية', 'مياة', 'مياه', 'لبن']):
                    dep_list.append({'الفرع': br, 'الفئة': 'مشروبات ومياه', 'الصنف': pn, 'الكمية المباعة': sq, 'الوحدة': 'علبة/حبة', 'الكمية المستهلكة': sq})

            df_dep = pd.DataFrame(dep_list)
            c1, c2 = st.columns(2)
            with c1:
                st.write("**🍗 إجمالي حبات الدجاج المستهلكة:**")
                st.dataframe(df_dep[df_dep['الفئة'] == 'دجاج كامل'].groupby('الفرع')['الكمية المستهلكة'].sum().reset_index(), use_container_width=True)
            with c2:
                st.write("**🐐 إجمالي لحم التيس (أنفار وذبائح كاملة):**")
                m_sum = df_dep[df_dep['الفئة'] == 'لحم تيس'].groupby('الفرع')['الكمية المستهلكة'].sum().reset_index()
                m_sum['ذبائح كاملة (تيس)'] = m_sum['الكمية المستهلكة'] / 16.0
                st.dataframe(m_sum, use_container_width=True)
            st.dataframe(df_dep, use_container_width=True)

    # 5. تصدير قوالب فودكس المعتمدة
    with admin_tabs[4]:
        st.subheader("🚀 تصدير ملفات فودكس المعتمدة")
        ex_b = st.selectbox("الفرع:", BRANCH_LIST, key="ex_b_admin")
        ex_d = st.date_input("التاريخ:", value=date.today(), key="ex_d_admin")
        c_p, c_t, c_i = st.columns(3)
        with c_p:
            df_p = pd.read_sql_query("SELECT item_name AS name, item_sku AS sku, quantity AS storage_quantity, 0 AS ingredients_quantity FROM operations_log WHERE branch=? AND entry_date=? AND entry_type LIKE '%إنتاج%'", conn, params=(ex_b, str(ex_d)))
            if not df_p.empty: st.download_button("📥 تحميل production.csv", df_p.to_csv(index=False).encode('utf-8'), "production.csv")
            else: st.warning("لا يوجد إنتاج مسجل")
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

    # 6. سجل العمليات
    with admin_tabs[5]:
        st.subheader("سجل العمليات اليومية لكافة الفروع")
        st.dataframe(pd.read_sql_query("SELECT * FROM operations_log ORDER BY id DESC", conn), use_container_width=True)