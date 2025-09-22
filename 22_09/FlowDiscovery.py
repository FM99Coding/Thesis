#!/usr/bin/env python3

"""Usage:
    python3 FlowDiscovery.py"""

#################################################################################################################Imports
from flask import Flask, jsonify #web server, expose data in JSON format
import requests #send request to ONOS REST-API endpoint

import pandas as pd #provide data structures

###Utility
import sys
import threading
import time
from datetime import datetime as dt

########################################################################################################Global Variables
###Exposed ONOS REST-API endpoints
onos_devices_url="http://localhost:8181/onos/v1/devices"
onos_flows_url="http://localhost:8181/onos/v1/flows"

###ONOS REST-API metadata
onos_auth=("onos", "rocks") #user credentials
headers={"Accept": "application/json"} #HTTP request headers

###Data Structures
df_flows=pd.DataFrame(columns=['id', 'deviceId', 'tableId', 'life', 'lastSeen', 'priority', 'timeout', 'isPermanent',
                               'bytes', 'packets', 'match', 'instructions']) #dataframe of OpenFlow rules
active_devices=[] #list of active OVS devices (APs/switches)

###Locks for multithreaded access to data structures
flows_lock=threading.Lock()
devices_lock=threading.Lock()

app=Flask(__name__) #initialize web server

######################################################################################################Start-up Functions
'''Fetch network data from ONOS controller upon server start-up'''
def fetch_data_from_onos():
    global df_flows
    global active_devices

    print(f"{dt.now().strftime('%H:%M:%S')} -> Fetching initial data from ONOS...")

    try:
        #######################################################################################Get active OVS device IDs
        devices_response=requests.get(onos_devices_url, auth=onos_auth, headers=headers)
        devices_response.raise_for_status() #raises HTTP exception
        onos_devices_data = devices_response.json().get("devices", []) #format fetched data to JSON
        active_devices=[device.get("id") for device in onos_devices_data] #save all IDs in a list
        print(f"{dt.now().strftime('%H:%M:%S')} -> Active devices found: {active_devices}")

        ##################################################################################################Get flow rules
        flows_response=requests.get(onos_flows_url, auth=onos_auth, headers=headers)
        flows_response.raise_for_status() #raises HTTP exception
        onos_flows_data=flows_response.json().get("flows", []) #format fetched data to JSON

        flows_list=[] #list of installed flow rules
        for flow in onos_flows_data:
            device_id=flow.get("deviceId") #get ID of OVS device
            if device_id in active_devices: #register rule only if the device is seen by ONOS
                flows_list.append({
                    "id": flow.get("id"),
                    "deviceId": device_id,
                    "tableId": flow.get("tableId"),
                    "life": flow.get("life"),
                    "lastSeen": flow.get("lastSeen"),
                    "priority": flow.get("priority"),
                    "timeout": flow.get("timeout"),
                    "isPermanent": flow.get("isPermanent"),
                    "bytes": flow.get("bytes"),
                    "packets": flow.get("packets"),
                    "match": flow.get("selector", {}).get("criteria", []),
                    "instructions": flow.get("treatment", {}).get("instructions", []) })

        if flows_list:
            df_flows=pd.DataFrame(flows_list) #populates flow rules dataframe with fetched data

        print(f"{dt.now().strftime('%H:%M:%S')} -> Initial flow rules data fetched successfully!")

    except requests.exceptions.RequestException as e:
        print(f"{dt.now().strftime('%H:%M:%S')} -> Error fetching data from ONOS at startup: {e}")
        print(f"{dt.now().strftime('%H:%M:%S')} -> Application cannot start without ONOS data. Exiting.")
        sys.exit(1)

