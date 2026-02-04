# 标准库
import os
import re
import random
import ipaddress
import subprocess
import concurrent.futures
import platform

# 第三方库
import requests
from lxml import etree
from fake_useragent import UserAgent
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 华为云SDK
from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkdns.v2 import DnsClient
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion
from huaweicloudsdkdns.v2.model import *
from huaweicloudsdkcore.exceptions import exceptions

# 文件配置
ips = "Fission_ip.txt"
domains = "Fission_domain.txt"
dns_result = "dns_result.txt"

# 华为云账号AccessKey，请填写您的AccessKey
access_key_id = 'HPUACWBMV5S86XLHYVLC'
access_key_secret = '54YIlbgKcn35oyeDlwoNcioaz0uZeaPgB5FJLUvN'

# 创建认证信息
credentials = BasicCredentials(access_key_id, access_key_secret)

# 创建DNS客户端
client = DnsClient.new_builder() \
    .with_credentials(credentials) \
    .with_region(DnsRegion.value_of("cn-north-4")) \
    .build()

# 域名配置
ZONE_NAME = "2808225.xyz"
RECORD_NAME = "华为云.2808225.xyz"


# 并发数配置
max_workers_request = 10   # 并发请求数量
max_workers_dns = 20       # 并发DNS查询数量

# 生成随机User-Agent
ua = UserAgent()

# 网站配置
sites_config = {
    "site_ip138": {
        "url": "https://site.ip138.com/",
        "xpath": '//ul[@id="list"]/li/a'
    },
    "dnsdblookup": {
        "url": "https://dnsdblookup.com/",
        "xpath": '//ul[@id="list"]/li/a'
    },
    "ipchaxun": {
        "url": "https://ipchaxun.com/",
        "xpath": '//div[@id="J_domain"]/p/a'
    }
}

# 设置会话
def setup_session():
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

# 生成请求头
def get_headers():
    return {
        'User-Agent': ua.random,
        'Accept': '*/*',
        'Connection': 'keep-alive',
    }

# 查询域名的函数，自动重试和切换网站
def fetch_domains_for_ip(ip_address, session, attempts=0, used_sites=None):
    if used_sites is None:
        used_sites = []
    if attempts >= 3:  # 如果已经尝试了3次，终止重试
        return []

    # 选择一个未使用的网站进行查询
    available_sites = {key: value for key, value in sites_config.items() if key not in used_sites}
    if not available_sites:
        return []  # 如果所有网站都尝试过，返回空结果

    site_key = random.choice(list(available_sites.keys()))
    site_info = available_sites[site_key]
    used_sites.append(site_key)

    try:
        url = f"{site_info['url']}{ip_address}/"
        headers = get_headers()
        response = session.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        html_content = response.text

        parser = etree.HTMLParser()
        tree = etree.fromstring(html_content, parser)
        a_elements = tree.xpath(site_info['xpath'])
        domains = [a.text for a in a_elements if a.text]

        if domains:
            return domains
        else:
            raise Exception("No domains found")

    except Exception as e:
        return fetch_domains_for_ip(ip_address, session, attempts + 1, used_sites)

# 并发处理所有IP地址
def fetch_domains_concurrently(ip_addresses):
    session = setup_session()
    domains = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_request) as executor:
        future_to_ip = {executor.submit(fetch_domains_for_ip, ip, session): ip for ip in ip_addresses}
        for future in concurrent.futures.as_completed(future_to_ip):
            domains.extend(future.result())

    return list(set(domains))

# DNS查询函数
def dns_lookup(domain):
    # print(f"Performing DNS lookup for {domain}...")
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)
    return domain, result.stdout

