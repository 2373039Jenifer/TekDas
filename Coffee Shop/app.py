"""Dashboard Coffee Shop Sales - versi modifikasi lengkap.
Tambahan: filter bulan/kategori/tipe hari/waktu, KPI tambahan, tren harian + rata-rata
bergerak, drill-down treemap, heatmap hari x jam, insight otomatis, unduh data.
Jalankan: python -m streamlit run app.py
"""
from pathlib import Path
import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Coffee Shop Sales", page_icon="☕", layout="wide")

TEAL, PURPLE, ORANGE = "#087F8C", "#7656B5", "#D98B39"
STORE_COLORS = {"Astoria": TEAL, "Hell's Kitchen": PURPLE, "Lower Manhattan": ORANGE}
DAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"]
DAYPARTS = ["Pagi (06-10)", "Siang (11-14)", "Sore (15-17)", "Malam (18-20)"]

st.markdown("""
<style>
.block-container {padding-top: 1.6rem;}
div[data-testid="stMetric"] {background: #F4F8F9; border-left: 6px solid #087F8C;
    border-radius: 10px; padding: 14px 16px;}
div[data-testid="stMetric"] label p {font-weight: 600; color: #3b4a52;}
div[data-testid="stMetricValue"] {color: #0b3d44;}
h1, h2, h3 {color: #0b3d44;}
section[data-testid="stSidebar"] > div:first-child {padding-top: 0;}
div[data-testid="stSidebarHeader"] {height: 2rem; padding-bottom: 0;}
div[data-testid="stSidebarUserContent"] {padding-top: 0.5rem;}
</style>
""", unsafe_allow_html=True)

folder = Path(__file__).resolve().parent
file_data = folder / "data_prepared" / "coffee_sales_prepared.csv"


@st.cache_data
def load_data(path, modified_time):
    # modified_time ikut jadi kunci cache: file berubah -> data dibaca ulang
    data = pd.read_csv(path)
    data["transaction_date"] = pd.to_datetime(data["transaction_date"])
    data["tipe_hari"] = data["day_of_week"].map(
        lambda d: "Akhir pekan" if d >= 5 else "Hari kerja")
    data["daypart"] = pd.cut(data["hour"], bins=[-1, 10, 14, 17, 23],
                             labels=DAYPARTS).astype(str)
    return data


def format_angka(value, decimals=2):
    # Format Indonesia: titik ribuan, koma desimal
    return (f"{value:,.{decimals}f}".replace(",", "_")
            .replace(".", ",").replace("_", "."))


st.title("☕ Dashboard Coffee Shop Sales")
st.caption("Januari-Juni 2023. Mata uang belum dinyatakan pada file; "
           "nilai disebut nilai penjualan.")
if not file_data.exists():
    st.error("Jalankan audit. File coffee_sales_prepared.csv belum ada.")
    st.stop()
df = load_data(str(file_data), file_data.stat().st_mtime_ns)

# ---------------- Filter ----------------
months = pd.period_range(
    df["transaction_date"].min().to_period("M"),
    df["transaction_date"].max().to_period("M"), freq="M"
).astype(str).tolist()

st.sidebar.header("Filter data")
stores = sorted(df["store_location"].unique().tolist())
selected = st.sidebar.multiselect("Pilih gerai", stores, default=stores)
categories = sorted(df["product_category"].unique().tolist())
selected_cat = st.sidebar.multiselect("Pilih kategori", categories, default=categories)
m_start, m_end = st.sidebar.select_slider(
    "Rentang bulan", options=months, value=(months[0], months[-1]))
sel_days = st.sidebar.multiselect("Tipe hari", ["Hari kerja", "Akhir pekan"],
                                  default=["Hari kerja", "Akhir pekan"])
sel_parts = st.sidebar.multiselect("Waktu transaksi", DAYPARTS, default=DAYPARTS)
if not (selected and selected_cat and sel_days and sel_parts):
    st.info("Pilih minimal satu opsi pada setiap filter.")
    st.stop()
st.sidebar.caption("Semua kartu, grafik, dan insight mengikuti kelima filter ini.")