#################################################################################################Thread Target Functions
'''Periodically update df_flows DataFrame'''
def update_flows():
    global df_flows
    global active_devices

    while True:
        time.sleep(30) #time interval in between updates

        try:
            with devices_lock: #update list of active OVS devices
                devices_response=requests.get(onos_devices_url, auth=onos_auth, headers=headers)
                devices_response.raise_for_status()
                onos_devices_data=devices_response.json().get("devices", [])
                active_devices={device.get("id") for device in onos_devices_data}

            flows_response=requests.get(onos_flows_url, auth=onos_auth, headers=headers)
            flows_response.raise_for_status()
            onos_flows_data=flows_response.json().get("flows", [])

            new_flows_list=[] #list of newly discovered OpenFlow rules
            with flows_lock: #updates flow dataframe
                current_flow_ids=set(df_flows['id']) #IDs of all flow rules currently registered in the dataframe
                onos_flow_ids={flow.get("id") for flow in onos_flows_data} #IDs of all flow rules currently seen by ONOS

                flows_to_remove=current_flow_ids-onos_flow_ids #identify flows to remove
                if flows_to_remove: #if a flow currently registered is not seen by ONOS, it should be removed
                    df_flows.set_index('id', inplace=True) #set dataframe index to field 'id'
                    df_flows.drop(list(flows_to_remove), inplace=True)
                    df_flows.reset_index(inplace=True) #rest index to default
                    print(f"{dt.now().strftime('%H:%M:%S')} -> Removed flows: {list(flows_to_remove)}")

                if not df_flows.empty: #remove flow rules if the OVS devise is not active anymore
                    stale_device_flows=df_flows[~df_flows['deviceId'].isin(active_devices)]['id'].tolist()
                    flows_to_remove.update(stale_device_flows)

                ###Add/Update flows
                for flow in onos_flows_data:
                    flow_id=flow.get("id")
                    device_id=flow.get("deviceId")

                    if device_id not in active_devices:
                        continue #go to next flow (do not install flow rule if the OVS device is not active)

                    if flow_id not in current_flow_ids: #register new flows
                        new_row={
                            "id": flow_id,
                            "deviceId": device_id,
                            "tableId": flow.get("tableId"),
                            "life": flow.get("life"),
                            "lastSeen": flow.get("lastSeen"),
                            "priority": flow.get("priority"),
                            "timeout": flow.get("timeout"),
                            "isPermanent": flow.get("isPermanent"),
                            "bytes": flow.get("bytes"),
                            "packets": flow.get("packets"),
                            "match": flow.get("selector", {}).get("criteria", []),
                            "instructions": flow.get("treatment", {}).get("instructions", []) } #create new rule

                        new_flows_list.append(new_row)
                        print(f"{dt.now().strftime('%H:%M:%S')} -> Added new flow rule: {flow_id} on device {device_id}")

                    else: #update existing flow rule
                        df_flows.loc[df_flows['id']==flow_id, 'life']=flow.get('life')
                        df_flows.loc[df_flows['id']==flow_id, 'lastSeen']=flow.get('lastSeen')
                        df_flows.loc[df_flows['id']==flow_id, 'bytes']=flow.get('bytes')
                        df_flows.loc[df_flows['id']==flow_id, 'packets']=flow.get('packets')

                if new_flows_list:
                    df_flows=pd.concat([df_flows, pd.DataFrame(new_flows_list)], ignore_index=True) #adds rules to dataframe

            print(f"{dt.now().strftime('%H:%M:%S')} -> Flow rules data updated successfully.")

        except requests.exceptions.RequestException as e:
            print(f"{dt.now().strftime('%H:%M:%S')} -> Error updating flow rules list: {e}")

################################################################################################Exposed Server Endpoints
@app.route("/flows", methods=["GET"]) #exposes GET http://localhost:8081/flows
def get_all_flows():
    with flows_lock:
        return jsonify(df_flows.to_dict(orient="records")) #converts dataframe to JSON to be exposed

@app.route("/flows/<deviceId>", methods=["GET"]) #exposes GET http://localhost:8081/flows/<deviceId>
def get_flows_by_device(deviceId):
    with flows_lock:
        device_flows=df_flows[df_flows['deviceId']==deviceId] #filters only flow rules of the specified device
        if device_flows.empty:
            return jsonify({"error": "No flows found for this device or device not found"}), 404
        return jsonify(device_flows.to_dict(orient="records"))

####################################################################################################################Main
if __name__ == "__main__":
    fetch_data_from_onos() #get data from ONOS

    ###Starting threads for updating network info
    update_thread=threading.Thread(target=update_flows, daemon=True)
    update_thread.start()

    app.run(host="0.0.0.0", port=8081, debug=True, use_reloader=False) #runs Flask server at http://localhost:8081