# DNS 自动更新工具

一个自动测试 IP 连接速度并更新华为云 DNS 记录的工具。

## 功能特性

- **IP 反查域名**：通过多个网站查询 IP 对应的域名
- **域名解析 IP**：批量查询域名的 DNS 记录
- **TCP 连接测试**：测试 IP 的连接速度，筛选快速 IP
- **运营商线路优化**：根据不同运营商分配最优 IP
- **自动更新 DNS**：自动更新华为云 DNS 记录
- **GitHub Actions 自动化**：支持每周自动执行

## 环境要求

- Python 3.10+
- 华为云账号（需要 DNS 服务权限）

## 安装依赖

```bash
pip install -r requirements.txt
```

## 配置说明

### 1. 华为云 AccessKey 配置

#### 方式一：环境变量（推荐）

在运行脚本前设置环境变量：

```bash
export HUAWEI_ACCESS_KEY_ID=你的AccessKeyID
export HUAWEI_ACCESS_KEY_SECRET=你的AccessKeySecret
```

#### 方式二：修改代码

直接修改 `Fission.py` 中的 AccessKey 配置：

```python
ACCESS_KEY_ID = '你的AccessKeyID'
ACCESS_KEY_SECRET = '你的AccessKeySecret'
```

### 2. 域名配置

修改 `Fission.py` 中的域名配置：

```python
ZONE_NAME = "你的域名"
RECORD_NAME = "*"  # 主机记录，如 @、*、www 等
```

## 使用方法

### 本地运行

```bash
python Fission.py
```

### GitHub Actions 自动运行

#### 1. 推送代码到 GitHub

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin <你的仓库地址>
git push -u origin main
```

#### 2. 配置 GitHub Secrets

在 GitHub 仓库中设置以下 Secrets：

- `HUAWEI_ACCESS_KEY_ID`：华为云 AccessKey ID
- `HUAWEI_ACCESS_KEY_SECRET`：华为云 AccessKey Secret

配置路径：Settings → Secrets and variables → Actions → New repository secret

#### 3. 工作流配置

默认配置为每周一 UTC 0:00（北京时间 8:00）自动运行。

修改执行时间：编辑 `.github/workflows/update-dns.yml` 中的 cron 表达式。

## 工作流程

1. **IP 反查域名**：从 `Fission_ip.txt` 读取 IP 列表，查询对应的域名
2. **域名解析 IP**：从 `Fission_domain.txt` 读取域名列表，解析出所有 IP
3. **TCP 连接测试**：测试所有 IP 的连接速度，筛选响应时间小于 200ms 的 IP
4. **运营商测试**：测试 IP 在不同运营商下的连接速度
5. **DNS 记录更新**：根据测试结果，为不同运营商线路分配最优 IP

## 文件说明

- `Fission.py` - 主程序文件
- `Fission_ip.txt` - IP 地址列表
- `Fission_domain.txt` - 域名列表
- `dns_result.txt` - DNS 查询结果
- `requirements.txt` - Python 依赖包列表
- `.github/workflows/update-dns.yml` - GitHub Actions 工作流配置

## 注意事项

1. **API 配额**：华为云 DNS API 有调用限制，请合理设置执行频率
2. **IP 筛选**：默认只选择响应时间小于 200ms 且不以 43 开头的 IP
3. **IP 前缀**：默认只选择以 104、162、172、108 开头的 IP
4. **运营商线路**：支持中国移动、中国联通、中国电信、全网默认、港澳台线路

## Cron 表达式说明

格式：`分 时 日 月 周`

- `0 0 * * 1` - 每周一 UTC 0:00（北京时间 8:00）
- `0 0 * * *` - 每天 UTC 0:00
- `0 */6 * * *` - 每 6 小时
- `0 2 * * *` - 每天 UTC 2:00（北京时间 10:00）

## 许可证

MIT License