# base = semua filter KECUALI bulan, supaya bulan pembanding growth tetap ada
base = df[df["store_location"].isin(selected)
          & df["product_category"].isin(selected_cat)
          & df["tipe_hari"].isin(sel_days)
          & df["daypart"].isin(sel_parts)]
data_filter = base[(base["month"] >= m_start) & (base["month"] <= m_end)].copy()
if data_filter.empty:
    st.info("Tidak ada data pada kombinasi filter ini.")
    st.stop()

# ---------------- Agregasi bulanan ----------------
monthly_all = base.groupby("month").agg(
    total_sales=("sales", "sum"),
    total_transactions=("transaction_id", "nunique"),
    total_units=("transaction_qty", "sum")).reindex(months)
previous = monthly_all["total_sales"].shift(1)
monthly_all["growth_pct"] = ((monthly_all["total_sales"] - previous) / previous * 100
                             ).where(previous.notna() & previous.ne(0))
monthly_all["average_transaction_value"] = (
    monthly_all["total_sales"] / monthly_all["total_transactions"])
monthly_all = monthly_all.reset_index().rename(columns={"index": "month"})
monthly = monthly_all[(monthly_all["month"] >= m_start) & (monthly_all["month"] <= m_end)]

total_sales = data_filter["sales"].sum()
total_transactions = data_filter["transaction_id"].nunique()
total_units = data_filter["transaction_qty"].sum()
average = total_sales / total_transactions if total_transactions else None
growth = monthly["growth_pct"].iloc[-1]
last_month = pd.Period(m_end, freq="M")
days_in_range = (data_filter["transaction_date"].max()
                 - data_filter["transaction_date"].min()).days + 1

# ---------------- Kartu ringkasan ----------------
st.subheader("Ringkasan penjualan")
st.caption(f"Total, transaksi, dan rata-rata: {m_start} sampai {m_end}. "
           f"Pertumbuhan: {last_month} terhadap {last_month - 1} "
           "(pembanding dari gerai, kategori, tipe hari, dan waktu yang sama).")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total penjualan", format_angka(total_sales))
c2.metric("Transaksi tercatat", format_angka(total_transactions, 0))
c3.metric("Rata-rata nilai transaksi",
          format_angka(average) if average is not None else "Belum tersedia")
c4.metric(f"Pertumbuhan {last_month} terhadap {last_month - 1}",
          f"{format_angka(growth)}%" if pd.notna(growth) else "Belum tersedia")

e1, e2, e3, e4 = st.columns(4)
e1.metric("Unit terjual", format_angka(total_units, 0))
e2.metric("Transaksi tercatat per hari", format_angka(total_transactions / days_in_range, 1))
e3.metric("Penjualan harian per gerai",
          format_angka(total_sales / days_in_range / len(selected)))
top10 = data_filter.groupby("product_id")["sales"].sum().nlargest(10).sum()
e4.metric("Porsi 10 produk teratas", f"{format_angka(top10 / total_sales * 100, 1)}%")
st.caption(f"Per hari memakai {days_in_range} hari kalender pada rentang terpilih. "
           "Hari tanpa catatan tidak otomatis berarti toko tutup.")

# ---------------- Insight otomatis ----------------
top_store = data_filter.groupby("store_location")["sales"].sum().idxmax()
cat_s = data_filter.groupby("product_category")["sales"].sum().sort_values(ascending=False)
peak_h = int(data_filter.groupby("hour")["transaction_id"].nunique().idxmax())
growth_txt = (f"Penjualan {last_month} {'naik' if growth >= 0 else 'turun'} "
              f"{format_angka(abs(growth))}% dibanding {last_month - 1}. "
              if pd.notna(growth) else f"Pertumbuhan {last_month} belum tersedia (tidak ada pembanding). ")
