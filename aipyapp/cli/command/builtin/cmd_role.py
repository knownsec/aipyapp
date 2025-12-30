import json

from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree
from rich.syntax import Syntax

from aipyapp import T
from ..base import ParserCommand
from .utils import record2table

class RoleCommand(ParserCommand):
    name = 'role'
    description = T('Role operations')

    def add_subcommands(self, subparsers):
        # List subcommand
        subparsers.add_parser('list', help=T('List available roles'))
        
        # Show subcommand
        show_parser = subparsers.add_parser('show', help=T('Show role details'))
        show_parser.add_argument('role', type=str, help=T('Role name'))
        
        # Use subcommand
        use_parser = subparsers.add_parser('use', help=T('Use a role'))
        use_parser.add_argument('role', type=str, help=T('Role name'))

    def get_arg_values(self, name, subcommand=None, partial=None):
        if name == 'role':
            ctx = self.manager.context
            return [(name, role.short) for name, role in ctx.tm.role_manager.roles.items()]
        return None
            
    def cmd_list(self, args, ctx):
        rows = ctx.tm.list_roles()
        table = record2table(rows)
        ctx.console.print(table)
        
    def cmd_show(self, args, ctx):
        role_name = args.role.lower()
        role = ctx.tm.role_manager.roles.get(role_name)
        if not role:
            self.log.error(T('Role not found').format(args.role))
            return
        
        # 基本信息表格
        basic_table = Table(title=f"{T('Role Information')}: {role.name}", show_lines=True)
        basic_table.add_column(T('Property'), style="bold cyan", justify="right")
        basic_table.add_column(T('Value'), style="bold white", justify="left")
        
        basic_table.add_row(T('Role name'), role.name)
        basic_table.add_row(T('Role description'), role.short)
        basic_table.add_row(T('Tips count'), str(len(role.tips)))
        basic_table.add_row(T('Environment variables count'), str(len(role.envs)))
        basic_table.add_row(T('Package dependencies count'), str(len(role.packages)))
        basic_table.add_row(T('Plugins count'), str(len(role.plugins)))
        basic_table.add_row(T('Features count'), str(len(role.features)))
        
        ctx.console.print(basic_table)
        
        # 详细描述
        if role.detail:
            detail_panel = Panel(role.detail, title=T('Role detail'), border_style="blue")
            ctx.console.print(detail_panel)
        
        # 提示信息表格
        if role.tips:
            tips_table = Table(title=T('Tips'), show_lines=True)
            tips_table.add_column(T('Name'), style="bold green", justify="left")
            tips_table.add_column(T('Description'), style="bold white", justify="left")
            
            for tip_name, tip in role.tips.items():
                tips_table.add_row(tip_name, tip.short)
            
            ctx.console.print(tips_table)
        
        # 环境变量表格
        if role.envs:
            env_table = Table(title=T('Environment variables'), show_lines=True)
            env_table.add_column(T('Name'), style="bold yellow", justify="left")
            env_table.add_column(T('Description'), style="bold white", justify="left")
            env_table.add_column(T('Value'), style="dim", justify="left")
            
            for env_name, (value, desc) in role.envs.items():
                # 截断过长的值
                display_value = value[:50] + "..." if len(value) > 50 else value
                env_table.add_row(env_name, desc, display_value)
            
            ctx.console.print(env_table)
        
        # 包依赖表格
        if role.packages:
            pkg_table = Table(title=T('Package dependencies'), show_lines=True)
            pkg_table.add_column(T('Language'), style="bold magenta", justify="left")
            pkg_table.add_column(T('Packages'), style="bold white", justify="left")
            
            for lang, packages in role.packages.items():
                pkg_table.add_row(lang, ', '.join(packages))
            
            ctx.console.print(pkg_table)

        # 插件表格
        if role.plugins:
            tree = Tree(T('Plugins'))
            for plugin_name, plugin_config in role.plugins.items():
                t = tree.add(plugin_name)
                t.add(Syntax(json.dumps(plugin_config, ensure_ascii=False, indent=2), "json", word_wrap=True))

            ctx.console.print(tree)

        # 功能开关表格
        if role.features:
            feature_table = Table(title=T('Features'), show_lines=True)
            feature_table.add_column(T('Feature name'), style="bold blue", justify="left")
            feature_table.add_column(T('Status'), style="bold white", justify="center")

            for feature_name, enabled in sorted(role.features.items()):
                status_text = T('Enabled') if enabled else T('Disabled')
                status = f"[bold green]✓ {status_text}[/bold green]" if enabled else f"[bold red]✗ {status_text}[/bold red]"
                feature_table.add_row(feature_name, status)

            ctx.console.print(feature_table)
        
    def cmd_use(self, args, ctx):
        success = ctx.tm.use(role=args.role)
        if success:
            self.log.info(f'Use {args.role} role')
        else:
            self.log.error(T('Failed to use role').format(args.role))

    def cmd(self, args, ctx):
        self.cmd_list(args, ctx) 