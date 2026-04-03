# GitHub Pages 配置说明

本项目支持通过 GitHub Pages 展示 DNS 测试结果的前端页面。以下是配置步骤：

## 配置步骤

1. **登录 GitHub**，进入本项目的仓库页面

2. **进入仓库设置**：
   - 点击仓库页面顶部的 `Settings` 标签

3. **找到 GitHub Pages 配置**：
   - 在左侧导航栏中点击 `Pages` 选项

4. **配置构建和部署**：
   - 在 `Build and deployment` 部分，选择 `Source` 为 `Deploy from a branch`
   - 在 `Branch` 下拉菜单中选择 `main` 分支
   - 在 `Folder` 下拉菜单中选择 `/ (root)` 根目录
   - 点击 `Save` 按钮保存配置

5. **等待部署完成**：
   - GitHub Pages 会自动开始部署过程
   - 部署完成后，页面顶部会显示部署成功的消息和访问 URL

6. **访问前端页面**：
   - 使用显示的 URL 访问前端页面（格式通常为 `https://<username>.github.io/<repository-name>`）

## 注意事项

- 首次配置 GitHub Pages 可能需要几分钟时间完成部署
- 每次推送代码到 main 分支时，GitHub Pages 会自动重新部署
- 前端页面会从 `dns_result.txt` 文件加载最新的测试结果
- 如果 DNS 测试结果没有显示，请确保 `dns_result.txt` 文件存在且包含有效的测试结果

## 页面功能

前端页面包含以下功能：

- 显示上次更新时间
- 显示可用 IP 数量
- 显示最快响应时间
- 以表格形式展示所有测试结果，包括 IP 地址、响应时间和最快运营商