# 通过域名列表获取绑定过的所有ip
def perform_dns_lookups(domain_filename, result_filename, unique_ipv4_filename):
    try:
        # 读取域名列表
        with open(domain_filename, 'r') as file:
            domains = file.read().splitlines()

        # 创建一个线程池并执行DNS查询
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_dns) as executor:
            results = list(executor.map(dns_lookup, domains))

        # 写入查询结果到文件
        with open(result_filename, 'w') as output_file:
            for domain, output in results:
                output_file.write(output)

        # 从结果文件中提取所有IPv4地址
        ipv4_addresses = set()
        for _, output in results:
            ipv4_addresses.update(re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', output))

        with open(unique_ipv4_filename, 'r') as file:
            exist_list = {ip.strip() for ip in file}

        # 检查IP地址是否为公网IP，并且不是43前缀
        filtered_ipv4_addresses = set()
        for ip in ipv4_addresses:
            try:
                ip_obj = ipaddress.ip_address(ip)
                if ip_obj.is_global and not ip.startswith("43."):
                    filtered_ipv4_addresses.add(ip)
            except ValueError:
                # 忽略无效IP地址
                continue
        
        # 同样过滤exist_list中的43前缀IP
        filtered_exist_list = {ip for ip in exist_list if not ip.startswith("43.")}
        filtered_ipv4_addresses.update(filtered_exist_list)

        # 保存IPv4地址
        with open(unique_ipv4_filename, 'w') as output_file:
            for address in filtered_ipv4_addresses:
                output_file.write(address + '\n')

    except Exception as e:
        print(f"Error performing DNS lookups: {e}")

# 主函数
def main():
    # 判断是否存在IP文件
    if not os.path.exists(ips):
        with open(ips, 'w') as file:
            file.write("")
    
    # 判断是否存在域名文件
    if not os.path.exists(domains):
        with open(domains, 'w') as file:
            file.write("")

    # IP反查域名
    with open(ips, 'r') as ips_txt:
        ip_list = [ip.strip() for ip in ips_txt]

    domain_list = fetch_domains_concurrently(ip_list)
    # print("域名列表为")
    # print(domain_list)
    with open("Fission_domain.txt", "r") as file:
        exist_list = [domain.strip() for domain in file]

    domain_list = list(set(domain_list + exist_list))

    with open("Fission_domain.txt", "w") as output:
        for domain in domain_list:
            output.write(domain + "\n")
    print("IP -> 域名 已完成")

    # 域名解析IP
    perform_dns_lookups(domains, dns_result, ips)
    print("域名 -> IP 已完成")
    
    # 清空Fission_domain.txt文件内容
    with open(domains, 'w') as file:
        file.write('')
    # print("已清空Fission_domain.txt文件内容")
    
    # 清空dns_result.txt文件内容
    with open(dns_result, 'w') as file:
        file.write('')
    # print("已清空dns_result.txt文件内容")
    
    # ========== 整合you.py中的ping功能 ==========
    print("\n开始执行ping测试功能...")
    
    # ping指定IP地址并获取响应时间
    def request_ip_status(ip, port=None, use_https=False, timeout=5):
        try:
            # 根据操作系统构建ping命令
            if platform.system().lower() == "windows":
                # Windows系统的ping命令
                command = ["ping", "-n", "2", "-w", str(timeout * 1000), ip]
            else:
                # Linux/Mac系统的ping命令
                command = ["ping", "-c", "2", "-W", str(timeout), ip]
            
            # 执行ping命令
            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout + 1
            )
            
            # 检查ping是否成功
            if result.returncode == 0:
                # 提取响应时间
                stdout = result.stdout
                avg_time_ms = None
                
                if platform.system().lower() == "windows":
                    # Windows格式：平均 = 123ms
                    match = re.search(r"平均\s*=\s*(\d+)ms", stdout)
                else:
                    # Linux/Mac格式：avg = 123.456 ms
                    match = re.search(r"avg\s*=\s*(\d+\.?\d*)\s*ms", stdout)
                
                if match:
                    avg_time_ms = float(match.group(1))
                
                return (1, avg_time_ms)  # ping成功
            else:
                return (0, None)  # ping失败
        except subprocess.TimeoutExpired:
            # print(f"ping超时 ({timeout}秒)")
            return (0, None)
        except Exception as e:
            print(f"ping出错: {type(e).__name__}: {e}")
            return None
    
    # 执行ping测试
    def run_ping_tests():
        # 配置文件路径
        ip_file = "Fission_ip.txt"
        
        # 配置超时时间
        timeout = 3
        
        # 多线程配置
        max_workers_ping = 50  # 并发ping测试数量
        
        try:
            # 读取IP地址列表
            with open(ip_file, 'r') as f:
                ip_addresses = [line.strip() for line in f if line.strip()]
            
            if not ip_addresses:
                print("IP地址列表为空")
            else:
                # 开始ping测试，不打印详细信息
                
                # 存储成功的ping结果，用于速度比较
                ping_results = []
                
                # 存储响应时间小于200ms的IP信息
                fast_ips = []
                
                # 使用多线程执行ping测试
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_ping) as executor:
                    # 提交所有ping测试任务
                    future_to_ip = {
                        executor.submit(request_ip_status, ip, timeout=timeout): ip 
                        for ip in ip_addresses
                    }
                    
                    # 收集所有任务的结果
                    for future in concurrent.futures.as_completed(future_to_ip):
                        ip = future_to_ip[future]
                        try:
                            ping_result = future.result()
                            
                            if ping_result is not None:
                                success, avg_time_ms = ping_result
                                
                                if success == 1:
                                    # 如果获取到响应时间，添加到结果列表
                                    if avg_time_ms is not None:
                                        # 保存结果用于速度比较
                                        ping_results.append({
                                            "ip": ip,
                                            "time": avg_time_ms
                                        })
                                        
                                        # 检查响应时间是否小于200ms，并且IP不是43前缀，同时IP必须以1开头
                                        if avg_time_ms < 100.0 and not ip.startswith("43.") and ip.startswith("1"):
                                            fast_ips.append({
                                                "ip": ip,
                                                "time": avg_time_ms
                                            })
                        except Exception as e:
                            pass
                
                if fast_ips:
                    try:
                        with open("dns_result.txt", "w", encoding="utf-8") as f:
                            for result in fast_ips:
                                f.write(f"{result['ip']} - 响应时间: {result['time']}ms\n")
                        print(f"\n已将 {len(fast_ips)} 个响应时间小于100ms的IP信息保存到dns_result.txt文件")
                    except Exception as e:
                        print(f"\n保存文件出错: {e}")
                else:
                    print("\n没有响应时间小于100ms的IP地址")
                
                # 删除Fission_ip.txt文件内容并添加104.18.38.23数据
                try:
                    with open("Fission_ip.txt", "w", encoding="utf-8") as f:
                        f.write("104.18.38.23\n")
                    # print("已更新Fission_ip.txt文件内容，仅保留104.18.38.23")
                except Exception as e:
                    print(f"更新Fission_ip.txt文件出错: {e}")
        except Exception as e:
            print(f"读取文件出错: {e}")
    
    # 运行ping测试
    run_ping_tests()
    
    # ========== 执行DNS更新 ==========
    print("\n开始执行DNS更新功能...")
    
    def update_dns_main():
        # 获取脚本所在目录
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_file = os.path.join(script_dir, 'dns_result.txt')
        
        # 先读取IP列表
        ips_by_operator = {
            '全网默认': [],
            '中国移动': [],
            '中国电信': [],
            '中国联通': [],
            '港澳台': []
        }
        
        # 读取所有IP地址
        all_ips = []
        try:
            with open(input_file, 'r', encoding='utf-8') as f:
                # 提取每行中的IP地址
                for line in f.read().splitlines():
                    line = line.strip()
                    if line:
                        # 从格式 "IP - 响应时间: XX.0ms" 中提取IP
                        parts = line.split(' - ')
                        if parts:
                            ip = parts[0].strip()
                            all_ips.append(ip)
            
        except Exception as e:
            print(f'读取文件失败: {str(e)}')
            return
        
        # 按照文件顺序分配IP到对应运营商
        # 规则：前2个IP写入全网默认，接下来2个写入中国移动，以此类推
        operators = ['全网默认', '中国移动', '中国电信', '中国联通', '港澳台']
        ip_index = 0
        
        for operator in operators:
            # 每个运营商分配2个IP
            for _ in range(2):
                if ip_index < len(all_ips):
                    ips_by_operator[operator].append(all_ips[ip_index])
                    ip_index += 1
        
        # 获取文件中存在的运营商列表
        existing_operators = [op for op, ips in ips_by_operator.items() if len(ips) > 0]
        print(f'文件中包含的运营商: {existing_operators}')
        
        # 获取所有A记录
        print('正在获取所有A记录...')
        records = get_all_a_records()
        if not records:
            print('未找到任何A记录，无需删除')
        else:
            print(f'找到{len(records)}条A记录，准备比对...')
        
        # 只删除目标域名的A记录
        target_name = RECORD_NAME + "."
        to_delete = []
        
        for record in records:
            if record.get('Name') == target_name:
                to_delete.append(record['RecordsetId'])

        
        if to_delete:
            print(f'正在删除{len(to_delete)}条旧记录...')
            for rid in to_delete:
                delete_dns_record(rid)
            print(' 删除完成')
        else:
            print('没有需要删除的旧记录')

        # 统计所有运营商的IP数量
        total_ips = sum(len(ips) for ips in ips_by_operator.values())
        
        if total_ips > 0:
            print(f'\n开始批量更新DNS记录集，共包含{total_ips}个IP...')
            
            # 为每个运营商创建对应的DNS记录集
            for operator, ips in ips_by_operator.items():
                if ips:
                    print(f'\n处理{operator}线路，包含{len(ips)}个IP...')
                    update_dns_records(ips, operator)
        else:
            print('没有IP需要更新')
    
    update_dns_main()
    clear_txt()

