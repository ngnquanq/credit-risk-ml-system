import os
from google.cloud import storage

def upload_csv_files_to_gcs(bucket_name, source_directory, destination_prefix="raw_data/"):
    """
    Uploads all CSV files from a local directory to a specified GCS bucket.

    Args:
        bucket_name (str): The name of the GCS bucket.
        source_directory (str): The local directory containing the CSV files.
        destination_prefix (str): The GCS prefix (folder path) where files will be uploaded.
                                  Defaults to "raw_data/".
    """
    client = storage.Client()
    bucket = client.bucket(bucket_name)

    print(f"Starting upload of CSV files from '{source_directory}' to 'gs://{bucket_name}/{destination_prefix}'...")

    if not os.path.exists(source_directory):
        print(f"Error: Source directory '{source_directory}' does not exist.")
        return

    uploaded_count = 0
    for root, _, files in os.walk(source_directory):
        for filename in files:
            if filename.endswith(".csv"):
                local_file_path = os.path.join(root, filename)
                # Determine the GCS blob name, preserving subdirectories if any
                # The relative_path will be "filename.csv" if source_directory is 'data',
                # or "subdir/filename.csv" if 'data' has subdirs.
                relative_path = os.path.relpath(local_file_path, source_directory)
                gcs_blob_name = os.path.join(destination_prefix, relative_path).replace("\\", "/") # Ensure forward slashes for GCS

                blob = bucket.blob(gcs_blob_name)

                try:
                    blob.upload_from_filename(local_file_path)
                    print(f"Uploaded: '{local_file_path}' to 'gs://{bucket_name}/{gcs_blob_name}'")
                    uploaded_count += 1
                except Exception as e:
                    print(f"Failed to upload '{local_file_path}': {e}")

    if uploaded_count > 0:
        print(f"\nSuccessfully uploaded {uploaded_count} CSV file(s) to gs://{bucket_name}/{destination_prefix}.")
    else:
        print("\nNo CSV files found or uploaded.")

if __name__ == "__main__":
    # Your actual bucket name from Terraform
    your_gcs_bucket_name = "credit-risk-modeling-bucket" # Keep this as your actual bucket name

    # The source_directory is now explicitly 'data' because that's where your CSVs are.
    # This path is relative to the directory from which you *execute* this script.
    # If you run from the project root, 'data/' is correct.
    source_data_folder = "data"

    upload_csv_files_to_gcs(your_gcs_bucket_name, source_directory=source_data_folder)