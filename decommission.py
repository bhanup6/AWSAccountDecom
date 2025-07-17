import json
import logging
import requests
import time

from tfc import remove_resources_cli
from aws_account import close_aws_account

TFE_API_URL = "https://app.terraform.io/api/v2"

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def tfe_headers(token):
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/vnd.api+json"}

def get_workspaces(org, token):
    url = f"{TFE_API_URL}/organizations/{org}/workspaces"
    workspaces = []
    while url:
        r = requests.get(url, headers=tfe_headers(token))
        r.raise_for_status()
        d = r.json()
        workspaces += d["data"]
        url = d.get("links", {}).get("next")
    return workspaces

def trigger_destroy_run(ws_id, token):
    url = f"{TFE_API_URL}/runs"
    payload = {
        "data": {
            "type": "runs",
            "attributes": {"is-destroy": True, "message": "Automated destroy"},
            "relationships": {"workspace": {"data": {"type": "workspaces", "id": ws_id}}},
        }
    }
    r = requests.post(url, headers=tfe_headers(token), json=payload)
    r.raise_for_status()
    return r.json()["data"]["id"]

def wait_for_run(run_id, token):
    url = f"{TFE_API_URL}/runs/{run_id}"
    while True:
        r = requests.get(url, headers=tfe_headers(token))
        r.raise_for_status()
        status = r.json()["data"]["attributes"]["status"]
        if status in ["applied", "planned_and_finished"]:
            logging.info(f"Run {run_id} completed.")
            return True
        if status in ["errored", "canceled"]:
            raise Exception(f"Run {run_id} failed: {status}")
        time.sleep(10)

def destroy_and_delete_all_app_workspaces(org, token, app_ws_list):
    all_ws = get_workspaces(org, token)
    ws_map = {ws["attributes"]["name"]: ws["id"] for ws in all_ws}
    ws_list = app_ws_list if app_ws_list else list(ws_map.keys())

    for ws_name in ws_list:
        ws_id = ws_map.get(ws_name)
        if not ws_id:
            logging.warning(f"Workspace {ws_name} not found in org {org}, skipping.")
            continue
        run_id = trigger_destroy_run(ws_id, token)
        wait_for_run(run_id, token)
        requests.delete(f"{TFE_API_URL}/organizations/{org}/workspaces/{ws_name}", headers=tfe_headers(token))
        logging.info(f"Destroyed and deleted workspace {ws_name} in org {org}")

def destroy_management_workspace(org, workspace, token):
    ws_list = get_workspaces(org, token)
    for ws in ws_list:
        if ws["attributes"]["name"] == workspace:
            ws_id = ws["id"]
            run_id = trigger_destroy_run(ws_id, token)
            wait_for_run(run_id, token)
            requests.delete(f"{TFE_API_URL}/organizations/{org}/workspaces/{workspace}", headers=tfe_headers(token))
            logging.info(f"Destroyed and deleted management workspace {workspace}")
            return

def main():
    with open("config.json") as f:
        cfg = json.load(f)

    tfc_token = cfg["tfc_token"]
    mgmt_org = cfg["mgmt_org"]
    mgmt_ws = cfg["mgmt_ws"]
    app_org = cfg["app_org"]
    app_ws_list = cfg.get("app_ws_list", [])
    aws_account_id = cfg.get("aws_account_id")
    s3_resources = cfg.get("s3_buckets_to_remove", [])

    logging.info("Starting AWS account decommission workflow...")

    logging.info(f"Removing S3 bucket resources from management workspace state...")
    remove_resources_cli(mgmt_org, mgmt_ws, tfc_token, s3_resources)

    logging.info("Destroying and deleting all application workspaces...")
    destroy_and_delete_all_app_workspaces(app_org, tfc_token, app_ws_list)

    logging.info("Destroying and deleting management workspace...")
    destroy_management_workspace(mgmt_org, mgmt_ws, tfc_token)

    if aws_account_id and aws_account_id.lower() != "skip":
        #close_aws_account(aws_account_id)
        pass
    else:
        logging.info("Skipping AWS account closure step.")

    logging.info("Decommission workflow complete.")

if __name__ == "__main__":
    main()
