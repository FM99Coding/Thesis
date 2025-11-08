#!/usr/bin/env python3

"""Usage:
    python3 TopoDiscovery.py"""

#################################################################################################################Imports
###ONOS Interaction
import requests #send request to ONOS REST-API endpoint
import urllib.parse #correctly format URLs

###OpenAPI Client
from openapi_client_1.api_client import ApiClient
from openapi_client_1.configuration import Configuration
from openapi_client_1.exceptions import ApiException
from openapi_client_1.exceptions import OpenApiException

###Entity/Attribute Models
from pydantic import BaseModel
from openapi_client_1.models.creation_record import CreationRecord
from openapi_client_1.models.modification_record import ModificationRecord
from openapi_client_1.models.observation_record import ObservationRecord

from openapi_client_1.models.is_part_of import IsPartOf
from openapi_client_1.models.geometry_multi_point import GeometryMultiPoint
from openapi_client_1.models.geometry import Geometry
from openapi_client_1.models.geo_property import GeoProperty

from openapi_client_1.models.network import Network
from openapi_client_1.models.network_id import NetworkId
from openapi_client_1.models.network_types import NetworkTypes

from openapi_client_1.models.network_node import NetworkNode
from openapi_client_1.models.node_id import NodeId
from openapi_client_1.models.device_type import DeviceType

from openapi_client_1.models.network_node_termination_point import NetworkNodeTerminationPoint
from openapi_client_1.models.tp_id import TpId
from openapi_client_1.models.interface_ref import InterfaceRef

from openapi_client_1.models.interface import Interface
from openapi_client_1.models.interface_name import InterfaceName
from openapi_client_1.models.interface_type import InterfaceType
from openapi_client_1.models.oper_status import OperStatus
from openapi_client_1.models.phys_address import PhysAddress
from openapi_client_1.models.higher_layer_if import HigherLayerIf
from openapi_client_1.models.lower_layer_if import LowerLayerIf
from openapi_client_1.models.speed import Speed
from openapi_client_1.models.ipv4_enabled import Ipv4Enabled
from openapi_client_1.models.ipv4_address import Ipv4Address
from openapi_client_1.models.subnet_prefix_length import SubnetPrefixLength
from openapi_client_1.models.origin import Origin

from openapi_client_1.models.interface_statistics import InterfaceStatistics
from openapi_client_1.models.in_octets import InOctets
from openapi_client_1.models.in_unicast_pkts import InUnicastPkts
from openapi_client_1.models.in_discards import InDiscards
from openapi_client_1.models.in_errors import InErrors
from openapi_client_1.models.out_octets import OutOctets
from openapi_client_1.models.out_unicast_pkts import OutUnicastPkts
from openapi_client_1.models.out_discards import OutDiscards
from openapi_client_1.models.out_errors import OutErrors

from openapi_client_1.models.carrier_termination import CarrierTermination

from openapi_client_1.models.network_link import NetworkLink
from openapi_client_1.models.network_link_source import NetworkLinkSource
from openapi_client_1.models.network_link_destination import NetworkLinkDestination

from openapi_client_1.models.network_radio_connection import NetworkRadioConnection
from openapi_client_1.models.network_radio_connection_source import NetworkRadioConnectionSource
from openapi_client_1.models.network_radio_connection_destinations import NetworkRadioConnectionDestinations

###Utilities
import json
from datetime import datetime as dt, timezone
from typing import Dict, Any, List, Optional
import threading
import time
import sys

########################################################################################################Global Variables
###Exposed ONOS REST-API endpoints
onos_system_url="http://localhost:8181/onos/v1/system"
onos_devices_url="http://localhost:8181/onos/v1/devices"
onos_hosts_url="http://localhost:8181/onos/v1/hosts"
onos_ports_url="http://localhost:8181/onos/v1/devices/ports"
onos_port_stats_url="http://localhost:8181/onos/v1/statistics/ports"
onos_links_url="http://localhost:8181/onos/v1/links"

###ONOS REST-API metadata
onos_auth=("onos", "rocks") #user credentials
get_headers={"Accept": "application/json"} #HTTP request headers

###NGSI-LD API metadata
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

