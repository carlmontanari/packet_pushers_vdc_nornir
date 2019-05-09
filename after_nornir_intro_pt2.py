import pathlib
from nornir import InitNornir
from nornir.plugins.functions.text import print_result
from nornir.plugins.tasks.text import template_file
from nornir.plugins.tasks.files import write_file
from nornir.plugins.tasks import networking
import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning

# Disable urllib3 warnings
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)

# Initialize Nornir object from config_file
nr = InitNornir(config_file="config.yaml")


def backup_configs(task):
    """
    Nornir task to backup device configurations.

    Args:
        task: nornir task object
    """
    if task.host.platform == "nxos":
        task.host.open_connection("napalm", None)
        r = task.host.connections["napalm"].connection._get_checkpoint_file()
        task.host["backup_config"] = r
    else:
        r = task.run(
            task=networking.napalm_get,
            name="Backup Device Configuration",
            getters=["config"],
        )
        task.host["backup_config"] = r.result["config"]["running"]


def write_configs(task, backup=False, diff=False):
    """
    Nornir task to write device configurations to disk.

    Args:
        task: nornir task object

    Kwargs:
        backup: bool Optional: write backup or newly generated configs to file
    """
    filename = task.host["dev_hostname"]
    if backup is False:
        pathlib.Path("configs").mkdir(exist_ok=True)
        task.run(
            task=write_file,
            filename=f"configs/{filename}",
            content=task.host["config"],
        )
    else:
        pathlib.Path("backup").mkdir(exist_ok=True)
        task.run(
            task=write_file,
            filename=f"backup/{filename}",
            content=task.host["backup_config"],
        )


def render_configs(task):
    """
    Nornir task to render device configurations from j2 templates.

    Args:
        task: nornir task object
    """
    filename = task.host["j2_template_file"]
    r = task.run(
        task=template_file,
        name="Base Template Configuration",
        template=filename,
        path="templates",
        **task.host,
    )
    task.host["config"] = r.result


def deploy_configs(task, dry_run=False, diff=False, backup=False):
    """
    Nornir task to deploy device configurations.

    Args:
        task: nornir task object
        backup: bool Optional: deploy backup or newly generated configs to file
    """
    filename = task.host["dev_hostname"]
    if backup is False:
        config = task.host["config"]
    else:
        with open(f"backup/{filename}", "rb") as f:
            config = f.read()

    deployment = task.run(
        task=networking.napalm_configure,
        name="Deploy Configuration",
        configuration=config,
        replace=True,
        dry_run=dry_run,
    )
    task.host["diff"] = deployment.diff
    if diff:
        pathlib.Path("diffs").mkdir(exist_ok=True)
        task.run(
            task=write_file,
            filename=f"diffs/{filename}",
            content=task.host["diff"],
        )


if __name__ == "__main__":
    render_task = nr.run(task=render_configs)
    write_task = nr.run(task=write_configs)
    backup_task = nr.run(task=backup_configs)
    write_task = nr.run(task=write_configs, backup=True)
    deploy_task = nr.run(task=deploy_configs, dry_run=True, diff=True)
    deploy_task = nr.run(task=deploy_configs, dry_run=False, diff=False)
    print_result(deploy_task)
