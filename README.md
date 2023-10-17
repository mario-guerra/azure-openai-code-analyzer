# Code Analyzer with Azure OpenAI

Code Analyzer is a Python script that uses Azure OpenAI models and a [sliding content window](https://marioguerra.xyz/ai-document-summarization-with-sliding-content-window/) to analyze code files for potential issues, including syntax errors, logic errors, semantic errors, runtime errors, memory issues, security vulnerabilities, and common malware signatures.

The script processes the input code files in chunks and uses the `AzureChatCompletion` connector from the [Semantic Kernel library](https://github.com/microsoft/semantic-kernel) to generate analysis results. Token rate limit errors and timeouts are handled with retry logic. The final analysis is written to the specified output file.

The input code files can be in any supported language, such as Python, JavaScript/TypeScript, Java, C#, or Rust.

**This script works, but still needs refinement. It's very much a work in progress.**

## Dependencies

- Python 3.6 or later
- semantic_kernel

You can install the required library using pip:

`pip install semantic_kernel`

_Note: The `semantic_kernel` library is not a standard library and might not be available through pip. If so, the package can be found [here](https://aka.ms/sk/pypi)_

## Requirements

An Azure OpenAI subscription is required to run this script, along with a deployment for one of the following models:
- gpt-3.5-turbo
- gpt-4
- gpt-4-32k

The difference in models are tradeoffs between performance and speed. The gpt-4 model produces the best analysis results, but gpt-35-turbo is faster. In testing with technical content, gpt-4 was better than the other two models at analyzing and retaining technical aspects of the content. The other two models produce decent analysis, but potentially important details are lost.

## Overview

The script reads the input code files in chunks and uses the `AzureChatCompletion` connector from the [Semantic Kernel library](https://github.com/microsoft/semantic-kernel) to generate analysis results. Token rate limit errors and timeouts are handled with retry logic. The final analysis is written to the specified output file.

The input code files can be in any supported language, such as Python, JavaScript, Java, C, C++, or TypeScript.

## Usage

1. Clone the repository to your local machine.

2. Open a terminal and navigate to the folder containing the script file.

3. Install the dependency outlined above using pip: `pip install semantic_kernel`

4. Change the name of '.env.example' to '.env' and add your Azure OpenAI deployment name, API key, and endpoint.

5. Run the script using the following command:

`python analyzer.py <input_dir_path> <output_path> [--language <language>]`

Replace `<input_dir_path>` with the path to the input directory containing code files, `<output_path>` with the path to the output analysis file, and `<language>` (optional) with one of the supported languages: "python", "javascript", "java", "c", "cpp", "typescript", "csharp". If the `--language` flag is not used, the default option is "python".

Examples:

`python analyzer.py input_code_directory analysis.txt`

`python analyzer.py input_code_directory analysis.txt --language typescript`

These commands will analyze the code files in the input directory and save the analysis results in the `analysis.txt` file.