DATASET_ID="urn:ngsi-ld:DatasetId:ONOS"
NETWORK_NAME="WineFactoryNetwork"

###Data Structures
networks={} #dictionary of model instances of type 'Network'
identities={} #dictionary of IDs of NGSI Entities of type 'YANGIdentity'

net_nodes={} #dictionary of model instances of type 'NetworkNode'

net_terminations={} #dictionary of model instances of type 'NetworkNodeTerminationPoint'
interfaces={} #dictionary of model instances of type 'Interface'
intf_stats={} #dictionary of model instances of type 'InterfaceStatistics'
carriers={} #dictionary of model instances of type 'CarrierTermination'

net_links={} #dictionary of model instances of type 'NetworkLink'
net_link_sources={} #dictionary of model instances of type 'NetworkLinkSource'
net_link_destinations={} #dictionary of model instances of type 'NetworkLinkDestination'

net_connections={} #dictionary of model instances of type 'NetworkRadioConnection'
net_connection_sources={} #dictionary of model instances of type 'NetworkRadioConnectionSource'
net_connection_destinations={} #dictionary of model instances of type 'NetworkRadioConnectionDestinations'

###Locks for multithreaded access to data structures
net_lock=threading.Lock()

nodes_lock=threading.Lock()
tps_lock=threading.Lock()

intf_lock=threading.Lock()
stats_lock=threading.Lock()
carriers_lock=threading.Lock()

links_lock=threading.Lock()
link_sources_lock=threading.Lock()
link_dest_lock=threading.Lock()

connections_lock=threading.Lock()
connection_sources_lock=threading.Lock()
connection_dest_lock=threading.Lock()

###################################################################################################NGSI-LD API Functions
def get_entity_uris(api_client: ApiClient, entity_type: str, limit: int=1000) -> List[str]:
    global CONTEXT_URLS, NGSI_LD_CONTEXT_LINK_REL

    #create Link header to reference context files
    link_parts=[]
    for url in CONTEXT_URLS:
        link_parts.append(f"<{url}>; {NGSI_LD_CONTEXT_LINK_REL}")

    headers={ 'Accept': 'application/json',
              'Link': ','.join(link_parts)} #headers of GET Request

    #define request URL and query params
    query_params={}
    if entity_type: #GET /entities?type={type}&limit={limit}
        url=f"/entities"
        query_params['type']=entity_type
        query_params['limit']=limit

        get_entities_response_map = {'200': 'List[object]',
                                     '4XX': 'object',
                                     '5XX': 'object'}  #response status map for a get entity request

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
        #print("'--> Class:", type(raw_response))
        #print("'--> Raw Response Status:", raw_response.status)
        #print("'--> Raw Response Headers:", raw_response.getheaders())
        #print("'--> Raw Response Reason:", raw_response.reason)

        response=api_client.response_deserialize(raw_response, response_types_map=get_entities_response_map)

        if 200<=response.status_code<300 and response.data is not None:
            #print(f"✅ Success: Found {len(response.data)} entities of type {entity_type}. Status: {response.status_code}")
            id_list=[]
            for entity in response.data:
                id_list.append(entity['id'])
            return id_list
        elif response.status_code==204:
            print("No Entity Found (Status 204 No Content)")
            return []
        else:
            return []

    except ApiException as e:
        print(f"❌ API Error During GET Request: {e}")
        return []
    except Exception as e:
        print(f"❌ Unexpected Error During GET Request: {e}")
        return []

def upload_entity(entity: BaseModel, api_client: ApiClient):
    global CREATE_ENTITY_RESPONSE_MAP, CONTEXT_URLS

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

##############################################################################################ONOS Interaction Functions
'''Create Network model instances with data read from onos
   @param json onos_summary_data'''
