# text-humanizer
<img width="1090" height="291" alt="image" src="https://github.com/user-attachments/assets/02e48463-1c9f-4538-907a-53983b9fbf28" />





![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg) ![Python](https://img.shields.io/badge/python-3.6%2B-blue)
<p align="center">
  English | <a href="README-zh.md">中文</a>
</p>

# Overview
text-Humanizer is a completely free open-sourced project designed to humanize AI-generated text through a multilingual LLM-powered rewriting pipeline. By leveraging large language models for semantic-preserving text transformation, the system rewrites content with more natural sentence structures, varied linguistic patterns, and improved stylistic diversity while maintaining the original meaning across multiple languages.

## Features
- Preserves original meaning while improving text naturalness
- Bypasses most of AI-detectors
- Fully free and open-source
- Adaptable to different writing styles and tones
- 8 languages supported(en, ja, zh, ko, de, fr, es.)
# How it works

**Step 1 - LLM Rewrite (DeepSeek)**

Text is rewritten using the DeepSeek LLM to generate a semantically equivalent version with modified sentence structures, phrasing, and information flow. During this stage, the model also translates the content into Chinese as an intermediate representation to introduce structural variation and reduce original language patterns.

**Step 2 - Google Translation (EN → TR)**

The output from Step 1 is translated into Turkish using Google Translate. This stage introduces additional syntactic distortion and cross-lingual variation based on rule-based and statistical translation differences.

**Step 3 - DeepL Translation (Optional, TR → JA)**

If a DeepL API key is provided, the Turkish text is further translated into Japanese using DeepL API. This optional step improves linguistic diversity and adds a second independent translation engine into the pipeline.

**Step 4 - Final Reconstruction (DeepSeek)**
The resulting text is translated back into the original input language using the DeepSeek LLM. This step removes accumulated translation artifacts, restores readability, and reconstructs natural sentence flow while preserving semantic meaning.

<p align="center">
<img width="850" height="400" alt="image" src="https://github.com/user-attachments/assets/89c0823c-d324-42bd-b820-04f8161bfc69" />
</p>

# Quick start(Windows/Linux/MacOS)

```bash
git clone https://github.com/korcarc/text-humanizer.git
cd text-humanizer
pip install -r requirements.txt

copy .\config\config.example.toml .\config.toml #config file creation

python main.py # run humanizer
```
## Configuration
Edit `config.toml` to configurate text-humanizer:

| Option        | Description                                   |
|--------------|-------------------------------------------------|
| `target_language`  | Which language to use used for output/input(en, ja, zh, ko, de, fr, es)         |
| `deepseek_api_key` | Your DeepSeek API key               |
| `deepl_api_key`   | Your DeepL API key(optional)                            |
| `base_url`  | Override API base url(empy = provider default)               |
| `model` | Model slug(empty = provider default)    |
| `temperature` | LLM temperature(1.3 recommended)    |


# License
[MIT](LICENSE) License.

