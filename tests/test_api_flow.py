#!/usr/bin/env python3
"""
Test script for the complete API-based data flow:
Frontend → API Service → MinIO → PostgreSQL
"""

import requests
import json
from datetime import date

# Configuration
API_BASE_URL = "http://localhost:8000"
POSTGRES_HOST = "localhost"
POSTGRES_PORT = "5434"
POSTGRES_DB = "operations"
POSTGRES_USER = "ops_admin"
POSTGRES_PASSWORD = "ops_password"

def test_api_health():
    """Test API health endpoint"""
    print("🔄 Testing API health...")
    try:
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            print("✅ API is healthy")
            return True
        else:
            print(f"❌ API health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"❌ API health check failed: {e}")
        return False

def test_presigned_url():
    """Test pre-signed URL generation"""
    print("🔄 Testing pre-signed URL generation...")
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/presigned-url",
            json={
                "document_type": 2,
                "file_extension": "pdf"
            }
        )
        response.raise_for_status()
        data = response.json()
        print(f"✅ Pre-signed URL generated: {data['document_id']}")
        return data
    except Exception as e:
        print(f"❌ Pre-signed URL generation failed: {e}")
        return None

def test_document_upload(presigned_data):
    """Test document upload to MinIO"""
    print("🔄 Testing document upload...")
    try:
        # Create a test document
        test_content = b"This is a test PDF document for loan application"
        
        # Upload to MinIO using pre-signed URL
        response = requests.put(
            presigned_data['upload_url'],
            data=test_content
        )
        response.raise_for_status()
        print(f"✅ Document uploaded successfully: {presigned_data['document_id']}")
        return presigned_data['document_id']
    except Exception as e:
        print(f"❌ Document upload failed: {e}")
        return None

def test_loan_application_submission(document_id):
    """Test loan application submission"""
    print("🔄 Testing loan application submission...")
    try:
        application_data = {
            "code_gender": "M",
            "birth_date": "1985-05-15",
            "cnt_children": 2,
            "amt_income_total": 75000.0,
            "amt_credit": 250000.0,
            "amt_annuity": 6000.0,
            "amt_goods_price": 0.0,
            "name_contract_type": "Cash loans",
            "name_income_type": "Working",
            "name_education_type": "Higher education",
            "name_family_status": "Married",
            "name_housing_type": "House / apartment",
            "employment_start_date": "2020-01-15",
            "occupation_type": "Engineer",
            "organization_type": "Tech Company",
            "flag_mobil": 1,
            "flag_emp_phone": 1,
            "flag_work_phone": 0,
            "flag_phone": 0,
            "flag_email": 1,
            "flag_own_car": 1,
            "flag_own_realty": 1,
            "own_car_age": 5,
            "document_ids": {
                "document_id_2": document_id
            }
        }
        
        response = requests.post(
            f"{API_BASE_URL}/api/v1/applications",
            json=application_data
        )
        response.raise_for_status()
        data = response.json()
        print(f"✅ Loan application submitted: {data['customer_id']}")
        return data['customer_id']
    except Exception as e:
        print(f"❌ Loan application submission failed: {e}")
        return None

def test_application_status(customer_id):
    """Test application status retrieval"""
    print("🔄 Testing application status retrieval...")
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/applications/{customer_id}/status")
        response.raise_for_status()
        data = response.json()
        print(f"✅ Application status: {data['status']} by {data['updated_by']}")
        return True
    except Exception as e:
        print(f"❌ Application status retrieval failed: {e}")
        return False

def test_database_verification(customer_id):
    """Verify data in PostgreSQL directly"""
    print("🔄 Verifying data in PostgreSQL...")
    try:
        import psycopg2
        
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor()
        
        # Check loan application
        cursor.execute("SELECT sk_id_curr, code_gender, amt_income_total FROM loan_applications WHERE sk_id_curr = %s", (customer_id,))
        app_result = cursor.fetchone()
        
        if app_result:
            print(f"✅ Application found in database: {app_result[0]}, {app_result[1]}, ${app_result[2]:,.2f}")
        else:
            print("❌ Application not found in database")
            return False
            
        # Check status log
        cursor.execute("SELECT status, created_by FROM application_status_log WHERE sk_id_curr = %s ORDER BY created_at DESC LIMIT 1", (customer_id,))
        status_result = cursor.fetchone()
        
        if status_result:
            print(f"✅ Status log found: {status_result[0]} by {status_result[1]}")
        else:
            print("❌ Status log not found")
            return False
            
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database verification failed: {e}")
        return False

def main():
    print("🏦 Testing Complete API-Based Data Flow")
    print("=" * 50)
    
    # Test 1: API Health
    if not test_api_health():
        print("❌ API is not running. Please start the API service.")
        return
    
    print()
    
    # Test 2: Pre-signed URL
    presigned_data = test_presigned_url()
    if not presigned_data:
        print("❌ Pre-signed URL test failed")
        return
    
    print()
    
    # Test 3: Document Upload
    document_id = test_document_upload(presigned_data)
    if not document_id:
        print("❌ Document upload test failed")
        return
    
    print()
    
    # Test 4: Loan Application Submission
    customer_id = test_loan_application_submission(document_id)
    if not customer_id:
        print("❌ Loan application submission test failed")
        return
    
    print()
    
    # Test 5: Application Status
    if not test_application_status(customer_id):
        print("❌ Application status test failed")
        return
    
    print()
    
    # Test 6: Database Verification
    if not test_database_verification(customer_id):
        print("❌ Database verification test failed")
        return
    
    print()
    print("🎉 All API-based data flow tests passed!")
    print(f"   📄 Document ID: {document_id}")
    print(f"   👤 Customer ID: {customer_id}")
    print(f"   ✅ Frontend → API → MinIO → PostgreSQL flow verified")
    
    print()
    print("📋 Next steps:")
    print("   1. Start the Streamlit frontend: streamlit run application/frontend/frontend.py")
    print("   2. Test the complete web interface!")

if __name__ == "__main__":
    main()