def read_topo(onos_summary_data):
    global networks, identities, DATASET_ID, NETWORK_NAME

    ###Metadata
    current_timestamp=dt.now(tz=timezone.utc)
    iso_timestamp=current_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') #ISO 8601 string format for date-time values

    ###Temporal Metadata (NGSI-LD Properties)
    creation_record_instance=CreationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    modification_record_instance=ModificationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    observation_record_instance=ObservationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)

    ###Network Entity
    network_id_instance=NetworkId(type='Property', value=NETWORK_NAME, datasetId=DATASET_ID, observedAt=current_timestamp) #property
    network_types_instance=NetworkTypes(type="Relationship", object=[identities['mobile-radio-network']],
                                        datasetId=DATASET_ID, observedAt=current_timestamp) #relationship

    network_instance=Network(id=f"urn:ngsi-ld:Network:{NETWORK_NAME}",
                             type="Network",
                             networkId=network_id_instance,
                             networkTypes=network_types_instance,
                             creationRecord=creation_record_instance,
                             modificationRecord=modification_record_instance,
                             observationRecord=observation_record_instance) #entity

    networks[NETWORK_NAME]=network_instance #add model instance to dictionary

    ###Later: create Controller Entity

'''Create NetworkNode model instances with data about OVS devices (APs/switches) read from onos
   @param json onos_devices_data'''
def read_devices(onos_devices_data):
    global net_nodes, networks, DATASET_ID, NETWORK_NAME

    ###Metadata
    current_timestamp=dt.now(tz=timezone.utc)
    iso_timestamp=current_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') #ISO 8601 string format for date-time values

    ###Temporal Metadata (NGSI-LD Properties)
    creation_record_instance=CreationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    modification_record_instance=ModificationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    observation_record_instance=ObservationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)

    for device in onos_devices_data:
        datapath_description=device.get("annotations", {}).get("datapathDescription", "")

        ###NetworkNode Entity
        node_id_instance=NodeId(type='Property', value=device.get("id"), datasetId=DATASET_ID, observedAt=current_timestamp)
        if datapath_description.startswith("ap"):
            device_type_instance=DeviceType(type="Property", value="ran-ap", datasetId=DATASET_ID, observedAt=current_timestamp)

            if 'position' in device.get("annotations", {}):
                pos=json.loads(device.get("annotations", {}).get("position"))
                pos=[float(c) for c in pos]
                coordinates=[pos]

                multi_point_instance=GeometryMultiPoint(type='MultiPoint', coordinates=coordinates)
                geometry_instance=Geometry(multi_point_instance)
                geo_property_instance=GeoProperty(type='GeoProperty', value=geometry_instance, datasetId=DATASET_ID, observedAt=current_timestamp)
            else:
                geo_property_instance=None
        else:
            device_type_instance=DeviceType(type="Property", value="core-switch", datasetId=DATASET_ID, observedAt=current_timestamp)
            geo_property_instance=None

        is_part_of_instance=IsPartOf(type="Relationship", object=networks[NETWORK_NAME].id, datasetId=DATASET_ID, observedAt=current_timestamp)

        network_node_instance=NetworkNode(id=f"urn:ngsi-ld:NetworkNode:{datapath_description}",
                                          type="NetworkNode",
                                          nodeId=node_id_instance,
                                          deviceType=device_type_instance,
                                          location=geo_property_instance,
                                          isPartOf=is_part_of_instance,
                                          creationRecord=creation_record_instance,
                                          modificationRecord=modification_record_instance,
                                          observationRecord=observation_record_instance)

        net_nodes[datapath_description]=network_node_instance

'''Create NetworkNode model instances with data about host and station devices read from onos
   @param json onos_hosts_data'''