st.info(
    f"**Insight (otomatis, mengikuti filter).** Periode {m_start} sampai {m_end}, "
    f"{len(selected)} gerai, {len(selected_cat)} kategori. Total penjualan "
    f"{format_angka(total_sales)} dari {format_angka(total_transactions, 0)} transaksi tercatat. "
    f"{growth_txt}Gerai tertinggi: {top_store}. Kategori terbesar: {cat_s.index[0]} "
    f"({format_angka(cat_s.iloc[0] / total_sales * 100, 1)}%). Jam transaksi tercatat "
    f"terbanyak: {peak_h:02d}:00. Batasan: deskriptif, belum menunjukkan penyebab, "
    "dan jam tersibuk belum membuktikan antrean. Tindakan: telusuri gerai/kategori pendorong.")

tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["📈 Tren", "🏪 Gerai & Kategori", "🛍️ Produk", "🕒 Waktu", "🗂️ Data"])

# ---------------- Tab tren ----------------
with tab1:
    view = st.radio("Tampilan tren bulanan", ["Total", "Per gerai"], horizontal=True)
    if view == "Total":
        fig = px.line(monthly, x="month", y="total_sales", markers=True,
                      labels={"month": "Bulan", "total_sales": "Nilai penjualan"})
        fig.update_traces(line_color=TEAL, connectgaps=False)
    else:
        ps = data_filter.groupby(["month", "store_location"], as_index=False).agg(
            total_sales=("sales", "sum"))
        fig = px.line(ps, x="month", y="total_sales", color="store_location", markers=True,
                      color_discrete_map=STORE_COLORS,
                      labels={"month": "Bulan", "total_sales": "Nilai penjualan",
                              "store_location": "Gerai"})
    fig.update_layout(xaxis_type="category", yaxis_rangemode="tozero")
    st.plotly_chart(fig, use_container_width=True, key="trend")

    st.subheader("Penjualan harian dan rata-rata bergerak 7 hari")
    daily = data_filter.groupby("transaction_date")["sales"].sum()
    daily = daily.reindex(pd.date_range(daily.index.min(), daily.index.max())
                          ).rename_axis("tanggal").reset_index(name="sales")
    daily["rata-rata 7 hari"] = daily["sales"].rolling(7, min_periods=7).mean()
    fig_d = px.line(daily, x="tanggal", y=["sales", "rata-rata 7 hari"],
                    labels={"value": "Nilai penjualan", "variable": "Seri"},
                    color_discrete_sequence=["#B8C4C8", TEAL])
    fig_d.update_layout(height=380)
    st.plotly_chart(fig_d, use_container_width=True, key="daily")
    st.caption("Garis abu-abu = nilai harian; garis teal = rata-rata 7 hari (halus). "
               "Menunjukkan pola yang sudah terjadi, bukan ramalan.")

    with st.expander("Lihat angka ringkasan bulanan"):
        table = monthly.rename(columns={
            "month": "Bulan", "total_sales": "Total penjualan",
            "total_transactions": "Transaksi tercatat", "total_units": "Unit terjual",
            "growth_pct": "Pertumbuhan (%)",
            "average_transaction_value": "Rata-rata nilai transaksi"})
        st.dataframe(table.style.format({
            "Total penjualan": "{:,.2f}", "Transaksi tercatat": "{:,.0f}",
            "Unit terjual": "{:,.0f}", "Pertumbuhan (%)": "{:,.2f}",
            "Rata-rata nilai transaksi": "{:,.2f}"}, na_rep="Belum tersedia",
            decimal=",", thousands="."), use_container_width=True, hide_index=True)

