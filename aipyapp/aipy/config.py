import sys
import re
import io
import datetime
from pathlib import Path
import traceback

from dynaconf import Dynaconf
from rich import print
import tomli_w

from .. import __respath__, T
from .trustoken import TrustToken
from .libmcp import MCPToolManager

__PACKAGE_NAME__ = "aipyapp"

OLD_SETTINGS_FILES = [
    Path.home() / '.aipy.toml',
    Path('aipython.toml').resolve(),
    Path('.aipy.toml').resolve(),
    Path('aipy.toml').resolve(),
]

CONFIG_FILE_NAME = f"{__PACKAGE_NAME__}.toml"
USER_CONFIG_FILE_NAME = "user_config.toml"
MCP_CONFIG_FILE_NAME = "mcp.json"

def get_tt_aio_api(tt_api_key) -> dict:
    """
    获取 TrustToken AIO API Key
    :param tt_api_key: API Key

    """
    if not tt_api_key:
        return {}

    search_url = f"{T('https://sapi.trustoken.ai/aio-api')}/search/unified"
    geoip_url = f"{T('https://sapi.trustoken.ai/aio-api')}/ipgeo"
    amap_url = f"{T('https://sapi.trustoken.ai/aio-api')}/amap"
    tt_aio_api = {
        'tt_aio_map': {
            'env': {'tt_aio_map': [tt_api_key, "最新地图API Key"]},
            'desc': f"""高德地图（地理编码、驾车、骑行、步行、公交路线规划，周边关键字搜索，天气查询，交通态势、店铺查询, 无法确定POI分类编码时请用关键字搜索API)，**参数中的origin、destination都是坐标**
当需要访问`https://restapi.amap.com/`时，请使用`{amap_url}/`代替，两者API接口完全一致""",
        },
        'tt_aio_geoip':{
            'env': {'tt_aio_geoip': [tt_api_key, "最新IP地理位置API Key"]},
            'desc': f"""如果任务中涉及到位置，但没有指定具体位置，可以用此接口获取地理位置信息，包括国家、省份、城市等信息。接口调用示例如下：
curl -H 'Authorization: Bearer xxx' {geoip_url}
响应数据如下：{{"city": "成都", "country": "中国", "ip": "171.2.1.1", "isp": "电信", "latitude": "32.676235", "longitude": "103.058986", "province": "四川", "version": 4}}""",
        },
        'tt_aio_search': {
            'env': {'tt_aio_search': [tt_api_key, "Trustoken网络搜索API Key"]},
            'desc': f"""联网搜索服务，用于搜索网络信息, **注意：1. 用户指定了搜索引擎时，请勿使用此API；2. 关键词不支持指定时间与网站（如：2025-01-01、site:edu.cn）**。仅在必须联网搜索时调用，接口调用示例如下：
curl  -X POST {search_url} \
--header "Authorization: Bearer xxxxx" \
--header "Content-Type: application/json" \
--data '{{"query": "网络搜索内容", "contents":{{"markdownText":true}}}}'
接口返回的数据样例：
{{
"pageItems": [{{
    "title": "网页标题",
    "link": "https://...",
    "snippet": "网页摘要",
    "publishedTime": "2025-03-09T22:13:38+08:00",
    "markdownText": "网页内容",
    "images": [
        "图片地址"
    ],
    "hostname": "网站名",
}}]
}}""",
        },
    }

    return tt_aio_api


def init_config_dir():
    """
    获取平台相关的配置目录，并确保目录存在
    """
    config_dir = Path.home() / f".{__PACKAGE_NAME__}"
    # 确保目录存在
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        print(T("Permission denied to create directory: {}").format(config_dir))
        raise
    except Exception as e:
        print(T("Error creating configuration directory: {}").format(config_dir, str(e)))
        raise

    return config_dir


CONFIG_DIR = init_config_dir()
PLUGINS_DIR = CONFIG_DIR / "plugins"
TIPS_DIR = CONFIG_DIR / "tips"

def get_config_file_path(config_dir=None, file_name=CONFIG_FILE_NAME, create=True):
    """
    获取配置文件的完整路径
    :return: 配置文件的完整路径
    """
    if config_dir:
        config_dir = Path(config_dir)
    else:
        config_dir = CONFIG_DIR

    config_file_path = config_dir / file_name

    # 如果配置文件不存在，则创建一个空文件
    if not config_file_path.exists() and create:
        try:
            config_file_path.touch()
        except Exception as e:
            print(T("Error creating configuration directory: {}").format(config_file_path))
            raise

    return config_file_path


def lowercase_keys(d):
    """递归地将字典中的所有键转换为小写"""
    if not isinstance(d, dict):
        return d
    return {k.lower(): lowercase_keys(v) for k, v in d.items()}