# ========== DNS更新功能 ==========

def get_zone_id():
    """获取域名的Zone ID"""
    try:
        request = ListPublicZonesRequest()
        request.name = ZONE_NAME
        response = client.list_public_zones(request)

        if response.zones and len(response.zones) > 0:
            return response.zones[0].id
        else:
            print(f'未找到域名 {ZONE_NAME}')
            return None
    except exceptions.ClientRequestException as e:
        print(f'获取Zone ID失败: {e}')
        return None


def get_all_a_records():
    """获取所有A记录"""
    zone_id = get_zone_id()
    if not zone_id:
        return []
    
    try:
        request = ListRecordSetsWithLineRequest()
        request.zone_id = zone_id
        request.type = "A"  # 只获取A记录类型

        response = client.list_record_sets_with_line(request)
        # print(response) 
        records = []
        if response.recordsets:
            for recordset in response.recordsets:
                # 只返回记录集信息，不重复每个IP
                records.append({
                    'RecordsetId': recordset.id,
                    'Name': recordset.name,
                    'Records': recordset.records,
                    'Line': recordset.line if hasattr(recordset, 'line') else ''
                })
        return records
    except exceptions.ClientRequestException as e:
        print(f'获取所有A记录失败: {str(e)}')
        return []


def delete_dns_record(recordset_id):
    """删除DNS记录"""
    if not recordset_id:
        return False

    zone_id = get_zone_id()
    if not zone_id:
        return False

    try:
        request = DeleteRecordSetRequest()
        request.zone_id = zone_id
        request.recordset_id = recordset_id
        
        response = client.delete_record_sets(request)
        return True
    except exceptions.ClientRequestException as e:
        return False


