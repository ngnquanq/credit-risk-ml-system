"""
Home Credit Loan Application Frontend
Streamlit app for loan applications with document upload
"""

import os
import sys
import streamlit as st
from datetime import date

# Support running as a package and as a standalone script
try:
    from .config import APP_NAME
    from .utils import (
        get_presigned_url,
        submit_application,
        get_application_status,
        upload_file_to_presigned_url,
        upload_document_via_api,
    )
except Exception:
    sys.path.append(os.path.dirname(__file__))
    from config import APP_NAME
    from utils import (
        get_presigned_url,
        submit_application,
        get_application_status,
        upload_file_to_presigned_url,
        upload_document_via_api,
    )

# No local config — imported from config.py for centralization


# Streamlit App
st.title(f"🏦 {APP_NAME}")
st.markdown("---")

# Application Form
with st.form("loan_application_form"):
    st.subheader("📋 Personal Information")
    
    col1, col2 = st.columns(2)
    
    with col1:
        customer_id = st.text_input("Customer ID")
        gender = st.selectbox("Gender", ["M", "F"])
        birth_date = st.date_input("Birth Date", min_value=date(1950, 1, 1), max_value=date(2005, 12, 31))
        children = st.number_input("Number of Children", min_value=0, max_value=10, value=0)
    
    with col2:
        income = st.number_input("Annual Income", min_value=0.0, value=50000.0, step=1000.0)
        credit_amount = st.number_input("Requested Loan Amount", min_value=0.0, value=200000.0, step=1000.0)
        annuity = st.number_input("Monthly Payment", min_value=0.0, value=5000.0, step=100.0)
        goods_price = st.number_input("Goods Price (if applicable)", min_value=0.0, value=0.0, step=1000.0)
    
    st.subheader("🎓 Employment & Personal Details")
    
    col3, col4 = st.columns(2)
    
    with col3:
        contract_type = st.selectbox("Contract Type", ["Cash loans", "Revolving loans"])
        income_type = st.selectbox("Income Type", [
            "Working", "Commercial associate", "Pensioner", 
            "State servant", "Student", "Businessman", "Maternity leave"
        ])
        education = st.selectbox("Education Level", [
            "Secondary / secondary special", "Higher education", 
            "Incomplete higher", "Lower secondary", "Academic degree"
        ])
        family_status = st.selectbox("Family Status", [
            "Single / not married", "Married", "Civil marriage", "Widow", "Separated"
        ])
    
    with col4:
        housing = st.selectbox("Housing Type", [
            "House / apartment", "Rented apartment", "With parents", 
            "Municipal apartment", "Office apartment", "Co-op apartment"
        ])
        employment_start = st.date_input("Employment Start Date", max_value=date.today())
        occupation = st.text_input("Occupation", value="")
        organization = st.text_input("Organization", value="")
    
    st.subheader("📱 Contact Information")
    
    col5, col6 = st.columns(2)
    
    with col5:
        has_mobile = st.checkbox("Has Mobile Phone", value=True)
        has_work_phone = st.checkbox("Has Work Phone", value=False)
        has_home_phone = st.checkbox("Has Home Phone", value=False)
    
    with col6:
        has_email = st.checkbox("Has Email", value=True)
        owns_car = st.checkbox("Owns Car", value=False)
        owns_realty = st.checkbox("Owns Real Estate", value=False)
        car_age = st.number_input("Car Age (years)", min_value=0, max_value=50, value=0) if owns_car else 0
    
    st.subheader("📄 Document Upload")
    st.markdown("Please upload the required documents:")
    
    # Primary documents (required)
    st.markdown("**Required Documents:**")
    col7, col8 = st.columns(2)
    
    with col7:
        doc_2 = st.file_uploader("Identity Document (Passport/ID)", type=['pdf', 'jpg', 'png'], key="doc_2")
        doc_3 = st.file_uploader("Income Proof", type=['pdf', 'jpg', 'png'], key="doc_3")
        doc_4 = st.file_uploader("Employment Certificate", type=['pdf', 'jpg', 'png'], key="doc_4")
    
    with col8:
        doc_5 = st.file_uploader("Bank Statement", type=['pdf', 'jpg', 'png'], key="doc_5")
        doc_6 = st.file_uploader("Utility Bills", type=['pdf', 'jpg', 'png'], key="doc_6")
    
    # Additional documents (optional)
    st.markdown("**Additional Documents (Optional):**")
    with st.expander("Additional Supporting Documents"):
        col9, col10 = st.columns(2)
        
        with col9:
            doc_7 = st.file_uploader("Property Ownership", type=['pdf', 'jpg', 'png'], key="doc_7")
            doc_8 = st.file_uploader("Vehicle Registration", type=['pdf', 'jpg', 'png'], key="doc_8")
            doc_9 = st.file_uploader("Insurance Policy", type=['pdf', 'jpg', 'png'], key="doc_9")
            doc_10 = st.file_uploader("Tax Returns", type=['pdf', 'jpg', 'png'], key="doc_10")
            doc_11 = st.file_uploader("Medical Certificate", type=['pdf', 'jpg', 'png'], key="doc_11")
            doc_12 = st.file_uploader("Education Certificate", type=['pdf', 'jpg', 'png'], key="doc_12")
            doc_13 = st.file_uploader("Marriage Certificate", type=['pdf', 'jpg', 'png'], key="doc_13")
            doc_14 = st.file_uploader("Divorce Certificate", type=['pdf', 'jpg', 'png'], key="doc_14")
        
        with col10:
            doc_15 = st.file_uploader("Birth Certificate", type=['pdf', 'jpg', 'png'], key="doc_15")
            doc_16 = st.file_uploader("Pension Certificate", type=['pdf', 'jpg', 'png'], key="doc_16")
            doc_17 = st.file_uploader("Military Service", type=['pdf', 'jpg', 'png'], key="doc_17")
            doc_18 = st.file_uploader("Business License", type=['pdf', 'jpg', 'png'], key="doc_18")
            doc_19 = st.file_uploader("Credit Report", type=['pdf', 'jpg', 'png'], key="doc_19")
            doc_20 = st.file_uploader("Reference Letter", type=['pdf', 'jpg', 'png'], key="doc_20")
            doc_21 = st.file_uploader("Other Supporting Document", type=['pdf', 'jpg', 'png'], key="doc_21")
    
    # Submit button
    submitted = st.form_submit_button("🚀 Submit Loan Application", type="primary")
    
    if submitted:
        if not customer_id or not customer_id.strip():
            st.error("❌ Customer ID is required. Please enter a Customer ID.")
        else:
            with st.spinner("Processing your application..."):
                # Upload documents via API using pre-signed URLs
                document_ids = {}
            
            # List of document variables with their types and names
            document_list = [
                (doc_2, 2, "Identity Document"),
                (doc_3, 3, "Income Proof"),
                (doc_4, 4, "Employment Certificate"),
                (doc_5, 5, "Bank Statement"),
                (doc_6, 6, "Utility Bills"),
                (doc_7, 7, "Property Ownership"),
                (doc_8, 8, "Vehicle Registration"),
                (doc_9, 9, "Insurance Policy"),
                (doc_10, 10, "Tax Returns"),
                (doc_11, 11, "Medical Certificate"),
                (doc_12, 12, "Education Certificate"),
                (doc_13, 13, "Marriage Certificate"),
                (doc_14, 14, "Divorce Certificate"),
                (doc_15, 15, "Birth Certificate"),
                (doc_16, 16, "Pension Certificate"),
                (doc_17, 17, "Military Service"),
                (doc_18, 18, "Business License"),
                (doc_19, 19, "Credit Report"),
                (doc_20, 20, "Reference Letter"),
                (doc_21, 21, "Other Supporting Document"),
            ]
            
            # Upload each document if provided
            for doc_file, doc_type, doc_name in document_list:
                if doc_file:
                    doc_uploaded = upload_document_via_api(
                        doc_file.getvalue(), doc_file.name, doc_type, customer_id
                    )
                    if doc_uploaded:
                        document_ids[f'document_id_{doc_type}'] = doc_uploaded
                    else:
                        st.warning(f"Failed to upload {doc_name}")
            
            # Prepare application data for API
            application_data = {
                "sk_id_curr": customer_id,
                "code_gender": gender,
                "birth_date": birth_date.strftime("%Y-%m-%d"),
                "cnt_children": children,
                "amt_income_total": float(income),
                "amt_credit": float(credit_amount),
                "amt_annuity": float(annuity) if annuity > 0 else None,
                "amt_goods_price": float(goods_price) if goods_price > 0 else None,
                "name_contract_type": contract_type,
                "name_income_type": income_type,
                "name_education_type": education,
                "name_family_status": family_status,
                "name_housing_type": housing,
                "employment_start_date": employment_start.strftime("%Y-%m-%d") if employment_start else None,
                "occupation_type": occupation if occupation.strip() else None,
                "organization_type": organization if organization.strip() else None,
                "flag_mobil": 1 if has_mobile else 0,
                "flag_emp_phone": 1 if has_work_phone else 0,
                "flag_work_phone": 1 if has_work_phone else 0,
                "flag_phone": 1 if has_home_phone else 0,
                "flag_email": 1 if has_email else 0,
                "flag_own_car": 1 if owns_car else 0,
                "flag_own_realty": 1 if owns_realty else 0,
                "own_car_age": int(car_age) if owns_car and car_age > 0 else None,
                "document_ids": document_ids if document_ids else {}
            }
            
            # Submit application via API
            result = submit_application(application_data)
            if result:
                st.success("✅ Loan application submitted successfully!")
                st.info(f"📋 Application ID: **{result['sk_id_curr']}**")
                
                if document_ids:
                    st.info("📄 Documents uploaded:")
                    for doc_type, doc_id in document_ids.items():
                        st.text(f"  • {doc_type}: {doc_id}")
                        
                # Store customer ID in session state for status checking
                st.session_state.customer_id = result['sk_id_curr']
            else:
                st.error("❌ Failed to submit application. Please try again.")

# Sidebar - Application Status Checker
st.sidebar.markdown("## 🔍 Check Application Status")

# Use session state customer ID if available
default_id = st.session_state.get('customer_id', '')
check_id = st.sidebar.text_input("Enter Application ID", value=default_id)

if st.sidebar.button("Check Status"):
    if check_id:
        status_result = get_application_status(check_id)
        if status_result:
            st.sidebar.success(f"Status: **{status_result['status']}**")
            st.sidebar.info(f"Updated: {status_result['updated_at']}")
            st.sidebar.info(f"By: {status_result['updated_by']}")
            if status_result.get('metadata'):
                st.sidebar.text(f"Details: {status_result['metadata']}")
        else:
            st.sidebar.error("Application not found or API error")

# Footer
st.markdown("---")
st.markdown("*Home Credit Loan Application System - Built with Streamlit*")
