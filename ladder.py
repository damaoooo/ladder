import json
import os
import re
import requests
import subprocess
import argparse

ENDING = "\033[0m"
RED = "\033[1;31;0m"
GREEN = "\033[1;32;0m"

def print_red(text):
    print(RED+text+ENDING)
    
def print_green(text):
    print(GREEN+text+ENDING)

def get_cloudflare_token(password):
    r = requests.post("https://basic-bundle-curly-cherry-0f53.damaoooo.workers.dev/cf_token", json={"password": password})
    if r.status_code == 200:
        return r.json()['token'], r.json()['zone_id']
    else:
        print_red("Get cloudflare token failed!")
        return "", ""
    
def create_dns_file(dns_token: str, file_path: str = "./.dns_token"):
    with open(file_path, "w") as f:
        f.write("dns_cloudflare_api_token = {}".format(dns_token))
        f.close()
    
def get_configs(password):
    r = requests.post("https://basic-bundle-curly-cherry-0f53.damaoooo.workers.dev/config_file", json={"password": password})
    if r.status_code == 200:
        return r.json()['v2'], r.json()['trojan'], r.json()['nginx']
    else:
        print_red("Get configs failed!")
        return "", "", ""
    
def get_cert_abs_path(domain_name: str):
    link_path = f"/etc/letsencrypt/live/{domain_name}"
    key_path = os.path.join(link_path, "privkey.pem")
    fullchain_path = os.path.join(link_path, "fullchain.pem")
    key_path = os.path.realpath(key_path)
    fullchain_path = os.path.realpath(fullchain_path)
    
    return fullchain_path, key_path


class TrojanConfig:
    def __init__(self, trojan_config: dict):
        self.trojan_config = trojan_config
        
    def update_trojan_config(self, domain_name: str):
        
        port = self.trojan_config["local_port"]
        port = input("Input the trojan port(default: {}):".format(port)) or port
        
        link_path = f"/etc/letsencrypt/live/{domain_name}"
        self.trojan_config["local_port"] = port
        self.trojan_config["password"] = ["fuckyoub1tch"]
        self.trojan_config["ssl"]["cert"] = os.path.join(link_path, "fullchain.pem")
        self.trojan_config["ssl"]["key"] = os.path.join(link_path, "privkey.pem")
    
    def save_trojan_config(self, save_path: str):
        with open(save_path, "w") as f:
            content = json.dumps(self.trojan_config, indent=4)
            f.write(content)


class V2rayConfig:
    def __init__(self, v2ray_config: dict):
        self.v2ray_config = v2ray_config
        self.inner_port = 0
        self.ws_path = ""
        
    def update_v2ray_config(self):
        
        inner_port = self.v2ray_config["inbounds"][0]["port"]
        ws_path = self.v2ray_config["inbounds"][0]["streamSettings"]["path"]
        
        inner_port = input("Input the inner v2ray port(default: {}):".format(inner_port)) or inner_port
        ws_path = input("Input the ws path(default: {}):".format(ws_path)) or ws_path
        
        self.v2ray_config["inbounds"][0]["port"] = inner_port
        self.v2ray_config["inbounds"][0]["streamSettings"]["path"] = ws_path
        
        self.inner_port = inner_port
        self.ws_path = ws_path
        
    def save_v2ray_config(self, save_path: str):
        with open(save_path, "w") as f:
            content = json.dumps(self.v2ray_config, indent=4)
            f.write(content)


class NginxConfig:
    def __init__(self, nginx_config: str) -> None:
        self.nginx_config = nginx_config
        
    def update_nginx_config(self, domain_name: str, v2ray_port: int, ws_path: str):
        domain_cert_path = "/etc/letsencrypt/live/{}/fullchain.pem".format(domain_name)
        domain_key_path = "/etc/letsencrypt/live/{}/privkey.pem".format(domain_name)
        
        loaded_cert_path = re.findall(r"/etc/letsencrypt/live/.+/fullchain\.pem", self.nginx_config)[0]
        loaded_key_path = re.findall(r"/etc/letsencrypt/live/.+/privkey\.pem", self.nginx_config)[0]
    
        loaded_ws_path = re.findall(r"location .+ {", self.nginx_config)[0]
        loaded_v2ray_port = re.findall(r"http://127.0.0.1:\d+", self.nginx_config)[0]
        
        loaded_server_name = re.findall(r"server_name           .+;", self.nginx_config)[0]
        
        self.nginx_config = self.nginx_config.replace(loaded_cert_path, domain_cert_path)
        self.nginx_config = self.nginx_config.replace(loaded_key_path, domain_key_path)
        self.nginx_config = self.nginx_config.replace(loaded_ws_path, f"location {ws_path} {{")
        self.nginx_config = self.nginx_config.replace(loaded_v2ray_port, f"http://127.0.0.1:{v2ray_port}")
        self.nginx_config = self.nginx_config.replace(loaded_server_name, f"server_name           {domain_name};")
        
    def save_nginx_config(self, save_path: str):
        with open(save_path, "w") as f:
            f.write(self.nginx_config)
            
    
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
    
    trojan_dns = "trojan." + "v4." + dns_name
    v2ray_dns = "v2ray." + "v4." + dns_name
    
    ipv4 = get_ipv4()
    
    if dns_solver.check_dns_exist(trojan_dns):
        print_red("Trojan DNS already exists, check {}".format(trojan_dns))
        exit(1)
        
    if dns_solver.check_dns_exist(v2ray_dns):
        print_red("V2ray DNS already exists, check {}".format(v2ray_dns))
        exit(1)
        
    dns_solver.create_dns_record(trojan_dns, ipv4)
    dns_solver.create_dns_record(v2ray_dns, ipv4, proxied=True)
    
        
    print_green("Create DNS record successfully!")
    return trojan_dns, v2ray_dns
    

if __name__ == "__main__":
    
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("--dns_name", type=str, help="The DNS name")
    args = arg_parser.parse_args()
    
    dns_name: str = args.dns_name
    
    password = input("Please input the password:")

    trojan_name, v2ray_name = create_dns_record(password, dns_name)
    v2_config, trojan_config, nginx_config = get_configs(password)
    
    v2_config = json.loads(v2_config)
    trojan_config = json.loads(trojan_config)
    
    v2ray_config_manager = V2rayConfig(v2_config)
    trojan_config_manager = TrojanConfig(trojan_config)
    nginx_config_manager = NginxConfig(nginx_config)
    
    v2ray_config_manager.update_v2ray_config()
    trojan_config_manager.update_trojan_config(trojan_name)
    nginx_config_manager.update_nginx_config(v2ray_name, v2ray_config_manager.inner_port, v2ray_config_manager.ws_path)
    
    v2ray_config_manager.save_v2ray_config("./v2ray_config.json")
    trojan_config_manager.save_trojan_config("./trojan_config.json")
    nginx_config_manager.save_nginx_config("./nginx_config.conf")
    
    print_green("Update configs successfully!")
    
    cf_token, _ = get_cloudflare_token(password)
    create_dns_file(cf_token, "./.dns_token")
