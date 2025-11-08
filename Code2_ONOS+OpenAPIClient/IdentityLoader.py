#################################################################################################################Imports
###OpenAPI Client
from openapi_client_1.api_client import ApiClient
from openapi_client_1.configuration import Configuration
from openapi_client_1.exceptions import ApiException
from openapi_client_1.exceptions import OpenApiException

###Entity/Attribute Models
from openapi_client_1.models.yang_identity import YANGIdentity
from openapi_client_1.models.creation_record import CreationRecord
from openapi_client_1.models.modification_record import ModificationRecord
from openapi_client_1.models.observation_record import ObservationRecord

###Utilities
import json
from datetime import datetime, timezone
from typing import Dict, Any, List

########################################################################################################Global Variables
CONTEXT_BROKER_URL="http://localhost:9091/ngsi-ld/v1" #Scorpio Context Broker URL
FILE_PATH='/home/francesco2/Documenti/Thesis_2025/NGSI-LD/Network_+_Interface/version15_10/YANGIdentities.json' #file containing Entities' payload

CONTEXT_URLS=["http://localhost:3004/mobile-radio-network-context.jsonld",
              "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.9.jsonld"] #Context Files to interpret NGSI-LD Data

NGSI_LD_CONTEXT_LINK_REL='rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'

CREATE_ENTITY_RESPONSE_MAP = { '201': None,
                               '4XX': 'str',
                               '5XX': 'str' } #response status map for a create entity request

DATASET_ID="urn:ngsi-ld:DatasetId:Config"

###############################################################################################################Functions
'''API Call to context broker to create an entity
   @param ApiClient api_client (client <-> server communication object with Context Broker)
   @param dict<str,any> entity_body (create request payload)'''
def create_entity(api_client: ApiClient, entity_body: Dict[str, Any]) -> None:
    global CREATE_ENTITY_RESPONSE_MAP

    method='POST' #HTTP operation for creating entities
    url=f"{api_client.configuration.host}/entities" #endpoint for entities creation

    headers={ 'Content-Type': 'application/ld+json'} #headers of the create request

    try:
        #Executing create request
        raw_response=api_client.call_api(method, url, header_params=headers, body=entity_body)

        raw_response.read()
        print("Raw Response Object -->", raw_response.response)
        print("'--> Class:", type(raw_response))
        print("'--> Raw Response Status:", raw_response.status)
        print("'--> Raw Response Payload:", raw_response.data)
        print("'--> Raw Response Reason:", raw_response.reason)
        print('\n')

        response=api_client.response_deserialize(response_data=raw_response, response_types_map=CREATE_ENTITY_RESPONSE_MAP)

        if 200 <= response.status_code < 300:  # expected response status is "201 Created"
            print(f"✅ Success: Entity '{entity_body.get('id')}' created (Status: {response.status_code})\n")

    except ApiException as e:
        print(f"❌ API error while uploading '{entity_body.get('id')}': {e}\n")
    except Exception as e:
        print(f"❌ Unexpected error: {e}\n")

'''Loading entities of type YANGIdentity from .json file to Context Broker
   @param str file_path
   @param str context_broker_url'''
def load_identities(file_path: str, context_broker_url: str) -> None:
    global CONTEXT_BROKER_URL, NGSI_LD_CONTEXT_LINK_REL, DATASET_ID

    #API client configuration
    config=Configuration(host=context_broker_url)
    api_client=ApiClient(config)

    print(f"Uploading entities on: {context_broker_url}")
    print("-"*50+"\n")

    ###Temporal Metadata (NGSI-LD Properties)
    current_timestamp=datetime.now(tz=timezone.utc)
    iso_timestamp=current_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') #ISO 8601 string format for date-time values

    creation_record_instance=CreationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    modification_record_instance=ModificationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    observation_record_instance=ObservationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)

    try:
        with open(file_path, 'r', encoding='utf-8') as f: #reading content of .json file
            entities_json_list: List[Dict[str, Any]]=json.load(f)

        print(f"Found {len(entities_json_list)} entities to upload\n")

        for entity_data in entities_json_list:
            try:
                yang_identity_model=YANGIdentity.from_dict(entity_data) #create entity object from data

                #Add metadata to entity object and its attributes
                yang_identity_model.yang_identity_namespace.observed_at=current_timestamp
                yang_identity_model.yang_identity_description.observed_at=current_timestamp
                yang_identity_model.yang_identity_identifier.observed_at=current_timestamp

                yang_identity_model.yang_identity_namespace.dataset_id=DATASET_ID
                yang_identity_model.yang_identity_description.dataset_id=DATASET_ID
                yang_identity_model.yang_identity_identifier.dataset_id=DATASET_ID

                if yang_identity_model.yang_identity_broader: #if a relationship to a parent YANG identity is present
                    yang_identity_model.yang_identity_broader.observed_at=current_timestamp
                    yang_identity_model.yang_identity_broader.dataset_id=DATASET_ID

                yang_identity_model.creation_record=creation_record_instance
                yang_identity_model.modification_record=modification_record_instance
                yang_identity_model.observation_record=observation_record_instance

                entity_body_dict=yang_identity_model.to_dict() #convert entity object into dict<str,any> for serialization

                #Add NGSI-LD context to payload
                entity_body_dict["@context"]=["http://localhost:3004/mobile-radio-network-context.jsonld",
                                              "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context.jsonld"]

                sanitized_body=api_client.sanitize_for_serialization(entity_body_dict)

                #print(f'{type(sanitized_body)} --> {sanitized_body}\n')
                create_entity(api_client, sanitized_body)

            except Exception as model_error:
                entity_id=entity_data.get('id', 'Unknown ID')
                print(f"⚠️ Validation/serialization error for '{entity_id}': {model_error}\n")

    except FileNotFoundError:
        print(f"Error: File not found at '{file_path}'\n")
    except json.JSONDecodeError:
        print(f"Error: Cannot decode file '{file_path}'\n")
    except OpenApiException as e:
        print(f"Serialization error: {e}\n")
    except Exception as e:
        print(f"Error while reading file or initializing API client: {e}\n")

    print("-"*50)
    print("Upload Completed\n")

####################################################################################################################Main
if __name__ == "__main__":
    load_identities(FILE_PATH, CONTEXT_BROKER_URL)