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
IPS_FILE = "Fission_ip.txt"
DOMAINS_FILE = "Fission_domain.txt"
DNS_RESULT_FILE = "dns_result.txt"

# 华为云账号AccessKey，请填写您的AccessKey
import os
ACCESS_KEY_ID = os.environ.get('ACCESS_KEY_ID', 'HPUACWBMV5S86XLHYVLC')
ACCESS_KEY_SECRET = os.environ.get('ACCESS_KEY_SECRET', '54YIlbgKcn35oyeDlwoNcioaz0uZeaPgB5FJLUvN')

# 创建认证信息
CREDENTIALS = BasicCredentials(ACCESS_KEY_ID, ACCESS_KEY_SECRET)

# 创建DNS客户端
CLIENT = DnsClient.new_builder() \
    .with_credentials(CREDENTIALS) \
    .with_region(DnsRegion.value_of("cn-north-4")) \
    .build()

# 域名配置
ZONE_NAME = "华为云.2808225.xyz"
RECORD_NAME = "@"

# 并发数配置
MAX_WORKERS_REQUEST = 10  # 并发请求数量
MAX_WORKERS_DNS = 20      # 并发DNS查询数量

# 生成随机User-Agent
UA = UserAgent()

# 网站配置
SITES_CONFIG = {
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


def setup_session():
    """设置请求会话，配置重试机制"""
    session = requests.Session()
    retries = Retry(total=5, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retries)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def get_headers():
    """生成随机请求头"""
    return {
        'User-Agent': UA.random,
        'Accept': '*/*',
        'Connection': 'keep-alive',
    }


def fetch_domains_for_ip(ip_address, session, attempts=0, used_sites=None):
    """查询IP对应的域名，自动重试和切换网站"""
    if used_sites is None:
        used_sites = []
    if attempts >= 3:  # 如果已经尝试了3次，终止重试
        return []

    # 选择一个未使用的网站进行查询
    available_sites = {key: value for key, value in SITES_CONFIG.items() if key not in used_sites}
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


def fetch_domains_concurrently(ip_addresses):
    """并发处理所有IP地址，查询对应的域名"""
    session = setup_session()
    domains = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_REQUEST) as executor:
        future_to_ip = {executor.submit(fetch_domains_for_ip, ip, session): ip for ip in ip_addresses}
        for future in concurrent.futures.as_completed(future_to_ip):
            domains.extend(future.result())

    return list(set(domains))


def dns_lookup(domain):
    """执行DNS查询"""
    result = subprocess.run(["nslookup", domain], capture_output=True, text=True)
    return domain, result.stdout


