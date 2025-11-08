"""This code test the main functionalities of an OpenAPI client to interact with FIWARE Context Broker
Usage: python Client_Test.py [--create-test] #Test the creation of model class instances (NGSI-LD entities within the client)
                             [--upload-test] #Test the creation of NGSI-LD entities on the context broker
                             [--get-test] #Test retrieving NGSI-LD entities from the context broker
                             [--update-test] #Test updating NGSI-LD entity data on the context broker"""

#################################################################################################################Imports
###OpenAPI Client
from openapi_client_1.api_client import ApiClient
from openapi_client_1.configuration import Configuration
from openapi_client_1.exceptions import ApiException
from openapi_client_1.exceptions import OpenApiException

###Entity/Attribute Models
from pydantic import BaseModel
from openapi_client_1.models.geometry_multi_point import GeometryMultiPoint
from openapi_client_1.models.geometry import Geometry
from openapi_client_1.models.geo_property import GeoProperty
from openapi_client_1.models.network import Network
from openapi_client_1.models.network_id import NetworkId
from openapi_client_1.models.network_types import NetworkTypes
from openapi_client_1.models.yang_identity import YANGIdentity
from openapi_client_1.models.yang_identity_identifier import YANGIdentityIdentifier
from openapi_client_1.models.yang_identity_namespace import YANGIdentityNamespace
from openapi_client_1.models.yang_identity_description import YANGIdentityDescription
from openapi_client_1.models.creation_record import CreationRecord
from openapi_client_1.models.modification_record import ModificationRecord
from openapi_client_1.models.observation_record import ObservationRecord

###Utilities
import sys
from datetime import datetime, timezone
from typing import Dict, Optional

########################################################################################################Global Variables
CONTEXT_BROKER_URL="http://localhost:9090/ngsi-ld/v1" #Scorpio Context Broker URL

CONTEXT_URLS=["http://localhost:3004/mobile-radio-network-context.jsonld",
              "https://uri.etsi.org/ngsi-ld/v1/ngsi-ld-core-context-v1.9.jsonld"] #Context Files to interpret NGSI-LD Data

NGSI_LD_CONTEXT_LINK_REL='rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"'

CREATE_ENTITY_RESPONSE_MAP = { '201': None,
                               '4XX': 'str',
                               '5XX': 'str' } #response status map for a create entity request

UPDATE_ENTITY_RESPONSE_MAP = { '204': None,
                               '4XX': 'str',
                               '5XX': 'str' } #response status map for an update entity request

###############################################################################################################Functions
'''Creating instances of model class YANGIdentity and model class Network, which represent NGSI-LD entities
   @return Dict[str, BaseModel] dictionary <entity_id, created_entity>'''
def create_entities() -> Dict[str, BaseModel]:
    entity_dict: Dict[str, BaseModel]={} #initialize dictionary

    ###Metadata
    current_timestamp=datetime.now(tz=timezone.utc)
    iso_timestamp=current_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') #ISO 8601 string format for date-time values
    dataset_id_value="urn:ngsi-ld:DatasetId:ONOS"
    dataset_id_value2="urn:ngsi-ld:DatasetId:Config"

    ###Temporal Metadata (NGSI-LD Properties)
    creation_record_instance=CreationRecord(type='Property', value=iso_timestamp, datasetId=dataset_id_value)
    modification_record_instance=ModificationRecord(type='Property', value=iso_timestamp, datasetId=dataset_id_value)
    observation_record_instance=ObservationRecord(type='Property', value=iso_timestamp, datasetId=dataset_id_value)

    ###YANGIdentity Entity
    yang_identity_identifier_instance=YANGIdentityIdentifier(type='Property', value="mobile-radio-network",
                                                             datasetId=dataset_id_value2, observedAt=current_timestamp) #property

    yang_identity_namespace_instance=YANGIdentityNamespace(type='Property', value="urn:unical:dimes:tlc:params:yml:ns:yang:mobile-radio-network",
                                                           datasetId=dataset_id_value2, observedAt=current_timestamp) #property

    yang_identity_description_instance=YANGIdentityDescription(type='Property', value="A network representing a mobile radio access network (RAN).",
                                                               datasetId=dataset_id_value2, observedAt=current_timestamp) #property

    yang_identity_instance=YANGIdentity(id="urn:ngsi-ld:YANGIdentity:mobile-radio-network:mobile-radio-network", type="YANGIdentity",
                                        YANGIdentityIdentifier=yang_identity_identifier_instance,
                                        YANGIdentityNamespace=yang_identity_namespace_instance,
                                        YANGIdentityDescription=yang_identity_description_instance,
                                        creationRecord=creation_record_instance,
                                        modificationRecord=modification_record_instance,
                                        observationRecord=observation_record_instance) #entity

    ###Network Entity (spatial metadata)
    test_coordinates=[ [12.4922, 41.8906], [12.4839, 41.8978] ]

    multi_point_instance=GeometryMultiPoint(type='MultiPoint', coordinates=test_coordinates)
    geometry_instance=Geometry(multi_point_instance)

    geo_property_instance=GeoProperty(type='GeoProperty', value=geometry_instance, datasetId=dataset_id_value, observedAt=current_timestamp) #property

    ###Network Entity
    network_id_instance=NetworkId(type='Property', value="VPN-A-101", datasetId=dataset_id_value, observedAt=current_timestamp) #property

    network_types_instance=NetworkTypes(type="Relationship", object=[yang_identity_instance.id],
                                        datasetId=dataset_id_value, observedAt=current_timestamp) #relationship

    network_instance=Network(id="urn:ngsi-ld:Network:001",
                             type="Network",
                             location=geo_property_instance,
                             networkId=network_id_instance,
                             networkTypes=network_types_instance,
                             creationRecord=creation_record_instance,
                             modificationRecord=modification_record_instance,
                             observationRecord=observation_record_instance) #entity

    ###Dictionary of all created entities
    entity_dict[yang_identity_instance.id]=yang_identity_instance
    entity_dict[network_instance.id]=network_instance
    return entity_dict

