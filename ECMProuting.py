#!/usr/bin/env python3

"""Usage:
    python3 ECMProuting.py"""

#################################################################################################################Imports
from flask import Flask, jsonify #web server, expose data in JSON format
import requests #send request to ONOS REST-API endpoint
import urllib.parse #correctly format URLs

import pandas as pd #provide data structures (DataFrames)

#Utility
import sys
import threading
import time

########################################################################################################Global Variables
###Exposed ONOS REST-API endpoints
onos_devices_url="http://localhost:8181/onos/v1/devices"
onos_hosts_url="http://localhost:8181/onos/v1/hosts"
onos_links_url="http://localhost:8181/onos/v1/links"
onos_paths_url="http://localhost:8181/onos/v1/paths"
onos_flows_url="http://localhost:8181/onos/v1/flows"

###ONOS REST-API metadata
onos_auth=("onos", "rocks") #user credentials
headers={"Accept": "application/json"} #HTTP request headers
flow_headers={"Content-Type": "application/json", "Accept": "application/json"} #HTTP POST headers (install a flow rule)

###OpenFlow Rules metadata
ECMP_priority=10 #priority values of ECMP flow rules
ECMP_timeout=0 #timeout of ECMP flow rules (0 means no expiration)
app_id="proactive_ecmp" #default application ID for installed rules

###Data Structures
devices=[] #list of OVS device IDs (APs/switches)
links=[] #list of links between OVS devices
df_hosts=pd.DataFrame(columns=['ID', 'MAC', 'IPv4', 'Connection_Point']) #dataframe of host devices
df_routes=pd.DataFrame(columns=['Route', 'Path Links', 'Cost (Hop Count)']) #dataframe for ECMP routes

###Locks for multithreaded access to data structures
devices_lock=threading.Lock()
hosts_lock=threading.Lock()
links_lock=threading.Lock()
routes_lock=threading.Lock()

app=Flask(__name__) #initialize web server

######################################################################################################Start-up Functions
'''Fetch network data from ONOS controller upon server start-up'''
def fetch_data_from_onos():
    global devices
    global df_hosts
    global links

    print("Fetching data from ONOS at startup...")

    try:
        ######################################################################################Get info about OVS devices
        devices_response=requests.get(onos_devices_url, auth=onos_auth, headers=headers) #fetches data from ONOS endpoint
        devices_response.raise_for_status() #raises HTTP exception
        onos_devices_data=devices_response.json().get("devices", [])

        for device in onos_devices_data:
            devices.append(device.get("id")) #adds OVS device ID to list

        ##############################################################Gets info about Ethernet links between OVS devices
        links_response=requests.get(onos_links_url, auth=onos_auth, headers=headers) #fetches data from ONOS endpoint
        links_response.raise_for_status() #raises HTTP exception
        onos_links_data=links_response.json().get("links", [])

        links_set=set() #this set contains 4-tuples <src, src port, dst, dst port> of all Ethernet links
        for link in onos_links_data: #for every Ethernet link
            src_device=link.get("src").get("device")
            src_port_num=link.get("src").get("port")

            dst_device=link.get("dst").get("device")
            dst_port_num=link.get("dst").get("port")

            if (src_device not in devices) or (dst_device not in devices): #if one of the endpoints is not a registered OVS device
                continue #go to next link (avoids saving a link when endpoints are not registered)

            link_tuple=tuple(sorted((f"{src_device}/{src_port_num}", f"{dst_device}/{dst_port_num}"))) #4-tuple identifying the link

            #to avoid bidirectional links repetition (the same link is saved twice in the list, in opposite directions)
            if link_tuple in links_set: #if the reversed 4-tuple is already in the set (same link, opposite direction)
                continue #go to next link (avoids saving the same link twice)
            else:
                links_set.add(link_tuple) #registers link's 4-tuple in the set
                links.append(f"{src_device}/{src_port_num} <-> {dst_device}/{dst_port_num}") #adds link's name to list

        #####################################################################################Get info about host devices
        hosts_response=requests.get(onos_hosts_url, auth=onos_auth, headers=headers) #fetches data from ONOS endpoint
        hosts_response.raise_for_status()  #raises HTTP exception
        onos_hosts_data=hosts_response.json().get("hosts", [])

        hosts_list=[] #list of all hosts seen by ONOS
        for host in onos_hosts_data:
            connection_device=f"{host.get('locations', {})[0].get('elementId', '')}".strip()
            if connection_device not in devices:
                continue #go to next host (avoid saving hosts if the OVS connection point is not registered)

            #append host's info into the list to be registered
            hosts_list.append({
                "ID": host.get("id"),
                "MAC": host.get("mac"),
                "IPv4": host.get("ipAddresses", [])[0],
                "Connection_Point": f"{connection_device}/{host.get('locations', {})[0].get('port')}".strip()})

        if hosts_list:
            df_hosts=pd.DataFrame(hosts_list) #populates host dataframe with fetched data

        print("Data fetched successfully!")

        #############################################################################Proactively initialize ECMP Routing
        for src_row in df_hosts.itertuples(index=False):
            for dst_row in df_hosts.itertuples(index=False):
                if src_row.ID==dst_row.ID:
                    continue #skip loopback connection
                ecmp_routing(src_row, dst_row)

    except requests.exceptions.RequestException as e:
        print(f"Error fetching data from ONOS at startup: {e}")
        print("Application cannot start without ONOS data. Exiting.")
        sys.exit(1)