def perform_dns_lookups(domain_filename, result_filename, unique_ipv4_filename):
    """通过域名列表获取绑定过的所有IP"""
    try:
        # 读取域名列表
        with open(domain_filename, 'r') as file:
            domains = file.read().splitlines()

        # 创建一个线程池并执行DNS查询
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS_DNS) as executor:
            results = list(executor.map(dns_lookup, domains))

        # 写入查询结果到文件
        with open(result_filename, 'w') as output_file:
            for domain, output in results:
                output_file.write(output)

        # 从结果文件中提取所有IPv4地址
        ipv4_addresses = set()
        for _, output in results:
            ipv4_addresses.update(re.findall(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b', output))

        # 读取已存在的IP列表
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


def request_ip_status(ip, port=80, use_https=False, timeout=5):
    """测试IP的TCP连接速度"""
    try:
        import socket
        import time
        
        times = []
        test_count = 3
        
        for _ in range(test_count):
            start_time = time.time()
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(timeout)
                sock.connect((ip, port))
                sock.close()
                connect_time = (time.time() - start_time) * 1000  # 转换为毫秒
                times.append(connect_time)
            except Exception:
                return (0, None)  # 连接失败
        
        if times:
            avg_time_ms = sum(times) / len(times)
            return (1, avg_time_ms)  # 连接成功，返回平均时间
        else:
            return (0, None)  # 连接失败
    except Exception as e:
        print(f"TCP测试出错: {type(e).__name__}: {e}")
        return None


def get_isp_info():
    """获取常见运营商的DNS服务器"""
    isp_dns = {
        "中国电信": ["202.102.192.68", "202.102.199.68"],
        "中国联通": ["202.99.192.66", "202.99.198.6"],
        "中国移动": ["211.136.192.6", "211.136.20.203"],
        "公共DNS": ["114.114.114.114", "8.8.8.8"]
    }
    return isp_dns


def test_isp_speed(target_ip, isp_dns, timeout=5):
    """测试不同运营商的TCP连接速度"""
    results = {}
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_isp = {}
        
        for isp, dns_servers in isp_dns.items():
            for dns in dns_servers:
                future = executor.submit(request_ip_status, target_ip, timeout=timeout)
                future_to_isp[future] = isp
        
        for future in concurrent.futures.as_completed(future_to_isp):
            isp = future_to_isp[future]
            try:
                result = future.result()
                if result is not None:
                    success, speed = result
                    if success == 1 and speed is not None:
                        if isp not in results:
                            results[isp] = []
                        results[isp].append(speed)
            except Exception:
                pass
    
    # 计算各运营商的平均速度
    avg_results = {}
    for isp, speeds in results.items():
        if speeds:
            avg_speed = sum(speeds) / len(speeds)
            avg_results[isp] = avg_speed
    
    return avg_results


def run_tcp_tests():
    """执行TCP连接速度测试"""
    # 配置文件路径
    ip_file = IPS_FILE
    
    # 配置超时时间
    timeout = 5
    
    # 多线程配置
    max_workers_tcp = 50  # 并发TCP测试数量
    
    try:
        # 读取IP地址列表
        with open(ip_file, 'r') as f:
            ip_addresses = [line.strip() for line in f if line.strip()]
        
        if not ip_addresses:
            print("IP地址列表为空")
        else:
            # 存储成功的TCP测试结果，用于速度比较
            tcp_results = []
            
            # 存储响应时间小于200ms的IP信息
            fast_ips = []
            
            # 获取运营商信息
            isp_dns = get_isp_info()
            
            # 使用多线程执行TCP测试
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers_tcp) as executor:
                # 提交所有TCP测试任务
                future_to_ip = {
                    executor.submit(request_ip_status, ip, timeout=timeout): ip 
                    for ip in ip_addresses
                }
                
                # 收集所有任务的结果
                for future in concurrent.futures.as_completed(future_to_ip):
                    ip = future_to_ip[future]
                    try:
                        tcp_result = future.result()
                        
                        if tcp_result is not None:
                            success, avg_time_ms = tcp_result
                            
                            if success == 1:
                                # 如果获取到响应时间，添加到结果列表
                                if avg_time_ms is not None:
                                    # 保存结果用于速度比较
                                    tcp_results.append({
                                        "ip": ip,
                                        "time": avg_time_ms
                                    })
                                        
                                    # 检查响应时间是否小于200ms，并且IP不是43前缀，同时IP必须以104、162或172开头
                                    if avg_time_ms < 200.0 and not ip.startswith("43.") and (
                                        ip.startswith("104.") or ip.startswith("162.") or 
                                        ip.startswith("172.") or ip.startswith("108.")
                                    ):
                                        # 测试该IP在不同运营商下的连接速度
                                        isp_speeds = test_isp_speed(ip, isp_dns, timeout=timeout)
                                            
                                        # 找出最快的运营商
                                        fastest_isp = None
                                        if isp_speeds:
                                            fastest_isp = min(isp_speeds, key=isp_speeds.get)
                                            
                                        fast_ips.append({
                                            "ip": ip,
                                            "time": avg_time_ms,
                                            "fastest_isp": fastest_isp
                                        })
                    except Exception:
                        pass
            
            if fast_ips:
                try:
                    with open(DNS_RESULT_FILE, "w", encoding="utf-8") as f:
                        for result in fast_ips:
                            # 格式化响应时间，保留两位小数
                            formatted_time = f"{result['time']:.2f}ms"
                            if result.get("fastest_isp"):
                                f.write(f"{result['ip']} - {formatted_time} - 最快运营商: {result['fastest_isp']}\n")
                            else:
                                f.write(f"{result['ip']} - {formatted_time}\n")
                    print(f"\n已将 {len(fast_ips)} 个响应时间小于200ms的IP信息保存到{DNS_RESULT_FILE}文件")
                except Exception as e:
                    print(f"\n保存文件出错: {e}")
            else:
                print("\n没有响应时间小于200ms的IP地址")
            
            # 更新Fission_ip.txt文件内容
            try:
                with open(IPS_FILE, "w", encoding="utf-8") as f:
                    f.write("162.159.39.13\n172.64.153.74\n104.19.37.10\n108.162.198.124\n")
            except Exception as e:
                print(f"更新{IPS_FILE}文件出错: {e}")
    except Exception as e:
        print(f"读取文件出错: {e}")


def get_zone_id():
    """获取域名的Zone ID"""
    try:
        request = ListPublicZonesRequest()
        request.name = ZONE_NAME
        response = CLIENT.list_public_zones(request)

        if response.zones and len(response.zones) > 0:
            zone_id = response.zones[0].id
            return zone_id
        else:
            print(f'未找到域名 {ZONE_NAME}')
            # 尝试列出所有可用的区域
            try:
                list_request = ListPublicZonesRequest()
                list_response = CLIENT.list_public_zones(list_request)
                print(f'所有可用的区域: {list_response}')
            except Exception as list_e:
                print(f'列出区域失败: {list_e}')
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

        response = CLIENT.list_record_sets_with_line(request)
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
        
        response = CLIENT.delete_record_sets(request)
        return True
    except exceptions.ClientRequestException:
        return False


def update_dns_records(ips, operator):
    """批量更新DNS记录，根据运营商设置不同线路类型"""
    zone_id = get_zone_id()
    if not zone_id:
        return False

    try:
        # 构建完整的记录集名称
        record_name = f"{RECORD_NAME}.{ZONE_NAME}."
        
        # 华为云DNS支持的线路类型代码
        line_types = {
            '中国移动': 'Yidong',    # 中国移动线路
            '中国电信': 'Dianxin',   # 中国电信线路
            '中国联通': 'Liantong',  # 中国联通线路
            '全网默认': 'default_view',  # 全网默认线路
            '港澳台': 'Abroad'       # 港澳台线路
        }
        
        # 获取当前运营商对应的线路类型代码
        line_type = line_types.get(operator, '')
        
        # 只使用前5个IP进行更新
        limited_ips = ips[:5]
        
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
                
                response = CLIENT.create_record_set_with_line(request)
                # 成功创建记录集
                print(f' {operator}线路，使用IP: {batch_ips}')
                
            except exceptions.ClientRequestException as e:
                # 创建记录集失败，打印详细错误信息
                print(f' 创建{operator}线路记录集失败: {str(e)}')
                # 继续创建其他批次，不因单个失败而停止
        
        return True
            
    except exceptions.ClientRequestException as e:
        print(f'批量更新DNS记录失败: {str(e)}')
        return False


def update_dns_main():
    """执行DNS更新操作"""
    # 获取脚本所在目录
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(script_dir, DNS_RESULT_FILE)
    
    # 先读取IP列表
    ips_by_operator = {
        '全网默认': [],
        '中国移动': [],
        '中国电信': [],
        '中国联通': [],
        '港澳台': []
    }
    
    # 读取所有IP地址和最快运营商信息
    ip_info_list = []
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f.read().splitlines():
                line = line.strip()
                if line:
                    # 从格式 "IP - 136.75ms - 最快运营商: 运营商名称" 中提取IP、响应时间和运营商
                    parts = line.split(' - ')
                    if len(parts) >= 2:
                        ip = parts[0].strip()
                        
                        # 提取响应时间（毫秒）
                        response_time = float('inf')
                        if parts[1].endswith('ms'):
                            try:
                                response_time = float(parts[1].replace('ms', ''))
                            except:
                                pass
                        
                        # 提取最快运营商信息
                        fastest_isp = None
                        if len(parts) >= 3 and '最快运营商:' in parts[2]:
                            fastest_isp = parts[2].split('最快运营商:')[1].strip()
                        
                        ip_info_list.append({
                            'ip': ip,
                            'response_time': response_time,
                            'fastest_isp': fastest_isp
                        })
        
        # 按响应时间排序，优先选择响应时间快的IP
        ip_info_list.sort(key=lambda x: x['response_time'])
        
        # 根据最快运营商分配到对应线路，优先选择响应时间快的IP
        for ip_info in ip_info_list:
            ip = ip_info['ip']
            fastest_isp = ip_info['fastest_isp']
            
            if fastest_isp == '中国移动':
                if len(ips_by_operator['中国移动']) < 2:
                    ips_by_operator['中国移动'].append(ip)
            elif fastest_isp == '中国联通':
                if len(ips_by_operator['中国联通']) < 2:
                    ips_by_operator['中国联通'].append(ip)
            elif fastest_isp == '中国电信':
                if len(ips_by_operator['中国电信']) < 2:
                    ips_by_operator['中国电信'].append(ip)
            elif fastest_isp == '公共DNS':
                # 公共DNS分配到全网默认
                if len(ips_by_operator['全网默认']) < 2:
                    ips_by_operator['全网默认'].append(ip)
        
    except Exception as e:
        print(f'读取文件失败: {str(e)}')
        return
    
    # 获取所有A记录
    print('正在获取所有A记录...')
    records = get_all_a_records()
    if not records:
        print('未找到任何A记录，无需删除')
    else:
        print(f'找到{len(records)}条A记录，准备比对...')
    
    # 只删除目标域名的A记录
    target_name = f"{RECORD_NAME}.{ZONE_NAME}."
    print(f"使用目标记录集名称: {target_name}")
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
        # 为每个运营商创建对应的DNS记录集
        for operator, ips in ips_by_operator.items():
            if ips:
                update_dns_records(ips, operator)
    else:
        print('没有IP需要更新')


def clear_txt():
    """清空DNS结果文件"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        input_file = os.path.join(script_dir, DNS_RESULT_FILE)
        with open(input_file, 'w') as f:
            f.write('')  # 清空文件
        print('已经更新dns记录')
    except Exception as e:
        print(f'清空文件失败: {str(e)}')


def main():
    """主函数"""
    # 判断是否存在IP文件
    if not os.path.exists(IPS_FILE):
        with open(IPS_FILE, 'w') as file:
            file.write("")
    
    # 判断是否存在域名文件
    if not os.path.exists(DOMAINS_FILE):
        with open(DOMAINS_FILE, 'w') as file:
            file.write("")

    # IP反查域名
    with open(IPS_FILE, 'r') as ips_txt:
        ip_list = [ip.strip() for ip in ips_txt]

    domain_list = fetch_domains_concurrently(ip_list)
    
    with open(DOMAINS_FILE, "r") as file:
        exist_list = [domain.strip() for domain in file]

    domain_list = list(set(domain_list + exist_list))

    with open(DOMAINS_FILE, "w") as output:
        for domain in domain_list:
            output.write(domain + "\n")
    print("IP -> 域名 已完成")

    # 域名解析IP
    perform_dns_lookups(DOMAINS_FILE, DNS_RESULT_FILE, IPS_FILE)
    print("域名 -> IP 已完成")
    
    # 清空域名文件和DNS结果文件内容
    with open(DOMAINS_FILE, 'w') as file:
        file.write('')
    
    with open(DNS_RESULT_FILE, 'w') as file:
        file.write('')
    
    # 执行TCP连接速度测试功能
    print("\n开始执行TCP连接速度测试功能...")
    run_tcp_tests()
    
    # 执行DNS更新功能
    print("\n开始执行DNS更新功能...")
    update_dns_main()

    # 清空DNS结果文件
    clear_txt()

# 程序入口
if __name__ == '__main__':
    main()