def is_valid_api_key(api_key):
    """
    校验是否为有效的 API Key 格式。
    API Key 格式为字母、数字、减号、下划线的组合，长度在 8 到 128 之间
    :param api_key: 待校验的 API Key 字符串
    :return: 如果格式有效返回 True，否则返回 False
    """
    pattern = r"^[A-Za-z0-9_-]{8,128}$"
    return bool(re.match(pattern, api_key))


def get_mcp(config_dir=None):
    mcp_config_file = get_config_file_path(
        config_dir, MCP_CONFIG_FILE_NAME, create=False
    )
    # exists and not empty
    if not mcp_config_file.exists() or mcp_config_file.stat().st_size == 0:
        return None
    return MCPToolManager(mcp_config_file)


def get_tt_api_key(settings=None) -> str:
    """获取 TrustToken API Key
    :param settings: 配置对象
    :return: API Key 字符串
    """
    if not settings or not isinstance(settings, Dynaconf):
        return ""

    key = settings.get('llm', {}).get('Trustoken', {}).get('api_key')
    if not key:
        key = settings.get('llm', {}).get('trustoken', {}).get('api_key')
    if not key:
        return ""
    return key


class ConfigManager:
    def __init__(self, config_dir=None):
        self.config_file = get_config_file_path(config_dir)
        self.user_config_file = get_config_file_path(config_dir, USER_CONFIG_FILE_NAME)
        self.default_config = __respath__ / "default.toml"
        self.config = self._load_config()

        self.config.update({'_config_dir': config_dir})

        self.trust_token = TrustToken()
        # print(self.config.to_dict())

    def get_work_dir(self):
        if self.config.workdir:
            return Path.cwd() / self.config.workdir
        return Path.cwd()

    def _load_config(self, settings_files=[]):
        """加载配置文件
        :param settings_files: 配置文件列表
        :return: 配置对象
        """
        if not settings_files:
            # 新版本配置文件
            settings_files = [
                self.default_config,
                self.user_config_file,
                self.config_file,
            ]
        # 读取配置文件
        try:
            config = Dynaconf(
                settings_files=settings_files, envvar_prefix="AIPY", merge_enabled=True
            )

            # check if it's a valid config
            assert config.to_dict()
        except Exception as e:
            # 配置加载异常处理
            # print(T('error_loading_config'), str(e))
            # 回退到一个空配置实例，避免后续代码因 config 未定义而出错
            config = Dynaconf(
                settings_files=[], envvar_prefix="AIPY", merge_enabled=True
            )
        return config

    def reload_config(self):
        self.config = self._load_config()
        return self.config

    def get_config(self):
        return self.config

    def update_sys_config(self, new_config, overwrite=False):
        """更新aipyapp.toml配置文件
        :param new_config: 新配置字典, 如 {"workdir": "/path/to/workdir"}
        """
        # 加载系统配置文件
        assert isinstance(new_config, dict)

        if overwrite:
            # 如果需要覆盖，则直接使用新的配置
            config = Dynaconf(
                settings_files=[], envvar_prefix="AIPY", merge_enabled=True
            )
        else:
            config = self._load_config(settings_files=[self.config_file])

        config.update(new_config)

        # 保存到配置文件
        header_comments = [
            f"# Configuration file for {__PACKAGE_NAME__}",
            "# Auto-generated on "
            + datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            f"# 请勿直接修改此文件，除非您了解具体配置格式，如果自定义配置，请放到{self.user_config_file}",
            f"# Please do not edit this file directly unless you understand the format. If you want to customize the configuration, please edit {self.user_config_file}",
            "",
        ]
        footer_comments = ["", "# End of configuration file"]
        # print(config.to_dict())
        cfg_dict = lowercase_keys(config.to_dict())

        with open(self.config_file, "w", encoding="utf-8") as f:
            # 1. 写入头部注释
            f.write("\n".join(header_comments) + "\n")

            # 2. 写入 TOML 内容到临时内存文件
            temp_buffer = io.BytesIO()
            tomli_w.dump(cfg_dict, temp_buffer, multiline_strings=True)
            toml_content = temp_buffer.getvalue().decode('utf-8')

            # 3. 写入 TOML 内容
            f.write(toml_content)

            # 4. 写入尾部注释
            f.write("\n".join(footer_comments))
        return config

    def update_api_config(self, new_api_config):
        """更新配置文件中的API定义"""
        assert isinstance(new_api_config, dict)
        assert 'api' in new_api_config
        config = self._load_config(settings_files=[self.config_file])
        cfg_dict = lowercase_keys(config.to_dict())
        cfg_dict.pop('api', None)
        cfg_dict.update(new_api_config)

        # 配置overwrite
        self.update_sys_config(cfg_dict, overwrite=True)

    def save_tt_config(self, api_key):
        config = {
            'llm': {
                'trustoken': {
                    'api_key': api_key,
                    'type': 'trust',
                    'base_url': T("https://sapi.trustoken.ai/v1"),
                    'model': 'auto',
                    'default': True,
                    'enable': True,
                }
            }
        }
        self.update_sys_config(config)
        return config

    def check_llm(self):
        """检查是否有可用的LLM配置。
        只要有可用的配置，就不强制要求trustoken配置。
        """
        llm = self.config.get("llm")
        if not llm:
            print(T("Missing 'llm' configuration."))

        llms = {}
        for name, config in self.config.get('llm', {}).items():
            if config.get("enable", True):
                llms[name] = config

        return llms

    def fetch_config(self):
        """从tt获取配置并保存到配置文件中。"""
        self.trust_token.fetch_token(self.save_tt_config)

    def check_config(self, gui=False):
        """检查配置文件是否存在，并加载配置。
        如果配置文件不存在，则创建一个新的配置文件。
        """
        try:
            if not self.config:
                print(T("Configuration not loaded."))
                return

            if self.check_llm():
                # 有状态为 enable 的配置文件，则不需要强制要求 trustoken 配置。
                return

            # 尝试从旧版本配置迁移
            if self._migrate_config():
                # 迁移完成后重新加载配置
                self.reload_config()

            # 如果仍然没有可用的 LLM 配置，则从网络拉取
            if not self.check_llm():
                if gui:
                    return 'TrustToken'
                self.fetch_config()
                self.reload_config()

            if not self.check_llm():
                print(T("Missing 'llm' configuration."))
                sys.exit(1)

        except Exception as e:
            traceback.print_exc()
            sys.exit(1)

    def _migrate_config(self):
        """
        Migrates configuration from old settings files (OLD_SETTINGS_FILES)
        to the new user_config.toml and potentially creates the main aipyapp.toml
        if a TrustToken configuration is found.
        """
        combined_toml_content = ""
        migrated_files = []
        backup_files = []

        for path in OLD_SETTINGS_FILES:
            if not path.exists():
                continue

            try:
                config = Dynaconf(settings_files=[path])
                config_dict = config.to_dict()
                assert config_dict

                try:
                    content = path.read_text(encoding='utf-8')
                except UnicodeDecodeError:
                    try:
                        content = path.read_text(encoding='gbk')
                    except Exception as e:
                        print(f"Error reading file {path}: {e}")
                        continue

                combined_toml_content += content + "\n\n"  # Add separator

                # 文件内容、格式都正常，则准备迁移
                migrated_files.append(str(path))
                # Backup the old file
                backup_path = path.with_name(f"{path.stem}-backup{path.suffix}")
                try:
                    path.rename(backup_path)
                    backup_files.append(str(backup_path))
                except Exception as e:
                    pass

            except Exception as e:
                pass
        if not combined_toml_content:
            return

        print(T("""Found old configuration files: {}
Attempting to migrate configuration from these files...
After migration, these files will be backed up to {}, please check them.""").format(
                ', '.join(migrated_files), ', '.join(backup_files)
            )
        )

        # Write combined content to user_config.toml
        try:
            with open(self.user_config_file, "w", encoding="utf-8") as f:
                f.write(f"# Migrated from: {', '.join(migrated_files)}\n")
                f.write(f"# Original files backed up to: {', '.join(backup_files)}\n\n")
                f.write(combined_toml_content)
                print(T("Successfully migrated old version user configuration to {}").format(self.user_config_file))
        except Exception as e:
            return

        # Now, load the newly created user config to find TT key
        try:
            temp_config = self._load_config(settings_files=[self.user_config_file])
            llm_config = temp_config.get('llm', {})

            for section_name, section_data in llm_config.items():
                if isinstance(section_data, dict) and self._is_tt_config(
                    section_name, section_data
                ):
                    api_key = section_data.get('api_key', section_data.get('api-key'))
                    if api_key:
                        # print("Token found:", api_key)
                        self.save_tt_config(api_key)
                        print(T("Successfully migrated old version trustoken configuration to {}").format(self.config_file))
                        break

        except Exception as e:
            pass

        return True

    def _is_tt_config(self, name, config):
        """
        判断配置是否符合特定条件

        参数:
            name: 配置名称
            config: 配置内容字典

        返回: 如果符合条件返回True
        """
        # 条件1: 配置名称包含目标关键字
        if any(keyword in name.lower() for keyword in ['trustoken', 'trust']):
            return True

        base_url = config.get('base_url', config.get('base-url', '')).lower()
        # 条件2: base_url包含目标域名
        if isinstance(config, dict) and base_url:
            if 'trustoken.' in base_url:
                return True

        # 条件3: 其他特定标记
        # type == trust, 且没有base_url.
        if isinstance(config, dict) and config.get('type') == 'trust' and not base_url:
            return True

        return False