'''Function testing field-accessibility of created model instances
   @param Dict[str, BaseModel] dictionary <entity_id, entity_instance>'''
def test_print(entity_dict: Dict[str, BaseModel]):
    yang_identity=entity_dict["urn:ngsi-ld:YANGIdentity:mobile-radio-network:mobile-radio-network"]
    assert type(yang_identity) is YANGIdentity

    print(f'Entity {yang_identity.id} of type {yang_identity.type}')
    print(f'Class: {type(yang_identity).__name__}')
    print(f'Attribute {yang_identity.yang_identity_identifier}')
    print(f'Attribute {yang_identity.yang_identity_namespace}')
    print(f'Attribute {yang_identity.yang_identity_description}')
    print(f'Attribute {yang_identity.creation_record}')
    print(f'Attribute {yang_identity.modification_record}')
    print(f'Attribute {yang_identity.observation_record}\n')

    network=entity_dict["urn:ngsi-ld:Network:001"]
    assert type(network) is Network

    print(f'Entity {network.id} of type {network.type}')
    print(f'Class: {type(network).__name__}')
    print(f'Attribute {network.network_id}')
    print(f'Attribute {network.network_types}')
    print(f'Attribute {network.location}')
    print(f'Attribute {network.creation_record}')
    print(f'Attribute {network.modification_record}')
    print(f'Attribute {network.observation_record}\n')

'''Function testing serialization functions in model classes
   @param Dict[str, BaseModel] dictionary <entity_id, entity_instance>'''
def test_serialization(entity_dict: Dict[str, BaseModel]):
    yang_identity=entity_dict["urn:ngsi-ld:YANGIdentity:mobile-radio-network:mobile-radio-network"]
    assert type(yang_identity) is YANGIdentity

    print(f'Entity {yang_identity.id} of type {yang_identity.type}')
    print(f'Class {type(yang_identity).__name__} --> {yang_identity}')
    print(f'To Dict --> {yang_identity.to_dict()}') #serialize in Python Dict
    print(f'To JSON --> {yang_identity.to_json()}') #serialize in JSON string
    print(f'To String --> {yang_identity.to_str()}\n') #serialize in string

    network=entity_dict["urn:ngsi-ld:Network:001"]
    assert type(network) is Network

    print(f'Entity {network.id} of type {network.type}')
    print(f'Class {type(network).__name__} --> {network}')
    print(f'To Dict --> {network.to_dict()}') #serialize in Python Dict
    print(f'To JSON --> {network.to_json()}') #serialize in JSON string
    print(f'To String --> {network.to_str()}\n') #serialize in string

'''Function creating NGSI-LD entities by issuing POST requests on the Context Broker
   @param Dict[str, BaseModel] dictionary <entity_id, entity_to_post>
   @param ApiClient api_client (application-level interaction with the Context Broker)'''
