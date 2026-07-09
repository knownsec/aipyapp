#! /usr/bin/env python3
# -*- coding: utf-8 -*-

import requests
from typing import List
import time
import webbrowser
import threading

import wx
import wx.adv
from loguru import logger

from ..aipy.trustoken import TrustTokenAPI
from .. import T

class InitialProviderPage(wx.adv.WizardPage):
    def __init__(self, parent, provider_config):
        super().__init__(parent)
        self.provider_config = provider_config
        self.init_ui()
        self.SetSize(800, 600)

    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 标题
        title = wx.StaticText(self, label=T('Select LLM Provider'))
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # Provider 选择
        provider_box = wx.StaticBox(self, label=T('Provider'))
        provider_sizer = wx.StaticBoxSizer(provider_box, wx.VERTICAL)

        self.provider_choice = wx.Choice(
            self,
            choices=['Trustoken', T('Other')]
        )
        self.provider_choice.SetSelection(0)  # 默认选中 TrustToken
        self.provider_choice.Bind(wx.EVT_CHOICE, self.on_provider_selected)
        provider_sizer.Add(self.provider_choice, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(provider_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 提示信息
        self.hint = wx.StaticText(self, label="")
        # 设置文本自动换行
        self.hint.Wrap(400)
        vbox.Add(self.hint, 0, wx.ALL | wx.EXPAND, 10)

        self.SetSizer(vbox)
        # 设置初始提示信息
        self.on_provider_selected(None)

    def on_provider_selected(self, event):
        provider = self.provider_choice.GetStringSelection()
        if provider == 'Trustoken':
            self.hint.SetLabel(f"""{T('Trustoken is an intelligent API Key management service')}：

1. {T('Auto get and manage API Key')}
2. {T('Support multiple LLM providers')}
3. {T('Auto select optimal model')}
4. {T('Recommended for beginners, easy to configure and feature-rich')}""")
        else:
            self.hint.SetLabel(f"""{T('Select other providers requires manual configuration')}：

1. {T('Need to apply for API Key yourself')}
2. {T('Manually input API Key')}
3. {T('Manually select model')}""")
        # 重新计算换行
        self.hint.Wrap(400)

    def get_selection(self):
        # 获取当前选择，如果没有选择则返回默认值
        selection = self.provider_choice.GetStringSelection()
        if not selection:
            # 如果获取不到选择，使用 GetSelection() 获取索引
            index = self.provider_choice.GetSelection()
            if index >= 0:
                selection = self.provider_choice.GetString(index)
            else:
                selection = 'Trustoken'  # 如果索引也无效，返回默认值
        return selection

    def GetNext(self):
        selection = self.get_selection()
        if selection == "Trustoken":
            return self.GetParent().trust_token_page
        else:
            return self.GetParent().provider_page

    def GetPrev(self):
        return None

class TrustTokenPage(wx.adv.WizardPage):
    def __init__(self, parent, provider_config):
        super().__init__(parent)
        self.provider_config = provider_config
        self.api = TrustTokenAPI()
        self.poll_interval = 5
        self.request_id = None
        self.polling_thread = None
        self.stop_polling = False
        self.start_time = None
        self.polling_timeout = 310  # 5分钟10秒
        self.init_ui()
        self.SetSize(800, 600)
        # 绑定页面切换事件
        self.GetParent().Bind(wx.adv.EVT_WIZARD_PAGE_CHANGING, self.on_page_changing)

    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 标题
        title = wx.StaticText(self, label=T('Trustoken Configuration'))
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # API Key 显示
        api_key_box = wx.StaticBox(self, label="API Key")
        api_key_sizer = wx.StaticBoxSizer(api_key_box, wx.VERTICAL)

        self.api_key_text = wx.TextCtrl(
            self,
            style=wx.TE_READONLY
        )
        api_key_sizer.Add(self.api_key_text, 1, wx.EXPAND | wx.ALL, 5)
        vbox.Add(api_key_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 获取按钮
        self.fetch_button = wx.Button(self, label=T('Auto open browser to get API Key'))
        self.fetch_button.Bind(wx.EVT_BUTTON, self.on_fetch)
        vbox.Add(self.fetch_button, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # 状态信息
        self.status_text = wx.StaticText(self, label="")
        vbox.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 5)

        self.url_ctrl = wx.adv.HyperlinkCtrl(self, label=T('You can also click this link to open browser to get API Key'), style=wx.adv.HL_ALIGN_LEFT | wx.adv.HL_CONTEXTMENU)
        self.url_ctrl.Hide()
        vbox.Add(self.url_ctrl, 0, wx.ALL, 5)

        vbox.AddSpacer(20)

        # 剩余时间文本
        self.time_text = wx.StaticText(self, label='')
        vbox.Add(self.time_text, 0, wx.EXPAND | wx.ALL, 5)

        # 进度条
        self.progress_bar = wx.Gauge(self, range=100)
        vbox.Add(self.progress_bar, 0, wx.EXPAND | wx.ALL, 5)

        self._toggle_progress(False)
        self.SetSizer(vbox)

    def _toggle_progress(self, show: bool):
        self.progress_bar.Show(show)
        self.time_text.Show(show)

    def _update_progress(self):
        if not self.start_time:
            return

        elapsed = time.time() - self.start_time
        if elapsed >= self.polling_timeout:
            progress = 100
            time_remaining = 0
        else:
            progress = int((elapsed / self.polling_timeout) * 100)
            time_remaining = int(self.polling_timeout - elapsed)

        wx.CallAfter(self.progress_bar.SetValue, progress)
        wx.CallAfter(self.time_text.SetLabel, f"{T('Remaining time')}: {time_remaining}{T('seconds')}")

    def _poll_status(self, save_func):
        self.start_time = time.time()
        while not self.stop_polling and time.time() - self.start_time < self.polling_timeout:
            self._update_progress()

            data = self.api.check_status(self.request_id)
            if not data:
                time.sleep(self.poll_interval)
                continue

            status = data.get('status')
            wx.CallAfter(self._update_status, f"{T('Current status')}: {status}")

            if status == 'approved':
                if save_func:
                    save_func(data['secret_token'])
                wx.CallAfter(self._on_success)
                return True
            elif status == 'expired':
                wx.CallAfter(self._update_status, T('Binding expired'))
                wx.CallAfter(self._on_failure)
                return False
            elif status == 'pending':
                pass
            else:
                wx.CallAfter(self._update_status, f"{T('Unknown status')}: {status}")
                wx.CallAfter(self._on_failure)
                return False

            time.sleep(self.poll_interval)

        if not self.stop_polling:
            wx.CallAfter(self._update_status, T('Waiting timeout'))
            wx.CallAfter(self._on_failure)
        return False

    def _update_status(self, status):
        self.status_text.SetLabel(status)

    def _on_success(self):
        self._toggle_progress(False)
        self.fetch_button.Enable()
        self.status_text.SetLabel(T("API Key obtained successfully!"))
        self.Layout()  # 强制重新布局

    def _on_failure(self):
        self._toggle_progress(False)
        self.fetch_button.Enable()
        self.status_text.SetLabel(T('API Key acquisition failed, please try again'))
        self.Layout()  # 强制重新布局

    def on_fetch(self, event):
        self.status_text.SetLabel(T('Requesting binding'))
        self.fetch_button.Disable()

        data = self.api.request_binding()
        if not data:
            self._on_failure()
            return

        approval_url = data['approval_url']
        self.request_id = data['request_id']
        expires_in = data['expires_in']
        self.polling_timeout = expires_in
        self._update_status(T('Waiting for user confirmation'))

        # 打开浏览器
        self.url_ctrl.SetURL(approval_url)
        self.url_ctrl.Show()
        webbrowser.open(approval_url)

        # 显示进度组并重新布局
        self._toggle_progress(True)
        self.Layout()

        # 开始轮询
        self.polling_thread = threading.Thread(
            target=self._poll_status,
            args=(self._save_token,)
        )
        self.polling_thread.daemon = True
        self.polling_thread.start()

    def _save_token(self, token):
        self.api_key_text.SetValue(token)

    def get_api_key(self):
        return self.api_key_text.GetValue()

    def on_page_changing(self, event):
        # 如果是当前页面，且是向前切换
        if event.GetPage() == self and event.GetDirection():
            api_key = self.get_api_key()
            if not api_key:
                wx.MessageBox(T('Please get API Key first'), T('Hint'), wx.OK | wx.ICON_INFORMATION)
                event.Veto()
                return
        event.Skip()

    def GetNext(self):
        return self.GetParent().model_page

    def GetPrev(self):
        return self.GetParent().initial_page

class ProviderPage(wx.adv.WizardPage):
    def __init__(self, parent, provider_config):
        super().__init__(parent)
        self.provider_config = provider_config
        self.init_ui()
        self.SetSize(800, 600)
        self.GetParent().Bind(wx.adv.EVT_WIZARD_PAGE_CHANGING, self.on_page_changing)

    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 标题
        title = wx.StaticText(self, label=T('Select LLM Provider'))
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # Provider 选择
        provider_box = wx.StaticBox(self, label=T('Provider'))
        provider_sizer = wx.StaticBoxSizer(provider_box, wx.VERTICAL)

        # 过滤掉 TrustToken
        providers = [name for name in self.provider_config.providers.keys() if name != "Trustoken"]
        self.provider_choice = wx.Choice(
            self,
            choices=providers
        )
        if providers:  # 确保列表不为空
            self.provider_choice.SetSelection(0)  # 默认选中第一个选项
        self.provider_choice.Bind(wx.EVT_CHOICE, self.on_provider_selected)
        provider_sizer.Add(self.provider_choice, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(provider_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # API Key 输入
        api_key_box = wx.StaticBox(self, label="API Key")
        api_key_sizer = wx.StaticBoxSizer(api_key_box, wx.VERTICAL)

        self.api_key_text = wx.TextCtrl(
            self,
            size=(400, -1)
        )
        api_key_sizer.Add(self.api_key_text, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(api_key_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 提示信息
        hint = wx.StaticText(self, label=T('Please select provider and input API Key, click Next to verify'))
        hint.SetForegroundColour(wx.Colour(100, 100, 100))
        vbox.Add(hint, 0, wx.ALL, 10)

        self.SetSizer(vbox)

    def on_provider_selected(self, event):
        provider = self.provider_choice.GetStringSelection()
        if provider in self.provider_config.config:
            config = self.provider_config.config[provider]
            self.api_key_text.SetValue(config["api_key"])

    def get_provider(self):
        return self.provider_choice.GetStringSelection()

    def get_api_key(self):
        return self.api_key_text.GetValue()

    def GetNext(self):
        return self.GetParent().model_page

    def GetPrev(self):
        return self.GetParent().initial_page

    def on_page_changing(self, event):
        # 如果是当前页面，且是向前切换
        if event.GetPage() == self and event.GetDirection():
            api_key = self.get_api_key()
            if not api_key:
                wx.MessageBox(T('Please get API Key first'), T('Hint'), wx.OK | wx.ICON_INFORMATION)
                event.Veto()
                return
        event.Skip()
        
class ModelPage(wx.adv.WizardPage):
    def __init__(self, parent, provider_config):
        super().__init__(parent)
        self.provider_config = provider_config
        self.prev_page = None  # 添加一个变量来记录上一页
        self.init_ui()
        self.SetSize(800, 600)

    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 标题
        title = wx.StaticText(self, label=T('Select Model'))
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # Model 选择
        model_box = wx.StaticBox(self, label=T('Available Models'))
        model_sizer = wx.StaticBoxSizer(model_box, wx.VERTICAL)

        self.model_choice = wx.Choice(self)
        model_sizer.Add(self.model_choice, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(model_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # Max Tokens 配置
        max_tokens_box = wx.StaticBox(self, label=T('Max Tokens'))
        max_tokens_sizer = wx.StaticBoxSizer(max_tokens_box, wx.VERTICAL)

        self.max_tokens_text = wx.TextCtrl(self, value="8192")
        max_tokens_sizer.Add(self.max_tokens_text, 0, wx.EXPAND | wx.ALL, 5)
        vbox.Add(max_tokens_sizer, 0, wx.EXPAND | wx.ALL, 5)

        # 提示信息
        self.hint = wx.StaticText(self, label=T('Please select model to use and configure parameters'))
        self.hint.SetForegroundColour(wx.Colour(100, 100, 100))
        vbox.Add(self.hint, 0, wx.ALL, 10)

        self.SetSizer(vbox)

    def set_models(self, models: List[str], selected_model: str = None, is_trust_token: bool = False):
        if is_trust_token:
            self.model_choice.SetItems(["auto"])
            self.model_choice.SetSelection(0)
            self.model_choice.Disable()  # 禁用选择
            self.hint.SetLabel(T('Trustoken uses automatic model selection'))
        else:
            self.model_choice.SetItems(models)
            self.model_choice.Enable()  # 启用选择
            if selected_model and selected_model in models:
                self.model_choice.SetStringSelection(selected_model)
            elif models:  # 如果有模型列表但没有指定选择的模型，默认选择第一个
                self.model_choice.SetSelection(0)
            self.hint.SetLabel(T('Please select model to use and configure parameters'))

    def get_selected_model(self):
        return self.model_choice.GetStringSelection()

    def get_max_tokens(self):
        try:
            return int(self.max_tokens_text.GetValue())
        except ValueError:
            return 8192

    def GetNext(self):
        return None

    def GetPrev(self):
        return self.prev_page

class OAuthPage(wx.adv.WizardPage):
    def __init__(self, parent, provider_config):
        super().__init__(parent)
        self.provider_config = provider_config
        self.prev_page = None
        self.init_ui()

    def init_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        # 标题
        title = wx.StaticText(self, label=T('OAuth Gateway Configuration'))
        title.SetFont(wx.Font(12, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD))
        vbox.Add(title, 0, wx.ALL | wx.ALIGN_CENTER, 10)

        # Client ID
        client_id_box = wx.BoxSizer(wx.HORIZONTAL)
        client_id_label = wx.StaticText(self, label=T('Client ID:'))
        self.client_id_input = wx.TextCtrl(self)
        client_id_box.Add(client_id_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        client_id_box.Add(self.client_id_input, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(client_id_box, 0, wx.EXPAND | wx.ALL, 5)

        # Client Secret
        client_secret_box = wx.BoxSizer(wx.HORIZONTAL)
        client_secret_label = wx.StaticText(self, label=T('Client Secret:'))
        self.client_secret_input = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        client_secret_box.Add(client_secret_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        client_secret_box.Add(self.client_secret_input, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(client_secret_box, 0, wx.EXPAND | wx.ALL, 5)

        # Token URL
        token_url_box = wx.BoxSizer(wx.HORIZONTAL)
        token_url_label = wx.StaticText(self, label=T('Token URL:'))
        self.token_url_input = wx.TextCtrl(self)
        token_url_box.Add(token_url_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        token_url_box.Add(self.token_url_input, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(token_url_box, 0, wx.EXPAND | wx.ALL, 5)

        # API Base URL
        base_url_box = wx.BoxSizer(wx.HORIZONTAL)
        base_url_label = wx.StaticText(self, label=T('API Base URL:'))
        self.base_url_input = wx.TextCtrl(self)
        base_url_box.Add(base_url_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        base_url_box.Add(self.base_url_input, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(base_url_box, 0, wx.EXPAND | wx.ALL, 5)

        # Model Name
        model_box = wx.BoxSizer(wx.HORIZONTAL)
        model_label = wx.StaticText(self, label=T('Model Name:'))
        self.model_input = wx.TextCtrl(self)
        model_box.Add(model_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        model_box.Add(self.model_input, 1, wx.ALL | wx.EXPAND, 5)
        vbox.Add(model_box, 0, wx.EXPAND | wx.ALL, 5)

        # 测试按钮
        test_box = wx.BoxSizer(wx.HORIZONTAL)
        self.test_button = wx.Button(self, label=T('Test Connection'))
        self.test_button.Bind(wx.EVT_BUTTON, self.on_test)
        test_box.Add(self.test_button, 0, wx.ALL, 5)
        self.test_result = wx.StaticText(self, label="")
        test_box.Add(self.test_result, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        vbox.Add(test_box, 0, wx.EXPAND | wx.ALL, 10)

        self.SetSizer(vbox)

    def get_client_id(self):
        return self.client_id_input.GetValue().strip()

    def get_client_secret(self):
        return self.client_secret_input.GetValue().strip()

    def get_token_url(self):
        return self.token_url_input.GetValue().strip()

    def get_base_url(self):
        return self.base_url_input.GetValue().strip()
    
    def get_model(self):
        return self.model_input.GetValue().strip()

    def on_test(self, event):
        client_id = self.get_client_id()
        client_secret = self.get_client_secret()
        token_url = self.get_token_url()
        base_url = self.get_base_url()
        model = self.get_model()
        
        if not client_id or not client_secret or not token_url or not base_url or not model:
            self.test_result.SetLabel(T("Please fill in all fields"))
            return

        # Start testing in a separate thread to avoid UI freeze
        threading.Thread(target=self._test_connection, args=(client_id, client_secret, token_url, base_url)).start()
        self.test_result.SetLabel(T("Testing connection..."))
        self.test_button.Enable(False)

    def _test_connection(self, client_id, client_secret, token_url, base_url):
        try:
            # First try to get a token
            response = requests.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": client_id,
                    "client_secret": client_secret
                },
                timeout=10
            )
            response.raise_for_status()
            token_data = response.json()
            token = token_data.get("access_token")
            
            if not token:
                wx.CallAfter(self._update_test_result, False, "No token received")
                return
                
            # Now try to access the models endpoint
            models_url = f"{base_url}/models"
            response = requests.get(
                models_url,
                headers={"Authorization": f"Bearer {token}"},
                timeout=10
            )
            response.raise_for_status()
            
            # If we get here, the connection is working
            wx.CallAfter(self._update_test_result, True)
        except Exception as e:
            wx.CallAfter(self._update_test_result, False, str(e))
    
    def _update_test_result(self, success, error=None):
        if success:
            self.test_result.SetLabel(T("✓ Connection successful"))
            self.test_result.SetForegroundColour(wx.Colour(0, 128, 0))
        else:
            self.test_result.SetLabel(f"✗ {error}")
            self.test_result.SetForegroundColour(wx.Colour(255, 0, 0))
        self.test_button.Enable(True)

    def GetNext(self):
        # In the wizard flow, this should go directly to the model page
        # but for OAuth we have the model defined here
        wizard = self.GetParent()
        return wizard.model_page

    def GetPrev(self):
        return self.prev_page

class ProviderConfigWizard(wx.adv.Wizard):
    def __init__(self, llm_config, parent):
        super().__init__(parent, title=T('LLM Provider Configuration Wizard'))
        self.provider_config = llm_config
        self.init_ui()
        self.SetPageSize((600, 400))
        self.Centre()
        self.log = logger.bind(src="wizard")

    def init_ui(self):
        # 创建向导页面
        self.initial_page = InitialProviderPage(self, self.provider_config)
        self.trust_token_page = TrustTokenPage(self, self.provider_config)
        self.provider_page = ProviderPage(self, self.provider_config)
        self.model_page = ModelPage(self, self.provider_config)
        self.oauth_page = OAuthPage(self, self.provider_config)

        # 绑定事件
        self.Bind(wx.adv.EVT_WIZARD_PAGE_CHANGED, self.on_page_changed)
        self.Bind(wx.adv.EVT_WIZARD_FINISHED, self.on_finished)

        wx.CallAfter(self._set_button_labels)

    def _set_button_labels(self):
        btn_next = self.FindWindowById(wx.ID_FORWARD)
        btn_back = self.FindWindowById(wx.ID_BACKWARD)
        btn_cancel = self.FindWindowById(wx.ID_CANCEL)

        if btn_next: btn_next.SetLabel(T('Next'))
        if btn_back: btn_back.SetLabel(T('Back'))
        if btn_cancel: btn_cancel.SetLabel(T('Cancel'))

    def on_page_changed(self, event):
        btn_next = self.FindWindowById(wx.ID_FORWARD)
        if btn_next: btn_next.SetLabel(T('Next'))

        if event.GetPage() == self.model_page:
            if btn_next: btn_next.SetLabel(T('Finish'))
            # 从第一步进入第二步时，验证 API Key 并获取模型列表
            provider = self.provider_page.get_provider()
            api_key = self.provider_page.get_api_key()
            if not provider or not api_key:
                self.model_page.prev_page = self.trust_token_page
                provider = "Trustoken"
                api_key = self.trust_token_page.get_api_key()
                # 对于 TrustToken，直接设置模型为 auto
                self.model_page.set_models([], None, is_trust_token=True)
            else:
                self.model_page.prev_page = self.provider_page
                models = self.get_models(provider, api_key)
                if not models:
                    event.Veto()
                    return

                # 设置模型列表
                selected_model = None
                if provider in self.provider_config.config:
                    selected_model = self.provider_config.config[provider].get("selected_model")
                self.model_page.set_models(models, selected_model)
        elif event.GetPage() == self.trust_token_page:
            self.trust_token_page.prev_page = self.initial_page
        elif event.GetPage() == self.provider_page:
            self.provider_page.prev_page = self.initial_page
        elif event.GetPage() == self.initial_page:
            self.initial_page.prev_page = None
        elif event.GetPage() == self.oauth_page:
            self.oauth_page.prev_page = self.initial_page

    def on_finished(self, event):
        # 根据 model_page 的 prev_page 来判断是从哪个路径来的
        if self.model_page.prev_page == self.trust_token_page:
            provider = "Trustoken"
            api_key = self.trust_token_page.get_api_key()
        else:
            provider = self.provider_page.get_provider()
            api_key = self.provider_page.get_api_key()

        selected_model = self.model_page.get_selected_model()
        max_tokens = self.model_page.get_max_tokens()
        provider_info = self.provider_config.providers[provider]

        config = self.provider_config.config
        config[provider] = {
            "api_key": api_key,
            "models": self.model_page.model_choice.GetItems(),
            "model": selected_model,
            "max_tokens": max_tokens,
            "type": provider_info["type"],
            "enable": True
        }

        self.provider_config.save_config(config)
        wx.MessageBox(T('Configuration saved'), T('Success'), wx.OK | wx.ICON_INFORMATION)

    def get_models(self, provider: str, api_key: str) -> List[str]:
        provider_info = self.provider_config.providers[provider]
        headers = {
            "Content-Type": "application/json"
        }

        if provider == "Claude":
            headers["x-api-key"] = api_key
            headers["anthropic-version"] = "2023-06-01"
        else:
            headers["Authorization"] = f"Bearer {api_key}"

        try:
            response = requests.get(
                f"{provider_info['api_base']}{provider_info['models_endpoint']}",
                headers=headers
            )
            self.log.info(f"获取模型列表: {response.text}")
            if response.status_code == 200:
                data = response.json()
                self.log.info(f"获取模型列表成功: {data}")
                if provider in ["OpenAI", "DeepSeek", "MiniMax", "xAI", "Claude"]:
                    return [model["id"] for model in data["data"]]
                elif provider == "Gemini":
                    return [model["name"] for model in data["models"]]
                # 其他 provider 的模型解析逻辑
                return []
        except Exception as e:
            wx.MessageBox(f"{T('Model list acquisition failed')}: {str(e)}", T('Error'), wx.OK | wx.ICON_ERROR)
            return []

def show_provider_config(llm_config, parent=None):
    wizard = ProviderConfigWizard(llm_config, parent)
    wizard.RunWizard(wizard.initial_page)
    wizard.Destroy()
    return wx.ID_OK
