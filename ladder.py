import copy
import json
import os
import requests
import subprocess
import argparse
import shutil
import getpass
import yaml
from typing import Union

ENDING = "\033[0m"
RED = "\033[1;31;0m"
GREEN = "\033[1;32;0m"


def print_red(text):
    print(RED + text + ENDING)


def print_green(text):
    print(GREEN + text + ENDING)


def get_cloudflare_token(password):
    r = requests.post("https://ladderworker.damaoooo.com/cf_token",
                      json={"password": password})
    if r.status_code == 200:
        return r.json()['token'], r.json()['zone_id']
    else:
        print_red("Get cloudflare token failed!")
        return "", ""


def create_dns_file(dns_token: str, file_path: str = "./.dns_token"):
    with open(file_path, "w") as f:
        f.write("dns_cloudflare_api_token = {}".format(dns_token))
    os.chmod(file_path, 0o600)


def get_pubkey(password):
    r = requests.post("https://ladderworker.damaoooo.com/pubkey",
                      json={"password": password})
    if r.status_code == 200:
        return r.json()
    else:
        print_red("Get pubkeys failed!")
        return {}
    
def get_stats_token(password):
    r = requests.post("https://ladderworker.damaoooo.com/stats_token",
                      json={"password": password})
    if r.status_code == 200:
        return r.json()['token']
    else:
        print_red("Get stats token failed!")
        return ""


def get_configs(password):
    r = requests.post("https://ladderworker.damaoooo.com/config_file",
                      json={"password": password})
    if r.status_code == 200:
        return r.json()['v2'], r.json()['user']
    else:
        print_red("Get configs failed!")
        return "", ""


def get_cert_abs_path(domain_name: str):
    link_path = f"/etc/letsencrypt/live/{domain_name}"
    key_path = os.path.join(link_path, "privkey.pem")
    fullchain_path = os.path.join(link_path, "fullchain.pem")
    key_path = os.path.realpath(key_path)
    fullchain_path = os.path.realpath(fullchain_path)

    return fullchain_path, key_path


class PubKeyManager:
    def __init__(self, dict_pubkey: dict, ssh_file_path: str = "/root/.ssh/authorized_keys"):
        self.pubkey = dict_pubkey
        self.ssh_file_path = ssh_file_path

    def check_authentication_file(self):
        if not os.path.exists(self.ssh_file_path):
            ssh_folder = os.path.dirname(self.ssh_file_path)

            if not os.path.exists(ssh_folder):
                os.makedirs(ssh_folder)

            # Run "yes y | ssh-keygen -t rsa -b 4096 -f ~/.ssh/id_rsa -q -N """
            os.system("yes y | ssh-keygen -t rsa -b 4096 -f {} -q -N \"\"".format(os.path.join(ssh_folder, "id_rsa")))

        if not os.path.exists(self.ssh_file_path):
            # Create the file
            with open(self.ssh_file_path, "w") as f:
                f.write("")
                f.close()

    def update_authentication_file(self):

        self.check_authentication_file()

        with open(self.ssh_file_path, "r") as f:
            all_file = f.read()
            f.close()

        new_file = copy.deepcopy(all_file)
        for username in self.pubkey.keys():
            if self.pubkey[username] not in all_file:
                new_file += "\n" + self.pubkey[username] + "\n"

        with open(self.ssh_file_path, "w") as f:
            f.write(new_file)
            f.close()


class XrayConfig:
    def __init__(self, Xray_config: Union[dict, str]):
        if isinstance(Xray_config, dict):
            self.xray_config = Xray_config
        else:
            with open(Xray_config, "r") as f:
                self.xray_config = json.load(f)

    @staticmethod
    def build_clients(user_dict: dict, template_client: dict):
        clients = []
        for username in user_dict.keys():
            user_uuid = user_dict[username]
            client = copy.deepcopy(template_client)
            client['id'] = user_uuid
            client['email'] = f"{username}@qq.com"
            clients.append(client)
        return clients

    @staticmethod
    def format_template_value(value, variables: dict):
        if isinstance(value, str):
            rendered = value
            for key, item in variables.items():
                rendered = rendered.replace('{' + key + '}', item)
            return rendered
        if isinstance(value, list):
            return [XrayConfig.format_template_value(item, variables) for item in value]
        if isinstance(value, dict):
            return {key: XrayConfig.format_template_value(item, variables) for key, item in value.items()}
        return value

    def update_xray_config(self, xray_name: str, cdn_name: str, user_dict: dict):
        variables = {
            'xray_name': xray_name,
            'cdn_name': cdn_name,
        }
        self.xray_config = self.format_template_value(self.xray_config, variables)
        self.update_clients(user_dict)

    def update_clients(self, user_dict: dict):
        for inbound in self.xray_config.get('inbounds', []):
            settings = inbound.get('settings')
            if not isinstance(settings, dict):
                continue

            clients = settings.get('clients')

            if not isinstance(clients, list) or not clients:
                continue

            settings['clients'] = self.build_clients(user_dict, clients[0])

    def save_xray_config(self, save_path: str):
        with open(save_path, "w") as f:
            content = json.dumps(self.xray_config, indent=4)
            f.write(content)

    def get_inner_xhttp_port(self):
        for inbound in self.xray_config.get('inbounds', []):
            if inbound.get('tag') == 'inner-xhttp':
                return inbound['port']

        for inbound in self.xray_config.get('inbounds', []):
            stream_settings = inbound.get('streamSettings', {})
            if (
                inbound.get('listen') in ('127.0.0.1', 'localhost')
                and stream_settings.get('network') == 'xhttp'
                and stream_settings.get('security', 'none') == 'none'
            ):
                return inbound['port']

        raise ValueError("inner-xhttp inbound port not found")


