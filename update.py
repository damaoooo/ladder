from ladder import get_configs, XrayConfig, print_green, print_red
import argparse
import os
import json


def get_args():
    """
    Get arguments from command line
    Arg List:
    -p, --password: The password
    -d, --dns_name: The DNS name
    :return: args
    """
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument("-p", "--password", type=str, help="The password")
    arg_parser.add_argument("-d", "--dns_name", type=str, help="The DNS name")
    args = arg_parser.parse_args()
    return args


def is_root():
    return os.geteuid() == 0


def restart_docker_compose():
    # check file "docker-compose.yml" exists
    if not os.path.exists("./docker-compose.yml"):
        print_red("docker-compose.yml not exists!")
        return
    else:
        os.system("docker-compose down")
        os.system("docker-compose up -d")
        print_green("Restart docker-compose successfully!")


def update_configs(password: str, dns_name: str):
    xray_config, user_dict = get_configs(password)
    xray_config = json.loads(xray_config)
    xray_config_manager = XrayConfig(xray_config)

    xray_name = "genshin-v4-" + dns_name
    cdn_name = "cdn-genshin-v4-" + dns_name

    xray_config_manager.update_xray_config(xray_name, cdn_name, user_dict)
    xray_config_manager.save_xray_config("./vless_config.json")

    print_green("Update configs successfully!")


if __name__ == "__main__":
    args = get_args()
    password = args.password
    dns_name = args.dns_name

    if not is_root():
        print_red("Please run this script as root!")
        exit(1)

    update_configs(password, dns_name)
    restart_docker_compose()

    print_green("All done!")