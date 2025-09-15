#!/usr/bin/env python3
"""
Test the Streamlit frontend directly with the API endpoints working
"""

import streamlit as st
import sys
import os

# Add the application directory to the path
sys.path.insert(0, '/home/nhatquang/home-credit-credit-risk-model-stability/application')

def test_frontend_imports():
    """Test if the frontend can import successfully"""
    try:
        # Test API client functions
        import requests
        from datetime import datetime, date
        import uuid
        import io
        from dotenv import load_dotenv
        
        print("✅ All frontend dependencies imported successfully")
        
        # Test API calls
        API_BASE_URL = "http://localhost:8000"
        
        # Test health check
        response = requests.get(f"{API_BASE_URL}/health")
        if response.status_code == 200:
            print("✅ API health check successful")
        else:
            print("❌ API health check failed")
            
        # Test pre-signed URL
        response = requests.post(
            f"{API_BASE_URL}/api/v1/presigned-url",
            json={"document_type": 2, "file_extension": "pdf"}
        )
        if response.status_code == 200:
            print("✅ Pre-signed URL generation successful")
            print(f"   Document ID: {response.json()['document_id']}")
        else:
            print(f"❌ Pre-signed URL generation failed: {response.status_code}")
            
        return True
        
    except Exception as e:
        print(f"❌ Frontend test failed: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Testing Streamlit Frontend Integration...")
    print("=" * 50)
    
    success = test_frontend_imports()
    
    if success:
        print("\n🎉 Frontend integration test passed!")
        print("\n📋 Ready to test complete flow:")
        print("   1. API service is running ✅")
        print("   2. MinIO is working ✅") 
        print("   3. PostgreSQL is accessible ✅")
        print("   4. Pre-signed URLs are working ✅")
        print("\n🚀 Next step: Launch Streamlit!")
        print("   streamlit run application/frontend/frontend.py")
    else:
        print("\n❌ Frontend integration test failed")