import json
import re
import hashlib
from collections import namedtuple
from . import cache
from .libmcp import MCPConfigReader
from .mcp_client import LazyMCPClient
from .. import T

def build_function_call_tool_name(server_name: str, tool_name: str) -> str:
    """
    构建函数调用工具名称，确保符合 Python 函数命名规范

    Args:
        server_name: 服务器名称
        tool_name: 工具名称

    Returns:
        处理后的工具名称
    """

    sanitized_server = server_name.strip()
    if not sanitized_server.isascii():
        # 生成MD5并取前4位
        sanitized_server = hashlib.md5(sanitized_server.encode('utf-8')).hexdigest()[:4]
    else:
        # 用下划线替换无效字符，保留 a-z, A-Z, 0-9
        sanitized_server = re.sub(r'[^a-zA-Z0-9]', '_', sanitized_server)

    sanitized_tool = tool_name.strip()
    # 用下划线替换无效字符
    sanitized_tool = re.sub(r'[^a-zA-Z0-9]', '_', sanitized_tool)

    # 合并服务器名称和工具名称
    name = sanitized_tool
    server_prefix = sanitized_server[:16]

    if server_prefix and server_prefix not in sanitized_tool:
        name = f"{server_prefix}_{sanitized_tool}"

    # 确保名称以字母或下划线开头
    if not re.match(r'^[a-zA-Z_]', name):
        name = f"tool_{name}"

    # 移除连续的下划线
    name = re.sub(r'_{2,}', '_', name)

    # 最大截断为 63 个字符
    if len(name) > 63:
        name = name[:63]

    # 处理边缘情况：确保截断后仍有有效名称
    name = name.strip('_')

    if not name:
        name = "mcp_tool"

    return name.lower()


