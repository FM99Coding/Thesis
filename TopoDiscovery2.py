#!/usr/bin/env python3

"""Usage:
    python3 TopoDiscovery.py"""

#################################################################################################################Imports
from flask import Flask, jsonify #web server, expose data in JSON format
import requests #send request to ONOS REST-API endpoint
import urllib.parse #correctly format URLs

import pandas as pd #provide data structures (DataFrames)

###Utility
import sys
import threading
import time

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

###Data Structures
topology_summary={} #dictionary containing main topology info
df_switches=pd.DataFrame(columns=['DPID', 'Name', 'Type', 'Model', 'Manufacturer', 'Control_Protocol']) #dataframe of OVS switches
df_aps=pd.DataFrame(columns=['DPID', 'Name', 'Type', 'Model', 'Manufacturer', 'Control_Protocol', 'Position']) #dataframe of OVS APs

df_hosts=pd.DataFrame(columns=['ID', 'MAC', 'IPv4', 'Connection_Point',
                               'Name', 'Type', 'Interface']) #dataframe of host devices
df_stations=pd.DataFrame(columns=['ID', 'MAC', 'IPv4', 'Connection_Point',
                                  'Name', 'Type', 'Interface',
                                  'Position', 'WiFi_Mode', 'WiFi_Frequency[GHz]', 'RSSI[dBm]', 'AP_SSID', 'AP_Distance[m]'
                                  'Tx_Bytes', 'Rx_Bytes', 'Tx_Packets', 'Rx_Packets',
                                  'Tx_Errors', 'Rx_Errors', 'Tx_Drops', 'Rx_Drops', 'Collisions']) #dataframe of station devices

df_eth_ports=pd.DataFrame(columns=['Name', 'OVS_Device', 'Type', 'Port_Num', 'MAC', 'Tx_Bytes', 'Rx_Bytes',
                                   'Tx_Packets', 'Rx_Packets', 'Tx_Errors', 'Rx_Errors', 'Tx_Drops', 'Rx_Drops', 'Sample_Time[s]',
                                   'Max_Throughput[Mbps]', 'Max_Queue_Length', 'Backlog_Packets', 'Backlog_Bytes']) #df of L2 Eth ports

df_wlan_ports=pd.DataFrame(columns=['Name', 'OVS_Device', 'Type', 'Port_Num', 'MAC', 'Tx_Bytes', 'Rx_Bytes',
                                    'Tx_Packets', 'Rx_Packets', 'Tx_Errors', 'Rx_Errors', 'Tx_Drops', 'Rx_Drops', 'Sample_Time[s]',
                                    'Max_Throughput[Mbps]', 'Max_Queue_Length', 'Backlog_Packets', 'Backlog_Bytes',
                                    'WiFi_Mode', 'WiFi_Frequency[GHz]', 'WiFi_Channel', 'Bandwidth[MHz]', 'Tx_Power[dBm]', 'Gain[dBm]',
                                    'SSID', 'Range[m]' 'Collisions']) #dataframe of L2 wireless ports

df_links=pd.DataFrame(columns=['Name', 'Source_Device', 'Source_Port', 'Dest_Device', 'Dest_Port', 'Type',
                               'Bandwidth[Mbps]', 'Queue_size', 'Backlog_Packets', 'Backlog_Bytes', 'Tot_Packets',
                               'Raw_Data[Byte]', 'Tot_Errors', 'Tot_Drops', 'Throughput[Mbps]', 'Utilization[%]', 'Occupation[%]',
                               'Error_Rate[%]', 'Drop_Rate[%]']) #dataframe of Ethernet links
df_connections=pd.DataFrame(columns=['Interface', 'AP', 'Access_Port', 'Connected_Devices', 'Type', 'Bandwidth[Mbps]',
                                     'Queue_size', 'Backlog_Packets', 'Backlog_Bytes' 'Tot_Packets', 'Raw_Data[Byte]',
                                     'Tot_Errors', 'Tot_Drops', 'Throughput[Mbps]', 'Utilization[%]', 'Occupation[%]',
                                     'Error_Rate[%]', 'Drop_Rate[%]', 'Collision_Rate[%]']) #dataframe of WiFi connections

###Locks for multithreaded access to data structures
summary_lock=threading.Lock()

switches_lock=threading.Lock()
aps_lock=threading.Lock()

hosts_lock=threading.Lock()
stas_lock=threading.Lock()

eth_ports_lock=threading.Lock()
wlan_ports_lock=threading.Lock()

links_lock=threading.Lock()
connections_lock=threading.Lock()

app=Flask(__name__) #initialize web server

######################################################################################################Start-up Functions
'''Fetch network data from ONOS controller upon server start-up'''
def fetch_data_from_onos():
    global df_switches, df_aps, df_hosts, df_stations, df_eth_ports, df_wlan_ports, df_links, df_connections

    print("Fetching data from ONOS at startup...")

    try:
        ############################################################################################Get topology summary
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
        wifi_connections_list=[]
        wifi_ports=df_eth_ports[df_eth_ports['Type']=='WiFi'] #filters only WiFi ports on OVS access points

        for index, row in wifi_ports.iterrows(): #for every WiFi port
            access_point=row['OVS_Device']
            access_port=row['Port_Num']
            connection_point=f"{access_point}/{access_port}"

            connected_hosts=df_hosts[df_hosts['Connection_Point']==connection_point] #host devices connected to this WiFi port
            connected_devices_list=connected_hosts['ID'].tolist() #extracts IDs of connected hosts

            if not connected_devices_list: #if no host device is connected to this WiFi port
                print(f"Error: unable to find connected hosts for Connection Point: {connection_point}")
                continue #go to next WiFi connection

            #Connection Metrics
            bandwidth=row['Port Speed [Mbps]'] #Mbps
            tx_bytes=row['Tx_Bytes']
            rx_bytes=row['Rx_Bytes']
            sampling_interval=row['Sample_Time[s]'] #s

            throughput=((tx_bytes+rx_bytes)*(8/sampling_interval))/1000000 #Mbps
            utilization=(throughput/bandwidth)*100

            wifi_connection_data = {
                'Interface': row['Name'],
                'AP': access_point,
                'Access_Port': access_port,
                'Connected_Devices': connected_devices_list,
                'Type': 'WiFi',
                'Bandwidth[Mbps]': bandwidth,
                'Raw_Data[Byte]': tx_bytes+rx_bytes,
                'Throughput[Mbps]': throughput,
                'Utilization[%]': utilization } #data about this WiFi connection

            wifi_connections_list.append(wifi_connection_data) #adds connection data to list

        if wifi_connections_list:
            df_connections=pd.DataFrame(wifi_connections_list) #populates dataframe about WiFi connections

        print("Data fetched successfully!")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from ONOS at startup: {e}")
        print("Application cannot start without ONOS data. Exiting.")
        sys.exit(1)

'''Populate topology summary with data read from onos
   @param json onos_summary_data'''
def read_topo(onos_summary_data):
    global topology_summary

    controllers_list=[] #controller instances list

    for _ in range(onos_summary_data.get("sccs", 0)):
        controllers_list.append({
            "IPv4": onos_summary_data.get("node"),
            "L4 Port": 6653,
            "ONOS Version": onos_summary_data.get("version")})

    topology_summary = {
        "Num OVS Devices": onos_summary_data.get("devices", 0),
        "Num Host Devices": onos_summary_data.get("hosts", 0),
        "Num Ethernet Links": onos_summary_data.get("links", 0),
        "Num WiFi Connections": len(df_connections),
        "Num Clusters": onos_summary_data.get("sccs", 0),
        "Num Controller Instances": onos_summary_data.get("sccs", 0),
        "Controllers": controllers_list} #mapping data from ONOS to my app

'''Populate dataframes with data about OVS devices (APs/switches) read from onos
   @param json onos_devices_data'''