def test_upload(entity_dict: Dict[str, BaseModel], api_client: ApiClient):
    global CREATE_ENTITY_RESPONSE_MAP, CONTEXT_URLS

    for id,entity in entity_dict.items():
        print(f'Entity {id} of type {entity.type}')
        print(f'Class {type(entity).__name__} --> {entity}\n')

        entity_body=None

        try: #Serialization
            entity_body=entity.to_dict()
            entity_body["@context"]=CONTEXT_URLS #add context references to jsonld payload

            print(f'Serialized payload --> {api_client.sanitize_for_serialization(entity_body)}\n')
        except OpenApiException as e:
            print(f"Serialization error: {e}\n")
        except Exception as e:
            print(f"Unexpected error: {e}\n")

        try:
            method='POST' #HTTP operation for creating entities
            url=f"{api_client.configuration.host}/entities"  #endpoint for entities creation

            headers={'Content-Type': 'application/ld+json'} #headers of the create request

            raw_response=api_client.call_api(method, url, header_params=headers,
                                             body=api_client.sanitize_for_serialization(entity_body)) #issue create request

            raw_response.read()
            print("Raw Response Object -->", raw_response.response)
            print("'--> Class:", type(raw_response))
            print("'--> Raw Response Status:", raw_response.status)
            print("'--> Raw Response Payload:", raw_response.data)
            print("'--> Raw Response Reason:", raw_response.reason)
            print('\n')

            response=api_client.response_deserialize(response_data=raw_response,
                                                     response_types_map=CREATE_ENTITY_RESPONSE_MAP) #de-serialize response

            if 200 <= response.status_code < 300: #expected response status is "201 Created"
                print(f"✅ Success: Entity '{entity_body.get('id')}' created (Status: {response.status_code})\n")

        except ApiException as e:
            print(f"❌ API error while uploading '{entity_body.get('id')}': {e}\n")
        except Exception as e:
            print(f"❌ Unexpected error: {e}\n")

'''Issues a GET request to Context Broker to fetch entities in key-value format, filtering by ID or type
   @param ApiClient api_client (application-level interaction with the Context Broker)
   @param str/None entity_type (entity type filter)
   @param str/None entity_id (entity id filter)
   @param int limit (output size limit)
   @return Dict[str, str]/List[Dict[str, str]]'''
def get_entities_key_values(api_client: ApiClient, entity_type: Optional[str]=None, entity_id: Optional[str]=None, limit: int=100):
    global CONTEXT_URLS, NGSI_LD_CONTEXT_LINK_REL

    #create Link header to reference context files
    link_parts=[]
    for url in CONTEXT_URLS:
        link_parts.append(f"<{url}>; {NGSI_LD_CONTEXT_LINK_REL}")

    headers={ 'Accept': 'application/json',
              'Link': ','.join(link_parts)} #headers of GET Request

    #define request URL and query params
    query_params={}
    if entity_id: #GET /entities/{entity_id}
        url=f"/entities/{entity_id}"

        get_entities_response_map = {'200': 'object',
                                     '4XX': 'object',
                                     '5XX': 'object'}  # response status map for a get entity request
    elif entity_type: #GET /entities?type={type}&limit={limit}
        url=f"/entities"
        query_params['type']=entity_type
        query_params['limit']=limit

        get_entities_response_map = {'200': 'List[object]',
                                     '4XX': 'object',
                                     '5XX': 'object'}  #response status map for a get entity request
    else:
        raise ValueError("Specify either 'entity_type' filter and/or 'entity_id' filter.\n")

    query_params['options']='keyValues'

    try: #Serialze request and prepare URL
        method, full_url, header_params, body, post_params=api_client.param_serialize(
            method='GET',
            resource_path=url,
            query_params=query_params,
            header_params=headers)

    except OpenApiException as e:
        print(f"Serialization error: {e}\n")
    except Exception as e:
        print(f"Unexpected error: {e}\n")

    try:
        raw_response=api_client.call_api(method, full_url, header_params=header_params)

        raw_response.read()
        print("'--> Class:", type(raw_response))
        print("'--> Raw Response Status:", raw_response.status)
        print("'--> Raw Response Headers:", raw_response.getheaders())
        print("'--> Raw Response Reason:", raw_response.reason)

        response=api_client.response_deserialize(raw_response, response_types_map=get_entities_response_map)

        if 200<=response.status_code<300 and response.data is not None:
            print(f"✅ Success: Found {len(response.data) if isinstance(response.data, list) else 1} entities. Status: {response.status_code}")
            return response.data
        elif response.status_code==204:
            print("No Entity Found (Status 204 No Content)")
            return {}
        else:
            return {}

    except ApiException as e:
        print(f"❌ API Error During GET Request: {e}")
        return {"Error": str(e)}
    except Exception as e:
        print(f"❌ Unexpected Error During GET Request: {e}")
        return {"Error": str(e)}

