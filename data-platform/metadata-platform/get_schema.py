import requests
import json

def get_full_dataset_metadata_from_datahub(dataset_urn, datahub_gms_url="http://localhost:8080/api/graphql"):
    """
    Queries DataHub's GraphQL API to retrieve comprehensive metadata for a dataset,
    including descriptions and profile statistics.
    """
    query = """
    query getFullDatasetMetadata($urn: String!) {
      dataset(urn: $urn) {
        urn
        properties {
          name
          description # Dataset description from source properties (e.g., table comment)
        }
        editableProperties {
          description # User-edited dataset description from DataHub UI
        }
        schemaMetadata {
          fields {
            fieldPath       # Column name
            type            # DataHub's logical type (e.g., STRING, NUMBER)
            nativeDataType  # Original database type (e.g., VARCHAR, INT)
            nullable
            description     # Column description
          }
        }
        datasetProfile { # Requires data profiling ingestion to be run
          rowCount
          columnCount
          fieldProfiles {
            fieldPath
            nullCount
            nullProportion
            distinctCount
            distinctProportion
            min
            max
            mean
            stDev
            sampleValues
            # Add other stats if needed from https://datahubproject.io/docs/graphql/objects/#fieldprofile
          }
        }
        # You can add other aspects like tags, ownership etc., if needed for your LLM
        # globalTags { tags { tag { name } } }
        # ownership { owners { owner { urn properties { email } } } }
      }
    }
    """
    variables = {"urn": dataset_urn}
    headers = {"Content-Type": "application/json"}

    try:
        print(f"Querying DataHub GMS at {datahub_gms_url} for full metadata of dataset: {dataset_urn}")
        response = requests.post(
            datahub_gms_url,
            headers=headers,
            json={"query": query, "variables": variables}
        )
        response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
        data = response.json()

        dataset_data = data.get("data", {}).get("dataset")
        if not dataset_data:
            print(f"Error: Dataset with URN '{dataset_urn}' not found or no data returned.")
            print(f"Full response: {json.dumps(data, indent=2)}")
            return None

        # Prepare the output dictionary
        output_metadata = {
            "urn": dataset_data.get("urn"),
            "table_name": dataset_data.get("properties", {}).get("name"),
            "description_from_source": dataset_data.get("properties", {}).get("description"),
            "description_from_datahub_ui": dataset_data.get("editableProperties", {}).get("description"),
            "columns": [],
            "profile_stats": {}
        }

        # Process columns
        schema_metadata = dataset_data.get("schemaMetadata")
        if schema_metadata and schema_metadata.get("fields"):
            for field in schema_metadata["fields"]:
                output_metadata["columns"].append({
                    "column_name": field.get("fieldPath"),
                    "data_type": field.get("nativeDataType"),
                    "description": field.get("description"),
                    "nullable": field.get("nullable")
                })

        # Process dataset profile stats
        dataset_profile = dataset_data.get("datasetProfile")
        if dataset_profile:
            output_metadata["profile_stats"]["rowCount"] = dataset_profile.get("rowCount")
            output_metadata["profile_stats"]["columnCount"] = dataset_profile.get("columnCount")
            output_metadata["profile_stats"]["column_profiles"] = []
            if dataset_profile.get("fieldProfiles"):
                for field_profile in dataset_profile["fieldProfiles"]:
                    output_metadata["profile_stats"]["column_profiles"].append({
                        "fieldPath": field_profile.get("fieldPath"),
                        "nullCount": field_profile.get("nullCount"),
                        "nullProportion": field_profile.get("nullProportion"),
                        "distinctCount": field_profile.get("distinctCount"),
                        "distinctProportion": field_profile.get("distinctProportion"),
                        "min": field_profile.get("min"),
                        "max": field_profile.get("max"),
                        "mean": field_profile.get("mean"),
                        "stDev": field_profile.get("stDev"),
                        "sampleValues": field_profile.get("sampleValues")
                    })
        else:
            print("Note: No dataset profile statistics found. Ensure you have run data profiling ingestion.")


        return output_metadata

    except requests.exceptions.RequestException as e:
        print(f"Error connecting to DataHub GMS: {e}")
        print(f"Ensure DataHub GMS is running and accessible at {datahub_gms_url}.")
        return None
    except json.JSONDecodeError:
        print(f"Error decoding JSON response from {datahub_gms_url}: {response.text}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

if __name__ == "__main__":
    # --- IMPORTANT: Replace with the actual URN of your ingested table ---
    # Find this URN in the DataHub UI. Example:
    my_dataset_urn = "urn:li:dataset:(urn:li:dataPlatform:postgres,homecredit.data.application_train,PROD)"

    # --- Adjust GMS URL based on where you run this Python script ---
    # If running this script on your HOST MACHINE:
    gms_url = "http://localhost:8080/api/graphql"
    # If running this script from INSIDE ANOTHER DOCKER CONTAINER:
    # gms_url = "http://datahub-gms:8080/api/graphql"

    full_metadata = get_full_dataset_metadata_from_datahub(my_dataset_urn, gms_url)

    if full_metadata:
        print("\n--- Full Ingested Metadata from DataHub (JSON) ---")
        print(json.dumps(full_metadata, indent=2))
        print("\n--- End of Metadata ---")
        print("\nYou can now copy and paste this JSON metadata into your LLM prompt.")
    else:
        print("Failed to retrieve full metadata from DataHub.")