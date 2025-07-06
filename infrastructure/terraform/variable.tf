variable "project_id" { default = "global-phalanx-449403-d2"}
variable "region"  { default = "us-central1" }
variable "zone"    { default = "us-central1-a" }

variable "vm_name"      { default = "credit-risk-modeling" }
variable "machine_type" { default = "e2-medium" }  # free-tier eligible
variable "gke_name"     { default = "application-gke" }
variable "data_proc_name" { default = "data-processing-cluster" }
variable "bucket_name" { default = "credit-risk-modeling-bucket" }