'''Issues a GET request to Context Broker to fetch entities in normalized format, filtering by ID or type
   @param ApiClient api_client (application-level interaction with the Context Broker)
   @param str entity_type (entity type filter)
   @param str/None entity_id (entity id filter)
   @param int limit (output size limit)
   @return ModelClass/List[ModelClass]'''
def get_entities_normalized(api_client: ApiClient, entity_type: str, entity_id: Optional[str]=None, limit: int=100):
    global CONTEXT_URLS, NGSI_LD_CONTEXT_LINK_REL

    #create Link header to reference context files
    link_parts=[]
    for url in CONTEXT_URLS:
        link_parts.append(f"<{url}>; {NGSI_LD_CONTEXT_LINK_REL}")

    headers={ 'Accept': 'application/ld+json',
              'Link': ','.join(link_parts)} #headers of GET Request

    #define request URL and query params
    query_params={}
    if entity_id: #GET /entities/{entity_id}
        url=f"/entities/{entity_id}"

        get_entities_response_map = {'200': entity_type,
                                     '4XX': 'object',
                                     '5XX': 'object'}  # response status map for a get entity request
    elif not entity_id and entity_type: #GET /entities?type={type}&limit={limit}
        url=f"/entities"
        query_params['type']=entity_type
        query_params['limit']=limit

        get_entities_response_map = {'200': f'List[{entity_type}]',
                                     '4XX': 'object',
                                     '5XX': 'object'}  #response status map for a get entity request
    else:
        raise ValueError("Specify either 'entity_type' filter and/or 'entity_id' filter.\n")

    query_params['options']='normalized'

    try: #Serialze request and prepare URL
        method, full_url, header_params, body, post_params=api_client.param_serialize(
            method='GET',
            resource_path=url,
            query_params=query_params,
            header_params=headers)

    except OpenApiException as e:
        print(f"Serialization error: {e}\n")
    except Exception as e:
        print(f"Unexpected error: {e}\n")

    try:
        raw_response=api_client.call_api(method, full_url, header_params=header_params)

        raw_response.read()
        print("'--> Class:", type(raw_response))
        print("'--> Raw Response Status:", raw_response.status)
        print("'--> Raw Response Headers:", raw_response.getheaders())
        print("'--> Raw Response Reason:", raw_response.reason)

        response=api_client.response_deserialize(raw_response, response_types_map=get_entities_response_map)

        if 200<=response.status_code<300 and response.data is not None:
            print(f"✅ Success: Found {len(response.data) if isinstance(response.data, list) else 1} entities. Status: {response.status_code}")
            return response.data
        elif response.status_code==204:
            print("No Entity Found (Status 204 No Content)")
            return {}
        else:
            return {}

    except ApiException as e:
        print(f"❌ API Error During GET Request: {e}")
        return {"Error": str(e)}
    except Exception as e:
        print(f"❌ Unexpected Error During GET Request: {e}")
        return {"Error": str(e)}