def read_hosts(onos_hosts_data):
    global net_nodes, networks, DATASET_ID, NETWORK_NAME

    ###Metadata
    current_timestamp=dt.now(tz=timezone.utc)
    iso_timestamp=current_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') #ISO 8601 string format for date-time values

    ###Temporal Metadata (NGSI-LD Properties)
    creation_record_instance=CreationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    modification_record_instance=ModificationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    observation_record_instance=ObservationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)

    for host in onos_hosts_data:
        mac=host.get("mac")
        if "annotations" in host:
            name=host.get("annotations", {}).get("name")
        else:
            name=mac_to_name(mac)

        ###NetworkNode Entity
        node_id_instance=NodeId(type='Property', value=host.get("id"), datasetId=DATASET_ID, observedAt=current_timestamp)

        if name.startswith("sta"):
            device_type_instance=DeviceType(type="Property", value="mobile-station", datasetId=DATASET_ID, observedAt=current_timestamp)

            if 'position' in host.get("annotations", {}):
                pos=json.loads(host.get("annotations", {}).get("position"))
                pos=[float(c) for c in pos]
                coordinates=[pos]

                multi_point_instance=GeometryMultiPoint(type='MultiPoint', coordinates=coordinates)
                geometry_instance=Geometry(multi_point_instance)
                geo_property_instance=GeoProperty(type='GeoProperty', value=geometry_instance, datasetId=DATASET_ID, observedAt=current_timestamp)
            else:
                geo_property_instance=None
        else:
            device_type_instance=DeviceType(type="Property", value="host", datasetId=DATASET_ID, observedAt=current_timestamp)
            geo_property_instance=None

        is_part_of_instance=IsPartOf(type="Relationship", object=networks[NETWORK_NAME].id, datasetId=DATASET_ID, observedAt=current_timestamp)

        network_node_instance=NetworkNode(id=f"urn:ngsi-ld:NetworkNode:{name}",
                                          type="NetworkNode",
                                          nodeId=node_id_instance,
                                          deviceType=device_type_instance,
                                          location=geo_property_instance,
                                          isPartOf=is_part_of_instance,
                                          creationRecord=creation_record_instance,
                                          modificationRecord=modification_record_instance,
                                          observationRecord=observation_record_instance)

        net_nodes[name]=network_node_instance

'''Create NetworkNodeTerminationPoint, Interface, InterfaceStatistics, and CarrierTermination model instances with data about host and station devices read from onos
   @param json onos_hosts_data'''