#################################################################################################Thread Target Functions
'''Periodically check changes in topology's OVS devices (APs/switches) and links and eventually recompute paths'''
def handle_ovs_link_changes():
    global devices
    global links
    global df_hosts

    while True:
        recompute_routes=False #flag (if set to True, ECMP flow rules will be recomputed and re-installed)
        time.sleep(2*60) #waiting interval of 2 mins in between updates

        try:
            #########################################################Acquire list of OVS devices from ONOS REST endpoint
            devices_response=requests.get(onos_devices_url, auth=onos_auth, headers=headers)
            devices_response.raise_for_status()
            onos_devices_data=devices_response.json().get("devices", [])

            new_device_list=[device.get("id") for device in onos_devices_data] #OVS devices that are currently seen by ONOS

            with devices_lock:
                if set(new_device_list)!=set(devices): #if the list of OVS devices seen by ONOS has changed
                    recompute_routes=True #set flag to true
                devices=new_device_list #updates device list

            ###########################################Acquire list of links between OVS devices from ONOS REST endpoint
            links_response=requests.get(onos_links_url, auth=onos_auth, headers=headers)
            links_response.raise_for_status()
            onos_links_data=links_response.json().get("links", [])

            new_links_list=[] #list of Ethernet links currently seen by ONOS
            new_links_set=set() #this set contains 4-tuples <src, src port, dst, dst port> of all Ethernet links currently seen by ONOS
            for link in onos_links_data: #for every Ethernet link
                src_device=link.get("src").get("device")
                src_port_num=link.get("src").get("port")

                dst_device=link.get("dst").get("device")
                dst_port_num=link.get("dst").get("port")

                if (src_device not in devices) or (dst_device not in devices): #if one of the endpoints is not a registered OVS device
                    continue #go to next link (avoids saving a link when endpoints are not registered)

                link_tuple=tuple(sorted((f"{src_device}/{src_port_num}", f"{dst_device}/{dst_port_num}"))) #4-tuple identifying the link

                #to avoid bidirectional links repetition (the same link is saved twice in the list, in opposite directions)
                if link_tuple in new_links_set: #if the reversed 4-tuple is already in the set (same link, opposite direction)
                    continue #go to next link (avoids saving the same link twice)
                else:
                    new_links_set.add(link_tuple) #registers link's 4-tuple in the set
                    new_links_list.append(f"{src_device}/{src_port_num} <-> {dst_device}/{dst_port_num}") #adds link's name to new list

            with links_lock:
                if set(new_links_list)!=set(links): #if the list of Ethernet links seen by ONOS has changed
                    recompute_routes=True #set flag to true
                links=new_links_list #updates links list

            if recompute_routes: ##############################################################recompute ECMP flow rules
                for src_row in df_hosts.itertuples(index=False):
                    for dst_row in df_hosts.itertuples(index=False):
                        if src_row.ID==dst_row.ID:
                            continue #skip loopback connection
                        ecmp_routing(src_row, dst_row)

        except requests.exceptions.RequestException as e:
            print(f"Error updating devices list: {e}")

