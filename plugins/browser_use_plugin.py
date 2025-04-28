"""
Browser Use 插件使用说明
------------------------

功能介绍：
    本插件集成了Browser-Use工具，可以让AiPy通过浏览器访问网站，获取网页信息，
    并进行分析和处理。插件会自动获取当前AiPy使用的LLM配置，无需手动设置。

安装依赖：
    1. pip install browser-use
    2. pip install playwright
    3. playwright install chromium

使用方法：
    1. 将插件复制到AiPy的插件目录(plugins)下;
    1. 在任务中描述需要访问的网站和获取的信息;
    2. AiPy会自动生成使用Browser-Use的代码;
    3. 代码执行后，Browser-Use会打开浏览器访问网站，获取信息并返回结果.

示例任务：
    "帮我打开知道创宇云防御官方网站，将网站中所有产品相关信息整理出来。"
    "访问百度，搜索'人工智能最新进展'，并总结前三条结果"

注意事项：
    1. 首次使用时可能需要安装依赖
    2. 确保网络连接正常
    3. 如果遇到问题，可以查看控制台输出的错误信息

配置说明：
    插件会自动获取当前AiPy使用的LLM配置（model_name, base_url, api_key），
    无需手动配置。如果无法获取，会使用默认值并提示用户输入。
"""

