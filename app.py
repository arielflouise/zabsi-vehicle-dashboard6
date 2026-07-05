import streamlit as st
from streamlit_gsheets import GSheetsConnection
import pandas as pd
import datetime
import json
from google.oauth2.service_account import Credentials
import gspread
from PIL import Image

st.set_page_config(page_title="Zabsi Vehicle Control", page_icon="🛻", layout="wide")

# --- COMPANY LOGO (JPEG SUPPORT) ---
# Try to load local logo (supports .jpg, .jpeg, .png)
try:
    # Try different common extensions
    logo_file = None
    for ext in ['.jpg', '.jpeg', '.png']:
        try:
            logo_file = f"logo{ext}"
            logo = Image.open(logo_file)
            break
        except:
            continue
    
    if logo_file:
        # Resize logo
        logo = logo.resize((150, 150))
        
        # Display logo and title in columns
        col1, col2 = st.columns([1, 5])
        with col1:
            st.image(logo, width=120)
        with col2:
            st.title("📊 ZABSI Fleet, Booking & Compliance System")
            st.markdown("Sistem Log Penggunaan Kenderaan dan Pemantauan Tarikh Dokumen Syarikat secara Live.")
    else:
        # Fallback if logo not found - just show title
        st.title("📊 ZABSI Fleet, Booking & Compliance System")
        st.markdown("Sistem Log Penggunaan Kenderaan dan Pemantauan Tarikh Dokumen Syarikat secara Live.")
        
except Exception as e:
    # Fallback if any error occurs - just show title
    st.title("📊 ZABSI Fleet, Booking & Compliance System")
    st.markdown("Sistem Log Penggunaan Kenderaan dan Pemantauan Tarikh Dokumen Syarikat secara Live.")

# 1. Get credentials from Secrets
try:
    sheet_url = st.secrets["connections"]["gsheets"]["spreadsheet"]
    sheet_id = sheet_url.split("/d/")[1].split("/")[0]
    
    service_account_info = {
        "type": st.secrets["google_service_account"]["type"],
        "project_id": st.secrets["google_service_account"]["project_id"],
        "private_key_id": st.secrets["google_service_account"]["private_key_id"],
        "private_key": st.secrets["google_service_account"]["private_key"],
        "client_email": st.secrets["google_service_account"]["client_email"],
        "client_id": st.secrets["google_service_account"]["client_id"],
        "auth_uri": st.secrets["google_service_account"]["auth_uri"],
        "token_uri": st.secrets["google_service_account"]["token_uri"],
        "auth_provider_x509_cert_url": st.secrets["google_service_account"]["auth_provider_x509_cert_url"],
        "client_x509_cert_url": st.secrets["google_service_account"]["client_x509_cert_url"],
        "universe_domain": st.secrets["google_service_account"]["universe_domain"]
    }
    
except Exception as e:
    st.error(f"Error loading credentials: {str(e)}")
    st.stop()

# 2. Connect to Google Sheets
try:
    credentials = Credentials.from_service_account_info(
        service_account_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )
    
    conn = st.connection("gsheets", type=GSheetsConnection)
    df = conn.read(ttl=1)
    
    gc = gspread.authorize(credentials)
    spreadsheet = gc.open_by_key(sheet_id)
    worksheet = spreadsheet.get_worksheet(0)
    
except Exception as e:
    st.error(f"Failed to connect to Google Sheets: {str(e)}")
    st.stop()

# Clean Date Columns
for col in ["Tarikh Mula", "Tarikh Tamat", "Road Tax Expiry", "Insurance Expiry", "Puspakom Expiry"]:
    if col in df.columns:
        df[col] = pd.to_datetime(df[col], errors='coerce')

today = datetime.datetime.now()