def read_devices(onos_devices_data):
    global df_switches, df_aps

    switches_list=[]
    aps_list=[]
    for device in onos_devices_data:
        datapath_description=device.get("annotations", {}).get("datapathDescription", "")
        device_type="Access Point" if datapath_description.startswith("ap") else "Switch"

        device_dict={ "DPID": device.get("id"),
                    "Name": datapath_description,
                    "Type": device_type,
                    "Model": f"{device.get('hw', '')} {device.get('sw', '')}".strip(),
                    "Manufacturer": device.get("mfr"),
                    "Control_Protocol": device.get("annotations", {}).get("protocol")}

        if device_type=="Switch":
            switches_list.append(device_dict)
        else: #device_type=="Access Point"
            if 'position' in device.get("annotations", {}):
                pos=device.get("annotations", {}).get("position")
            else:
                pos='NaN'

            device_dict["Position"]=pos
            aps_list.append(device_dict)

    if switches_list:
        df_switches=pd.DataFrame(switches_list) #populates OVS switch dataframe with fetched data

    if aps_list:
        df_aps=pd.DataFrame(aps_list) #populates OVS ap dataframe with fetched data

'''Populate dataframes with data about host and station devices read from onos
   @param json onos_hosts_data'''
def read_hosts(onos_hosts_data):
    global df_hosts, df_stations

    hosts_list=[]
    stas_list=[]
    for host in onos_hosts_data:
        mac=host.get("mac")
        if "annotations" in host:
            name=host.get("annotations", {}).get("name")
            intf=host.get("annotations", {}).get("interfaces")
            type=host.get("annotations", {}).get("type")
        else:
            name=mac_to_name(mac)
            type="Host" if "h" in name else "Station"
            intf='NaN'

        host_dict={"ID": host.get("id"),
                    "MAC": mac,
                    "Name": name,
                    "Type": type,
                    "IPv4": host.get("ipAddresses", [None])[0],
                    "Connection_Point": f"{host.get('locations', {})[0].get('elementId', '')}/"
                                        f"{host.get('locations', {})[0].get('port')}".strip(),
                    "Interface": intf}

        if type=="Host":
            hosts_list.append(host_dict)

        else: #type=="Station"
            if "position" in host.get("annotations", {}):
                annotation=host.get("annotations", {})

                pos=annotation.get("position")
                mode=annotation.get("wifiMode")
                freq=annotation.get("wifiFrequency")
                rssi=annotation.get("RSSI")
                ap_ssid=annotation.get("apSSID")
                ap_distance=annotation.get("distanceFromAp")
                tx_bytes=annotation.get("txBytes")
                rx_bytes=annotation.get("rxBytes")
                tx_packets=annotation.get("txPackets")
                rx_packets=annotation.get("rxPackets")
                tx_errors=annotation.get("txErrors")
                rx_errors=annotation.get("rxErrors")
                tx_drops=annotation.get("txDropped")
                rx_drops=annotation.get("rxDropped")
                cols=annotation.get("collisions")
            else:
                pos, mode, freq, rssi, ap_ssid, ap_distance, tx_bytes, rx_bytes, tx_packets, rx_packets,\
                tx_errors, rx_errors, tx_drops, rx_drops, cols=("Nan", "NaN", "Nan", "NaN", "Nan", "NaN", "Nan", "NaN",
                                                                "NaN", "Nan", "NaN", "Nan", "NaN", "NaN", "Nan")

            host_dict.update({ "Position": pos,
                                "WiFi_Mode": mode,
                                "WiFi_Frequency[GHz]": freq,
                                "RSSI[dBm]": rssi,
                                "AP_SSID": ap_ssid,
                                "AP_Distance[m]": ap_distance,
                                "Tx_Bytes": tx_bytes,
                                "Rx_Bytes": rx_bytes,
                                "Tx_Packets": tx_packets,
                                "Rx_Packets": rx_packets,
                                "Tx_Errors": tx_errors,
                                "Rx_Errors": rx_errors,
                                "Tx_Drops": tx_drops,
                                "Rx_Drops": rx_drops,
                                "Collisions": cols})

            stas_list.append(host_dict)

    if hosts_list:
        df_hosts=pd.DataFrame(hosts_list) #populates host dataframe with fetched data

    if stas_list:
        df_stations=pd.DataFrame(stas_list) #populates stations dataframe with fetched data

'''Populate dataframes with data about L2 ports on OVS devices read from onos
   @param json onos_ports_data'''
def read_ports(onos_ports_data):
    global df_eth_ports, df_wlan_ports

    eth_ports_list=[]
    wlan_ports_list=[]
    for port in onos_ports_data: #for every L2 port
        port_name=port.get("annotations", {}).get("portName")
        port_num=port.get("port") #port number

        if port_num=="local": #control plane port (connection towards ONOS controller instance)
            continue #go to next port (save info only about data plane ports)

        port_type="WiFi" if "wlan" in port_name else "Ethernet"

        ovs_device=port.get("element") #OVS switch/AP on which the L2 port is located
        if port_type=="Ethernet":
            device=df_switches[df_switches['DPID']==ovs_device] #extract the target device from the OVS switches dataframe
        else:
            device=df_aps[df_aps['DPID']==port_name] #extract the target device from the OVS APs dataframe

        if device.empty: #if the OVS device of the current port cannot be found in the memorized data
            print(f"Error: unable to find device {ovs_device} for port {port_name}")
            continue #go to next port
        if not port.get("isEnabled"): #if this port is not currently configured to allow traffic
            continue #go to next port

        #Retrieves port's statistics from ONOS REST-API
        stats_url=f"{onos_port_stats_url}/{urllib.parse.quote(ovs_device)}/{port_num}"
        stats_response=requests.get(stats_url, auth=onos_auth, headers=get_headers)  # fetches data from ONOS endpoint
        stats_response.raise_for_status() #raises HTTP exception
        port_stats_data=stats_response.json().get("statistics", [{}])[0].get("ports", [{}])[0]

        if "maxThroughput" in port.get("annotations", {}):
            annotation=port.get("annotations", {})

            max_throughput=annotation.get("maxThroughput")
            max_queue=annotation.get("maxQueueLength")
            backlog_p=annotation.get("backlogPackets")
            backlog_b=annotation.get("backlogBytes")
        else:
            max_throughput, max_queue, backlog_p, backlog_b=("Nan", "Nan", "Nan", "NaN")

        port_dict={ "Name": port_name,
                "Type": port_type,
                "OVS_Device": ovs_device,
                "Port_Num": port_num,
                "MAC": port.get("annotations", {}).get("portMac"),
                "Max_Throughput[Mbps]": max_throughput,
                "Max_Queue_Length": max_queue,
                "Backlog_Packets": backlog_p,
                "Backlog_Bytes": backlog_b,
                "Tx_Bytes": port_stats_data.get("bytesSent"),
                "Rx_Bytes": port_stats_data.get("bytesReceived"),
                "Tx_Packets": port_stats_data.get("packetsSent"),
                "Rx_Packets": port_stats_data.get("packetsReceived"),
                "Tx_Errors": port_stats_data.get("packetsTxErrors"),
                "Rx_Errors": port_stats_data.get("packetsRxErrors"),
                "Tx_Drops": port_stats_data.get("packetsTxDropped"),
                "Rx_Drops": port_stats_data.get("packetsRxDropped"),
                "Sample_Time[s]": port_stats_data.get("durationSec")}

        if port_type=="Ethernet":
            eth_ports_list.append(port_dict)
        else: #port_type=='WiFi'
            if "wifiMode" in port.get("annotations", {}):
                annotation=port.get("annotations", {})

                mode=annotation.get("wifiMode")
                freq=annotation.get("wifiFrequency")
                channel=annotation.get("wifiChannel")
                band=annotation.get("Bandwidth")
                tx_power=annotation.get("txPower")
                gain=annotation.get("gain")
                ssid=annotation.get("ssid")
                range=annotation.get("range")
                cols=annotation.get("collisions")

            else:
                mode, freq, channel, band, tx_power, gain, ssid, range, cols=("Nan", "NaN", "Nan", "NaN", "Nan", "NaN", "Nan",
                                                                              "NaN", "NaN")

            port_dict.update({"WiFi_Mode": mode,
                            "WiFi_Frequency[GHz]": freq,
                            "WiFi_Channel": channel,
                            "Bandwidth[MHz]": band,
                            "Tx_Power[dBm]": tx_power,
                            "Gain[dBm]": gain,
                            "SSID":ssid,
                            "Range[m]": range,
                            "Collisions": cols})

            wlan_ports_list.append(port_dict)

    if eth_ports_list:
        df_eth_ports=pd.DataFrame(eth_ports_list) #populates eth ports dataframe with fetched data

    if wlan_ports_list:
        df_wlan_ports=pd.DataFrame(wlan_ports_list) #populates wlan ports dataframe with fetched data

