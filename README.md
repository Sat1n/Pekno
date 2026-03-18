## 🔌 插件开发指南 (Plugin Development Quickstart)

Iris Hub 拥有一个极其自由且安全的动态插件系统。任何人都可以为它编写插件来同步新的数据源！

为了让系统能够安全地热加载你的代码，请确保你的插件包（ZIP 或文件夹）遵守以下 **“三大铁律”**：

### 铁律 1：明确的入口文件
你的插件包根目录下，必须包含主入口文件，系统只会从以下文件寻找代码：
* 单文件插件：`任意名字.py` 
* 文件夹插件：`plugin.py` 或 `__init__.py`
### 铁律 1：强制包含 `manifest.json`
插件包根目录必须提供静态配置清单，系统会据此进行安全预检。
**样板 (Boilerplate)：**
```json
{
  "id": "my_unique_plugin",
  "name": "插件展示名称",
  "description": "一句简短的描述，说明插件的作用",
  "version": "1.0.0",
  "author": "Your Name",
  "permissions": ["network"],
  "settings_schema": {
    "api_url": {
      "type": "string",
      "label": "接口地址",
      "default": "[https://example.com/api](https://example.com/api)"
    },
    "access_token": {
      "type": "string",
      "label": "访问令牌",
      "secret": true,
      "required": false
    }
  }
}
```

### 铁律 2：明确的主入口文件
你的插件逻辑必须存放在与 `manifest.json` 同级的 `plugin.py` 文件中。

### 铁律 3：强制导出 `plugin` 实例
在 `plugin.py` 中，必须继承 `BasePlugin`，并在文件最末尾暴露一个名为 `plugin` 的全局实例。
```python
# plugin.py
from shared.plugins.base import BasePlugin, PluginContext
import json

class MyPlugin(BasePlugin):
    @property
    def manifest(self) -> dict:
        # 建议直接读取同目录的 json 文件保持一致性
        with open("manifest.json", "r", encoding="utf-8") as f:
            return json.load(f)

    async def fetch_data(self, ctx: PluginContext) -> list[dict]:
        pass # 你的数据抓取逻辑

    def normalize_item(self, raw_item: dict) -> dict:
        pass # 你的数据清洗逻辑

# ⚠️ 必须暴露实例！
plugin = MyPlugin()
```

---

### 🛠️ 极简插件模板 (Hello World)

创建一个 `my_plugin/` 文件夹，里面只需要一个 `plugin.py`：

```python
# plugin.py
from shared.plugins.base import BasePlugin, PluginContext

class MyAwesomePlugin(BasePlugin):
    @property
    def manifest(self) -> dict:
        return {
            "id": "my_awesome_plugin",
            "name": "我的神仙插件",
            "description": "这是我给 Iris 写的第一个插件",
            "version": "1.0.0",
            "settings_schema": {
                # 这里定义你想让用户在 UI 上填的配置
                "api_key": {"type": "string", "secret": True, "label": "API 密钥"}
            }
        }

    async def fetch_data(self, ctx: PluginContext) -> list[dict]:
        # 从你的配置里读取用户填写的内容
        api_key = ctx.config.get("api_key")
        ctx.logger.info("正在获取数据...")
        
        # 返回原始数据列表
        return [{"id": "item_1", "title": "Hello", "content": "World"}]

    def normalize_item(self, raw_item: dict) -> dict:
        # 将原始数据转换为 Iris 标准格式
        return {
            "id": raw_item["id"],
            "title": raw_item["title"],
            "content_text": raw_item["content"],
            "source_type": "my_plugin",
            "raw_link": "[https://example.com](https://example.com)"
        }

# ⚠️ 铁律：必须在文件末尾暴露这个实例！
plugin = MyAwesomePlugin()
```