class NginxConfig:
    def __init__(self, template_path: str = "./nginx.conf"):
        with open(template_path, "r") as f:
            self.nginx_config = f.read()

    def update_nginx_config(self, xray_name: str, cdn_name: str, xhttp_port: Union[int, str]):
        replacements = {
            "__XRAY_NAME__": xray_name,
            "__CDN_NAME__": cdn_name,
            "__XHTTP_PORT__": str(xhttp_port),
        }
        for old, new in replacements.items():
            self.nginx_config = self.nginx_config.replace(old, new)

    def save_nginx_config(self, save_path: str):
        with open(save_path, "w") as f:
            f.write(self.nginx_config)


class Hy2Config:
    def __init__(self, hy2_config: Union[dict, str]):
        if isinstance(hy2_config, dict):
            self.hy2_config = hy2_config
        else:
            with open(hy2_config, "r") as f:
                self.hy2_config = yaml.load(f, Loader=yaml.FullLoader)

    def update_hy2_config(self, domain_name: str, user_dict: dict):
        self.hy2_config['tls']['cert'] = f"/etc/letsencrypt/live/{domain_name}/fullchain.pem"
        self.hy2_config['tls']['key'] = f"/etc/letsencrypt/live/{domain_name}/privkey.pem"

        self.hy2_config['auth']['userpass'] = user_dict

    def save_hy2_config(self, save_path: str):

        with open(save_path, "w") as f:
            content = yaml.dump(self.hy2_config, default_flow_style=False)
            f.write(content)


class DNSSolver:
    def __init__(self, zone_id: str, token: str) -> None:
        self.zone_id = zone_id
        self.token = token

    def check_dns_exist(self, domain_name):
        url = "https://api.cloudflare.com/client/v4/zones/{}/dns_records".format(self.zone_id)
        header = {'Authorization': 'Bearer ' + self.token}
        params = {"search": domain_name}

        r = requests.get(url, headers=header, params=params)

        if r.status_code == 400:
            print("Token is invalid!")
            return False

        data = r.json()
        if len(data["result"]):
            # Print the record
            output_dns = []
            for i in range(len(data["result"])):
                dns_name = data["result"][i]["name"]
                dns_type = data["result"][i]["type"]
                dns_ip = data["result"][i]["content"]
                string = "Type:{:6s}Name:{:40s}IP:{:16s}".format(dns_type, dns_name, dns_ip)
                output_dns.append(string)
            print('\n'.join(output_dns))
            return True
        else:
            return False

    def create_dns_record(self, domain_name, ip, record_type="A", proxied=False):
        url = "https://api.cloudflare.com/client/v4/zones/{}/dns_records".format(self.zone_id)
        header = {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}
        data = {
            "type": record_type,
            "name": domain_name,
            "content": ip,
            "ttl": 1,
            "proxied": proxied
        }

        r = requests.post(url, headers=header, json=data)
        assert r.status_code == 200
        ret = r.json()
        if ret['success']:
            return True
        else:
            print("Create DNS Failed", ret)
            return False


class EnvManager:
    def __init__(self):
        self.env_file = "./.env"

    def check_env_file(self):
        if not os.path.exists(self.env_file):
            with open(self.env_file, "w") as f:
                f.write("")
                f.close()

    def write_stat_password(self, password: str):
        self.check_env_file()

        with open(self.env_file, "r") as f:
            all_file = f.read()
            f.close()

        new_file = copy.deepcopy(all_file)
        if "STAT_PASSWORD" not in all_file:
            new_file += f"\nSTAT_PASSWORD={password}\n"
        else:
            # Find and replace the entire line containing STAT_PASSWORD
            lines = new_file.split('\n')
            for i, line in enumerate(lines):
                if line.startswith('STAT_PASSWORD='):
                    lines[i] = f"STAT_PASSWORD={password}"
            new_file = '\n'.join(lines)

        with open(self.env_file, "w") as f:
            f.write(new_file)

    def update_env_file(self, stats_token: str):
        self.write_stat_password(stats_token)