'''Populate dataframes with data about Ethernet links between OVS devices read from onos
   @param json onos_links_data'''
def read_links(onos_links_data):
    global df_links

    links_list=[] #list of all Ethernet link
    links_set=set() #this set contains 4-tuples <src, src port, dst, dst port> of all Ethernet links
    for link in onos_links_data: #for every Ethernet link
        src_device=link.get("src").get("device")
        src_port_num=link.get("src").get("port")

        dst_device=link.get("dst").get("device")
        dst_port_num=link.get("dst").get("port")

        #to avoid bidirectional links repetition (the same link is saved twice in the list, in opposite directions)
        if (dst_device, dst_port_num, src_device, src_port_num) in links_set: #reversed 4-tuple is already in the set
            continue #go to next link (avoids saving the same link twice)
        links_set.add((src_device, src_port_num, dst_device, dst_port_num)) #registers link's 4-tuple in the set

        #from L2 ports dataframe, extract the source port and the destination port of the current link
        src_port_data=df_eth_ports[(df_eth_ports['OVS_Device']==src_device) & (df_eth_ports['Port_Num']==src_port_num)]
        dst_port_data=df_eth_ports[(df_eth_ports['OVS_Device']==dst_device) & (df_eth_ports['Port_Num']==dst_port_num)]

        if src_port_data.empty or dst_port_data.empty: #if the source port and/or the dst port cannot be found in the dataframe
            print(f"Error: unable to find ports for link {src_device}/{src_port_num}-{dst_device}/{dst_port_num}")
            continue #go to next link (do not save this one)
        else:
            src_port_name=src_port_data.at[src_port_data.index[0], 'Name']
            dst_port_name=dst_port_data.at[dst_port_data.index[0], 'Name']

            ###Link's metrics
            tx_bytes=src_port_data['Tx_Bytes'].iloc[0]
            rx_bytes=src_port_data['Rx_Bytes'].iloc[0]
            tx_packets=src_port_data['Tx_Packets'].iloc[0]
            rx_packets=src_port_data['Rx_Packets'].iloc[0]
            tx_errors=src_port_data['Tx_Errors'].iloc[0]
            rx_errors=src_port_data['Rx_Errors'].iloc[0]
            tx_drops=src_port_data['Tx_Drops'].iloc[0]
            rx_drops=src_port_data['Rx_Drops'].iloc[0]

            bandwidth=src_port_data['Max_Throughput[Mbps]'].iloc[0]
            queue_size=src_port_data['Max_Queue_Length'].iloc[0]+dst_port_data['Max_Queue_Length'].iloc[0]
            backlog_p=src_port_data['Backlog_Packets'].iloc[0]+dst_port_data['Backlog_Packets'].iloc[0]

            sampling_interval=src_port_data['Sample_Time[s]'].iloc[0]

            throughput=((tx_bytes+rx_bytes)*(8/sampling_interval))/1000000 #Mbps
            utilization=(throughput/bandwidth)*100 #current occupied link's bandwidth [%]

            occupation=(backlog_p/queue_size)*100 #current occupation of link's endpoint buffers [%]
            try:
                error_rate=(tx_errors+rx_errors)/(tx_packets+rx_packets+tx_errors+rx_errors+tx_drops+rx_drops)
                drop_rate=(tx_drops+rx_drops)/(tx_packets+rx_packets+tx_errors+rx_errors+tx_drops+rx_drops)
            except ZeroDivisionError:
                error_rate=0
                drop_rate=0

        links_list.append({
            "Name": f"{src_port_name} <-> {dst_port_name}",
            "Source_Device": src_device,
            "Source_Port": src_port_num,
            "Dest_Device": dst_device,
            "Dest_Port": dst_port_num,
            "Type": "Ethernet",
            "Bandwidth[Mbps]": bandwidth,
            "Queue_Size": queue_size,
            "Backlog_Packets": backlog_p,
            "Backlog_Bytes": src_port_data['Backlog_Bytes'].iloc[0]+dst_port_data['Backlog_Bytes'].iloc[0],
            "Tot_Packets": tx_packets+rx_packets,
            "Raw_Data[Byte]": tx_bytes+rx_bytes,
            "Tot_Errors": tx_errors+rx_errors,
            "Tot_Drops": tx_drops+rx_drops,
            "Throughput[Mbps]": throughput,
            "Utilization[%]": utilization,
            "Occupation[%]": occupation,
            "Error_Rate[%]": error_rate,
            "Drop_Rate[%]": drop_rate}) #adds data about the current Ethernet link to the list

    if links_list:
        df_links=pd.DataFrame(links_list) #populates Ethernet links dataframe with fetched data

#################################################################################################Thread Target Functions
'''Periodically update topology_summary dictionary (content of endpoint http://localhost:8080/topology)'''
def update_topology():
    global topology_summary, df_connections

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire topology summary from ONOS REST endpoint
            summary_response=requests.get(onos_system_url, auth=onos_auth, headers=get_headers)
            summary_response.raise_for_status()
            onos_summary_data=summary_response.json()

            controllers_list=[] #controller instances list
            for _ in range(onos_summary_data.get("sccs", 0)):
                controllers_list.append({
                    "IPv4": onos_summary_data.get("node"),
                    "L4 Port": 6653,
                    "ONOS Version": onos_summary_data.get("version") })

            with connections_lock:
                num_wifi_connections=len(df_connections)

            with summary_lock: #over-write dictionary with up-to-date
                topology_summary.update({
                    "Num OVS Devices": onos_summary_data.get("devices", 0),
                    "Num Host Devices": onos_summary_data.get("hosts", 0),
                    "Num Ethernet Links": onos_summary_data.get("links", 0),
                    "Num WiFi Connections": num_wifi_connections,
                    "Num Clusters": onos_summary_data.get("sccs", 0),
                    "Num Controller Instances": onos_summary_data.get("sccs", 0),
                    "Controllers": controllers_list })

            print("Topology summary updated successfully.")

        except requests.exceptions.RequestException as e:
            print(f"Error updating topology summary: {e}")

'''Periodically update df_switches DataFrame (content of endpoint http://localhost:8080/topology/devices/switches)'''
def update_switches():
    global df_switches

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of OVS devices from ONOS REST endpoint
            devices_response=requests.get(onos_devices_url, auth=onos_auth, headers=get_headers)
            devices_response.raise_for_status()
            onos_devices_data=devices_response.json().get("devices", [])

            onos_switches_data=[]
            for device in onos_devices_data:
                datapath_description=device.get("annotations", {}).get("datapathDescription", "")
                if "sw" in datapath_description:
                    onos_switches_data.append(device)

            new_switches_list=[] #list of newly discovered OVS devices
            with switches_lock:
                current_dpid_set=set(df_switches['DPID']) #DPIDs of currently registered OVS devices
                onos_dpid_set={sw.get("id") for sw in onos_switches_data} #OVS switches that are still seen by ONOS
                switches_to_remove=list(current_dpid_set-onos_dpid_set) #if ONOS does not see the switch anymore, it has to be removed

                if switches_to_remove: #if there are OVS devices to be removed
                    df_switches.set_index('DPID', inplace=True) #sets column DPID as DataFrame index (more efficient removal)
                    df_switches.drop(switches_to_remove, inplace=True) #remove DataFrame rows corresponding to stale OVS devices
                    df_switches.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed switches: {switches_to_remove}")

                for sw in onos_switches_data: #for all OVS devices seen by ONOS
                    dpid=sw.get("id")

                    if dpid not in current_dpid_set: #if the OVS sw is new (not yet registered in the dataframe)

                        datapath_description=sw.get("annotations", {}).get("datapathDescription", "")
                        type="Switch"

                        new_row={
                            "DPID": dpid,
                            "Name": datapath_description,
                            "Type": type,
                            "Model": f"{sw.get('hw', '')} {sw.get('sw', '')}".strip(),
                            "Manufacturer": sw.get("mfr"),
                            "Control_Protocol": sw.get("annotations", {}).get("protocol")} #create new row for the OVS sw

                        new_switches_list.append(new_row)
                        print(f"Added new switch: {dpid}")

                if new_switches_list:
                        df_switches=pd.concat([df_switches, pd.DataFrame(new_switches_list)], ignore_index=True) #adds new rows

        except requests.exceptions.RequestException as e:
            print(f"Error updating switches list: {e}")