# ---------------- Tab gerai & kategori ----------------
with tab2:
    left, right = st.columns(2)
    with left:
        st.subheader("Penjualan per gerai")
        sbs = data_filter.groupby("store_location", as_index=False).agg(
            total_sales=("sales", "sum")).sort_values("total_sales", ascending=False)
        fig_s = px.bar(sbs, x="store_location", y="total_sales", color="store_location",
                       text_auto=".2s", color_discrete_map=STORE_COLORS,
                       labels={"store_location": "Gerai", "total_sales": "Nilai penjualan"})
        fig_s.update_layout(showlegend=False, height=400)
        st.plotly_chart(fig_s, use_container_width=True, key="stores")
        st.caption("Hanya gerai yang dipilih muncul pada grafik.")
    with right:
        st.subheader("Kontribusi penjualan kategori")
        sbc = data_filter.groupby("product_category", as_index=False).agg(
            total_sales=("sales", "sum")).sort_values("total_sales", ascending=False)
        fig_c = px.pie(sbc, names="product_category", values="total_sales", hole=0.55)
        fig_c.update_traces(textinfo="none", hovertemplate=(
            "%{label}<br>Penjualan: %{value:,.2f}<br>Kontribusi: %{percent}<extra></extra>"))
        fig_c.update_layout(height=400, legend_title_text="Kategori")
        st.plotly_chart(fig_c, use_container_width=True, key="categories")
        st.caption("Kontribusi terhadap total dalam filter yang sama.")

    st.subheader("Gerai × kategori")
    gk = data_filter.groupby(["store_location", "product_category"], as_index=False).agg(
        total_sales=("sales", "sum"))
    fig_gk = px.bar(gk, x="store_location", y="total_sales", color="product_category",
                    barmode="stack",
                    labels={"store_location": "Gerai", "total_sales": "Nilai penjualan",
                            "product_category": "Kategori"})
    fig_gk.update_layout(height=420)
    st.plotly_chart(fig_gk, use_container_width=True, key="store_cat")

    st.subheader("Drill-down: kategori → jenis → produk")
    fig_tm = px.treemap(data_filter, path=[px.Constant("Semua"), "product_category",
                                           "product_type", "product_detail"],
                        values="sales", color="product_category")
    fig_tm.update_traces(hovertemplate="%{label}<br>Penjualan: %{value:,.2f}<br>"
                         "Porsi induk: %{percentParent:.1%}<extra></extra>")
    fig_tm.update_layout(height=520, margin=dict(t=10, l=0, r=0, b=0))
    st.plotly_chart(fig_tm, use_container_width=True, key="treemap")
    st.caption("Klik kotak untuk masuk ke tingkat lebih rinci; klik judul di atas untuk kembali.")

# ---------------- Tab produk ----------------
with tab3:
    left, right = st.columns(2)
    with left:
        st.subheader("10 produk dengan penjualan tertinggi")
        tp = data_filter.groupby(["product_id", "product_detail"], as_index=False).agg(
            total_sales=("sales", "sum")).nlargest(10, "total_sales").sort_values(
            "total_sales", ascending=True)
        tp["label"] = tp["product_detail"] + " (" + tp["product_id"].astype(str) + ")"
        fig_p = px.bar(tp, x="total_sales", y="label", orientation="h",
                       color_discrete_sequence=[PURPLE],
                       labels={"total_sales": "Nilai penjualan", "label": "Produk"})
        fig_p.update_layout(height=470, yaxis={
            "categoryorder": "array", "categoryarray": tp["label"].tolist()})
        st.plotly_chart(fig_p, use_container_width=True, key="products")
        st.caption("Peringkat nilai penjualan, bukan unit atau keuntungan.")
    with right:
        st.subheader("10 produk dengan unit terjual terbanyak")
        tu = data_filter.groupby(["product_id", "product_detail"], as_index=False).agg(
            total_units=("transaction_qty", "sum")).nlargest(10, "total_units").sort_values(
            "total_units", ascending=True)
        tu["label"] = tu["product_detail"] + " (" + tu["product_id"].astype(str) + ")"
        fig_u = px.bar(tu, x="total_units", y="label", orientation="h",
                       color_discrete_sequence=[ORANGE],
                       labels={"total_units": "Unit terjual", "label": "Produk"})
        fig_u.update_layout(height=470, yaxis={
            "categoryorder": "array", "categoryarray": tu["label"].tolist()})
        st.plotly_chart(fig_u, use_container_width=True, key="products_units")
        st.caption("Peringkat unit bisa berbeda dari peringkat nilai penjualan.")

    st.subheader("Produk dengan variasi harga")
    price = data_filter.groupby(["product_id", "product_detail"]).agg(
        harga_min=("unit_price", "min"), harga_maks=("unit_price", "max"),
        jumlah_harga=("unit_price", "nunique")).reset_index()
    price = price[price["jumlah_harga"] > 1].sort_values("jumlah_harga", ascending=False)
    st.dataframe(price, use_container_width=True, hide_index=True)
    st.caption("Harga berbeda belum tentu salah; telusuri menurut tanggal sebelum menyimpulkan.")