'''Main'''
if __name__ == "__main__":
    print(f'Running Configurations: {sys.argv}\n')

    entity_dict=create_entities()

    if '--create-test' in sys.argv:
        test_print(entity_dict)
        test_serialization(entity_dict)

    config=Configuration(host=CONTEXT_BROKER_URL)
    api_client=ApiClient(config)

    if '--upload-test' in sys.argv:
        test_upload(entity_dict, api_client)

    ###Testing Get Requests (JSON Format)
    if '--get-test' in sys.argv:
        print(f'#######################################################Search by entity ID, return in key-value format')
        for id in entity_dict.keys():
            result=get_entities_key_values(api_client, entity_id=id)
            print(f'Result --> {result}')
            print(f'Result Type --> {type(result)}\n')

        print(f'#####################################################Search by entity type, return in key-value format')
        for entity in entity_dict.values():
            result=get_entities_key_values(api_client, entity_type=entity.type)
            print(f"Result --> {result}")
            if len(result) > 0:
                print(f'Result Type --> {type(result)} of {type(result[0])}\n')

        ###Testing Get Requests (Normalized JSON-LD Format)
        print(f'######################################################Search by entity ID, return in normalized format')
        for id in entity_dict.keys():
            result=get_entities_normalized(api_client, entity_type=entity_dict[id].type, entity_id=id)
            print(f"Result --> {result}")
            print(f'Result Type --> {type(result)}\n')

        print(f'####################################################Search by entity type, return in normalized format')
        for entity in entity_dict.values():
            result=get_entities_normalized(api_client, entity_type=entity.type)
            print(f"Result --> {result}")
            if len(result) > 0:
                print(f'Result Type --> {type(result)} of {type(result[0])}\n')

    ###Testing Entity Updates
    if '--update-test' in sys.argv:
        net_id="urn:ngsi-ld:Network:001"

        #create Link header to reference context files
        link_parts=[]
        for url in CONTEXT_URLS:
            link_parts.append(f"<{url}>; {NGSI_LD_CONTEXT_LINK_REL}")

        method='PATCH' #HTTP operation for updating entities
        url=f"{api_client.configuration.host}/entities/{net_id}/attrs" #endpoint for updating entities

        headers={'Content-Type': 'application/json',
                 'Link': ','.join(link_parts)} #headers of PATCH Request

        print(f'{url}')
        print(f'{headers}\n')
        try:
            ###Update Attributes
            current_timestamp=datetime.now(tz=timezone.utc)
            iso_timestamp=current_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ')  # ISO 8601 string format for date-time values
            dataset_id_value="urn:ngsi-ld:DatasetId:ONOS"

            modification_record_instance=ModificationRecord(type='Property', value=iso_timestamp, datasetId=dataset_id_value)
            observation_record_instance=ObservationRecord(type='Property', value=iso_timestamp,  datasetId=dataset_id_value)

            test_coordinates=[[8, 8.8], [8.88, 88.8]]
            multi_point_instance=GeometryMultiPoint(type='MultiPoint', coordinates=test_coordinates)
            geometry_instance=Geometry(multi_point_instance)
            geo_property_instance=GeoProperty(type='GeoProperty', value=geometry_instance,
                                              datasetId=dataset_id_value,
                                              observedAt=current_timestamp)

            ###Update Entity Instance
            entity_dict[net_id].location=geo_property_instance
            entity_dict[net_id].modification_record=modification_record_instance
            entity_dict[net_id].observation_record=observation_record_instance

            print(f'Entity {net_id} of type {entity_dict[net_id].type}')
            print(f'Class {type(entity_dict[net_id]).__name__} --> {entity_dict[net_id]}')
            print(f'To Dict --> {entity_dict[net_id].to_dict()}') #serialize in Python Dict
            print(f'To JSON --> {entity_dict[net_id].to_json()}') #serialize in JSON string
            print(f'To String --> {entity_dict[net_id].to_str()}\n') #serialize in string

            ###Update Entity on Context Broker
            payload_body={}
            try: #Serialization
                payload_body["location"]=geo_property_instance.to_dict()
                payload_body["modificationRecord"]=modification_record_instance.to_dict()
                payload_body["observationRecord"]=observation_record_instance.to_dict()

                print(f'Serialized payload --> {api_client.sanitize_for_serialization(payload_body)}\n')
            except OpenApiException as e:
                print(f"Serialization error: {e}\n")
            except Exception as e:
                print(f"Unexpected error: {e}\n")

            raw_response=api_client.call_api(method, url, header_params=headers,
                                             body=api_client.sanitize_for_serialization(payload_body)) #issue update request

            raw_response.read()
            print("Raw Response Object -->", raw_response.response)
            print("'--> Class:", type(raw_response))
            print("'--> Raw Response Status:", raw_response.status)
            print("'--> Raw Response Payload:", raw_response.data)
            print("'--> Raw Response Reason:", raw_response.reason)
            print('\n')

            response=api_client.response_deserialize(response_data=raw_response,
                                                     response_types_map=CREATE_ENTITY_RESPONSE_MAP) #de-serialize response

            if 200 <= response.status_code < 300:  # expected response status is "201 Created"
                print(f"✅ Success: Entity '{net_id}' updated (Status: {response.status_code})\n")

        except ApiException as e:
            print(f"❌ API error while updating '{net_id}': {e}\n")
        except Exception as e:
            print(f"❌ Unexpected error: {e}\n")

        result=get_entities_key_values(api_client, entity_id=net_id)
        print(f'Result --> {result}')
        print(f'Result Type --> {type(result)}\n')

        result=get_entities_normalized(api_client, entity_type=entity_dict[net_id].type, entity_id=net_id)
        print(f"Result --> {result}")
        print(f'Result Type --> {type(result)}\n')