'''Periodically update df_aps DataFrame (content of endpoint http://localhost:8080/topology/devices/aps)'''
def update_aps():
    global df_aps

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of OVS devices from ONOS REST endpoint
            devices_response=requests.get(onos_devices_url, auth=onos_auth, headers=get_headers)
            devices_response.raise_for_status()
            onos_devices_data=devices_response.json().get("devices", [])

            onos_aps_data=[]
            for device in onos_devices_data:
                datapath_description=device.get("annotations", {}).get("datapathDescription", "")
                if "ap" in datapath_description:
                    onos_aps_data.append(device)

            new_aps_list=[] #list of newly discovered OVS devices
            with aps_lock:
                current_dpid_set=set(df_aps['DPID']) #DPIDs of currently registered OVS devices
                onos_dpid_set={ap.get("id") for ap in onos_aps_data} #OVS APs that are still seen by ONOS
                aps_to_remove=list(current_dpid_set-onos_dpid_set) #if ONOS does not see the AP anymore, it has to be removed

                if aps_to_remove: #if there are OVS devices to be removed
                    df_aps.set_index('DPID', inplace=True) #sets column DPID as DataFrame index (more efficient removal)
                    df_aps.drop(aps_to_remove, inplace=True) #remove DataFrame rows corresponding to stale OVS devices
                    df_aps.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed switches: {aps_to_remove}")

                for ap in onos_aps_data: #for all OVS devices seen by ONOS
                    dpid=ap.get("id")

                    if dpid not in current_dpid_set: #if the OVS ap is new (not yet registered in the dataframe)

                        datapath_description=ap.get("annotations", {}).get("datapathDescription", "")
                        type="Access Point"

                        if 'position' in ap.get("annotations", {}):
                            pos=ap.get("annotations", {}).get("position")
                        else:
                            pos='NaN'

                        new_row={
                            "DPID": dpid,
                            "Name": datapath_description,
                            "Type": type,
                            "Model": f"{ap.get('hw', '')} {ap.get('sw', '')}".strip(),
                            "Manufacturer": ap.get("mfr"),
                            "Control_Protocol": ap.get("annotations", {}).get("protocol"),
                            "Position": pos} #create new row for the OVS ap

                        new_aps_list.append(new_row)
                        print(f"Added new AP: {dpid}")

                if new_aps_list:
                        df_aps=pd.concat([df_aps, pd.DataFrame(new_aps_list)], ignore_index=True) #adds new rows

        except requests.exceptions.RequestException as e:
            print(f"Error updating APs list: {e}")

'''Periodically update df_hosts DataFrame (content of endpoint http://localhost:8080/topology/hosts)'''
def update_hosts():
    global df_hosts

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of host devices from ONOS REST endpoint
            hosts_response=requests.get(onos_hosts_url, auth=onos_auth, headers=get_headers)
            hosts_response.raise_for_status()
            onos_hosts_data=hosts_response.json().get("hosts", [])

            for host in onos_hosts_data:
                name=mac_to_name(host.get("mac"))
                if "sta" in name:
                    onos_hosts_data.remove(host)

            new_hosts_list=[] #list of newly discovered host/station devices
            with hosts_lock:
                current_id_set=set(df_hosts['ID']) #IDs of currently registered host devices
                onos_id_set={host.get("id") for host in onos_hosts_data} #host devices that are still seen by ONOS
                hosts_to_remove=list(current_id_set-onos_id_set) #if ONOS does not see the host device anymore, it has to be removed

                if hosts_to_remove: #if there are host devices to be removed
                    df_hosts.set_index('ID', inplace=True) #sets column ID as DataFrame index (more efficient removal)
                    df_hosts.drop(hosts_to_remove, inplace=True) #remove DataFrame rows corresponding to stale host devices
                    df_hosts.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed host devices: {hosts_to_remove}")

                for host in onos_hosts_data: #for all host devices seen by ONOS
                    id=host.get("id")
                    type="Host"

                    if id not in current_id_set: #if the host device is new (not yet registered in the dataframe)
                        if "annotations" in host:
                            name=host.get("annotations", {}).get("name")
                            intf=host.get("annotations", {}).get("interfaces")
                        else:
                            name=mac_to_name(host.get("mac"))
                            intf='NaN'

                        new_row={
                            "ID": host.get("id"),
                            "MAC": host.get("mac"),
                            "Name": name,
                            "Type": type,
                            "IPv4": host.get("ipAddresses", [None])[0],
                            "Connection_Point": f"{host.get('locations', {})[0].get('elementId', '')}/"
                                                f"{host.get('locations', {})[0].get('port')}".strip(),
                            "Interface": intf} #create row for new host device

                        new_hosts_list.append(new_row)
                        print(f"Added new host device: {id}")

                    else: #if the host device is not new
                        connection_point=(f"{host.get('locations', {})[0].get('elementId', '')}/"
                                          f"{host.get('locations', {})[0].get('port')}").strip()

                        host_row=df_hosts['ID']==id #filter to get dataframe row corresponding to current host

                        if not df_hosts.loc[host_row, 'Connection_Point'].iloc[0]==connection_point: #if host changed connection point
                            df_hosts.loc[host_row, 'Connection_Point']=connection_point #updates host's connection point

                if new_hosts_list:
                    df_hosts=pd.concat([df_hosts, pd.DataFrame(new_hosts_list)], ignore_index=True) #adds row to hosts DataFrame

        except requests.exceptions.RequestException as e:
            print(f"Error updating hosts list: {e}")

