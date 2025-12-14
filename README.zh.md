![logo](https://github.com/user-attachments/assets/3af4e228-79b2-4fa0-a45c-c38276c6db91)

# Python use

AIPy is a concrete implementation of the Python-use concept, aiming to demonstrate the practical value and application potential of this concept.

- **Mission**: Unleash the full potential of large language models
- **Vision**: Smarter LLMs that can autonomously improve and use AIPy

## What

Python use provides the entire Python execution environment to LLM for use. You can imagine LLM sitting in front of a computer, typing various commands in the Python command line interpreter with a keyboard, pressing Enter to run, then observing the execution results, and then inputting code and executing again.

The difference from Agent is that Python use does not define any tools interfaces. LLM can freely use all functions provided by the Python runtime environment.

## Why

If you are a data engineer, you must be familiar with the following scenarios:

- Processing data files in various formats: csv/excel, json, html, sqlite, parquet ...
- Performing data cleaning, transformation, calculation, aggregation, sorting, grouping, filtering, analysis, visualization and other operations

This process often requires:

- Starting Python, importing pandas as pd, typing a bunch of commands to process data
- Generating a bunch of intermediate temporary files
- Finding ChatGPT / Claude to describe your needs, manually copying generated data processing code to run.

So why not start the Python command line interpreter and directly describe your data processing needs, then complete automatically? The benefits are:

- No need to manually type a bunch of Python commands temporarily
- No need to find GPT to describe needs, copy programs, and then run manually

This is the problem that Python use aims to solve!

## How

Python use (aipython) is a Python command line interpreter integrated with LLM. You can:

- Input and execute Python commands as usual
- Describe your needs in natural language, aipython will automatically generate Python commands and execute them

Moreover, the two modes can access each other's data. For example, after aipython processes your natural language commands, you can use standard Python commands to view various data.

## Usage

AIPython has two running modes:

- Task mode: Very simple and easy to use, directly input your task, suitable for users unfamiliar with Python.
- Python mode: Suitable for users familiar with Python, can input both tasks and Python commands, suitable for advanced users.

The default running mode is task mode, you can switch to Python mode through `--python` parameter.

### Minimal Configuration

~/.aipyapp/aipyapp.toml:

```toml
[llm.deepseek]
type = "deepseek"
api_key = "Your DeepSeek API Key"
```

### Task Mode

`uv run aipy`

```
>>> Get the latest posts from Reddit r/LocalLLaMA
......
......
>>> /done
```

`pip install aipyapp`, run aipy command to enter task mode

```
-> % aipy
🚀 Python use - AIPython (0.1.22) [https://aipy.app]
Please enter the task to be processed by AI (enter /use <following LLM> to switch)
>> Get the latest posts from Reddit r/LocalLLaMA
......
>>
```

### Python Mode

#### Basic Usage

Automatic task processing:

```
>>> ai("Get the homepage title of Google official website")
```

#### Automatic request to install third-party libraries

```
Python use - AIPython (Quit with 'exit()')
>>> ai("Use psutil to list all current MacOS processes")

📦 LLM requests to install third-party packages: ['psutil']
If you agree and have installed, please enter 'y [y/n] (n): y

```

## Thanks

- Heige: Product manager/senior user/chief testing officer
- Sonnet 3.7: Generated the first version of the code, almost usable without modification.
- ChatGPT: Provided many suggestions and code snippets, especially command line interface.
- Codeium: Code intelligent completion
- Copilot: Code improvement suggestions and README translation