# --- FUNCTION TO CHECK BOOKING CONFLICT ---
def check_booking_conflict(df, vehicle, start_date, end_date):
    """
    Check if a vehicle is already booked for the given date range
    Returns: (has_conflict, conflict_details)
    """
    if df.empty or "No. Pendaftaran" not in df.columns:
        return False, None
    
    # Filter for the same vehicle
    vehicle_bookings = df[df["No. Pendaftaran"] == vehicle]
    
    if vehicle_bookings.empty:
        return False, None
    
    # Check for date overlaps
    conflicts = []
    for _, booking in vehicle_bookings.iterrows():
        if pd.notnull(booking["Tarikh Mula"]) and pd.notnull(booking["Tarikh Tamat"]):
            existing_start = booking["Tarikh Mula"]
            existing_end = booking["Tarikh Tamat"]
            
            # Check if date ranges overlap
            if not (end_date < existing_start or start_date > existing_end):
                conflicts.append({
                    "date": f"{existing_start.strftime('%d/%m/%Y')} - {existing_end.strftime('%d/%m/%Y')}",
                    "pic": booking.get("PIC", "Unknown"),
                    "location": booking.get("Lokasi", "Unknown")
                })
    
    if conflicts:
        return True, conflicts
    return False, None

# --- SIDEBAR: VIEW OPTIONS ---
st.sidebar.header("📂 Paparan")
view_option = st.sidebar.radio(
    "Pilih paparan:",
    [
        "📅 Mengikut Tarikh", 
        "🚗 Mengikut Kenderaan",
        "📋 Tempahan Aktif",
        "📊 Ringkasan Kenderaan"
    ]
)

# --- SIDEBAR: BOOKING FORM ---
st.sidebar.header("➕ Borang Tempahan Baru")

if not df.empty and "No. Pendaftaran" in df.columns:
    unique_vehicles = sorted(df["Kenderaan"].dropna().unique()) if "Kenderaan" in df.columns else []
    unique_plates = sorted(df["No. Pendaftaran"].dropna().unique())

    with st.sidebar.form(key="booking_form", clear_on_submit=True):
        input_vehicle = st.selectbox("Pilih Kenderaan", unique_vehicles) if unique_vehicles else st.text_input("Nama Kenderaan")
        input_plate = st.selectbox("No. Pendaftaran", unique_plates)

        matched_rows = df[df["No. Pendaftaran"] == input_plate]
        default_fuel = matched_rows["Jenis Minyak"].values[0] if "Jenis Minyak" in df.columns and not matched_rows.empty else "PETROL"
        st.caption(f"⛽ Jenis Minyak: **{default_fuel}**")

        input_start = st.date_input("Tarikh Mula Perjalanan", datetime.date.today())
        input_end = st.date_input("Tarikh Tamat Perjalanan", datetime.date.today())
        input_lokasi = st.text_input("📍 Lokasi / Site")
        input_pic = st.text_input("👤 Nama PIC / Pemandu")
        input_nota = st.text_input("📝 Nota / Kegunaan (Opsional)")

        submit_button = st.form_submit_button(label="Hantar Tempahan")

    if submit_button:
        if not input_lokasi or not input_pic:
            st.sidebar.error("❌ Sila isi bahagian Lokasi dan PIC!")
        else:
            # --- CHECK FOR CONFLICTS ---
            has_conflict, conflict_details = check_booking_conflict(
                df, 
                input_plate, 
                pd.Timestamp(input_start), 
                pd.Timestamp(input_end)
            )
            
            if has_conflict:
                st.sidebar.error("❌ Tempahan GAGAL! Kenderaan ini sudah ditempah pada tarikh tersebut.")
                st.sidebar.markdown("**📅 Tempahan sedia ada:**")
                for conflict in conflict_details:
                    st.sidebar.markdown(f"""
                    - **Tarikh:** {conflict['date']}
                    - **PIC:** {conflict['pic']}
                    - **Lokasi:** {conflict['location']}
                    ---
                    """)
            else:
                # No conflict - proceed with booking
                rt_val = matched_rows["Road Tax Expiry"].values[0] if "Road Tax Expiry" in df.columns and not matched_rows.empty else None
                ins_val = matched_rows["Insurance Expiry"].values[0] if "Insurance Expiry" in df.columns and not matched_rows.empty else None
                pk_val = matched_rows["Puspakom Expiry"].values[0] if "Puspakom Expiry" in df.columns and not matched_rows.empty else None

                rt_str = pd.to_datetime(rt_val).strftime('%Y-%m-%d') if pd.notnull(rt_val) else ""
                ins_str = pd.to_datetime(ins_val).strftime('%Y-%m-%d') if pd.notnull(ins_val) else ""
                pk_str = pd.to_datetime(pk_val).strftime('%Y-%m-%d') if pd.notnull(pk_val) else ""

                new_row_idx = len(df) + 1

                new_row_data = [
                    new_row_idx,
                    str(input_vehicle),
                    str(input_plate),
                    str(default_fuel),
                    input_start.strftime('%Y-%m-%d'),
                    input_end.strftime('%Y-%m-%d'),
                    str(input_lokasi),
                    str(input_pic),
                    str(input_nota) if input_nota else "",
                    rt_str,
                    ins_str,
                    pk_str
                ]

                try:
                    worksheet.append_row(new_row_data)
                    df = conn.read(ttl=1)
                    st.sidebar.success("✅ Tempahan berjaya disimpan!")
                    st.rerun()
                    
                except Exception as e:
                    st.sidebar.error(f"❌ Gagal menyimpan: {str(e)}")