'''Periodically check changes in topology's host/station devices and eventually recompute paths'''
def handle_host_changes():
    global df_hosts

    while True:
        time.sleep(30) #waiting interval of 30 s in between updates

        try:
            #Acquire list of host devices from ONOS REST endpoint
            hosts_response=requests.get(onos_hosts_url, auth=onos_auth, headers=headers)
            hosts_response.raise_for_status()
            onos_hosts_data=hosts_response.json().get("hosts", [])

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

                    connection_device=f"{host.get('locations', {})[0].get('elementId', '')}".strip()
                    if connection_device not in devices:
                        continue #go to next host (avoid saving hosts if the OVS connection point is not registered)

                    if id not in current_id_set: #if the host device is new (not yet registered in the dataframe)
                        new_row=pd.DataFrame([{
                            "ID": host.get("id"),
                            "MAC": host.get("mac"),
                            "IPv4": host.get("ipAddresses", [])[0],
                            "Connection_Point": f"{connection_device}/{host.get('locations', {})[0].get('port')}".strip()}]) #new row

                        new_row_tuple=next(new_row.itertuples(index=False)) #transform df row into named tuple
                        for dst_row in df_hosts.itertuples(index=False): #compute flow rules from new node
                            ecmp_routing(new_row_tuple, dst_row)
                        for src_row in df_hosts.itertuples(index=False): #compute flow rules towards new node
                            ecmp_routing(src_row, new_row_tuple)

                        df_hosts=pd.concat([df_hosts, new_row], ignore_index=True) #adds row to hosts DataFrame
                        print(f"Added new host device: {id}")

                    else: #if the host device is not new
                        connection_point=f"{connection_device}/{host.get('locations', {})[0].get('port')}".strip()

                        host_row=df_hosts['ID']==id #filter to get dataframe row corresponding to current host

                        if not df_hosts.loc[host_row, 'Connection_Point'].iloc[0]==connection_point: #if connection point has changed
                            df_hosts.loc[host_row, 'Connection_Point']=connection_point #updates host's connection point

                            host_row_tuple=next(df_hosts[host_row].itertuples(index=False)) #transform df row into named tuple
                            for dst_row in df_hosts.itertuples(index=False): #compute flow rules from current node
                                ecmp_routing(host_row_tuple, dst_row)
                            for src_row in df_hosts.itertuples(index=False): #compute flow rules towards current node
                                ecmp_routing(src_row, host_row_tuple)

        except requests.exceptions.RequestException as e:
            print(f"Error updating hosts list: {e}")

#######################################################################################################Routing Functions
'''Proactively computes and installs ECMP flow rules for a given source-destination host/station pair.
   @param tuple source (source host/station)
   @param tuple destination (destination host/station)'''
def ecmp_routing(source, destination):
    global df_routes

    src_mac=source.MAC #get source MAC address
    dst_mac=destination.MAC #get destination MAC

    src_ipv4=source.IPv4 #get IPv4 source address
    dst_ipv4=destination.IPv4 #get IPv4 destination address

    #URL to request ONOS least-cost paths between source and destination
    encoded_source=urllib.parse.quote(source.ID, safe='')
    encoded_destination=urllib.parse.quote(destination.ID, safe='')
    paths_url=f"{onos_paths_url}/{encoded_source}/{encoded_destination}"

    try: #ask ONOS to compute paths (algorithm: Dijkstra, metric: hop count)
        paths_response=requests.get(paths_url, auth=onos_auth, headers=headers)
        paths_response.raise_for_status()
        paths_data=paths_response.json().get("paths", [])

        if not paths_data:
            print(f"No paths found between {src_mac} and {dst_mac}")
            return 0

        print(f"Found {len(paths_data)} least-cost paths from {src_mac} to {dst_mac}")
        print(f"Cost: {paths_data[0].get('cost')}")

        #Hash-based mod-N selection to choose a single path among redundant equal-cost alternatives
        hash_val=hash(f"{src_mac}{src_ipv4}{dst_mac}{dst_ipv4}")
        selected_path_index=hash_val%len(paths_data)
        selected_path=paths_data[selected_path_index]

        path_links=[] #list of traversed links
        for i, link in enumerate(selected_path.get("links", [])):
            src_node=link.get("src") #contains device ID and port number on source endpoint
            dst_node=link.get("dst") #contains device ID and port number on destination endpoint

            link_name=""
            if link.get("type")=="EDGE": #if we are on an edge link (first or last)
                if "host" in src_node: #if we are on the first link (host/station <-> AP/switch)
                    link_name=(f"{src_node.get('host')}/{src_node.get('port')} <-> "
                               f"{dst_node.get('device')}/{dst_node.get('port')}")

                elif "host" in dst_node: #if we are on the last link (AP/switch <-> host/station)
                    link_name=(f"{src_node.get('device')}/{src_node.get('port')} <-> "
                               f"{dst_node.get('host')}/{dst_node.get('port')}")

                    ovs_device=src_node.get("device") #where to install flow rules
                    out_port=src_node.get("port") #action output from a specific L2 port

                    install_flow_rule(ovs_device, "IPv4",
                                      src_ipv4=src_ipv4, dst_ipv4=dst_ipv4, out_port=out_port) #IPv4 rule

            elif link.get("type")=="DIRECT": #intermediate link (AP/switch <-> AP/switch)
                link_name=(f"{src_node.get('device')}/{src_node.get('port')} <-> "
                           f"{dst_node.get('device')}/{dst_node.get('port')}")

                ovs_device=src_node.get("device") #where to install flow rules
                out_port=src_node.get("port") #action output from a specific L2 port

                install_flow_rule(ovs_device, "IPv4",
                                  src_ipv4=src_ipv4, dst_ipv4=dst_ipv4, out_port=out_port) #IPv4 rule

            path_links.append(link_name) #add link's name to list of traversed links

        with routes_lock:
            df_routes.set_index('Route', inplace=True) #sets column Route as DataFrame index (more efficient addition)
            route=f"{src_mac} <-> {dst_mac}"
            df_routes.loc[route]={'Path Links': path_links,
                                  'Cost (Hop Count)': selected_path.get("cost")}
            df_routes.reset_index(inplace=True) #reset original DataFrame index

        print(f"ECMP route installed for {src_mac} -> {dst_mac}\n")
        return None

    except requests.exceptions.RequestException as e:
        print(f"Error fetching paths from ONOS: {e}")
        return None

