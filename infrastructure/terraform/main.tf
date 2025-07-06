# 1. Enable necessary Google Cloud APIs
resource "google_project_service" "apis" {
  for_each = toset([
    "compute.googleapis.com",
    "dataproc.googleapis.com",
    "storage.googleapis.com",
  ])
  project = var.project_id
  service = each.key
  disable_on_destroy = false # Keep APIs enabled after terraform destroy
}

# 2. Create a GCS bucket for Dataproc staging and notebooks
resource "google_storage_bucket" "dataproc_bucket" {
  project       = var.project_id
  name          = var.bucket_name
  location      = var.region
  force_destroy = true # Allows deletion of non-empty bucket
  uniform_bucket_level_access = true

  depends_on = [
    google_project_service.apis["storage.googleapis.com"]
  ]
}

# 3. Create a Dataproc Cluster with Jupyter
resource "google_dataproc_cluster" "dataproc_cluster" {
  project = var.project_id
  name    = var.data_proc_name
  region  = var.region

  cluster_config {
    staging_bucket = google_storage_bucket.dataproc_bucket.name

    gce_cluster_config {
      zone               = var.zone
      # Using default network for simplicity, consider custom VPC for production
      service_account_scopes = [
        "https://www.googleapis.com/auth/cloud-platform",
      ]
    }

    master_config {
      num_instances = 1
      machine_type  = var.machine_type
      disk_config {
        boot_disk_type    = "pd-ssd"
        boot_disk_size_gb = 50
      }
    }

    worker_config {
      num_instances = 2
      machine_type  = var.machine_type
      disk_config {
        boot_disk_type    = "pd-ssd"
        boot_disk_size_gb = 50
      }
    }

    software_config {
      image_version = "2.1-debian11"
      override_properties = {
        "dataproc:jupyter.notebook.gcs.dir" = "gs://${google_storage_bucket.dataproc_bucket.name}/jupyter-notebooks"
      }
      optional_components = ["JUPYTER"] # Install Jupyter
    }

    endpoint_config {
      enable_http_port_access = true # Enable Component Gateway for web access
    }
  }

  depends_on = [
    google_project_service.apis["dataproc.googleapis.com"]
  ]
}