# --- MAIN DISPLAY ---
if view_option == "📅 Mengikut Tarikh":
    st.subheader("📋 Log Tempahan (Mengikut Tarikh)")
    
    # Sort by date (newest first)
    if "Tarikh Mula" in df.columns:
        display_df = df.sort_values("Tarikh Mula", ascending=False)
    else:
        display_df = df
    
    st.dataframe(display_df, use_container_width=True)

elif view_option == "🚗 Mengikut Kenderaan":
    st.subheader("📋 Log Tempahan (Mengikut Kenderaan)")
    
    # Sort by vehicle, then by date
    if "Kenderaan" in df.columns and "Tarikh Mula" in df.columns:
        display_df = df.sort_values(["Kenderaan", "Tarikh Mula"], ascending=[True, False])
    else:
        display_df = df
    
    # Reorder columns: Car first
    column_order = []
    for col in ["Kenderaan", "No. Pendaftaran", "Tarikh Mula", "Tarikh Tamat", "PIC", "Lokasi", "Nota / Kegunaan", "Jenis Minyak", "Road Tax Expiry", "Insurance Expiry", "Puspakom Expiry"]:
        if col in display_df.columns:
            column_order.append(col)
    
    display_df = display_df[column_order]
    st.dataframe(display_df, use_container_width=True)

elif view_option == "📋 Tempahan Aktif":
    st.subheader("📋 Tempahan Aktif (Akan Datang)")
    
    # Filter for active bookings (today and future)
    if "Tarikh Tamat" in df.columns:
        active_df = df[df["Tarikh Tamat"] >= pd.Timestamp(today)]
        
        if not active_df.empty:
            # Sort by vehicle, then by start date
            active_df = active_df.sort_values(["Kenderaan", "Tarikh Mula"])
            
            # Group by vehicle
            for vehicle in active_df["Kenderaan"].unique():
                vehicle_data = active_df[active_df["Kenderaan"] == vehicle]
                plate = vehicle_data.iloc[0]["No. Pendaftaran"]
                
                with st.expander(f"🚗 **{vehicle}** ({plate}) - {len(vehicle_data)} tempahan"):
                    # Show only relevant columns
                    display_cols = ["Tarikh Mula", "Tarikh Tamat", "PIC", "Lokasi", "Nota / Kegunaan"]
                    display_cols = [col for col in display_cols if col in vehicle_data.columns]
                    st.dataframe(vehicle_data[display_cols], use_container_width=True)
        else:
            st.info("Tiada tempahan aktif pada masa ini.")
    else:
        st.dataframe(df, use_container_width=True)