'''Periodically update df_stations DataFrame (content of endpoint http://localhost:8080/topology/stations)'''
def update_stations():
    global df_stations

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of host devices from ONOS REST endpoint
            hosts_response=requests.get(onos_hosts_url, auth=onos_auth, headers=get_headers)
            hosts_response.raise_for_status()
            onos_hosts_data=hosts_response.json().get("hosts", [])

            onos_stations_data=[]
            for host in onos_hosts_data:
                name=mac_to_name(host.get("mac"))
                if "sta" in name:
                    onos_stations_data.append(host)

            new_stations_list=[] #list of newly discovered station devices
            with stas_lock:
                current_id_set=set(df_stations['ID']) #IDs of currently registered station devices
                onos_id_set={station.get("id") for station in onos_stations_data} #station devices that are still seen by ONOS
                stations_to_remove=list(current_id_set-onos_id_set) #if ONOS does not see the station device anymore

                if stations_to_remove: #if there are station devices to be removed
                    df_stations.set_index('ID', inplace=True) #sets column ID as DataFrame index (more efficient removal)
                    df_stations.drop(stations_to_remove, inplace=True) #remove DataFrame rows corresponding to stale station devices
                    df_stations.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed station devices: {stations_to_remove}")

                for station in onos_stations_data: #for all station devices seen by ONOS
                    id=station.get("id")
                    type="Station"

                    if id not in current_id_set: #if the station device is new (not yet registered in the dataframe)
                        if "annotations" in station:
                            annotation=station.get("annotations", {})

                            name=annotation.get("name")
                            intf=annotation.get("interfaces")
                            pos=annotation.get("position")
                            mode=annotation.get("wifiMode")
                            freq=annotation.get("wifiFrequency")
                            rssi=annotation.get("RSSI[dBm]")
                            ap_ssid=annotation.get("apSSID")
                            ap_distance=annotation.get("distanceFromAp")
                            tx_bytes=annotation.get("txBytes")
                            rx_bytes=annotation.get("rxBytes")
                            tx_packets=annotation.get("txPackets")
                            rx_packets=annotation.get("rxPackets")
                            tx_errors=annotation.get("txErrors")
                            rx_errors=annotation.get("rxErrors")
                            tx_drops=annotation.get("txDropped")
                            rx_drops=annotation.get("rxDropped")
                            cols=annotation.get("collisions")
                        else:
                            name=mac_to_name(station.get("mac"))
                            intf, pos, mode, freq, rssi, ap_ssid, ap_distance, tx_bytes, rx_bytes, tx_packets, rx_packets, \
                                tx_errors, rx_errors, tx_drops, rx_drops, cols = ("Nan", "NaN", "Nan", "NaN", "Nan",
                                                                                  "NaN", "Nan", "NaN",
                                                                                  "NaN", "Nan", "NaN", "Nan", "NaN",
                                                                                  "NaN", "Nan", "NaN")
                        new_row={
                            "ID": station.get("id"),
                            "MAC": station.get("mac"),
                            "Name": name,
                            "Type": type,
                            "IPv4": station.get("ipAddresses", [None])[0],
                            "Connection_Point": f"{station.get('locations', {})[0].get('elementId', '')}/"
                                                f"{station.get('locations', {})[0].get('port')}".strip(),
                            "Interface": intf,
                            "Position": pos,
                            "WiFi_Mode": mode,
                            "WiFi_Frequency[GHz]": freq,
                            "RSSI[dBm]": rssi,
                            "AP_SSID": ap_ssid,
                            "AP_Distance[m]": ap_distance,
                            "Tx_Bytes": tx_bytes,
                            "Rx_Bytes": rx_bytes,
                            "Tx_Packets": tx_packets,
                            "Rx_Packets": rx_packets,
                            "Tx_Errors": tx_errors,
                            "Rx_Errors": rx_errors,
                            "Tx_Drops": tx_drops,
                            "Rx_Drops": rx_drops,
                            "Collisions": cols} #create row for new station device

                        new_stations_list.append(new_row)
                        print(f"Added new station device: {id}")

                    else: #if the station device is not new
                        connection_point=(f"{station.get('locations', {})[0].get('elementId', '')}/"
                                          f"{station.get('locations', {})[0].get('port')}").strip()

                        annotation=station.get("annotations", {})

                        freq=annotation.get("wifiFrequency")
                        rssi=annotation.get("RSSI[dBm]")
                        ap_ssid=annotation.get("apSSID")
                        ap_distance=annotation.get("distanceFromAp")
                        tx_bytes=annotation.get("txBytes")
                        rx_bytes=annotation.get("rxBytes")
                        tx_packets=annotation.get("txPackets")
                        rx_packets=annotation.get("rxPackets")
                        tx_errors=annotation.get("txErrors")
                        rx_errors=annotation.get("rxErrors")
                        tx_drops=annotation.get("txDropped")
                        rx_drops=annotation.get("rxDropped")
                        cols=annotation.get("collisions")

                        station_row=df_stations['ID']==id #filter to get dataframe row corresponding to current station

                        if not df_stations.loc[station_row, 'Connection_Point'].iloc[0]==connection_point: #sta changed connection point
                            df_stations.loc[station_row, 'Connection_Point']=connection_point
                            df_stations.loc[station_row, 'AP_SSID']=ap_ssid
                            df_stations.loc[station_row, 'AP_Distance[m]']=ap_distance
                            df_stations.loc[station_row, 'WiFi_Frequency[GHz]']=freq
                            df_stations.loc[station_row, 'RSSI[dBm]']=rssi

                        #Update metrics measured on the station
                        df_stations.loc[station_row, 'Tx_Bytes']=tx_bytes
                        df_stations.loc[station_row, 'Rx_Bytes']=rx_bytes
                        df_stations.loc[station_row, 'Tx_Packets']=tx_packets
                        df_stations.loc[station_row, 'Rx_Packets']=rx_packets
                        df_stations.loc[station_row, 'Tx_Errors']=tx_errors
                        df_stations.loc[station_row, 'Rx_Errors']=rx_errors
                        df_stations.loc[station_row, 'Tx_Drops']=tx_drops
                        df_stations.loc[station_row, 'Rx_Drops']=rx_drops
                        df_stations.loc[station_row, 'Collisions']=cols

                if new_stations_list:
                    df_stations=pd.concat([df_stations, pd.DataFrame(new_stations_list)], ignore_index=True) #adds row to DataFrame

        except requests.exceptions.RequestException as e:
            print(f"Error updating stations list: {e}")

