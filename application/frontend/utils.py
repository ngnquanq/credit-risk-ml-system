import requests
import streamlit as st

# Support running as a package (streamlit run with PYTHONPATH) and as a script
try:  # Relative import when part of a package
    from .config import API_BASE_URL
except Exception:
    try:
        from config import API_BASE_URL  # Fallback for script execution
    except Exception:
        import os
        API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8001")


# API client functions
def get_presigned_url(document_type: int, file_extension: str, sk_id_curr: str):
    """Get pre-signed URL from API service."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/presigned-url",
            json={
                "document_type": document_type,
                "file_extension": file_extension,
                "sk_id_curr": sk_id_curr,
            },
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Failed to get upload URL: {e}")
        return None


def submit_application(application_data: dict):
    """Submit loan application to API service."""
    try:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/applications", json=application_data
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Failed to submit application: {e}")
        return None


def get_application_status(customer_id: str):
    """Get application status from API service."""
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/v1/applications/{customer_id}/status"
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as e:
        st.error(f"Failed to get application status: {e}")
        return None


def upload_file_to_presigned_url(presigned_url: str, file_content: bytes):
    """Upload file directly to MinIO using pre-signed URL.

    Returns a tuple: (success: bool, status_code: int | None)
    """
    try:
        response = requests.put(presigned_url, data=file_content)
        if 200 <= response.status_code < 300:
            return True, response.status_code
        return False, response.status_code
    except requests.RequestException as e:
        st.error(f"Failed to upload file: {e}")
        return False, None


def upload_document_via_api(
    file_data: bytes, filename: str, document_type: int, sk_id_curr: str
):
    """Upload document via API service using a pre-signed URL."""
    try:
        # Get file extension
        file_extension = filename.split(".")[-1] if "." in filename else "pdf"

        # Get pre-signed URL from API
        presigned_response = get_presigned_url(
            document_type, file_extension, sk_id_curr
        )
        if not presigned_response:
            return None

        # Upload file directly to MinIO using pre-signed URL
        success, status = upload_file_to_presigned_url(
            presigned_response["upload_url"], file_data
        )

        # If URL expired or signature invalid (403), refresh once and retry
        if not success and status == 403:
            retry_response = get_presigned_url(document_type, file_extension, sk_id_curr)
            if retry_response and retry_response.get("upload_url"):
                success2, status2 = upload_file_to_presigned_url(
                    retry_response["upload_url"], file_data
                )
                if success2:
                    return retry_response["document_id"]
                else:
                    st.error(
                        f"Upload failed after retry (status {status2}). Please try again."
                    )
                    return None

        if success:
            return presigned_response["document_id"]
        st.error(
            f"Upload failed (status {status}). If this persists, please reselect the file."
        )
        return None

    except Exception as e:
        st.error(f"Document upload failed: {e}")
        return None
