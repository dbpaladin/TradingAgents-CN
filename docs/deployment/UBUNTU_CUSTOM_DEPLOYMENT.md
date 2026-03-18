# 专属部署与维护指南 (Ubuntu 服务器)

这份文档专门为了记录本项目在 Ubuntu 服务器上的标准部署流程，以及针对**第三方 Tushare 数据源代理**的魔改说明。

## 1. 核心代码魔改记录（已完成）

本项目默认使用官方 Tushare 接口。为了接入第三方 Tushare 特价数据源代理（IP: `118.25.178.42:5000`），我们修改了以下代码以拦截并重定向底层请求：

**修改文件路径**：
`tradingagents/dataflows/providers/china/tushare.py`

**修改内容**：
我们在 `connect_sync()` 和 `async connect()` 函数初始化 `ts.pro_api()` 的所有地方（包含从数据库 `db_token` 获取以及从环境变量 `env_token` 获取），强行注入了第三方服务的 URL：
```python
ts.set_token(db_token)       # 或者 env_token 
self.api = ts.pro_api()
# 🔥 拦截官方请求，转给第三方服务
self.api._DataApi__token = db_token  # 你的第三方 Token
self.api._DataApi__http_url = 'http://118.25.178.42:5000'
```

---

## 2. Ubuntu 服务器独立部署流程

这套系统采用了**代码与数据解耦**的架构。使用 `docker-compose` 部署，配置文件和数据已经映射到了外部磁盘（`./data`, `./config`, `./logs`），所以升级代码不会丢失任何持仓数据和系统配置。

### 第一步：克隆你专属的魔改版仓库
为了保留你的修改，**绝对不要**克隆上游原始官方仓库，必须克隆你 Fork 后的个人仓库：
```bash
git clone https://github.com/dbpaladin/TradingAgents-CN.git
cd TradingAgents-CN
```

### 第二步：准备配置文件
环境里必须要有对应的变量文件作为容器启动的养料：
```bash
cp .env.docker .env
```
随后使用编辑器打开它：
```bash
vim .env
```
此时你需要确保至少配置好两个核心组件：
1. **大模型 API Key（核心大脑）**：比如 `DEEPSEEK_API_KEY`（极其推荐），或者阿里 `DASHSCOPE_API_KEY` 等。
2. **TUSHARE API Token（行情眼睛）**：找到 `TUSHARE_TOKEN=`，这里要填写**你的第三方服务商提供给你的专属 Token**。填写完保存退出。

### 第三步：一键编译与启动
最后一步，让 Docker 接管一切：
```bash
docker-compose up -d --build
```
*（参数说明：`-d` 代表后台运行，`--build` 代表根据当前的代码重新构建 Docker 镜像，确保你的重定向魔改代码打进了系统里）*

启动后，访问 `http://服务器IP:3000` 即可使用前台，A股的底层数据流就会无缝切入第三方节点。

---

## 3. 日常白嫖与长久维护

这套玩法最爽的就是日后升级极速且安全。

假设未来官方更新了修复或者逆天的新功能，你的维护流如下：
1. 在浏览器上打开你的个人的 GitHub Fork 页面：`https://github.com/dbpaladin/TradingAgents-CN`
2. 点击绿色的 **"Sync fork"** 按钮，一键白嫖上游官方代码到你的仓库。*(这不会覆盖你的魔改代码，Git 会自动合并融合。)*
3. 登录回到你的 Ubuntu 服务器上（进入项目目录）：
```bash
git pull origin main
docker-compose up -d --build
```
等几分钟容器构建重启完，“缝合”了全新官方版本和你个人魔改 Tushare 地址的最强版系统就诞生了！