# ---------------- Tab waktu ----------------
with tab4:
    left, right = st.columns(2)
    with left:
        st.subheader("Transaksi tercatat menurut jam")
        bh = data_filter.groupby("hour", as_index=False).agg(
            total_transactions=("transaction_id", "nunique")).sort_values("hour")
        bh["label"] = bh["hour"].astype(int).astype(str).str.zfill(2) + ":00"
        fig_h = px.bar(bh, x="label", y="total_transactions",
                       color_discrete_sequence=[ORANGE],
                       labels={"label": "Jam", "total_transactions": "Transaksi tercatat"})
        fig_h.update_layout(height=420, xaxis_type="category")
        st.plotly_chart(fig_h, use_container_width=True, key="hours")
        st.caption("Akumulasi sepanjang periode, belum mengukur antrean layanan.")
    with right:
        st.subheader("Transaksi tercatat menurut hari")
        bd = data_filter.groupby("day_name_id")["transaction_id"].nunique().reindex(
            DAYS).dropna().reset_index(name="transaksi")
        fig_w = px.bar(bd, x="day_name_id", y="transaksi",
                       color_discrete_sequence=[TEAL],
                       labels={"day_name_id": "Hari", "transaksi": "Transaksi tercatat"})
        fig_w.update_layout(height=420)
        st.plotly_chart(fig_w, use_container_width=True, key="weekday")
        st.caption("Jumlah hari tiap nama hari tidak persis sama; bandingkan pola, bukan selisih kecil.")

    st.subheader("Heatmap transaksi tercatat: hari × jam")
    heat = data_filter.groupby(["day_name_id", "hour"]).agg(
        n=("transaction_id", "nunique")).reset_index()
    heat = heat.pivot(index="day_name_id", columns="hour", values="n").reindex(DAYS)
    fig_ht = px.imshow(heat, aspect="auto", color_continuous_scale="Teal",
                       labels={"x": "Jam", "y": "Hari", "color": "Transaksi"})
    fig_ht.update_layout(height=380)
    fig_ht.update_xaxes(dtick=1)
    st.plotly_chart(fig_ht, use_container_width=True, key="heatmap")

    st.subheader("Penjualan menurut waktu transaksi")
    dp = data_filter.groupby("daypart", as_index=False).agg(total_sales=("sales", "sum"))
    dp["daypart"] = pd.Categorical(dp["daypart"], DAYPARTS, ordered=True)
    fig_dp = px.bar(dp.sort_values("daypart"), x="daypart", y="total_sales",
                    color_discrete_sequence=[PURPLE],
                    labels={"daypart": "Waktu", "total_sales": "Nilai penjualan"})
    fig_dp.update_layout(height=360)
    st.plotly_chart(fig_dp, use_container_width=True, key="daypart")

# ---------------- Tab data ----------------
with tab5:
    st.subheader("Data hasil filter")
    st.caption(f"{format_angka(len(data_filter), 0)} baris sesuai filter saat ini.")
    show_cols = ["transaction_id", "transaction_date", "transaction_time", "store_location",
                 "product_category", "product_type", "product_detail",
                 "transaction_qty", "unit_price", "sales"]
    st.dataframe(data_filter[show_cols].head(1000), use_container_width=True, hide_index=True)
    st.caption("Tabel menampilkan 1.000 baris pertama; unduhan memuat seluruh hasil filter.")
    d1, d2 = st.columns(2)
    d1.download_button("⬇️ Unduh data terfilter (CSV)",
                       data_filter[show_cols].to_csv(index=False).encode("utf-8-sig"),
                       "coffee_terfilter.csv", "text/csv")
    d2.download_button("⬇️ Unduh ringkasan bulanan (CSV)",
                       monthly.to_csv(index=False).encode("utf-8-sig"),
                       "ringkasan_bulanan_terfilter.csv", "text/csv")

st.caption("Transaksi tercatat adalah transaction_id unik, bukan pelanggan unik. "
           "Rata-rata nilainya belum dipastikan sebagai seluruh isi struk pelanggan.")