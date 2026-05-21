# Fish Shell 虚拟环境激活指南

本项目默认使用 `.venv` 作为 Python 虚拟环境目录。如果你使用的是 **fish shell**，直接用 bash 的 `source .venv/bin/activate` 会报错，因为 fish 的语法不同。

## 推荐方法

### 方法一：使用 fish 专用激活脚本（推荐）

```bash
source .venv/bin/activate.fish
```

> 大多数 `venv` 创建的环境都会同时生成 `activate.fish`，这是 fish 的原生支持方式。

### 方法二：直接使用 Python 解释器

```bash
.venv/bin/python main.py
```

> 不激活环境，直接调用虚拟环境中的 Python 解释器来运行脚本。

### 方法三：手动设置环境变量

```bash
set -x VIRTUAL_ENV (pwd)/.venv
set -x PATH $VIRTUAL_ENV/bin $PATH
```

> 临时生效，关闭终端后失效。适合脚本或一次性使用。

### 方法四：安装 virtualfish 插件

```bash
pip install virtualfish
vf install
vf activate .venv
```

> `virtualfish` 是 fish shell 的虚拟环境管理工具，提供 `vf` 命令来统一管理 venv。

## 退出虚拟环境

```bash
deactivate
```

> fish 的 `activate.fish` 同样会注册 `deactivate` 函数。

## 常见问题

| 问题 | 原因 | 解决 |
|------|------|------|
`source: Error while reading file '.venv/bin/activate'` | fish 不支持 bash 的 `case` 语法 | 改用 `activate.fish` |
`activate.fish: No such file` | 环境不是用 `venv` 创建的 | 重新创建：`python -m venv .venv` |
`python` 还是系统版本 | PATH 没有正确设置 | 检查 `which python` 的输出 |

## 一键设置别名（可选）

在 `~/.config/fish/config.fish` 中添加：

```bash
alias venv='source .venv/bin/activate.fish'
```

以后只需在项目目录执行 `venv` 即可激活。
