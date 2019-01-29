import json
import pathlib
import time
import sys
import yaml
from nornir import InitNornir
from nornir.core.task import Result
from nornir.plugins.functions.text import print_result
from nornir.plugins.tasks.text import template_file
from nornir.plugins.tasks.files import write_file
from nornir.plugins.tasks import networking
from napalm.base import validate as npval
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
        task.host.open_connection("napalm", task.host)
        r = task.host.connections["napalm"].connection._get_checkpoint_file()
        task.host["backup_config"] = r
    else:
        r = task.run(
            task=networking.napalm_get,
            name="Backup Device Configuration",
            getters=["config"],
        )
        task.host["backup_config"] = r.result["config"]["running"]

    if task.host.platform == "eos":
        infile = task.host["backup_config"]
        infile = infile.split("\n")
        for index, line in enumerate(infile):
            if (
                len(line) - len(line.lstrip()) == 6
                and len(infile[index + 1]) - len(infile[index + 1].lstrip())
                != 6
            ):
                indent = " " * (
                    len(infile[index]) - len(infile[index].lstrip()) - 3
                )
                infile.insert(index + 1, f"{indent}!")
        outfile = "\n".join(infile)
        task.host["backup_config"] = outfile


def write_configs(task, backup=False):
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
        vars=task.host,
    )
    task.host["config"] = r.result


def deploy_configs(task, backup=False):
    """
    Nornir task to deploy device configurations.

    Args:
        task: nornir task object
        backup: bool Optional: deploy backup or newly generated configs to file
    """
    filename = task.host["dev_hostname"]
    if task.host.platform == "nxos":
        if backup is False:
            config = task.host["config"].encode()
        else:
            with open(f"backup/{filename}", "rb") as f:
                config = f.read()
    else:
        if backup is False:
            config = task.host["config"]
        else:
            with open(f"backup/{filename}", "r") as f:
                config = f.read()
    task.run(
        task=networking.napalm_configure,
        name="Deploy Configuration",
        configuration=config,
        replace=True,
    )


def napalm_tests(task):
    """
    Nornir task to deploy run napalm validate tests.

    Args:
        task: nornir task object
    """
    filename = task.host["dev_hostname"]
    task.run(
        task=networking.napalm_validate,
        name="Validate Deployed Configurations (NAPALM)",
        src=f"network_tests/{filename}_napalm.yaml",
    )


def netmiko_tests(task):
    """
    Nornir task to deploy run custom netmiko validate tests.

    Args:
        task: nornir task object
    """
    filename = task.host["dev_hostname"]
    with open(f"network_tests/{filename}_netmiko.yaml", "r") as f:
        validation_source = yaml.safe_load(f)
    task.run(
        task=netmiko_validate,
        name="Validate Deployed Configurations (Netmiko)",
        src=validation_source,
    )


class NXOSNetmikoTests:
    """
    Custom class for NAPALM-like Netmiko tests for demonstration purposes.
    """

    def __init__(self, task=None, port=22):
        self.task = task
        if "netmiko_port" in task.host.keys():
            port = task.host["netmiko_port"]
        else:
            port = 22
        task.host.open_connection("netmiko", task.host, port=port)

    def ospf_peer(
        self,
        context="default",
        process_id=1,
        interface=None,
        peer_address=None,
        peer_id=None,
    ):
        """
        Netmiko test to validate OSPF Peering

        Kwargs:
            context: str Optional: vrf/context for peer (not used yet...)
            prcoess_id: int(or str?) Optional: OSPF process ID
            interface: str fully qualified interface name
                (supports only 'Ethernet' at this point)
            peer_address: str IP address of OSPF peer
            peer_id: str Router ID of OSPF peer

        Returns:
            result:
        """
        result = {}
        interface = interface.replace("Ethernet", "Eth")
        cmd = f"show ip ospf neighbor {interface} | json"
        r = self.task.host.connections["netmiko"].connection.send_command(cmd)
        r = json.loads(r)

        try:
            peers = r["TABLE_ctx"]["ROW_ctx"]["TABLE_nbr"]["ROW_nbr"]
        except KeyError:
            peers = False

        if isinstance(peers, list):
            peer = [
                peer
                for peer in peers
                if peer["rid"] == peer_id and peer["addr"] == peer_address
            ] or None
        elif isinstance(peers, dict):
            peer = [peers]
        else:
            peer = peers

        if not peer:
            result["error"] = "No matching peer found."
        elif len(peer) != 1:
            result["error"] = "Multiple peer matches, something went wrong."
        else:
            peer = peer[0]
            result["success"] = {"state": peer["state"].upper()}
        return result


