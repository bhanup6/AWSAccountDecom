import subprocess
import os
import sys
import json
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

def write_backend_config(org, workspace):
    tf_backend = f'''
terraform {{
  cloud {{
    organization = "{org}"
    workspaces {{
      name = "{workspace}"
    }}
  }}
}}
'''
    with open('backend.tf', 'w') as f:
        f.write(tf_backend)
    logging.info(f"backend.tf written for {org}/{workspace}")

def write_terraform_credentials(token):
    """
    Automatically write Terraform CLI credentials file to enable non-interactive login.
    """
    appdata = os.environ.get("APPDATA")
    if appdata:
        creds_dir = os.path.join(appdata, "terraform.d")
    else:
        creds_dir = os.path.expanduser("~/.terraform.d")
    creds_file = os.path.join(creds_dir, "credentials.tfrc.json")

    if not os.path.exists(creds_dir):
        os.makedirs(creds_dir, mode=0o700)

    creds_content = {
        "credentials": {
            "app.terraform.io": {
                "token": token
            }
        }
    }

    with open(creds_file, "w") as f:
        json.dump(creds_content, f)
    os.chmod(creds_file, 0o600)
    logging.info(f"Terraform credentials file written at {creds_file}")

def ensure_terraform_init_and_login(org, workspace, token):
    """
    Writes backend config and credentials file,
    runs terraform init and selects workspace,
    ensuring full automation without manual login.
    """
    write_backend_config(org, workspace)
    write_terraform_credentials(token)

    # Run terraform init
    subprocess.run(["terraform", "init"], check=True)

    # Select existing or create new workspace locally
    try:
        subprocess.run(["terraform", "workspace", "select", workspace], check=True)
        logging.info(f"Selected existing workspace {workspace}")
    except subprocess.CalledProcessError:
        logging.info(f"Workspace {workspace} not found locally, creating it.")
        subprocess.run(["terraform", "workspace", "new", workspace], check=True)

def remove_resources_cli(org, workspace, token, resources):
    """
    Remove resources from terraform state using CLI with ensured login.
    """
    ensure_terraform_init_and_login(org, workspace, token)

    cmd = ["terraform", "state", "rm"] + resources
    subprocess.run(cmd, check=True)
    logging.info(f"Removed resources {resources} from state in workspace {workspace}")
