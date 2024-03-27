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


if command -v apt-get &> /dev/null; then
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

git clone https://github.com/damaoooo/ladder.git

cd ladder

chmod +x start.sh

./start.sh

rm .dns_token