def read_host_interfaces(onos_hosts_data):
    global identities, net_nodes, net_terminations, interfaces, intf_stats, carriers, DATASET_ID

    ###Metadata
    current_timestamp=dt.now(tz=timezone.utc)
    iso_timestamp=current_timestamp.strftime('%Y-%m-%dT%H:%M:%S.%fZ') #ISO 8601 string format for date-time values

    ###Temporal Metadata (NGSI-LD Properties)
    creation_record_instance=CreationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    modification_record_instance=ModificationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)
    observation_record_instance=ObservationRecord(type='Property', value=iso_timestamp, datasetId=DATASET_ID)

    hosts_list=[] ########################################
    stas_list=[] #########################################
    for host in onos_hosts_data:
        mac=host.get("mac")
        if "annotations" in host:
            host_name=host.get("annotations", {}).get("name")
            intf=json.loads(host.get("annotations", {}).get("interfaces"))[0]
        else:
            host_name=mac_to_name(mac)
            intf='NaN' #################################################################################################

        ###NetworkNodeTerminationPoint Entity
        tp_id_instance=TpId(type='Property', value=intf, datasetId=DATASET_ID, observedAt=current_timestamp)
        is_part_of_instance=IsPartOf(type="Relationship", object=net_nodes[host_name].id, datasetId=DATASET_ID, observedAt=current_timestamp)
        network_tp_instance=NetworkNodeTerminationPoint(id=f"urn:ngsi-ld:NetworkNodeTerminationPoint:{intf}",
                                                        type="NetworkNodeTerminationPoint",
                                                        tpId=tp_id_instance,
                                                        isPartOf=is_part_of_instance,
                                                        creationRecord=creation_record_instance,
                                                        modificationRecord=modification_record_instance,
                                                        observationRecord=observation_record_instance)

        ###Interface Entity (layer 2)
        interface_name_instance=InterfaceName(type='Property', value=intf, datasetId=DATASET_ID, observedAt=current_timestamp)
        oper_status_instance=OperStatus(type='Property', value="up", datasetId=DATASET_ID, observedAt=current_timestamp)
        phys_address_instance=PhysAddress(type='Property', value=mac, datasetId=DATASET_ID, observedAt=current_timestamp)
        ipv4_enabled_instance=Ipv4Enabled(type='Property', value=False, datasetId=DATASET_ID, observedAt=current_timestamp)
        interface_l2_instance=Interface(id=f"urn:ngsi-ld:Interface:{intf}",
                                        type="Interface",
                                        interfaceName=interface_name_instance,
                                        operStatus=oper_status_instance,
                                        physAddress=phys_address_instance,
                                        ipv4Enabled=ipv4_enabled_instance,
                                        creationRecord=creation_record_instance,
                                        modificationRecord=modification_record_instance,
                                        observationRecord=observation_record_instance)

        ###Connecting TP to L2 Interface
        network_tp_instance.interface_ref=InterfaceRef(type='Relationship', object=interface_l2_instance.id, datasetId=DATASET_ID, observedAt=current_timestamp)

        ###Interface Entity (layer 3)
        ipv4_enabled_instance=Ipv4Enabled(type='Property', value=False, datasetId=DATASET_ID, observedAt=current_timestamp)
        ipv4_address_instance=Ipv4Address(type='Property', value=host.get("ipAddresses", [None])[0], datasetId=DATASET_ID, observedAt=current_timestamp)
        prefix_length_instance=SubnetPrefixLength(type='Property', value=24, datasetId=DATASET_ID, observedAt=current_timestamp)
        origin_instance=Origin(type='Property', value='static', datasetId=DATASET_ID, observedAt=current_timestamp)
        interface_l3_instance=Interface(id=f"urn:ngsi-ld:Interface:l3-{intf}",
                                        type="Interface",
                                        ipv4Enabled=ipv4_enabled_instance,
                                        ipv4Address=ipv4_address_instance,
                                        prefixLength=prefix_length_instance,
                                        origin=origin_instance,
                                        creationRecord=creation_record_instance,
                                        modificationRecord=modification_record_instance,
                                        observationRecord=observation_record_instance)

        ###Hierarchical Relationship between L2 and L3 Interfaces
        interface_l2_instance.higher_layer_if=HigherLayerIf(type='Relationship', object=interface_l3_instance.id, datasetId=DATASET_ID, observedAt=current_timestamp)
        interface_l3_instance.lower_layer_if=LowerLayerIf(type='Relationship', object=interface_l2_instance.id, datasetId=DATASET_ID, observedAt=current_timestamp)

        if host_name.startswith("h"):
            interface_l2_instance.interface_type=InterfaceType(type='Relationship', object=identities['ethernetCsmacd'],
                                                               datasetId=DATASET_ID, observedAt=current_timestamp)

        else:
            interface_l2_instance.interface_type=InterfaceType(type='Relationship', object=identities['ieee80211'],
                                                               datasetId=DATASET_ID, observedAt=current_timestamp)

            if "position" in host.get("annotations", {}):
                annotation=host.get("annotations", {})

                ###InterfaceStatistics Entity
                in_octets_instance=InOctets(type='Property', value=int(annotation.get("rxBytes")), datasetId=DATASET_ID, observedAt=current_timestamp)
                in_unicast_instance=InUnicastPkts(type='Property', value=int(annotation.get("rxPackets")), datasetId=DATASET_ID, observedAt=current_timestamp)
                in_errors_instance=InErrors(type='Property', value=int(annotation.get("rxErrors")), datasetId=DATASET_ID, observedAt=current_timestamp)
                in_discards_instance=InDiscards(type='Property', value=int(annotation.get("rxDropped")), datasetId=DATASET_ID, observedAt=current_timestamp)

                out_octets_instance=OutOctets(type='Property', value=int(annotation.get("txBytes")), datasetId=DATASET_ID, observedAt=current_timestamp)
                out_unicast_instance=OutUnicastPkts(type='Property', value=int(annotation.get("txPackets")), datasetId=DATASET_ID, observedAt=current_timestamp)
                out_errors_instance=OutErrors(type='Property', value=int(annotation.get("txErrors")), datasetId=DATASET_ID, observedAt=current_timestamp)
                out_discards_instance=OutDiscards(type='Property', value=int(annotation.get("txDropped")), datasetId=DATASET_ID, observedAt=current_timestamp)

                is_part_of_instance=IsPartOf(type='Relationship', object=interface_l2_instance.id, datasetId=DATASET_ID, observedAt=current_timestamp)
                intf_stats_instance=InterfaceStatistics(id=f"urn:ngsi-ld:Interface:stats-{intf}",
                                                        type="InterfaceStatistics",
                                                        inOctets=in_octets_instance,
                                                        inUnicastPkts=in_unicast_instance,
                                                        inErrors=in_errors_instance,
                                                        inDiscards=in_discards_instance,
                                                        outOctets=out_octets_instance,
                                                        outUnicastPkts=out_unicast_instance,
                                                        outErrors=out_errors_instance,
                                                        outDiscards=out_discards_instance,
                                                        isPartOf=is_part_of_instance,
                                                        creationRecord=creation_record_instance,
                                                        modificationRecord=modification_record_instance,
                                                        observationRecord=observation_record_instance)


                mode=annotation.get("wifiMode")
                freq=float(annotation.get("wifiFrequency"))
                rssi=float(annotation.get("RSSI"))



