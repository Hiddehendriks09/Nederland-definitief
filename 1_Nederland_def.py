import streamlit as st
import pandas as pd
import io

def clean_csv(file):
    lines = file.getvalue().decode("utf-8", errors="replace").splitlines()
    cleaned_lines = [line.strip().strip('"') for line in lines]
    return "\n".join(cleaned_lines)

def to_float_eu(series: pd.Series) -> pd.Series:
    """
    Robust EU-decimal parser:
    - handles '15,0', '8,5%', ' 7,0 ', etc.
    - returns float (NaN if not parseable)
    """
    s = series.astype(str)
    s = s.str.replace("%", "", regex=False)
    s = s.str.replace("\u00a0", " ", regex=False)  # NBSP -> space
    s = s.str.replace(",", ".", regex=False)
    s = s.str.replace(r"[^0-9.\-]+", "", regex=True)  # keep digits/dot/minus
    s = s.str.strip()
    return pd.to_numeric(s, errors="coerce")

def process_files(main_file, reference_file, start_date, end_date):
    # --- Load main data file ---
    try:
        main_file.seek(0)
    except Exception:
        pass

    data = pd.read_csv(main_file, dtype=str)
    if "Fulfillment Status" in data.columns:
        data = data[data["Fulfillment Status"] != "restocked"]  # gecancelde/restocked orders weg

    # Renaming columns and preparing the data
    data = data.rename(columns={"Lineitem sku": "SKU"})
    data["SKU"] = data["SKU"].astype(str).str.replace(r"(-\d+|[A-Z])$", "", regex=True)

    # --- Load reference data file ---
    reference_file_content = clean_csv(reference_file)
    check = pd.read_csv(io.StringIO(reference_file_content), dtype=str).drop_duplicates()

    # Merging data with reference data
    data = pd.merge(data, check[["SKU", "Alcohol Percentage"]], on="SKU", how="left")

    # Alcohol Percentage -> numeric (for comparisons)
    data["Alcohol Percentage"] = to_float_eu(data["Alcohol Percentage"])

    # Filling missing data
    for col in ["Fulfilled at", "Billing Country", "Billing Name", "Billing Street"]:
        if col in data.columns:
            data[col] = data[col].ffill()

    # Filtering data for specific conditions
    df = data[~data["Billing Country"].isin(["NL", "FR"])]

    selected_columns = [
        "Name",
        "Created at",
        "Fulfilled at",
        "Lineitem quantity",
        "Lineitem name",
        "Billing Name",
        "Billing Street",
        "Alcohol Percentage",
        "Billing Country",
    ]
    new_df = df[selected_columns].copy()

    new_df = new_df.rename(
        columns={
            "Name": "Invoice/order",
            "Created at": "Invoice date",
            "Fulfilled at": "Delivery date",
            "Lineitem name": "Product name",
            "Lineitem quantity": "Number of sold items",
            "Billing Name": "Name of client",
            "Billing Street": "Address details",
            "Billing Country": "Country",
        }
    )

    # Remove timezone offset and then convert to datetime
    new_df["Invoice date"] = pd.to_datetime(
        new_df["Invoice date"].astype(str).str.slice(0, 19), errors="coerce"
    )
    new_df["Delivery date"] = pd.to_datetime(
        new_df["Delivery date"].astype(str).str.slice(0, 19), errors="coerce"
    )

    # Numeric conversions needed for calculations
    new_df["Number of sold items"] = pd.to_numeric(new_df["Number of sold items"], errors="coerce").fillna(0)

    new_df["Plato percentage"] = 0

    # Last number in product name -> Content (e.g. ml)
    new_df["Content"] = pd.to_numeric(
        new_df["Product name"].astype(str).str.extract(r"(\d+)(?!.*\d)")[0],
        errors="coerce"
    )

    new_df["Total content"] = new_df["Content"] * new_df["Number of sold items"]

    # Date filtering
    filtered_df = new_df[
        (new_df["Delivery date"] >= start_date) & (new_df["Delivery date"] <= end_date)
    ].copy()

    final_cols = [
        "Invoice/order",
        "Invoice date",
        "Delivery date",
        "Name of client",
        "Address details",
        "Product name",
        "Number of sold items",
        "Content",
        "Total content",
        "Alcohol Percentage",
        "Plato percentage",
        "Country",
    ]
    final_data = filtered_df[final_cols].drop_duplicates().copy()

    # Sums by alcohol threshold
    total_content_sum_lower = final_data.loc[final_data["Alcohol Percentage"] <= 8.5, "Total content"].sum(skipna=True)
    total_content_sum_higher = final_data.loc[final_data["Alcohol Percentage"] > 8.5, "Total content"].sum(skipna=True)

    # Summary rows (same columns as final_data)
    summary_rows = pd.DataFrame({
        "Invoice/order": ["Total Content <= 8.5%", "Total Content > 8.5%"],
        "Total content": [total_content_sum_lower / 1000, total_content_sum_higher / 1000],
    })
    for c in final_data.columns:
        if c not in summary_rows.columns:
            summary_rows[c] = pd.NA
    summary_rows = summary_rows[final_data.columns]

    # Put summary at the top
    final_data = pd.concat([summary_rows, final_data], ignore_index=True)

    # --- Ensure decimal separator is '.' in the final output (as text) ---
    # This forces display with '.' even if the source had commas.
    # (Note: storing as text means Excel will treat it as text unless you convert back.)
    final_data["Alcohol Percentage"] = final_data["Alcohol Percentage"].map(
        lambda x: "" if pd.isna(x) else f"{float(x):.1f}"
    )

    return final_data


st.title("Accijnsaangifte Nederland")

uploaded_file = st.file_uploader("Importeer de csv file van shopify", type=["csv"])
reference_file = st.file_uploader("Importeer de referentie csv file", type=["csv"])
start_time = st.text_input("Start datum in format: (YYYY-MM-DD HH:MM:SS)")
end_time = st.text_input("Eind datum in format: (YYYY-MM-DD HH:MM:SS)")

if st.button("Download bestand"):
    if uploaded_file is not None and reference_file is not None and start_time and end_time:
        try:
            start_time_dt = pd.to_datetime(start_time)
            end_time_dt = pd.to_datetime(end_time)

            result_df = process_files(uploaded_file, reference_file, start_time_dt, end_time_dt)
            st.write(result_df)

            towrite = io.BytesIO()
            result_df.to_excel(towrite, index=False, engine="openpyxl")
            towrite.seek(0)

            formatted_start_time = start_time_dt.strftime("%Y%m%d")
            formatted_end_time = end_time_dt.strftime("%Y%m%d")
            file_name = f"NL_VINIOWIJNIMPORT_{formatted_start_time}_to_{formatted_end_time}.xlsx"

            st.download_button(
                label="Download Excel file",
                data=towrite,
                file_name=file_name,
                mime="application/vnd.ms-excel",
            )
        except ValueError as e:
            st.error(f"Error in date format: {e}")
    else:
        st.error("Please upload both files and specify the date range to continue.")
