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
    print_message "Please run this script as root user!" "$RED"
	exit
fi

if command -v docker &> /dev/null; then
    print_message "Docker is already installed!" "$GREEN"
else
    print_message "Docker is not installed! Will Install it..." "$RED"
    # Install Docker
    curl -fsSL https://get.docker.com -o get-docker.sh
    sh get-docker.sh
fi


# docker get 
docker pull gogost/gost:3.0.0-rc8
docker pull ghcr.io/xtls/xray-core
docker pull certbot/dns-cloudflare
docker pull tobyxdd/hysteria
docker pull nginx

if command -v apt-get &> /dev/null; then
    apt-get update > /dev/null
    apt-get install -y git python3 python3-pip iptables-persistent > /dev/null
elif command -v dnf &> /dev/null; then
    dnf install -y git python3 python3-pip iptables-persistent > /dev/null
elif command -v yum &> /dev/null; then
    yum install -y git python3 python3-pip iptables-persistent > /dev/null
elif command -v pacman &> /dev/null; then
    pacman -Syu --noconfirm git python3 python3-pip iptables-persistent > /dev/null
else
    print_message "无法确定操作系统的包管理器，请手动安装" "$RED"
    exit 1
fi
print_message "git python pip 安装完成" "$GREEN"

if [ -f /etc/os-release ]; then
    . /etc/os-release
    if [ "$ID" = "ubuntu" ]; then
        if [ "$VERSION_ID" = "24.04" ]; then
            pip3 install -r ./requirements.txt --break-system-packages
        else
            pip3 install -r ./requirements.txt
        fi
    elif [ "$ID" = "debian" ]; then
        pip3 install -r ./requirements.txt --break-system-packages
    else
        echo "This is another distribution: $ID"
        pip3 install -r ./requirements.txt
    fi
else
    echo "/etc/os-release file not found."
    pip3 install -r ./requirements.txt
fi



read -p "Enter the DNS Full Name(aaa.bbb.ccc): " DNS_FULL_NAME

if [ -z "$DNS_FULL_NAME" ]; then
    print_message "DNS Full Name is empty" "$RED"
    exit 1
fi

python3 ./ladder.py --dns_name $DNS_FULL_NAME

docker run -it --rm --name certbot --net=host \
    -v "/etc/letsencrypt:/etc/letsencrypt" \
    -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
    -v "./.dns_token:/.token" \
    certbot/dns-cloudflare certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /.token \
    --dns-cloudflare-propagation-seconds 30 \
    -d "genshin-v4-${DNS_FULL_NAME}"

docker run -it --rm --name certbot --net=host \
    -v "/etc/letsencrypt:/etc/letsencrypt" \
    -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
    -v "./.dns_token:/.token" \
    certbot/dns-cloudflare certonly \
    --dns-cloudflare \
    --dns-cloudflare-credentials /.token \
    --dns-cloudflare-propagation-seconds 30 \
    -d "cdn-genshin-v4-${DNS_FULL_NAME}"

# Enable trojan and v2ray and nginx in docker-compose.yml
docker compose up -d

# To renew certificates
#docker run -it --rm --net=host --name certbot \
#    -v "/etc/letsencrypt:/etc/letsencrypt" \
#    -v "/var/lib/letsencrypt:/var/lib/letsencrypt" \
#    -v "./.dns_token:/.token" \
#    certbot/dns-cloudflare renew \
#    --dns-cloudflare-credentials /.token

rm ./.dns_token

# Monitor Sevice
cp ./ladder-monitor.service /etc/systemd/system/
systemctl enable ladder-monitor
systemctl start ladder-monitor