'''Periodically update df_eth_ports DataFrame (content of endpoint http://localhost:8080/topology/ports/eth)'''
def update_eth_ports():
    global df_eth_ports, df_switches, df_aps

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of L2 ports from ONOS REST endpoint
            ports_response=requests.get(onos_ports_url, auth=onos_auth, headers=get_headers)
            ports_response.raise_for_status()
            onos_ports_data=ports_response.json().get("ports", [])

            onos_eth_data=[]
            for port in onos_ports_data:
                if "eth" in port.get("annotations", {}).get("portName"):
                    onos_eth_data.append(port)

            new_ports_list=[] #list of newly discovered L2 Ethernet ports on OVS devices
            with eth_ports_lock:
                current_ports_map={row['Name']: row.name for index, row in df_eth_ports.iterrows()} #<name, row index> for ports in df
                onos_ports_map={port.get("annotations", {}).get("portName"):
                                    port for port in onos_eth_data} #<name, info> for ports seen by Onos

                ports_to_remove=set(current_ports_map.keys())-set(onos_ports_map.keys()) #if ONOS does not see the Ethernet port anymore
                if ports_to_remove: #if there are Ethernet ports to be removed
                    df_eth_ports.set_index('Name', inplace=True) #sets column Name as DataFrame index (more efficient removal)
                    df_eth_ports.drop(list(ports_to_remove), inplace=True) #remove DataFrame rows corresponding to stale L2 ports
                    df_eth_ports.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed ports: {ports_to_remove}")

                for port_name, port in onos_ports_map.items(): #for all Ethernet ports seen by ONOS
                    port_num=port.get("port")
                    ovs_device=port.get("element") #OVS switch/AP on which the L2 Ethernet port is located

                    if port_num=="local":
                        continue #go to next port (ignore local interface)

                    port_type="Ethernet"

                    ###confirming OVS device (switch/AP) registration
                    with switches_lock:
                        device_exists=not df_switches[df_switches['DPID']==ovs_device].empty #flag confirming switch registration
                    if not device_exists: #if the OVS device is not a switch, it may be an AP
                        with aps_lock:
                            device_exists=not df_aps[df_aps['DPID']==ovs_device].empty #flag confirming switch registration

                    if not device_exists or not port.get("isEnabled"): #if OVS device does not exist, or the port is not configured
                        if port_name in current_ports_map: #if current Ethernet port is already registered
                            df_eth_ports.drop(index=current_ports_map[port_name], inplace=True) #remove row corresponding ports
                            print(f"Removed inactive/invalid Ethernet port: {port_name}")
                        continue #go to next Ethernet port (if current port is new, it will not be registered in the DataFrame)

                    #Fetches real-time stats about current L2 Ethernet port from ONOS endpoint
                    stats_url=f"{onos_port_stats_url}/{urllib.parse.quote(ovs_device)}/{port_num}"
                    stats_response=requests.get(stats_url, auth=onos_auth, headers=get_headers)
                    stats_response.raise_for_status()
                    port_stats_data=stats_response.json().get("statistics", [{}])[0].get("ports", [{}])[0]

                    if "maxThroughput" in port.get("annotations", {}):
                        annotation=port.get("annotations", {})

                        max_throughput=annotation.get("maxThroughput")
                        max_queue=annotation.get("maxQueueLength")
                        backlog_p=annotation.get("backlogPackets")
                        backlog_b=annotation.get("backlogBytes")
                    else:
                        max_throughput, max_queue, backlog_p, backlog_b = ("Nan", "Nan", "Nan", "NaN")

                    if port_name not in current_ports_map: #if the Ethernet port is new, it has to be registered in the DataFrame
                        new_row={
                            "Name": port_name,
                            "Type": port_type,
                            "OVS_Device": ovs_device,
                            "Port_Num": port_num,
                            "MAC": port.get("annotations", {}).get("portMac"),
                            "Max_Throughput[Mbps]": max_throughput,
                            "Max_Queue_Length": max_queue,
                            "Backlog_Packets": backlog_p,
                            "Backlog_Bytes": backlog_b,
                            "Tx_Bytes": port_stats_data.get("bytesSent"),
                            "Rx_Bytes": port_stats_data.get("bytesReceived"),
                            "Tx_Packets": port_stats_data.get("packetsSent"),
                            "Rx_Packets": port_stats_data.get("packetsReceived"),
                            "Tx_Errors": port_stats_data.get("packetsTxErrors"),
                            "Rx_Errors": port_stats_data.get("packetsRxErrors"),
                            "Tx_Drops": port_stats_data.get("packetsTxDropped"),
                            "Rx_Drops": port_stats_data.get("packetsRxDropped"),
                            "Sample_Time[s]": port_stats_data.get("durationSec")} #row for the new port

                        new_ports_list.append(new_row)
                        print(f"Added new port: {port_name}")

                    else: #if the port is already registered and still active
                        df_eth_ports.loc[current_ports_map[port_name], 'Tx_Bytes']=port_stats_data.get("bytesSent") #updates tx bytes
                        df_eth_ports.loc[current_ports_map[port_name], 'Rx_Bytes']=port_stats_data.get("bytesReceived") #updates rx bytes
                        df_eth_ports.loc[current_ports_map[port_name], 'Tx_Packets']=port_stats_data.get("packetsSent")
                        df_eth_ports.loc[current_ports_map[port_name], 'Rx_Packets']=port_stats_data.get("packetsReceived")
                        df_eth_ports.loc[current_ports_map[port_name], 'Tx_Errors']=port_stats_data.get("packetsTxErrors")
                        df_eth_ports.loc[current_ports_map[port_name], 'Rx_Errors']=port_stats_data.get("packetsRxErrors")
                        df_eth_ports.loc[current_ports_map[port_name], 'Tx_Drops']=port_stats_data.get("packetsTxDropped")
                        df_eth_ports.loc[current_ports_map[port_name], 'Rx_Drops']=port_stats_data.get("packetsRxDropped")

                        df_eth_ports.loc[current_ports_map[port_name], 'Backlog_Packets']=backlog_p
                        df_eth_ports.loc[current_ports_map[port_name], 'Backlog_Bytes']=backlog_b

                        ###updates time record
                        df_eth_ports.loc[current_ports_map[port_name], 'Sample_Time[s]']=port_stats_data.get("durationSec")
                        print(f"Updated stats for Ethernet port: {port_name}")

                if new_ports_list:
                    df_eth_ports=pd.concat([df_eth_ports, pd.DataFrame(new_ports_list)], ignore_index=True) #adds rows to the df

        except requests.exceptions.RequestException as e:
            print(f"Error updating ports list: {e}")

'''Periodically update df_wlan_ports DataFrame (content of endpoint http://localhost:8080/topology/ports/wlan)'''
def update_wlan_ports():
    global df_wlan_ports, df_aps

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of L2 ports from ONOS REST endpoint
            ports_response=requests.get(onos_ports_url, auth=onos_auth, headers=get_headers)
            ports_response.raise_for_status()
            onos_ports_data=ports_response.json().get("ports", [])

            onos_wlan_data=[]
            for port in onos_ports_data:
                if "wlan" in port.get("annotations", {}).get("portName"):
                    onos_wlan_data.append(port)

            new_ports_list=[] #list of newly discovered L2 wlan ports on OVS devices
            with eth_ports_lock:
                current_ports_map={row['Name']: row.name for index, row in df_wlan_ports.iterrows()} #<name, row index> for ports in df
                onos_ports_map={port.get("annotations", {}).get("portName"):
                                      port for port in onos_wlan_data} #<name, info> for ports seen by Onos

                ports_to_remove=set(current_ports_map.keys())-set(onos_ports_map.keys()) #if ONOS does not see the WiFi port anymore
                if ports_to_remove: #if there are WiFi ports to be removed
                    df_wlan_ports.set_index('Name', inplace=True) #sets column Name as DataFrame index (more efficient removal)
                    df_wlan_ports.drop(list(ports_to_remove), inplace=True) #remove DataFrame rows corresponding to stale L2 ports
                    df_wlan_ports.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed WiFi ports: {ports_to_remove}")

                for port_name, port in onos_ports_map.items(): #for all WiFi ports seen by ONOS
                    port_num=port.get("port")
                    ovs_device=port.get("element") #OVS AP on which the L2 Ethernet port is located

                    if port_num=="local":
                        continue #go to next port (ignore local interface)

                    port_type="WiFi"

                    with aps_lock:
                        device_exists=not df_aps[df_aps['DPID']==ovs_device].empty #flag confirming AP registration

                    if not device_exists or not port.get("isEnabled"): #if OVS device does not exist, or the port is not configured
                        if port_name in current_ports_map: #if current WiFi port is already registered
                            df_wlan_ports.drop(index=current_ports_map[port_name], inplace=True) #remove row corresponding ports
                            print(f"Removed inactive/invalid WiFi port: {port_name}")
                        continue #go to next WiFi port (if current port is new, it will not be registered in the DataFrame)

                    #Fetches real-time stats about current L2 WiFi port from ONOS endpoint
                    stats_url=f"{onos_port_stats_url}/{urllib.parse.quote(ovs_device)}/{port_num}"
                    stats_response=requests.get(stats_url, auth=onos_auth, headers=get_headers)
                    stats_response.raise_for_status()
                    port_stats_data=stats_response.json().get("statistics", [{}])[0].get("ports", [{}])[0]

                    if "maxThroughput" in port.get("annotations", {}):
                        annotation=port.get("annotations", {})

                        max_throughput=annotation.get("maxThroughput")
                        max_queue=annotation.get("maxQueueLength")
                        backlog_p=annotation.get("backlogPackets")
                        backlog_b=annotation.get("backlogBytes")
                        mode=annotation.get("wifiMode")
                        freq=annotation.get("wifiFrequency")
                        channel=annotation.get("wifiChannel")
                        band=annotation.get("Bandwidth")
                        tx_power=annotation.get("txPower")
                        gain=annotation.get("gain")
                        ssid=annotation.get("ssid")
                        range=annotation.get("range")
                        cols=annotation.get("collisions")
                    else:
                        max_throughput, max_queue, backlog_p, backlog_b=("Nan", "Nan", "Nan", "NaN")
                        mode, freq, channel, band, tx_power, gain, ssid, range, cols=("Nan", "NaN", "Nan", "NaN", "Nan",
                                                                                      "NaN", "Nan", "NaN", "NaN")

                    if port_name not in current_ports_map: #if the WiFi port is new, it has to be registered in the DataFrame
                        new_row={
                            "Name": port_name,
                            "Type": port_type,
                            "OVS_Device": ovs_device,
                            "Port_Num": port_num,
                            "MAC": port.get("annotations", {}).get("portMac"),
                            "Max_Throughput[Mbps]": max_throughput,
                            "Max_Queue_Length": max_queue,
                            "Backlog_Packets": backlog_p,
                            "Backlog_Bytes": backlog_b,
                            "Tx_Bytes": port_stats_data.get("bytesSent"),
                            "Rx_Bytes": port_stats_data.get("bytesReceived"),
                            "Tx_Packets": port_stats_data.get("packetsSent"),
                            "Rx_Packets": port_stats_data.get("packetsReceived"),
                            "Tx_Errors": port_stats_data.get("packetsTxErrors"),
                            "Rx_Errors": port_stats_data.get("packetsRxErrors"),
                            "Tx_Drops": port_stats_data.get("packetsTxDropped"),
                            "Rx_Drops": port_stats_data.get("packetsRxDropped"),
                            "Sample_Time[s]": port_stats_data.get("durationSec"),
                            "WiFi_Mode": mode,
                            "WiFi_Frequency[GHz]": freq,
                            "WiFi_Channel": channel,
                            "Bandwidth[MHz]": band,
                            "Tx_Power[dBm]": tx_power,
                            "Gain[dBm]": gain,
                            "SSID": ssid,
                            "Range[m]": range,
                            "Collisions": cols} #row for the new port

                        new_ports_list.append(new_row)
                        print(f"Added new port: {port_name}")

                    else: #if the port is already registered and still active
                        df_wlan_ports.loc[current_ports_map[port_name], 'Tx_Bytes']=port_stats_data.get("bytesSent") #updates tx bytes
                        df_wlan_ports.loc[current_ports_map[port_name], 'Rx_Bytes']=port_stats_data.get("bytesReceived") #update rx bytes
                        df_wlan_ports.loc[current_ports_map[port_name], 'Tx_Packets']=port_stats_data.get("packetsSent")
                        df_wlan_ports.loc[current_ports_map[port_name], 'Rx_Packets']=port_stats_data.get("packetsReceived")
                        df_wlan_ports.loc[current_ports_map[port_name], 'Tx_Errors']=port_stats_data.get("packetsTxErrors")
                        df_wlan_ports.loc[current_ports_map[port_name], 'Rx_Errors']=port_stats_data.get("packetsRxErrors")
                        df_wlan_ports.loc[current_ports_map[port_name], 'Tx_Drops']=port_stats_data.get("packetsTxDropped")
                        df_wlan_ports.loc[current_ports_map[port_name], 'Rx_Drops']=port_stats_data.get("packetsRxDropped")

                        df_wlan_ports.loc[current_ports_map[port_name], 'Backlog_Packets']=backlog_p
                        df_wlan_ports.loc[current_ports_map[port_name], 'Backlog_Bytes']=backlog_b
                        df_wlan_ports.loc[current_ports_map[port_name], 'Collisions']=cols

                        ###updates time record
                        df_wlan_ports.loc[current_ports_map[port_name], 'Sample_Time[s]']=port_stats_data.get("durationSec")
                        print(f"Updated stats for WiFi port: {port_name}")

                if new_ports_list:
                    df_wlan_ports=pd.concat([df_wlan_ports, pd.DataFrame(new_ports_list)], ignore_index=True) #adds rows to the df

        except requests.exceptions.RequestException as e:
            print(f"Error updating ports list: {e}")