def update_dns_records(ips, operator):
    """批量更新DNS记录，根据运营商设置不同线路类型"""
    zone_id = get_zone_id()
    if not zone_id:
        return False

    try:
        record_name = RECORD_NAME + "."
        
        # 华为云DNS支持的线路类型代码
        line_types = {
            '中国移动': 'Yidong',    # 中国移动线路
            '中国电信': 'Dianxin',   # 中国电信线路
            '中国联通': 'Liantong',  # 中国联通线路
            '全网默认': 'default_view',           # 全网默认线路
            '港澳台': 'Abroad'       # 港澳台线路
        }
        
        # 获取当前运营商对应的线路类型代码
        line_type = line_types.get(operator, '')
        
        # 只使用前2个IP进行更新
        limited_ips = ips[:2]
        
        # 将IP分批处理，每个记录集包含多个IP以节省配额
        batch_size = 50  # 每个记录集最多包含50个IP
        total_batches = (len(limited_ips) + batch_size - 1) // batch_size  # 计算总批次数
        
        for batch_num in range(total_batches):
            start_idx = batch_num * batch_size
            end_idx = min(start_idx + batch_size, len(limited_ips))
            batch_ips = limited_ips[start_idx:end_idx]
            
            try:
                # 为不同运营商创建不同线路的DNS记录
                request = CreateRecordSetWithLineRequest()
                request.zone_id = zone_id
                
                request.body = CreateRecordSetWithLineRequestBody(
                    records=batch_ips,
                    ttl=1,
                    type="A",
                    name=record_name,
                    line=line_type  # 设置线路类型
                )
                
                response = client.create_record_set_with_line(request)
                # 成功创建记录集，不打印详细信息
                
            except exceptions.ClientRequestException as e:
                # 创建记录集失败，不打印详细信息
                pass
                # 继续创建其他批次，不因单个失败而停止
        
        print(f' 已更新{operator}线路，使用{len(limited_ips)}个IP')
        return True
            
    except exceptions.ClientRequestException as e:
        print(f'批量更新DNS记录失败: {str(e)}')
        return False


def clear_txt():
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_file = os.path.join(script_dir, 'dns_result.txt')
        with open(input_file, 'w') as f:
            f.write('')  # 清空文件
        print('已成功清空')
    except Exception as e:
        print(f'清空文件失败: {str(e)}')

# 程序入口
if __name__ == '__main__':
    main()