class EOSNetmikoTests:
    def __init__(self, task=None):
        self.task = task
        if "netmiko_port" in self.task.host.keys():
            port = self.task.host["netmiko_port"]
        else:
            port = 22
        self.task.host.open_connection("netmiko", task.host, port=port)

    def ospf_peer(
        self,
        context="default",
        process_id=1,
        interface=None,
        peer_address=None,
        peer_id=None,
    ):
        """
        Netmiko test to validate OSPF Peering

        Kwargs:
            context: str Optional: vrf/context for peer (not used yet...)
            prcoess_id: int(or str?) Optional: OSPF process ID
            interface: str fully qualified interface name
                (supports only 'Ethernet' at this point)
            peer_address: str IP address of OSPF peer
            peer_id: str Router ID of OSPF peer

        Returns:
            result:
        """
        result = {}
        cmd = f"show ip ospf neighbor {interface} | json"
        r = self.task.host.connections["netmiko"].connection.send_command(cmd)
        r = json.loads(r)
        peers = r["vrfs"][context]["instList"][str(process_id)][
            "ospfNeighborEntries"
        ]

        peer = [
            peer
            for peer in peers
            if peer["routerId"] == peer_id
            and peer["interfaceAddress"] == peer_address
        ] or None

        if not peer:
            result["error"] = "No matching peer found."
        elif len(peer) != 1:
            result["error"] = "Multiple peer matches, something went wrong."
        else:
            peer = peer[0]
            result["success"] = {"state": peer["adjacencyState"].upper()}
        return result


def netmiko_validate(task, src):
    """
    Plagarized from NAPALM;
        in here to support some temp custom Netmiko Test classes

    Args:
        src: NAPALM-like validation YAML file;
            supports only 'ospf_peer' at this time
    """
    report = {}
    if task.host.platform == "nxos":
        _class = NXOSNetmikoTests(task=task)
    elif task.host.platform == "eos":
        _class = EOSNetmikoTests(task=task)
    validation_source = src
    for validation_check in validation_source:
        for getter, expected_results in validation_check.items():
            key = expected_results.pop("_name", "") or getter
            try:
                kwargs = expected_results.pop("_kwargs", {})
                actual_results = getattr(_class, getter)(**kwargs)
                report[key] = npval.compare(expected_results, actual_results)
            except NotImplementedError:
                report[key] = {"skipped": True, "reason": "NotImplemented"}
    return Result(host=task.host, result=report)


def determine_validate_fails(validate_result):
    """
    Helper function to find all False for complies in validate reults.

    Args:
        validate_result: Nornir Result obj containing napalm/netmiko
            validate results

    Returns:
        failed_tasks: dict of hosts(str, key) and
            failed tasks(list, task names)
    """
    failed_tasks = {}
    for host, data in {k: v[1] for (k, v) in validate_result.items()}.items():
        for test, output in data.result.items():
            if test == "skipped":
                pass
            elif test == "complies":
                pass
            elif output["complies"] is False:
                failed_tasks.setdefault(host, []).append(test)
    return failed_tasks


if __name__ == "__main__":
    backup_task = nr.run(task=backup_configs)
    if any(r[0].failed is True for r in backup_task.values()):
        print_result(backup_task)
        print("Couldn't backup configs, exiting before causing any chaos!...")
        sys.exit(1)
    else:
        print("Backups completed successfully!")

    write_task = nr.run(task=write_configs, backup=True)
    if any(r[0].failed is True for r in write_task.values()):
        print_result(write_task)
    else:
        print("Writing backups to disk completed successfully!")

    render_task = nr.run(task=render_configs)
    if any(r[0].failed is True for r in render_task.values()):
        print_result(render_task)
    else:
        print("Rendering configurations completed successfully!")

    write_task = nr.run(task=write_configs)
    if any(r[0].failed is True for r in write_task.values()):
        print_result(write_task)
    else:
        print("Writing configurations to disk completed successfully!")

    deploy_task = nr.run(task=deploy_configs)
    if any(r[0].failed is True for r in deploy_task.values()):
        print_result(deploy_task)
    else:
        print("Deploying configurations completed successfully!")

    print("Sleeping for ten seconds before testing...")
    time.sleep(10)

    validate_task_napalm = nr.run(task=napalm_tests)
    napalm_failed_tasks = determine_validate_fails(validate_task_napalm)
    validate_task_netmiko = nr.run(task=netmiko_tests)
    netmiko_failed_tasks = determine_validate_fails(validate_task_netmiko)
    failed_tasks = {**napalm_failed_tasks, **netmiko_failed_tasks}

    if failed_tasks:
        print("The following task(s) failed:")
        for host, task in failed_tasks.items():
            print(f"Host: {host}, Task: {task}")
        rollback_task = nr.run(task=deploy_configs, backup=True)
        if any(r[0].failed is True for r in rollback_task.values()):
            print_result(rollback_task)
        else:
            print("Rollback of configurations completed successfully!")
    else:
        print("Validating configurations completed successfully!")