'''Periodically update df_links DataFrame (content of endpoint http://localhost:8080/topology/links)'''
def update_links():
    global df_links, df_eth_ports

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of links between OVS devices from ONOS REST endpoint
            links_response=requests.get(onos_links_url, auth=onos_auth, headers=get_headers)
            links_response.raise_for_status()
            onos_links_data=links_response.json().get("links", [])

            new_links_list=[] #list of newly discovered Ethernet links between OVS devices
            with links_lock:
                current_links_map={row['Name']: row.name for index, row in df_links.iterrows()} #<link name, row index> for all links in the DataFrame

                onos_links_set=set() #contains 4-tuple <src device, src port, dst device, dst port> for every link currently seen by ONOS
                onos_links_dict={} #<link name, link info> for all links seen by Onos
                for link in onos_links_data: #for all links seen by ONOS (bidirectional links are reported twice in opposite directions)
                    src_device=link.get("src").get("device")
                    src_port_num=link.get("src").get("port")
                    dst_device=link.get("dst").get("device")
                    dst_port_num=link.get("dst").get("port")

                    link_tuple=tuple(sorted((f"{src_device}/{src_port_num}", f"{dst_device}/{dst_port_num}"))) #4-tuple identifying the link

                    src_port_data=df_eth_ports[(df_eth_ports['OVS_Device']==src_device) & (df_eth_ports['Port_Num']==src_port_num)]
                    dst_port_data=df_eth_ports[(df_eth_ports['OVS_Device']==dst_device) & (df_eth_ports['Port_Num']==dst_port_num)]
                    if src_port_data.empty or dst_port_data.empty:
                        continue #go to next link
                    src_port_name=src_port_data['Name'].iloc[0]
                    dst_port_name=dst_port_data['Name'].iloc[0]
                    link_name=f"{src_port_name} <-> {dst_port_name}"

                    if link_tuple not in onos_links_set: #this control avoids adding the same link twice, in opposite directions
                        onos_links_set.add(link_tuple) #adds 4-tuple to the set, to avoid adding the reverse-direction link
                        onos_links_dict[link_name]=link #saves link's info in the dictionary

                links_to_remove=set(current_links_map.keys())-set(onos_links_dict.keys()) #if ONOS does not see the link anymore, it has to be removed
                if links_to_remove: #if there are links to be removed
                    df_links.set_index('Name', inplace=True) #sets column Name as DataFrame index (more efficient removal)
                    df_links.drop(list(links_to_remove), inplace=True) #remove DataFrame rows corresponding to stale links
                    df_links.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed links: {links_to_remove}")

                for link_name, link in onos_links_dict.items(): #for all links seen by ONOS (bidirectional links are reported just once)
                    src_device=link.get("src").get("device")
                    src_port_num=link.get("src").get("port")
                    dst_device=link.get("dst").get("device")
                    dst_port_num=link.get("dst").get("port")

                    with eth_ports_lock:
                        src_port_data=df_eth_ports[(df_eth_ports['OVS_Device']==src_device) & (df_eth_ports['Port_Num']==src_port_num)] #gets source port info
                        dst_port_data=df_eth_ports[(df_eth_ports['OVS_Device']==dst_device) & (df_eth_ports['Port_Num']==dst_port_num)] #gets destination port info

                        if src_port_data.empty or dst_port_data.empty: #if either the source or destination port of the link is not recorded
                            if link_name in current_links_map: #if the current link is already in the DataFrame
                                df_links.drop(index=current_links_map[link_name], inplace=True) #removes row corresponding to invalid link
                                print(f"Removed link with invalid ports: {link_name}")
                            continue #go to next link (if the current link was new, it will not be saved in the DataFrame)

                        #gets link's stats from source port
                        tx_bytes=src_port_data['Tx_Bytes'].iloc[0]
                        rx_bytes=src_port_data['Rx_Bytes'].iloc[0]
                        bandwidth=src_port_data['Port Speed [Mbps]'].iloc[0]
                        sampling_interval=src_port_data['Sample_Time[s]'].iloc[0]

                    if link_name not in current_links_map: #if the link is new (registered for the first time in the DataFrame)
                        throughput=((tx_bytes+rx_bytes)*(8/sampling_interval))/1000000 #[Mbps]
                        utilization=(throughput/bandwidth)*100 #[%]

                        new_row={
                            "Name": f"{link_name}",
                            "Source_Device": src_device,
                            "Source_Port": src_port_num,
                            "Dest_Device": dst_device,
                            "Dest_Port": dst_port_num,
                            "Type": "Ethernet",
                            "Bandwidth[Mbps]": bandwidth,
                            "Raw_Data[Byte]": tx_bytes+rx_bytes,
                            "Throughput[Mbps]": throughput,
                            "Utilization[%]": utilization} #creates row for the new link

                        new_links_list.append(new_row)
                        print(f"Added new link: {link_name}")

                    else: #if the link is not new (already registered in the DataFrame)
                        previous_data=df_links.loc[current_links_map[link_name], 'Raw_Data[Byte]']
                        throughput=((tx_bytes+rx_bytes-previous_data)*(8/30))/1000000 #[Mbps]
                        utilization=(throughput/bandwidth)*100 #[%]

                        df_links.loc[current_links_map[link_name], 'Raw_Data[Byte]']=tx_bytes+rx_bytes #updates field in the DataFrame
                        df_links.loc[current_links_map[link_name], 'Throughput[Mbps]']=throughput #updates field in the DataFrame
                        df_links.loc[current_links_map[link_name], 'Utilization[%]']=utilization #updates field in the DataFrame
                        print(f"Updated stats for link: {link_name}")

                if new_links_list:
                    df_links=pd.concat([df_links, pd.DataFrame(new_links_list)], ignore_index=True) #adds new rows to the DataFrame

        except requests.exceptions.RequestException as e:
            print(f"Error updating links list: {e}")