elif view_option == "📊 Ringkasan Kenderaan":
    st.subheader("📊 Ringkasan Penggunaan Kenderaan")
    
    if "Kenderaan" in df.columns:
        # Get unique vehicles
        vehicles = sorted(df["Kenderaan"].unique())
        
        # Let user select a vehicle
        selected_vehicle = st.selectbox("Pilih Kenderaan untuk lihat jadual:", vehicles)
        
        if selected_vehicle:
            vehicle_data = df[df["Kenderaan"] == selected_vehicle].sort_values("Tarikh Mula")
            plate = vehicle_data.iloc[0]["No. Pendaftaran"] if not vehicle_data.empty else "N/A"
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📝 Jumlah Tempahan", len(vehicle_data))
            with col2:
                if not vehicle_data.empty and "Tarikh Mula" in vehicle_data.columns:
                    first_booking = vehicle_data["Tarikh Mula"].min()
                    st.metric("📅 Tempahan Pertama", first_booking.strftime('%d/%m/%Y'))
            with col3:
                if not vehicle_data.empty and "Tarikh Tamat" in vehicle_data.columns:
                    last_booking = vehicle_data["Tarikh Tamat"].max()
                    st.metric("📅 Tempahan Terakhir", last_booking.strftime('%d/%m/%Y'))
            
            st.markdown(f"### 🚗 {selected_vehicle} ({plate})")
            
            # Show upcoming bookings
            upcoming = vehicle_data[vehicle_data["Tarikh Tamat"] >= pd.Timestamp(today)]
            if not upcoming.empty:
                st.markdown("**📅 Tempahan Akan Datang:**")
                display_cols = ["Tarikh Mula", "Tarikh Tamat", "PIC", "Lokasi"]
                display_cols = [col for col in display_cols if col in upcoming.columns]
                st.dataframe(upcoming[display_cols], use_container_width=True)
            else:
                st.info("Tiada tempahan akan datang untuk kenderaan ini.")
            
            # Show past bookings (last 5)
            past = vehicle_data[vehicle_data["Tarikh Tamat"] < pd.Timestamp(today)].sort_values("Tarikh Tamat", ascending=False)
            if not past.empty:
                st.markdown("**📜 Tempahan Lalu (5 terkini):**")
                display_cols = ["Tarikh Mula", "Tarikh Tamat", "PIC", "Lokasi"]
                display_cols = [col for col in display_cols if col in past.columns]
                st.dataframe(past.head(5)[display_cols], use_container_width=True)

st.markdown("---")

# --- COMPLIANCE ALERTS ---
st.subheader("🚨 Amaran Pematuhan Dokumen")
if not df.empty and "No. Pendaftaran" in df.columns:
    cols_to_check = [c for c in ["Kenderaan", "No. Pendaftaran", "Road Tax Expiry", "Insurance Expiry", "Puspakom Expiry"] if c in df.columns]
    master_fleet = df[cols_to_check].drop_duplicates(subset=["No. Pendaftaran"])

    comp_col1, comp_col2, comp_col3 = st.columns(3)

    with comp_col1:
        st.markdown("#### 🚗 Road Tax")
        if "Road Tax Expiry" in master_fleet.columns:
            for _, row in master_fleet.iterrows():
                if pd.notnull(row["Road Tax Expiry"]):
                    days_left = (row["Road Tax Expiry"] - today).days
                    plate = row["No. Pendaftaran"]
                    vehicle = row["Kenderaan"] if "Kenderaan" in row else ""
                    if days_left < 0:
                        st.error(f"🔴 **{plate}** ({vehicle}) - TAMAT ({abs(days_left)} hari lepas)")
                    elif days_left <= 30:
                        st.warning(f"🟡 **{plate}** ({vehicle}) - {days_left} hari lagi!")
                    else:
                        st.success(f"🟢 **{plate}** ({vehicle}) - Sah")

    with comp_col2:
        st.markdown("#### 🛡️ Insurance")
        if "Insurance Expiry" in master_fleet.columns:
            for _, row in master_fleet.iterrows():
                if pd.notnull(row["Insurance Expiry"]):
                    days_left = (row["Insurance Expiry"] - today).days
                    plate = row["No. Pendaftaran"]
                    vehicle = row["Kenderaan"] if "Kenderaan" in row else ""
                    if days_left < 0:
                        st.error(f"🔴 **{plate}** ({vehicle}) - TAMAT!")
                    elif days_left <= 30:
                        st.warning(f"🟡 **{plate}** ({vehicle}) - {days_left} hari lagi")
                    else:
                        st.success(f"🟢 **{plate}** ({vehicle}) - Sah")

    with comp_col3:
        st.markdown("#### 🚛 Puspakom")
        if "Puspakom Expiry" in master_fleet.columns:
            for _, row in master_fleet.iterrows():
                if pd.notnull(row["Puspakom Expiry"]):
                    days_left = (row["Puspakom Expiry"] - today).days
                    plate = row["No. Pendaftaran"]
                    vehicle = row["Kenderaan"] if "Kenderaan" in row else ""
                    if days_left < 0:
                        st.error(f"🔴 **{plate}** ({vehicle}) - TAMAT")
                    elif days_left <= 30:
                        st.warning(f"🟡 **{plate}** ({vehicle}) - {days_left} hari lagi")
                    else:
                        st.success(f"🟢 **{plate}** ({vehicle}) - Sah")