class MCPToolManager:
    def __init__(self, config_path, tt_api_key):
        self.config_path = config_path
        self.config_reader = MCPConfigReader(config_path, tt_api_key=tt_api_key)
        self.user_mcp = self.config_reader.get_user_mcp()
        self.sys_mcp = self.config_reader.get_sys_mcp()
        self.mcp_servers = self.sys_mcp | self.user_mcp
        self._tools_dict = {}  # 缓存已获取的工具列表
        self._inited = False

        # 全局启用/禁用用户MCP标志，默认禁用
        self._user_mcp_enabled = False
        self._sys_mcp_enabled = False

        # 服务器状态缓存，记录每个服务器的启用/禁用状态
        self._server_status = self._init_server_status()

        # 创建全局的LazyMCPClient实例
        self._lazy_client = LazyMCPClient(
            mcp_servers=self.mcp_servers,
            idle_ttl_seconds=300,
            suppress_output=True,
        )

    def _init_server_status(self):
        """初始化服务器状态，从配置文件中读取初始状态，包括禁用的服务器，同时会被命令行更新，维护在内存中"""

        server_status = {}
        for server_name, server_config in self.mcp_servers.items():
            # sys_mcp 服务器默认禁用，user_mcp 服务器默认启用
            if server_name in self.sys_mcp:
                # sys_mcp 服务器默认禁用
                is_enabled = False
            else:
                # user_mcp 服务器默认启用，除非配置中明确设置为禁用
                is_enabled = not (
                    server_config.get("disabled", False)
                    or server_config.get("enabled", True) is False
                )
            server_status[server_name] = is_enabled
        return server_status

    def list_tools(self, mcp_type="user", force_load=False):
        """返回所有MCP服务器的工具列表
        [{'description': 'Get weather alerts for a US state.\n'
                           '\n'
                           '    Args:\n'
                           '        state: Two-letter US state code (e.g. CA, '
                           'NY)\n'
                           '    ',
            'inputSchema': {'properties': {'state': {'title': 'State',
                                                     'type': 'string'}},
                            'required': ['state'],
                            'title': 'get_alertsArguments',
                            'type': 'object'},
            'name': 'get_alerts',
            'server': 'server1'
            },
        ]
        """
        if mcp_type == "user":
            if not self._user_mcp_enabled and not force_load:
                return []
            mcp_servers = self.user_mcp
            if self._user_mcp_enabled:
                print(
                    T(
                        "Initializing MCP server, this may take a while if it's "
                        "the first load, please wait patiently..."
                    )
                )
        else:
            mcp_servers = self.sys_mcp

        all_tools = []

        # 分别检查缓存和需要重新加载的服务器
        servers_to_load = []
        servers_from_cache = []

        for server_name, server_config in mcp_servers.items():
            if server_name in self._tools_dict:
                # 已经在内存中，直接使用
                continue

            key = f"mcp_tool:{server_name}:{cache.cache_key(server_config)}"
            cached_tools = cache.get_cache(key)

            if cached_tools is not None:
                # 从缓存中恢复
                # 重新计算工具ID，以防命名规则发生变化
                for tool in cached_tools:
                    tool["id"] = build_function_call_tool_name(
                        server_name, tool.get("name", "")
                    )
                self._tools_dict[server_name] = cached_tools
                servers_from_cache.append(server_name)
            else:
                # 需要重新加载
                servers_to_load.append((server_name, server_config))

        if servers_from_cache:
            print(f"+ Loading MCP server {', '.join(servers_from_cache)} from cache...")

        # 只有真正需要重新加载的服务器才去连接
        if servers_to_load:
            try:
                target_servers = [i[0] for i in servers_to_load]
                print(f"+ Loading MCP server {', '.join(target_servers)}...")
                # 使用全局 LazyMCPClient 一次性获取所有工具
                all_discovered_tools = self._lazy_client.list_tools(
                    discover_all=True,
                    servers=target_servers
                )

                # 按服务器名称分组工具
                for server_name, server_config in servers_to_load:
                    try:
                        #print(f"  Processing tools for {server_name}")
                        # 过滤出属于当前服务器的工具
                        server_tools = []
                        for tool in all_discovered_tools:
                            tool_name = tool.get("name", "")
                            if tool_name.startswith(f"{server_name}:"):
                                # 去掉服务器前缀，获取真实工具名
                                clean_tool = tool.copy()
                                clean_tool["name"] = tool_name[len(f"{server_name}:"):]
                                clean_tool["server"] = server_name
                                clean_tool["id"] = build_function_call_tool_name(
                                    server_name, clean_tool.get("name", "")
                                )
                                server_tools.append(clean_tool)

                        # 保存到缓存和内存
                        key = f"mcp_tool:{server_name}:{cache.cache_key(server_config)}"
                        if server_tools:
                            cache.set_cache(key, server_tools, ttl=60 * 60 * 24 * 2)

                        self._tools_dict[server_name] = server_tools

                    except Exception as e:
                        print(f"Error processing tools for server {server_name}: {e}")
                        self._tools_dict[server_name] = []

            except Exception as e:
                print(f"Error loading MCP tools: {e}")
                # 如果全局加载失败，为所有待加载的服务器设置空列表
                for server_name, _ in servers_to_load:
                    if server_name not in self._tools_dict:
                        self._tools_dict[server_name] = []

        # 收集所有工具
        for server_name, server_config in mcp_servers.items():
            all_tools.extend(self._tools_dict.get(server_name, []))

        self._inited = True
        return all_tools

    def get_openai_tools(self):
        """获取 OpenAI 格式的工具列表"""
        tools = self.get_available_tools()
        if not tools:
            return []

        openai_tools = []
        for tool in tools:
            input_schema = tool.get("inputSchema", {}).copy()
            if "additionalProperties" in input_schema:
                del input_schema["additionalProperties"]
            if "$schema" in input_schema:
                del input_schema["$schema"]

            openai_tools.append({
                "type": "function",
                "function": {
                    "name": tool.get("id", ""),
                    "description": tool.get("description", ""),
                    "parameters": input_schema
                }
            })
        return openai_tools

    def get_tools_prompt(self):
        """获取工具列表并转换为 Markdown 格式"""
        tools = self.get_available_tools()  # 获取启用的工具
        if not tools:
            return ""

        ret = []
        for tool in tools:
            # 构建工具信息的 JSON 对象
            # 去掉 inputSchema里的additionalProperties、$schema
            input_schema = tool.get("inputSchema", {}).copy()
            if "additionalProperties" in input_schema:
                del input_schema["additionalProperties"]
            if "$schema" in input_schema:
                del input_schema["$schema"]

            ret.append(
                {
                    "name": tool.get("id", ""),
                    "description": tool.get("description", ""),
                    "arguments": input_schema,
                }
            )

        # 转换为 JSON 字符串并添加到 Markdown 中
        json_str = json.dumps(ret, ensure_ascii=False)
        return f"```json\n{json_str}\n```\n"

    def get_available_tools(self):
        """返回已经启用的工具列表"""

        if not self._inited:
            self.list_tools()

        all_tools = []
        for server_name, tools in self._tools_dict.items():
            # 检查全局启用状态和单个服务器状态
            is_user_server = server_name in self.user_mcp

            # user_mcp服务器需要同时满足全局启用和服务器启用
            # sys_mcp服务器只需要服务器启用
            server_enabled = self._server_status.get(server_name, True)
            if is_user_server:
                server_enabled = server_enabled and self._user_mcp_enabled

            if server_enabled:
                for tool in tools:
                    tool["server"] = server_name
                    all_tools.append(tool)
        return all_tools

    def get_server_info(self, mcp_type="user") -> dict:
        """返回所有服务器的列表及其启用状态"""
        if not self._inited:
            # 强制加载工具信息，即使全局禁用也要获取服务器和工具数量信息
            self.list_tools(mcp_type=mcp_type, force_load=True)

        if mcp_type == "user":
            mcp_servers = self.user_mcp
        else:
            mcp_servers = self.sys_mcp
        # 返回服务器列表及其启用状态
        servers_info = {}
        for server_name, _ in mcp_servers.items():
            is_enabled = self._server_status.get(server_name, True)
            tools = self._tools_dict.get(server_name, [])
            servers_info[server_name] = {
                "enabled": is_enabled,
                "tools_count": len(tools),
            }

        return servers_info

    def call_tool(self, tool_name, arguments):
        """调用指定名称的工具，自动选择最匹配的服务器"""
        # 获取所有工具
        all_tools = self.get_available_tools()
        if not all_tools:
            return {
                "isError": True,
                "content": [{
                    "type": "text",
                    "text": "No tools available to call."
                }]
            }

        # 查找匹配的工具，根据id查找
        matching_tools = [t for t in all_tools if t["id"] == tool_name]
        if not matching_tools:
            return {
                "isError": True,
                "content": [{
                    "type": "text",
                    "text": f"No tool found with name: {tool_name}"
                }]
            }

        # 选择参数匹配度最高的工具
        best_match = None
        best_score = -1

        for tool in matching_tools:
            score = 0
            required_params = []

            # 检查工具的输入模式
            if "inputSchema" in tool and "properties" in tool["inputSchema"]:
                properties = tool["inputSchema"]["properties"]
                required_params = tool["inputSchema"].get("required", [])

                # 检查所有必需参数是否提供
                required_provided = all(param in arguments for param in required_params)
                if not required_provided:
                    continue

                # 计算匹配的参数数量
                matching_params = sum(1 for param in arguments if param in properties)
                extra_params = len(arguments) - matching_params

                # 评分：匹配参数越多越好，额外参数越少越好
                score = matching_params - 0.1 * extra_params

            if score > best_score:
                best_score = score
                best_match = tool

        if not best_match:
            # 返回错误信息而不是抛出异常
            error_msg = f"No suitable tool found for {tool_name} with given arguments"
            return {
                "isError": True,
                "content": [{
                    "type": "text",
                    "text": error_msg
                }]
            }

        # 获取服务器配置
        server_name = best_match["server"]
        real_tool_name = best_match["name"]

        try:
            # 使用全局 LazyMCPClient 调用工具
            ret = self._lazy_client.call_tool(real_tool_name, arguments, server_name)
            # ret需要是字典，并且如果同时包含content和structuredContent字段，
            # 则丢弃content
            if (isinstance(ret, dict) and ret.get("content")
                and ret.get("structuredContent")):
                del ret["content"]
            return ret
        except Exception as e:
            # 捕获工具调用异常，返回错误信息给LLM
            error_msg = f"Tool call failed: {str(e)}"
            return {
                "isError": True,
                "content": [{
                    "type": "text",
                    "text": error_msg
                }]
            }

    @property
    def is_mcp_enabled(self):
        """是否需要启用MCP处理
        1. 如果系统MCP全局启用，则返回True
        2. 如果用户MCP全局禁用，则返回False
        3. 如果用户MCP全局启用，则返回用户MCP服务器中是否至少有一个服务器启用
        """
        if self._sys_mcp_enabled:
            return True
        
        if not self._user_mcp_enabled:
            return False
        
        user_server_status = [
            self._server_status.get(server_name, False) 
            for server_name in self.user_mcp
        ]
        return any(user_server_status)
    
    @property
    def is_sys_mcp_enabled(self):
        return self._sys_mcp_enabled
    
    @property
    def is_user_mcp_enabled(self):
        return self._user_mcp_enabled
    
    def enable_user_mcp(self, enable=True):
        """全局启用/禁用用户MCP"""
        self._user_mcp_enabled = enable
        if enable:
            self.list_tools(mcp_type="user")
        return True
        
    def enable_sys_mcp(self, enable=True):
        """全局启用/禁用系统MCP"""
        self._sys_mcp_enabled = enable
        for server_name in self.sys_mcp:
            self._server_status[server_name] = enable
        if enable:
            self.list_tools(mcp_type="sys")
        return True
            
    def enable_user_server(self, server_name, enable=True):
        """启用/禁用指定用户MCP服务器"""
        if server_name == "*" or not server_name:
            for srv_name in self.user_mcp.keys():
                self._server_status[srv_name] = enable
            ret = True
        elif server_name in self.user_mcp:
            self._server_status[server_name] = enable
            ret = True
        else:
            return False
            
        self.list_tools(mcp_type="user")
        return ret

    def list_user_servers(self):
        """返回所有用户MCP服务器列表"""
        status = self.get_server_info(mcp_type="user")
        ServerRecord = namedtuple("ServerRecord", ["Name", "Enabled", "ToolsCount"])
        return [
            ServerRecord(name, info['enabled'], info['tools_count']) 
            for name, info in status.items()
        ]
    
    def get_status(self):
        """返回MCP状态信息供状态栏使用"""
        total_tools = 0
        enabled_tools = 0
        enabled_servers = 0
        total_servers = 0

        sys_mcp_info = self.get_server_info(mcp_type="sys")
        for server_name, server_info in sys_mcp_info.items():
            total_servers += 1
            if server_info['enabled']:
                enabled_servers += 1
                enabled_tools += server_info['tools_count']
            total_tools += server_info['tools_count']
        if self.is_user_mcp_enabled:
            user_mcp_info = self.get_server_info(mcp_type="user")
            for server_name, server_info in user_mcp_info.items():
                total_servers += 1
                if server_info['enabled']:
                    enabled_servers += 1
                    enabled_tools += server_info['tools_count']
                total_tools += server_info['tools_count']
        return {
            'sys_mcp_enabled': self._sys_mcp_enabled,
            'user_mcp_enabled': self._user_mcp_enabled,
            'total_servers': total_servers,
            'total_tools': total_tools,
            'enabled_servers': enabled_servers,
            'enabled_tools': enabled_tools,
        }