'''Periodically update df_connections DataFrame (content of endpoint http://localhost:8080/topology/connections)'''
def update_connections():
    global df_connections, df_eth_ports, df_hosts

    while True:
        time.sleep(30) #waiting time of 30 [s] in between updates

        try:
            new_connections_list=[] #list of newly discovered connections
            with connections_lock:
                current_connections_map={row['Interface']: row.name
                                         for index, row in df_connections.iterrows()} #<connection name, row index> for all registered connections

                with eth_ports_lock:
                    wifi_ports=df_eth_ports[df_eth_ports['Type']=='WiFi'] #filters only WiFi L2 ports from df_eth_ports DataFrame

                connections_to_remove=set(current_connections_map.keys())-set(wifi_ports['Name']) #if the wlan port is not seen by ONOS anymore, remove connection
                if connections_to_remove: #if there are WiFi connections to be removed
                    df_connections.set_index('Interface', inplace=True) #sets column Interface as DataFrame index (more efficient removal)
                    df_connections.drop(list(connections_to_remove), inplace=True) #remove DataFrame rows corresponding to stale WiFi connections
                    df_connections.reset_index(inplace=True) #reset original DataFrame index
                    print(f"Removed inactive connections: {connections_to_remove}")

                for index, row in wifi_ports.iterrows(): #for every up-to-date WiFi connection
                    access_point=row['OVS_Device']
                    access_port=row['Port_Num']
                    connection_point=f"{access_point}/{access_port}"
                    interface_name=row['Name']

                    with hosts_lock:
                        connected_hosts=df_hosts[df_hosts['Connection_Point']==connection_point] #gets all up-to-date host devices on current WiFi connection
                        connected_hosts_list=connected_hosts['ID'].tolist()

                    if not connected_hosts_list: #if no host is exploiting this connection
                        if interface_name in current_connections_map: #if current connection is already registered in the DataFrame
                            df_connections.drop(index=current_connections_map[interface_name], inplace=True) #remove row related to unused connection
                            print(f"Removed connection with no hosts: {interface_name}")
                        continue #go to next connection (if the connection is new, it will not be saved in the DataFrame)

                    #gets stats about the WiFi connection from wlan port
                    bandwidth=row['Port Speed [Mbps]']
                    tx_bytes=row['Tx_Bytes']
                    rx_bytes=row['Rx_Bytes']
                    sampling_interval=row['Sample_Time[s]']

                    if interface_name not in current_connections_map: #if the WiFi connection is new
                        throughput=((tx_bytes+rx_bytes)*(8/sampling_interval))/1000000 #[Mbps]
                        utilization=(throughput/bandwidth)*100 #[%]

                        new_row={
                            "Interface": interface_name,
                            "AP": access_point,
                            "Access_Port": access_port,
                            "Connected_Devices": connected_hosts_list,
                            "Type": "WiFi",
                            "Bandwidth[Mbps]": bandwidth,
                            "Raw_Data[Byte]": tx_bytes+rx_bytes,
                            "Throughput[Mbps]": throughput,
                            "Utilization[%]": utilization }#creates row for new connection

                        new_connections_list.append(new_row)
                        print(f"Added new WiFi connection: {interface_name}")

                    else: #if the WiFi connection is already registered in the DataFrame
                        previous_data=df_connections.loc[current_connections_map[interface_name], 'Raw_Data[Byte]'] #Byte
                        throughput=((tx_bytes+rx_bytes-previous_data)*(8/30))/1000000 #[Mbps]
                        utilization=(throughput/bandwidth)*100 #[%]

                        df_connections.at[current_connections_map[interface_name], 'Connected_Devices']=connected_hosts_list #updates field
                        df_connections.loc[current_connections_map[interface_name], 'Raw_Data[Byte]']=tx_bytes+rx_bytes #updates field
                        df_connections.loc[current_connections_map[interface_name], 'Throughput[Mbps]']=throughput #updates field
                        df_connections.loc[current_connections_map[interface_name], 'Utilization[%]']=utilization #updates field
                        print(f"Updated stats for WiFi connection: {interface_name}")

                if new_connections_list:
                    df_connections=pd.concat([df_connections, pd.DataFrame(new_connections_list)], ignore_index=True) #adds new rows

        except requests.exceptions.RequestException as e:
            print(f"Error updating connections list: {e}")

################################################################################################Exposed Server Endpoints
@app.route("/topology", methods=["GET"]) #exposes GET http://localhost:8080/topology
def get_topology():
    return jsonify(topology_summary)

@app.route("/topology/devices", methods=["GET"]) #exposes GET http://localhost:8080/topology/devices
def get_ovs_devices():
    return jsonify(df_switches.to_dict(orient="records")) #converts dataframe to JSON to be exposed

@app.route("/topology/hosts", methods=["GET"]) #exposes GET http://localhost:8080/topology/hosts
def get_host_devices():
    return jsonify(df_hosts.to_dict(orient="records"))

@app.route("/topology/ports", methods=["GET"]) #exposes GET http://localhost:8080/topology/ports
def get_l2_ports():
    return jsonify(df_eth_ports.to_dict(orient="records"))

@app.route("/topology/ports/<deviceId>", methods=["GET"]) #exposes GET http://localhost:8081/topology/ports/<deviceId>
def get_ports_by_device(deviceId):
    with eth_ports_lock:
        device_ports=df_eth_ports[df_eth_ports['OVS_Device']==deviceId] #filters only l2 ports of the specified device
        if device_ports.empty:
            return jsonify({"error": "No L2 ports found for this device or device not found"}), 404
        return jsonify(device_ports.to_dict(orient="records"))

@app.route("/topology/links", methods=["GET"]) #exposes GET http://localhost:8080/topology/links
def get_ethernet_links():
    return jsonify(df_links.to_dict(orient="records"))

@app.route("/topology/connections", methods=["GET"]) #exposes GET http://localhost:8080/topology/connections
def get_wifi_connections():
    return jsonify(df_connections.to_dict(orient="records"))

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

####################################################################################################################Main
if __name__=="__main__":
    fetch_data_from_onos() #get data from ONOS

    #Starting threads for updating network info
    up_topology=threading.Thread(target=update_topology, daemon=True) #update topology summary
    up_switches=threading.Thread(target=update_switches, daemon=True) #update OVS devices dataframe
    up_aps=threading.Thread(target=update_aps, daemon=True)
    up_hosts=threading.Thread(target=update_hosts, daemon=True) #update host devices dataframe
    up_stations=threading.Thread(target=update_stations, daemon=True)
    up_eht_ports=threading.Thread(target=update_eth_ports, daemon=True) #update L2 Ethernet ports dataframe
    up_wlan_ports=threading.Thread(target=update_wlan_ports, daemon=True) #update L2 WiFi ports dataframe
    up_links=threading.Thread(target=update_links, daemon=True) #update Ethernet links dataframe
    up_connections=threading.Thread(target=update_connections, daemon=True) #update WiFi connections dataframe

    up_topology.start()
    up_switches.start()
    up_aps.start()
    up_hosts.start()
    up_stations.start()
    up_eht_ports.start()
    up_wlan_ports.start()
    up_links.start()
    up_connections.start()

    app.run(host="0.0.0.0", port=8080, debug=True) #runs Flask server at http://localhost:8080