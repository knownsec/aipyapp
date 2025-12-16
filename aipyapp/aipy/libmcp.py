import json

from loguru import logger
from .. import T


class MCPConfigReader:
    def __init__(self, config_path, tt_api_key):
        self.config_path = config_path
        self.tt_api_key = tt_api_key

    def _rewrite_config(self, servers):
        """rewrite MCP server config"""
        if not self.tt_api_key:
            return servers

        for _, server_config in servers.items():
            # 检查是否是trustoken的URL且transport类型为streamable_http
            url = server_config.get("url", "")
            transport = server_config.get("transport", {})

            if (
                url.startswith(T("https://sapi.trustoken.ai"))
                and transport.get("type") == "streamable_http"
            ):
                if "headers" not in server_config:
                    server_config["headers"] = {}

                server_config["headers"].update({
                    "Authorization": f"Bearer {self.tt_api_key}"
                })

        return servers

    def get_user_mcp(self) -> dict:
        """读取 mcp.json 文件并返回 MCP 服务器清单，包括禁用的服务器"""
        if not self.config_path:
            return {}
        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                servers = config.get("mcpServers", {})
                return self._rewrite_config(servers)
        except FileNotFoundError:
            print(f"Config file not found: {self.config_path}")
            return {}
        except json.JSONDecodeError as e:
            print(
                T("Error decoding MCP config file {}: {}").format(
                    self.config_path, e
                )
            )
            return {}


    def get_sys_mcp(self) -> dict:
        """
        获取内部 MCP 服务器配置。

        Returns:
            dict: 内部 MCP 服务器配置字典。
        """
        if not self.tt_api_key:
            logger.warning(
                "No Trustoken API key provided, sys_mcp will not be available."
            )
            return {}

        return {
            "Trustoken-map": {
                "url": f"{T('https://sapi.trustoken.ai')}/aio-api/mcp/amap/",
                "transport": {
                    "type": "streamable_http"
                },
                "headers": {
                    "Authorization": f"Bearer {self.tt_api_key}"
                }
            },
            "Trustoken-search": {
                "url": f"{T('https://sapi.trustoken.ai')}/mcp/",
                "transport": {
                    "type": "streamable_http"
                },
                "headers": {
                    "Authorization": f"Bearer {self.tt_api_key}"
                }
            }
        }
