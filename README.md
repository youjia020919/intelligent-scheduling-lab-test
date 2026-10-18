# 智能调度实验室 · 测试网站

本目录是可部署的测试版。确定性排程功能无需模型 API 密钥。COOPA 原系统入口在本部署中未配置，页面会显示未就绪。

## 本地启动

```text
python -m pip install -r requirements.txt
python server.py
```

浏览器打开 `http://127.0.0.1:8765/`。也可以通过环境变量 `PORT` 指定端口。

## Render 部署

将本目录作为独立 Git 仓库上传；在 Render 中选择 Blueprint，并使用 `render.yaml`。部署完成后使用 Render 分配的公开网址访问。不要公开设置模型 API 密钥，除非已准备好访问控制和费用限制。

测试版没有用户账户或数据持久化；请求输入仅用于当次计算。公开部署前应评估访问量和求解资源限制。
