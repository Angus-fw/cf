# Cloudflare CDN Fission

## 项目介绍

Cloudflare CDN Fission 是一个自动化工具，用于：

1. **IP 反查域名**：从 IP 地址列表中反向查询绑定的域名
2. **域名解析 IP**：从域名列表中解析出对应的 IP 地址
3. **Ping 测试**：对解析出的 IP 地址进行 Ping 测试，筛选响应时间小于 100ms 的 IP 地址
4. **DNS 记录更新**：将筛选后的 IP 地址按照运营商分配并更新到华为云 DNS 记录中
5. **自动化运行**：通过 GitHub Actions 实现每天自动更新 DNS 记录

## 功能特点

- **并发处理**：使用多线程并发执行 DNS 查询和 Ping 测试，提高效率
- **智能筛选**：筛选响应时间小于 100ms 的 1 开头 IP 地址
- **按序分配**：按照文件顺序将 IP 地址分配到对应运营商
- **自动化部署**：通过 GitHub Actions 实现定时自动更新
- **跨平台支持**：支持 Windows、Linux 和 macOS 系统

## 项目结构

```
├── .github/workflows/       # GitHub Actions 工作流配置
│   └── auto-update.yml      # 自动更新工作流
├── Fission.py               # 主脚本
├── Fission_ip.txt           # IP 地址列表
├── Fission_domain.txt       # 域名列表
├── dns_result.txt           # Ping 测试结果
├── requirements.txt         # 依赖包列表
└── README.md                # 项目说明
```

## 环境要求

- Python 3.10 或更高版本
- 华为云账号（用于 DNS 记录更新）
- GitHub 账号（用于自动化运行）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置说明

### 1. 华为云账号配置

在 `Fission.py` 文件中修改以下配置：

```python
# 华为云账号AccessKey，请填写您的AccessKey
access_key_id = 'YOUR_ACCESS_KEY_ID'
access_key_secret = 'YOUR_ACCESS_KEY_SECRET'

# 域名配置
ZONE_NAME = "your-domain.com"
RECORD_NAME = "subdomain.your-domain.com"
```

### 2. 并发数配置

根据您的网络环境调整并发数：

```python
# 并发数配置
max_workers_request = 10   # 并发请求数量
max_workers_dns = 20       # 并发DNS查询数量
max_workers_ping = 50      # 并发ping测试数量
```

## 使用方法

### 手动运行

1. 在 `Fission_ip.txt` 文件中添加初始 IP 地址
2. 运行脚本：

```bash
python Fission.py
```

### 自动运行（GitHub Actions）

1. 将项目推送到 GitHub 仓库
2. 在 GitHub 仓库的 **Settings** → **Secrets and variables** → **Actions** 中添加以下密钥（如果需要）：
   - `ACCESS_KEY_ID`：华为云 Access Key ID
   - `ACCESS_KEY_SECRET`：华为云 Access Key Secret

3. GitHub Actions 会自动执行以下操作：
   - 每天定时运行脚本（UTC 时间 0:00，对应北京时间 8:00）
   - 执行 Ping 测试，筛选响应时间小于 100ms 的 1 开头 IP 地址
   - 按照文件顺序将 IP 分配到对应运营商
   - 更新华为云 DNS 记录

4. 手动触发：
   - 在 GitHub 仓库的 **Actions** 页面，点击 **Auto Update DNS Records** 工作流
   - 点击 **Run workflow** 按钮手动触发运行

## GitHub Actions 使用教程

### 工作流配置

工作流文件 `auto-update.yml` 配置如下：

- **触发方式**：
  - 定时触发：每天 UTC 时间 0:00 运行
  - 手动触发：通过 GitHub 界面手动运行

- **运行环境**：Ubuntu latest

- **执行步骤**：
  1. 检出代码
  2. 设置 Python 3.10 环境
  3. 安装依赖
  4. 运行 Fission.py 脚本
  5. （可选）将更新后的结果提交回仓库

### 查看运行日志

1. 进入 GitHub 仓库的 **Actions** 页面
2. 点击 **Auto Update DNS Records** 工作流
3. 点击具体的运行记录查看详细日志

### 常见问题

1. **运行失败**：检查华为云 Access Key 是否正确配置
2. **DNS 更新失败**：检查域名配置是否正确，确保有足够的 DNS 记录配额
3. **没有符合条件的 IP**：检查网络环境，可能需要添加更多初始 IP 地址

## IP 分配规则

脚本按照以下规则将 IP 地址分配到对应运营商：

- **全网默认**：前 2 个 IP 地址
- **中国移动**：接下来 2 个 IP 地址
- **中国电信**：接下来 2 个 IP 地址
- **中国联通**：接下来 2 个 IP 地址
- **港澳台**：接下来 2 个 IP 地址

## 注意事项

1. **华为云 API 限制**：请确保您的华为云账号有足够的 API 调用配额
2. **DNS 记录配额**：华为云 DNS 每个域名的记录集数量有限制，请合理配置
3. **网络环境**：不同网络环境下的 Ping 测试结果可能不同
4. **安全性**：请不要将包含敏感信息的代码推送到公开仓库

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 贡献

欢迎提交 Issue 和 Pull Request 来改进这个项目。

## 联系方式

如有问题或建议，请通过 GitHub Issues 联系我们。