'''Installs a flow rule on a device'''
def install_flow_rule(device_id, rule_type, src_mac=None, dst_mac=None, src_ipv4=None, dst_ipv4=None, out_port=None):
    global ECMP_timeout, ECMP_priority, app_id

    flow_rule={
        "priority": ECMP_priority,
        "timeout": ECMP_timeout,
        "isPermanent": (ECMP_timeout==0),
        "deviceId": device_id,
        "treatment": {
            "instructions": [
                { "type": "OUTPUT",
                  "port": out_port }]}, #instructions to apply to matching packets
        "selector": {
            "criteria": []}} #JSON-formatted OpenFlow rule

    #defining rule's match
    if rule_type=="ARP":
        flow_rule["selector"]["criteria"].append({"type": "ETH_TYPE", "ethType": "0x806"})
    if rule_type=="IPv4":
        flow_rule["selector"]["criteria"].append({"type": "ETH_TYPE", "ethType": "0x800"})
    if src_mac:
        flow_rule["selector"]["criteria"].append({"type": "ETH_SRC", "mac": src_mac})
    if dst_mac:
        flow_rule["selector"]["criteria"].append({"type": "ETH_DST", "mac": dst_mac})
    if src_ipv4:
        flow_rule["selector"]["criteria"].append({"type": "IPV4_SRC", "ip": f"{src_ipv4}/32"}) #/32 mask means exact match
    if dst_ipv4:
        flow_rule["selector"]["criteria"].append({"type": "IPV4_DST", "ip": f"{dst_ipv4}/32"}) #/32 mask means exact match

    create_flow_url=f"{onos_flows_url}/{device_id}?appId={app_id}" #URL where to install new flow rules on a OVS device
    try:
        response=requests.post(create_flow_url, json=flow_rule, auth=onos_auth, headers=flow_headers)
        response.raise_for_status()
        print(f"Successfully installed {rule_type} flow rule on device {device_id} for port {out_port}")

    except requests.exceptions.RequestException as e:
        print(f"Error installing {rule_type} flow rule on device {device_id}: {e}")

################################################################################################Exposed Server Endpoints
@app.route("/paths", methods=["GET"]) #exposes GET http://localhost:8082/paths
def get_paths():
    return jsonify(df_routes.to_dict(orient="records")) #converts dataframe to JSON to be exposed

####################################################################################################################Main
if __name__=="__main__":
    fetch_data_from_onos() #get data from ONOS

    #Debugging
    for device in devices:
        print(device)
    print(f"\n")

    for link in links:
        print(link)
    print(f"\n")

    for row in df_hosts.itertuples(index=False):
        print(row.ID, row.MAC, row.IPv4, row.Connection_Point)
    print(f"\n")

    #Starting threads for updating routing in response network changes
    ovs_link_changes=threading.Thread(target=handle_ovs_link_changes, daemon=True)
    host_changes=threading.Thread(target=handle_host_changes, daemon=True)

    ovs_link_changes.start()
    host_changes.start()

    app.run(host="0.0.0.0", port=8082, debug=True, use_reloader=False) #runs Flask server at http://localhost:8082