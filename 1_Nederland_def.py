import streamlit as st
import pandas as pd
import io

def clean_csv(file):
    lines = file.getvalue().decode('utf-8').splitlines()
    cleaned_lines = [line.strip().strip('"') for line in lines]
    return "\n".join(cleaned_lines)
    
def process_files(main_file, reference_file, start_date, end_date):
    # Load main data file
    data = pd.read_csv(main_file)
    data = data[data['Fulfillment Status'] != 'restocked'] #toegevoegd omdat gecancelde orders wegmoeten
    # Renaming columns and preparing the data
    data = data.rename(columns={"Lineitem sku": "SKU"})
    data['SKU'] = data['SKU'].str.replace(r"(-\d+|[A-Z])$", "", regex=True)
    
    # Load reference data file
    reference_file_content = clean_csv(reference_file)
    check = pd.read_csv(io.StringIO(reference_file_content))
    check = check.drop_duplicates()
    # Merging data with reference data
    data = pd.merge(data, check[['SKU', 'Alcohol Percentage']], on='SKU', how='left')
    
    # Filling missing data
    data['Fulfilled at'] = data['Fulfilled at'].ffill()
    data['Billing Country'] = data['Billing Country'].ffill()
    data['Billing Name'] = data['Billing Name'].ffill()
    data['Billing Street'] = data['Billing Street'].ffill()
    
    # Filtering data for specific conditions
    df = data[data['Billing Country'] != 'NL']
    selected_columns = ["Name", "Created at", "Fulfilled at", "Lineitem quantity", "Lineitem name", "Billing Name", "Billing Street", "Alcohol Percentage", "Billing Country"]
    new_df = df[selected_columns]
    new_df = new_df.rename(columns={"Name": "Invoice/order", "Created at": "Invoice date", "Fulfilled at": "Delivery date","Lineitem name": "Product name", "Lineitem quantity": "Number of sold items", "Billing Name": "Name of client", "Billing Street": "Address details", "Billing Country": "Country"  })
    
    # Remove timezone offset and then convert to datetime
    new_df['Invoice date'] = pd.to_datetime(new_df['Invoice date'].str.slice(0, 19), errors='coerce')
    new_df['Delivery date'] = pd.to_datetime(new_df['Delivery date'].str.slice(0, 19), errors='coerce')
    
    new_df["Plato percentage"] = 0
    #new_df['Last Part'] = new_df['Product name'].str.split().str[-2:].str.join(' ')
    new_df['Content'] = new_df['Product name'].str.extract(r'(\d+)(?!.*\d)').astype(float).astype('Int64')
    new_df["Total content"] = new_df["Content"]*new_df["Number of sold items"]

    filtered_df = new_df[(new_df['Delivery date'] >= start_date) & (new_df['Delivery date'] <= end_date)]
    final_data = filtered_df[['Invoice/order', 'Invoice date', 'Delivery date', 'Name of client', 'Address details', 'Product name', 'Number of sold items', 'Content', 'Total content', 'Alcohol Percentage', 'Plato percentage', 'Country']]
    final_data = final_data.drop_duplicates()

    total_content_sum_lower = final_data[final_data['Alcohol Percentage'] <= 8.5]['Total content'].sum()
    total_content_sum_higher = final_data[final_data['Alcohol Percentage'] > 8.5]['Total content'].sum()
    
    summary_df = pd.DataFrame({
        'Invoice/order': ['Total Content <= 8.5%', 'Total Content > 8.5%'],
        'Total Content': [total_content_sum_lower/1000, total_content_sum_higher/1000]
    })
    
    # Concatenate summary rows at the top of the final DataFrame
    final_data = pd.concat([final_data, summary_df], ignore_index=True)

    return final_data

st.title('Accijnsaangifte Nederland')

# File uploaders
uploaded_file = st.file_uploader("Importeer de csv file van shopify", type=['csv'])
reference_file = st.file_uploader("Importeer de referentie csv file", type=['csv'])
start_time = st.text_input("Start datum in format: (YYYY-MM-DD HH:MM:SS)")
end_time = st.text_input("Eind datum in format: (YYYY-MM-DD HH:MM:SS)")


if st.button('Download bestand'):
    if uploaded_file is not None and reference_file is not None and start_time and end_time:
        try:
            # Convert string dates to datetime objects
            start_time = pd.to_datetime(start_time)
            end_time = pd.to_datetime(end_time)
            
            # Process files with the specified date and time
            result_df = process_files(uploaded_file, reference_file, start_time, end_time)
            st.write(result_df)
            # Convert DataFrame to Excel in memory
            towrite = io.BytesIO()
            result_df.to_excel(towrite, index=False, engine='openpyxl')  # write to BytesIO buffer
            towrite.seek(0)  # rewind the buffer
            
            formatted_start_time = start_time.strftime('%Y%m%d')
            formatted_end_time = end_time.strftime('%Y%m%d')
            file_name = f"NL_VINIOWIJNIMPORT_{formatted_start_time}_to_{formatted_end_time}.xlsx"
            # Create a link to download the Excel file
            st.download_button(label="Download Excel file",
                               data=towrite,
                               file_name= file_name,
                               mime="application/vnd.ms-excel")
        except ValueError as e:
            st.error(f"Error in date format: {e}")
    else:
        st.error("Please upload both files and specify the date range to continue.")
