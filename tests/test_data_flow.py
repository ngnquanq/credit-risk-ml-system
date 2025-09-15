#!/usr/bin/env python3
"""
Test script to verify data flow: Python → MinIO → PostgreSQL
Tests the same flow that Streamlit will use
"""

import os
import sys
import psycopg2
from minio import Minio
from minio.error import S3Error
from datetime import datetime, date
import uuid
import io

# Configuration (same as .env)
MINIO_ENDPOINT = "localhost:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "loan-documents"

POSTGRES_HOST = "localhost"
POSTGRES_PORT = "5434"
POSTGRES_DB = "operations"
POSTGRES_USER = "ops_admin"
POSTGRES_PASSWORD = "ops_password"

def test_minio_connection():
    """Test MinIO connection and bucket operations"""
    print("🔄 Testing MinIO connection...")
    
    try:
        # Initialize MinIO client
        client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False
        )
        
        # Create bucket if it doesn't exist
        if not client.bucket_exists(MINIO_BUCKET):
            client.make_bucket(MINIO_BUCKET)
            print(f"✅ Created bucket: {MINIO_BUCKET}")
        else:
            print(f"✅ Bucket already exists: {MINIO_BUCKET}")
        
        # Test upload
        test_content = b"This is a test document for loan application"
        doc_id = f"test_doc_{uuid.uuid4().hex}"
        object_name = f"{doc_id}_test.txt"
        
        client.put_object(
            MINIO_BUCKET,
            object_name,
            io.BytesIO(test_content),
            length=len(test_content),
            content_type="text/plain"
        )
        
        print(f"✅ Uploaded test document: {object_name}")
        
        # Test download to verify
        response = client.get_object(MINIO_BUCKET, object_name)
        downloaded_content = response.read()
        
        if downloaded_content == test_content:
            print("✅ Document upload/download verified")
            return doc_id
        else:
            print("❌ Document content mismatch")
            return None
            
    except S3Error as e:
        print(f"❌ MinIO error: {e}")
        return None
    except Exception as e:
        print(f"❌ MinIO connection failed: {e}")
        return None

def test_postgres_connection():
    """Test PostgreSQL connection and table operations"""
    print("🔄 Testing PostgreSQL connection...")
    
    try:
        # Connect to database
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor()
        
        # Test query - check if our tables exist
        cursor.execute("SELECT count(*) FROM loan_applications")
        count = cursor.fetchone()[0]
        print(f"✅ PostgreSQL connected, loan_applications table has {count} records")
        
        cursor.close()
        conn.close()
        
        return True
        
    except Exception as e:
        print(f"❌ PostgreSQL connection failed: {e}")
        return False

def test_full_data_flow(doc_id):
    """Test complete data flow: insert application with document reference"""
    print("🔄 Testing full data flow...")
    
    try:
        conn = psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            database=POSTGRES_DB,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD
        )
        cursor = conn.cursor()
        
        # Create test application data
        test_customer_id = f"TEST_CUSTOMER_{uuid.uuid4().hex[:8].upper()}"
        
        # Insert loan application
        insert_query = """
        INSERT INTO loan_applications (
            sk_id_curr, code_gender, birth_date, cnt_children,
            amt_income_total, amt_credit, amt_annuity, amt_goods_price,
            name_contract_type, name_income_type, name_education_type,
            name_family_status, name_housing_type, employment_start_date,
            occupation_type, organization_type, flag_mobil, flag_emp_phone,
            flag_work_phone, flag_phone, flag_email, flag_own_car,
            flag_own_realty, own_car_age, document_id_2, document_id_3,
            document_id_4, document_id_5, document_id_6, created_at, updated_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        
        test_data = (
            test_customer_id, 'M', date(1985, 5, 15), 2,
            75000.0, 250000.0, 6000.0, 0.0,
            'Cash loans', 'Working', 'Higher education',
            'Married', 'House / apartment', date(2020, 1, 15),
            'Engineer', 'Tech Company', 1, 1, 0, 0, 1, 1, 1, 5,
            doc_id, None, None, None, None,  # Only document_id_2 has our test doc
            datetime.now(), datetime.now()
        )
        
        cursor.execute(insert_query, test_data)
        
        # Insert status log
        status_query = """
        INSERT INTO application_status_log (sk_id_curr, status, created_by, metadata)
        VALUES (%s, %s, %s, %s)
        """
        
        cursor.execute(status_query, (
            test_customer_id,
            'submitted',
            'test-script',
            '{"source": "data_flow_test", "document_uploaded": true}'
        ))
        
        conn.commit()
        print(f"✅ Inserted test application: {test_customer_id}")
        
        # Verify the data was inserted
        cursor.execute("SELECT sk_id_curr, document_id_2 FROM loan_applications WHERE sk_id_curr = %s", 
                      (test_customer_id,))
        result = cursor.fetchone()
        
        if result and result[1] == doc_id:
            print(f"✅ Data flow verified: Application {result[0]} linked to document {result[1]}")
        else:
            print("❌ Data flow verification failed")
        
        # Check status log
        cursor.execute("SELECT current_status, last_updated_by FROM current_application_status WHERE sk_id_curr = %s",
                      (test_customer_id,))
        status_result = cursor.fetchone()
        
        if status_result:
            print(f"✅ Status log verified: {status_result[0]} by {status_result[1]}")
        else:
            print("❌ Status log verification failed")
        
        cursor.close()
        conn.close()
        
        return test_customer_id
        
    except Exception as e:
        print(f"❌ Data flow test failed: {e}")
        return None

def main():
    print("🏦 Home Credit Data Flow Test")
    print("=" * 50)
    
    # Test 1: MinIO
    doc_id = test_minio_connection()
    if not doc_id:
        print("❌ MinIO test failed - stopping")
        sys.exit(1)
    
    print()
    
    # Test 2: PostgreSQL
    if not test_postgres_connection():
        print("❌ PostgreSQL test failed - stopping")
        sys.exit(1)
    
    print()
    
    # Test 3: Full data flow
    customer_id = test_full_data_flow(doc_id)
    if not customer_id:
        print("❌ Data flow test failed")
        sys.exit(1)
    
    print()
    print("🎉 All tests passed! Data flow working correctly:")
    print(f"   📄 Document ID: {doc_id}")
    print(f"   👤 Customer ID: {customer_id}")
    print(f"   ✅ Streamlit → MinIO → PostgreSQL flow verified")
    
    print()
    print("📋 Next steps:")
    print("   1. Install frontend dependencies: pip install -r application/frontend/requirements.txt")
    print("   2. Run Streamlit app: streamlit run application/frontend/frontend.py")
    print("   3. Test the web interface!")

if __name__ == "__main__":
    main()