class Plugin:
	def __init__(self):
		print("[+] 加载Browser Use插件")
		# 以下是备用配置，实际会自动获取当前AiPy使用的LLM配置
		# 只有在无法获取当前LLM配置时才会使用这些默认值
		self.model_name = None
		self.base_url = None
		self.api_key = None
		self.task_manager = None
	def on_exec(self, blocks):
		"""
		执行代码事件
		param: blocks
		"""
		# 检查blocks是否为None
		if blocks is None:
			print("[!] Browser Use插件：blocks参数为None，跳过处理")
			return blocks

		# 检查blocks是否包含Python代码
		if isinstance(blocks, dict) and 'main' in blocks:
			code = blocks.get('main', '')

			# 如果代码中使用了runtime.getenv
			if 'runtime.getenv' in code:
				# 获取task_manager
				import inspect
				frame = inspect.currentframe()
				while frame:
					if 'self' in frame.f_locals and hasattr(frame.f_locals['self'], 'runner'):
						task_manager = frame.f_locals['self']
						self.task_manager = task_manager

						# 尝试获取当前LLM的配置
						if hasattr(task_manager, 'llm') and task_manager.llm:
							llm = task_manager.llm
							if hasattr(llm, 'current') and llm.current:
								current_llm = llm.current
								# 获取当前LLM的配置
								if hasattr(current_llm, '_model'):
									self.model_name = current_llm._model
								if hasattr(current_llm, '_base_url'):
									self.base_url = current_llm._base_url
								if hasattr(current_llm, '_api_key'):
									self.api_key = current_llm._api_key
								print(f"[+] Browser Use插件获取到当前LLM配置: {current_llm.name}, {self.model_name}")
							elif hasattr(llm, 'default') and llm.default:
								default_llm = llm.default
								# 获取默认LLM的配置
								if hasattr(default_llm, '_model'):
									self.model_name = default_llm._model
								if hasattr(default_llm, '_base_url'):
									self.base_url = default_llm._base_url
								if hasattr(default_llm, '_api_key'):
									self.api_key = default_llm._api_key
								print(f"[+] Browser Use插件获取到默认LLM配置: {default_llm.name}, {self.model_name}")

						# 设置默认值（如果没有获取到配置）
						if self.model_name is None:
							self.model_name = "auto"  # 默认模型
						if self.base_url is None:
							self.base_url = "https://api.trustoken.ai/v1"  # 默认API基础URL
						if self.api_key is None:
							self.api_key = ""  # 空字符串，会提示用户输入

						# 设置环境变量到Runner的env字典中
						if hasattr(task_manager, 'runner') and task_manager.runner:
							runner = task_manager.runner
							runner.env["model_name"] = (self.model_name, "LLM模型名称")
							runner.env["base_url"] = (self.base_url, "LLM API基础URL")
							runner.env["api_key"] = (self.api_key, "LLM API密钥")
							print("[+] Browser Use插件在代码执行前设置环境变量")
						break
					frame = frame.f_back

				# 不修改代码，让runtime.getenv自然工作
				print("[+] 使用Runner的env字典存储环境变量")
	def on_task_start(self, prompt):
		"""
		任务开始事件
		param: prompt
		"""
		# 检查prompt是否为None
		if prompt is None:
			print("[!] Browser Use插件：prompt参数为None，跳过处理")
			return prompt

		# 确保环境变量已设置
		if hasattr(prompt, 'get') and callable(prompt.get) and prompt.get('task'):
			# 获取task_manager
			import inspect
			frame = inspect.currentframe()
			while frame:
				if 'self' in frame.f_locals and hasattr(frame.f_locals['self'], 'runner'):
					task_manager = frame.f_locals['self']
					self.task_manager = task_manager

					# 尝试获取当前LLM的配置
					if hasattr(task_manager, 'llm') and task_manager.llm:
						llm = task_manager.llm
						if hasattr(llm, 'current') and llm.current:
							current_llm = llm.current
							# 获取当前LLM的配置
							if hasattr(current_llm, '_model'):
								self.model_name = current_llm._model
							if hasattr(current_llm, '_base_url'):
								self.base_url = current_llm._base_url
							if hasattr(current_llm, '_api_key'):
								self.api_key = current_llm._api_key
							print(f"[+] Browser Use插件获取到当前LLM配置: {current_llm.name}, {self.model_name}")
						elif hasattr(llm, 'default') and llm.default:
							default_llm = llm.default
							# 获取默认LLM的配置
							if hasattr(default_llm, '_model'):
								self.model_name = default_llm._model
							if hasattr(default_llm, '_base_url'):
								self.base_url = default_llm._base_url
							if hasattr(default_llm, '_api_key'):
								self.api_key = default_llm._api_key
							print(f"[+] Browser Use插件获取到默认LLM配置: {default_llm.name}, {self.model_name}")

					# 设置默认值（如果没有获取到配置）
					if self.model_name is None:
						self.model_name = "gpt-3.5-turbo"  # 默认模型
					if self.base_url is None:
						self.base_url = "https://api.openai.com/v1"  # 默认API基础URL
					if self.api_key is None:
						self.api_key = ""  # 空字符串，会提示用户输入

					# 设置环境变量到Runner的env字典中
					if hasattr(task_manager, 'runner') and task_manager.runner:
						runner = task_manager.runner
						runner.env["model_name"] = (self.model_name, "LLM模型名称")
						runner.env["base_url"] = (self.base_url, "LLM API基础URL")
						runner.env["api_key"] = (self.api_key, "LLM API密钥")
						print("[+] Browser Use插件在任务开始时设置环境变量")
					break
				frame = frame.f_back

			# 不设置系统环境变量，只使用Runner的env字典

		task = prompt.get('task')
		role = """当需要通过打开网站来获取信息时，优先使用Browser-Use来打开浏览器访问网站，以下为Browser-Use具体使用方法：
1. 使用Browser-Use时，调用LLM模型的API信息，请参考[api.browseruse]配置；
2. Browser-Use工具使用步骤：
Step1：使用 pip 安装 browser-use ,软件版本号为：0.1.40；
Step2：安装 playwright（说明：需要安装内置浏览器 playwright install chromium）；
Step3：通过Python程序调用Browser-Use工具打开浏览器，注意代码要求与格式
3. Browser-Use操作浏览器程序代码(注意：只能按以下代码来使用Browser-Use)
``python main
import asynciofrom langchain_openai import ChatOpenAI
from browser_use import Agent
import json
import sys

# 获取必要的环境变量
model_name = runtime.getenv("model_name", desc="LLM模型名称")
base_url = runtime.getenv("base_url", desc="LLM API基础URL")
api_key = runtime.getenv("api_key", desc="LLM API密钥")

if not all([model_name, base_url, api_key]):
    print("Error: 缺少必要的环境变量配置", file=sys.stderr)
    __result__ = {"status": "error", "message": "缺少必要的API环境变量配置"}
else:
    try:
        llm = ChatOpenAI(
            model=model_name,
            base_url=base_url,
            api_key=api_key
        )

        agent = Agent(
            task="此处对要访问的网页任务进行描述，需要指定目标网址。",
            llm=llm,
            use_vision=False,
        )

        # 运行浏览器代理
        result = asyncio.run(agent.run())
        
        # 将结果保存到变量中
        __result__ = {
            "status": "success",
            "website": "https://www.xxx.com/",
            "content": result,
            "message": "信息提取完成"
        }
        
        # 打印输出结果
        print(__result__)

    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        __result__ = {"status": "error", "message": str(e)}
```
4. 请不要对返回内容做任何格式上的处理，直接打印输出即可。
"""
		prompt['task'] = f"{role}\n{task}"