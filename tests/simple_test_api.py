#!/usr/bin/env python3
"""
Simplified test of the API functionality with minimal columns
"""

import requests
import json
from datetime import datetime
import psycopg2

API_BASE_URL = "http://localhost:8000"

# Test data
test_data = {
    "code_gender": "M",
    "birth_date": "1985-05-15",
    "cnt_children": 2,
    "amt_income_total": 75000.0,
    "amt_credit": 250000.0,
    "name_income_type": "Working",
    "name_education_type": "Higher education",
    "name_family_status": "Married",
    "name_housing_type": "House / apartment",
    "document_ids": {
        "document_id_2": "test_doc_123"
    }
}

def test_simple_insert():
    """Test direct database insert to understand the issue"""
    try:
        conn = psycopg2.connect(
            host="localhost", port="5434", database="operations",
            user="ops_admin", password="ops_password"
        )
        cursor = conn.cursor()
        
        # Simple insert with just required fields
        customer_id = f"TEST_{datetime.now().strftime('%H%M%S')}"
        
        cursor.execute("""
            INSERT INTO loan_applications (
                sk_id_curr, code_gender, birth_date, cnt_children,
                amt_income_total, amt_credit, name_income_type, 
                name_education_type, name_family_status, name_housing_type,
                created_at, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            customer_id, "M", "1985-05-15", 2,
            75000.0, 250000.0, "Working",
            "Higher education", "Married", "House / apartment",
            datetime.now(), datetime.now()
        ))
        
        conn.commit()
        print(f"✅ Direct database insert successful: {customer_id}")
        
        # Test status log
        cursor.execute("""
            INSERT INTO application_status_log (sk_id_curr, status, created_by, metadata)
            VALUES (%s, %s, %s, %s)
        """, (customer_id, "submitted", "test-script", "{}"))
        
        conn.commit()
        print(f"✅ Status log insert successful")
        
        cursor.close()
        conn.close()
        return customer_id
        
    except Exception as e:
        print(f"❌ Direct database test failed: {e}")
        return None

def test_api():
    """Test API call"""
    try:
        response = requests.post(f"{API_BASE_URL}/api/v1/applications", json=test_data)
        print(f"Response status: {response.status_code}")
        print(f"Response text: {response.text}")
        if response.status_code == 200:
            return response.json()
        else:
            return None
    except Exception as e:
        print(f"❌ API test failed: {e}")
        return None

if __name__ == "__main__":
    print("🔧 Testing simplified database operations...")
    
    # Test 1: Direct database insert
    db_result = test_simple_insert()
    
    print("\n" + "="*50 + "\n")
    
    # Test 2: API call
    api_result = test_api()
    
    if api_result:
        print(f"✅ API test successful: {api_result}")
    else:
        print("❌ API test failed")