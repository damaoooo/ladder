import copy
import json
import os
import requests
import subprocess
import argparse
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
        f.close()


def get_pubkey(password):
    r = requests.post("https://ladderworker.damaoooo.com/pubkey",
                      json={"password": password})
    if r.status_code == 200:
        return r.json()
    else:
        print_red("Get pubkeys failed!")
        return {}


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

    def update_xray_config(self, xray_name: str, cdn_name: str, user_dict: dict):
        # update the certificate
        xray_cert_file = f"/etc/letsencrypt/live/{xray_name}/fullchain.pem"
        xray_cert_key = f"/etc/letsencrypt/live/{xray_name}/privkey.pem"

        cdn_cert_file = f"/etc/letsencrypt/live/{cdn_name}/fullchain.pem"
        cdn_cert_key = f"/etc/letsencrypt/live/{cdn_name}/privkey.pem"

        xray_cert_setting = {
            "ocspStapling": 3600,
            "certificateFile": xray_cert_file,
            "keyFile": xray_cert_key
        }

        cdn_cert_setting = {
            "ocspStapling": 3600,
            "certificateFile": cdn_cert_file,
            "keyFile": cdn_cert_key
        }

        if len(self.xray_config['inbounds'][0]['streamSettings']['tlsSettings']['certificates']) == 2:
            self.xray_config['inbounds'][0]['streamSettings']['tlsSettings']['certificates'] = [xray_cert_setting, cdn_cert_setting]

        if xray_cert_setting not in self.xray_config['inbounds'][0]['streamSettings']['tlsSettings']['certificates']:
            self.xray_config['inbounds'][0]['streamSettings']['tlsSettings']['certificates'].append(xray_cert_setting)

        if cdn_cert_setting not in self.xray_config['inbounds'][0]['streamSettings']['tlsSettings']['certificates']:
            self.xray_config['inbounds'][0]['streamSettings']['tlsSettings']['certificates'].append(cdn_cert_setting)

        # set the user id
        vision_reality_clients = []
        ws_clients = []

        for username in user_dict.keys():
            user_uuid = user_dict[username]
            vision_reality_clients.append({"id": user_uuid, "flow": "xtls-rprx-vision", "email": f"{username}@qq.com"})
            ws_clients.append({'id': user_uuid, "email": f"{username}@qq.com"})

        self.xray_config['inbounds'][0]['settings']['clients'] = vision_reality_clients
        self.xray_config['inbounds'][1]['settings']['clients'] = vision_reality_clients
        self.xray_config['inbounds'][2]['settings']['clients'] = ws_clients

    def save_xray_config(self, save_path: str):
        with open(save_path, "w") as f:
            content = json.dumps(self.xray_config, indent=4)
            f.write(content)


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

    def get_default_nic(self):
        command = "ip route"
        r = os.popen(command)
        info = r.readlines()
        for line in info:
            if "default" in line:
                return line.split()[4]
        else:
            return None

    def flush_iptables(self):
        command = "iptables -F -t nat"
        os.system(command)

    def add_iptables_nat_rule(self, default_nic):
        command = (f"iptables -t nat -A PREROUTING -i {default_nic} -p udp "
                   f"--dport {self.range_start}:{self.range_end} -j REDIRECT --to-ports {self.redirect_port}")
        os.system(command)

    def update_iptables_nat_rule(self):

        if self.default_nic:
            self.flush_iptables()
            self.add_iptables_nat_rule(self.default_nic)
            print_green("Update iptables successfully!, routing nic: {} from {}-{} to {}".format(self.default_nic,
                                                                                                  self.range_start,
                                                                                                  self.range_end,
                                                                                                  self.redirect_port))
        else:
            print_red("Get default nic failed!")

    def save_iptables_nat_rule(self):
        command = "netfilter-persistent save"
        os.system(command)


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--dns_name", type=str, help="The DNS name")
    args = arg_parser.parse_args()

    dns_name: str = args.dns_name

    password = input("Please input the password:")

    xray_name, cdn_name = create_dns_record(password, dns_name)

    xray_config, user_dict = get_configs(password)
    xray_config = json.loads(xray_config)
    xray_config_manager = XrayConfig(xray_config)
    xray_config_manager.update_xray_config(xray_name, cdn_name, user_dict)
    xray_config_manager.save_xray_config("./vless_config.json")

    hy2_config = Hy2Config("./hy2_config.yaml")
    hy2_config.update_hy2_config(xray_name, user_dict)
    hy2_config.save_hy2_config("./hy2_config.yaml")

    print_green("add iptables nat rule")
    nic_manager = NICManager()
    nic_manager.update_iptables_nat_rule()
    nic_manager.save_iptables_nat_rule()

    print_green("adding ssh key files")
    pubkey_dict = get_pubkey(password)
    pubkey_manager = PubKeyManager(pubkey_dict)
    pubkey_manager.update_authentication_file()

    print_green("Update configs successfully!")

    cf_token, _ = get_cloudflare_token(password)
    create_dns_file(cf_token, "./.dns_token")