#################################################################################################################Utility
'''Converts a MAC format 00:00:00:0X:0Y:0Z into corresponding host name
   @param str MAC
   @return str name'''
def mac_to_name(mac: str) -> str:
    k=4 #fat-tree param

    _, _, _, X, Y, Z=mac.split(":")

    X=int(X, 16)
    Y=int(Y, 16)
    Z=int(Z, 16)

    if X==(k+1) or Z==k:
        return f"h{X}{Y}{Z}"
    elif Y>=(k//2):
        return f"h{X}{Y}{Z}"
    else:
        return f"sta{X}{Y}{Z}"

if __name__=="__main__":
    config=Configuration(host=CONTEXT_BROKER_URL)
    api_client=ApiClient(config) #configure connection with FIWARE Scorpio Context Broker

    ###Save URIs of all entities of type 'YANGIdentity'
    result=get_entity_uris(api_client, entity_type='YANGIdentity')
    for uri in result:
        key=uri.rsplit(':', 1)[-1]
        identities[key]=uri
    #print(identities)

    ###Fetch network data from ONOS controller upon server start-up and create NGSI-LD models instances
def fetch_data_from_onos():
    print(f"{dt.now().strftime('%H:%M:%S')} -> Fetching data from ONOS at startup...")

    try:
        #############################################################################################Get network summary
        summary_response=requests.get(onos_system_url, auth=onos_auth, headers=get_headers) #fetches data from ONOS endpoint
        summary_response.raise_for_status() #raises HTTP exception
        onos_summary_data=summary_response.json() #format fetched data to JSON

        read_topo(onos_summary_data)

        ######################################################################################Get info about OVS devices
        devices_response=requests.get(onos_devices_url, auth=onos_auth, headers=get_headers) #fetches data from ONOS endpoint
        devices_response.raise_for_status() #raises HTTP exception
        onos_devices_data=devices_response.json().get("devices", [])

        read_devices(onos_devices_data)

        #####################################################################################Get info about host devices
        hosts_response=requests.get(onos_hosts_url, auth=onos_auth, headers=get_headers) #fetches data from ONOS endpoint
        hosts_response.raise_for_status() #raises HTTP exception
        onos_hosts_data=hosts_response.json().get("hosts", [])

        read_hosts(onos_hosts_data)
        read_host_interfaces(onos_hosts_data)

        #########################################################################Gets info about L2 ports on OVS devices
        ports_response=requests.get(onos_ports_url, auth=onos_auth, headers=get_headers) #fetches data from ONOS endpoint
        ports_response.raise_for_status() #raises HTTP exception
        onos_ports_data=ports_response.json().get("ports", [])

        read_ports(onos_ports_data)

        ##############################################################Gets info about Ethernet links between OVS devices
        links_response=requests.get(onos_links_url, auth=onos_auth, headers=get_headers) #fetches data from ONOS endpoint
        links_response.raise_for_status() #raises HTTP exception
        onos_links_data=links_response.json().get("links", [])

        read_links(onos_links_data)

        ################################################################Gets info about WiFi connections of host devices
        read_connections()

        print(f"{dt.now().strftime('%H:%M:%S')} -> Data fetched successfully!")

    except requests.exceptions.RequestException as e:
        print(f"{dt.now().strftime('%H:%M:%S')} -> Error fetching data from ONOS at startup: {e}")
        print(f"{dt.now().strftime('%H:%M:%S')} -> Application cannot start without ONOS data. Exiting.")
        sys.exit(1)