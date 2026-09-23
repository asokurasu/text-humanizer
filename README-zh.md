# text-humanizer

![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) ![Python](https://img.shields.io/badge/python-3.6%2B-blue)

<p align="center">
  <a href="README.md">English</a> | 中文
</p>

# 项目概述

text-Humanizer 是一个完全免费且开源的项目，旨在通过基于大语言模型（LLM）的多语言重写流程，对 AI 生成的文本进行“人性化”处理。系统利用大语言模型在保持原始语义不变的前提下，对文本进行改写，使其具备更自然的句式结构、更丰富的语言表达模式以及更高的文风多样性，并支持多种语言。

## 功能特性

* 在提升文本自然度的同时保留原始含义
* 可绕过大多数 AI 内容检测器
* 完全免费且开源
* 支持适配不同写作风格和语气
* 支持 8 种语言（en、ja、zh、ko、de、fr、es）

# 工作原理

## 第一步：LLM 重写（DeepSeek）

使用 DeepSeek 大语言模型对文本进行改写，生成语义等价但句式结构、措辞方式和信息组织形式不同的新版本。在此阶段，模型还会将内容翻译为中文作为中间表示，以引入结构变化并减少原始语言模式的影响。

## 第二步：Google 翻译（EN → TR）

将第一步生成的文本通过 Google Translate 翻译为土耳其语。由于不同语言之间在语法规则和翻译策略上的差异，该步骤会进一步引入句法层面的变化和跨语言表达差异。

## 第三步：DeepL 翻译（可选，TR → JA）

如果提供了 DeepL API Key，则会使用 DeepL API 将土耳其语文本进一步翻译为日语。该可选步骤通过引入第二个独立的翻译引擎，进一步提升语言多样性。

## 第四步：最终重构（DeepSeek）

使用 DeepSeek 将得到的文本重新翻译回原始输入语言。此步骤会消除翻译过程中累积的表达痕迹，恢复文本可读性，并重建更加自然流畅的语言结构，同时保持原有语义不变。

# 快速开始（Windows / Linux / macOS）

```bash
git clone https://github.com/korcarc/text-humanizer.git
cd text-humanizer
pip install -r requirements.txt
copy .\config\config.example.toml .\config.toml # 创建配置文件
python main.py
```

## 配置说明

编辑 `config.toml` 文件以配置 text-humanizer：

| 选项                 | 说明                                  |
| ------------------ | ----------------------------------- |
| `target_language`  | 输入/输出所使用的目标语言（en、ja、zh、ko、de、fr、es） |
| `deepseek_api_key` | DeepSeek API 密钥                     |
| `deepl_api_key`    | DeepL API 密钥（可选）                    |
| `base_url`         | 自定义 API Base URL（留空则使用默认提供商地址）      |
| `model`            | 模型名称（留空则使用默认模型）                     |
| `temperature`      | LLM Temperature 参数（推荐值：1.3）         |

# 许可证

采用 MIT License 许可协议。