def get_ipv4():
    p = subprocess.Popen(["curl", "-4", "ip.sb"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = p.communicate()
    return stdout.decode()


def create_dns_record(password: str, dns_name: str):
    cf_token, zone_id = get_cloudflare_token(password)

    if not cf_token:
        print_red("Get cloudflare token failed!")
        return

    dns_solver = DNSSolver(zone_id=zone_id, token=cf_token)

    xray_dns = "genshin-" + "v4-" + dns_name
    cdn_dns = "cdn-genshin-" + "v4-" + dns_name

    ipv4 = get_ipv4()

    if dns_solver.check_dns_exist(xray_dns):
        print_red("XRay DNS already exists, check {}".format(xray_dns))
    else:
        dns_solver.create_dns_record(xray_dns, ipv4)

    if dns_solver.check_dns_exist(cdn_dns):
        print_red("CDN-XRay DNS already exists, check {}".format(cdn_dns))
    else:
        dns_solver.create_dns_record(cdn_dns, ipv4, proxied=True)

    print_green("Create DNS record successfully!")
    return xray_dns, cdn_dns


class NICManager:
    def __init__(self):
        self.range_start = 40000
        self.range_end = 41000
        self.redirect_port = 443
        self.default_nic = self.get_default_nic()
        self.table = "nat"
        self.chain = "PREROUTING"

    def get_default_nic(self):
        command = "ip route"
        r = os.popen(command)
        info = r.readlines()
        for line in info:
            if "default" in line:
                return line.split()[4]
        else:
            return None

    def get_redirect_rule(self, default_nic):
        return [
            "-i", default_nic,
            "-p", "udp",
            "--dport", f"{self.range_start}:{self.range_end}",
            "-j", "REDIRECT",
            "--to-ports", str(self.redirect_port),
        ]

    def iptables_rule_exists(self, default_nic):
        command = [
            "iptables",
            "-t", self.table,
            "-C", self.chain,
            *self.get_redirect_rule(default_nic),
        ]
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return result.returncode == 0

    def add_iptables_nat_rule(self, default_nic):
        command = [
            "iptables",
            "-t", self.table,
            "-A", self.chain,
            *self.get_redirect_rule(default_nic),
        ]
        subprocess.run(command, check=True)

    def update_iptables_nat_rule(self):

        if self.default_nic:
            if self.iptables_rule_exists(self.default_nic):
                print_green("Iptables rule already exists, routing nic: {} from {}-{} to {}".format(self.default_nic,
                                                                                                     self.range_start,
                                                                                                     self.range_end,
                                                                                                     self.redirect_port))
            else:
                self.add_iptables_nat_rule(self.default_nic)
                print_green("Add iptables rule successfully!, routing nic: {} from {}-{} to {}".format(self.default_nic,
                                                                                                        self.range_start,
                                                                                                        self.range_end,
                                                                                                        self.redirect_port))
        else:
            print_red("Get default nic failed!")

    def save_iptables_nat_rule(self):
        command = shutil.which("netfilter-persistent")
        if command:
            subprocess.run([command, "save"], check=False)
        else:
            print_red("netfilter-persistent not found, iptables rule is active but not persisted")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--dns_name", type=str, help="The DNS name")
    args = arg_parser.parse_args()

    dns_name: str = args.dns_name

    password = getpass.getpass("Please input the password:")

    xray_name, cdn_name = create_dns_record(password, dns_name)

    xray_template, user_dict = get_configs(password)
    xray_template = json.loads(xray_template)
    xray_config_manager = XrayConfig(xray_template)
    xray_config_manager.update_xray_config(xray_name, cdn_name, user_dict)
    xray_config_manager.save_xray_config("./vless_config.json")

    nginx_config = NginxConfig("./nginx.conf")
    nginx_config.update_nginx_config(xray_name, cdn_name, xray_config_manager.get_inner_xhttp_port())
    nginx_config.save_nginx_config("./nginx.generated.conf")

    hy2_config = Hy2Config("./hy2_config.yaml")
    hy2_config.update_hy2_config(xray_name, user_dict)
    hy2_config.save_hy2_config("./hy2_config.generated.yaml")

    print_green("add iptables nat rule")
    nic_manager = NICManager()
    nic_manager.update_iptables_nat_rule()
    nic_manager.save_iptables_nat_rule()

    print_green("adding ssh key files")
    pubkey_dict = get_pubkey(password)
    pubkey_manager = PubKeyManager(pubkey_dict)
    pubkey_manager.update_authentication_file()

    print_green("adding .env file")
    stats_token = get_stats_token(password)
    env_manager = EnvManager()
    env_manager.update_env_file(stats_token)

    print_green("Update configs successfully!")

    cf_token, _ = get_cloudflare_token(password)
    create_dns_file(cf_token, "./.dns_token")
    
    print_green("DNS file created successfully!")
    print_green("All done!")
