#!/bin/bash

# 添加颜色变量
RED="\e[31m"           # 红色
GREEN="\e[32m"         # 绿色
YELLOW="\e[33m"        # 黄色
RESET="\e[0m"          # 重置颜色

# 添加函数以显示不同颜色的消息
print_message() {
    local message="$1"
    local color="$2"
    echo -e "${color}${message}${RESET}"
}

if [ `whoami` != "root" ];then
    echo "Please run this script as root user!"
	exit
fi

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# dockerd-rootless-setuptool.sh install

# docker get 
docker pull gogost/gost:3.0.0-rc8
docker pull trojangfw/trojan
docker pull v2fly/v2fly-core
docker pull certbot/dns-cloudflare

if command -v apt &> /dev/null; then
    apt update > /dev/null
    apt install -y git python3 python3-pip > /dev/null
elif command -v apt-get &> /dev/null; then
    apt-get update > /dev/null
    apt-get install -y git python3 python3-pip > /dev/null
elif command -v dnf &> /dev/null; then
    dnf install -y git python3 python3-pip > /dev/null
elif command -v yum &> /dev/null; then
    yum install -y git python3 python3-pip > /dev/null
elif command -v pacman &> /dev/null; then
    pacman -Syu --noconfirm git python3 python3-pip > /dev/null
else
    print_message "无法确定操作系统的包管理器，请手动安装" "$RED"
    exit 1
fi
print_message "git python pip 安装完成" "$GREEN"

pip3 install requests

read -p "Enter the DNS Full Name(aaa.bbb.ccc): " DNS_FULL_NAME

if [ -z "$DNS_FULL_NAME" ]; then
    echo "DNS Full Name is empty"
    exit 1
fi

python ./ladder.py --dns_name $DNS_FULL_NAME

docker run -it --rm --name certbot \
    -v "/etc/letsencrypt:/etc/letsencrypt" \
    -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
    -v "./.dns_token:/.token" \
    certbot/dns-cloudflare certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /.token \
    -d "v2ray.v4.${DNS_FULL_NAME}"

docker run -it --rm --name certbot \
    -v "/etc/letsencrypt:/etc/letsencrypt" \
    -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
    -v "./.dns_token:/.token" \
    certbot/dns-cloudflare certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /.token \
    -d "trojan.v4.${DNS_FULL_NAME}"

# Enable trojan and v2ray and nginx in docker-compose.yml
docker compose up 
