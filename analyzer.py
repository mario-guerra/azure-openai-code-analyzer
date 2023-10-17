# Copyright (c) 2023 Mario Guerra
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

import argparse
import asyncio
import os, re
from pathlib import Path
import semantic_kernel as sk
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.connectors.ai.chat_request_settings import ChatRequestSettings
from semantic_kernel.connectors.ai.ai_exception import AIException

language_extensions = {
    "python": [".py"],
    "javascript": [".js"],
    "java": [".java"],
    "typescript": [".ts"],
    "csharp": [".cs"],
    "rust": [".rs"],
    "go": [".go"], 
    # Add more languages and extensions as needed
}

# Dictionary defining chunk sizes, which influence verbosity of the chat model output.
# The smaller the chunk size, the more verbose the output. The chunk size is
# used to determine the number of characters to process in a given text during a
# single request to the chat model.
summary_level = {
    "verbose": 5000,
}

# Dictionary defining request token sizes, which influence verbosity of the chat model output.
# The larger the request token size, the more verbose the output. The request token size is
# used to determine the number of tokens to request from the chat model during a single request.
request_token_size = {
    "verbose": 3000,
}
# Summary level and request token size are inversely related. The request tokens value sets an
# upper limit on the number of tokens that can be requested from the model. By reducing the
# input chunk size and increasing the request token size, we giving the model the leeway to be
# more verbose while summarzing less text at a time. This allows the model to include more detail
# in the summary, while still maintaining a reasonable summary length.

analysis_prompt = {
"verbose": """You are an expert in {language} software development and security analysis. Analyze the following code block for potential issues, including syntax errors, logic errors, semantic errors, runtime errors, memory issues, security vulnerabilities (such as SQL injection, XSS, CSRF, insecure file uploads, insecure cryptography, hardcoded credentials, insecure deserialization, and improper access control), and common malware signatures. Here is the code:
file name: {file_name}
{code_block}
Provide a detailed explanation of any issues found and suggestions for improvement. Label each issue with the file name, type of issue (e.g., [syntax error], [logic error], etc.) and the block of code where the issue occurs. Ignore undefined variables and types in the code block. Do not reiterate that the code block is incomplete or part of a larger body of code, just analyze the block. Split analysis blocks into paragraphs for ease of reading. Provide a concise summary of the code block's functionality. If no issues are found, state that no issues were found. Do not provide any other output.
"""
}

# Initialize the semantic kernel for use in getting settings from .env file.
# I'm not using the semantic kernel pipeline for communicating with the GPT models,
# I'm using the semantic kernel service connectors directly for simplicity.
kernel = sk.Kernel()

# Get deployment, API key, and endpoint from environment variables
deployment, api_key, endpoint = sk.azure_openai_settings_from_dot_env()

# Using the chat completion service for code analysis. 
summary_service = AzureChatCompletion(deployment, endpoint, api_key)

# Define a method for creating an analysis asynchronously. Each time this method is called,
# a list of messages is created and seeded with the system prompt, along with the user input.
# The user input consists of a portion of the previous summary, along with the current text chunk
# being processed.
#
# The number of tokens requested from the model is based on the tokenized size of the
# input text plus the system prompt tokens. The larger the chunk size, the fewer tokens
# we can request from the model to fit within the context window. Therefore the model
# will be less verbose with larger chunk sizes.
async def create_analysis(code_block, language):
    messages = [("system", analysis_prompt["verbose"]), ("user", code_block)]
    request_size = request_token_size["verbose"]
    reply = await summary_service.complete_chat_async(messages=messages,request_settings=ChatRequestSettings(temperature=0.25, top_p=0.4, max_tokens=request_size))
    return(reply)

# Process code and handle ChatGPT rate limit errors with retries. Rate limit errors
# are passed as a string in the summary text rather than thrown as an exception, which
# is why we need to check for the error message in the summary text. If a rate limit
# error is encountered, the method will retry the request after the specified delay.
# The delay is extracted from the error message, since it explicitly states how long
#  to wait before a retry.
async def process_code(code_block, language):
    MAX_RETRIES = 5
    retry_count = 0
    TIMEOUT_DELAY = 5  # Adjust the delay as needed

    # request_size = request_token_sizes[summary_level]

    while retry_count < MAX_RETRIES:
        try:
            summary = await create_analysis(code_block, language)
            if "exceeded token rate limit" in str(summary):
                error_message = str(summary)
                delay_str = re.search(r'Please retry after (\d+)', error_message)
                if delay_str:
                    delay = int(delay_str.group(1))
                    print(f"Rate limit exceeded. Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    retry_count += 1
                else:
                    raise Exception("Unknown error message when processing text.")
            else:
                return summary
        except AIException as e:
            if "Request timed out" in str(e):
                print(f"Timeout error occurred. Retrying in {TIMEOUT_DELAY} seconds...")
                await asyncio.sleep(TIMEOUT_DELAY)
                retry_count += 1
            elif "exceeded token rate limit" in str(e):
                error_message = str(e)
                delay_str = re.search(r'Please retry after (\d+)', error_message)
                if delay_str:
                    delay = int(delay_str.group(1))
                    print(f"Rate limit exceeded. Retrying in {delay} seconds...")
                    await asyncio.sleep(delay)
                    retry_count += 1
            else:
                raise
    if retry_count == MAX_RETRIES:
        if "Request timed out" in str(e):
            raise Exception("Timeout error. All retries failed.")
        else:
            raise Exception("Rate limit error. All retries failed.")

# Write paragraphs to the output file
def write_paragraphs(out_f, paragraphs):
    for p in paragraphs:
        out_f.write(p + "\n\n")
        out_f.flush()

# Extract summary paragraphs from the summary text
def extract_analysis_blocks(summary_text):
    paragraphs = str(summary_text).split('\n\n')
    return [p.strip() for p in paragraphs]

# Summarize a document asynchronously
async def analyze_code(input_path, output_path, language):
    max_analysis_blocks = 3
    previous_analysis_blocks = []

    # Set the chunk size for processing text based on summary level.
    chunk_size = summary_level["verbose"]

    # Remove the output file if it already exists
    if os.path.exists(output_path):
        os.remove(output_path)

    with open(input_path, "r") as f:
        input_text = f.read()

    total_chars = len(input_text)

    # Process the input text in chunks and generate the summary
    with open(output_path, "a", encoding="utf-8") as out_f:
        processed_chars = 0
        while True:
            # Read a block of code from the input text
            chunk = input_text[processed_chars:processed_chars+chunk_size]
            #print("current chunk: ", chunk)
            processed_chars += len(chunk)

            # Break the loop if there's no more text to process
            if not chunk:
                break

            # Combine previous summary paragraphs and the current chunk
            input_text_chunk = f"file name: {input_path}\n\n" + "[PREVIOUS_ANALYSIS]\n\n" + "\n\n".join(previous_analysis_blocks) + "\n\n" + "[CURRENT_CHUNK]\n\n" + chunk

            # Process the text chunk and generate a summary
            analysis_ctx = await process_code(input_text_chunk, language)

            analysis = str(analysis_ctx)

            # Update the previous summary paragraphs based on the new summary.
            # If the summary has more than max_context_paragraphs, remove the first
            # paragraph until the summary is within the limit. As paragraphs are removed,
            # they are written to the output file.
            if analysis:
                analysis_blocks = extract_analysis_blocks(analysis)
                while len(analysis_blocks) > max_analysis_blocks:
                    out_f.write(analysis_blocks.pop(0) + "\n\n")
                previous_analysis_blocks = analysis_blocks
                print("\nAnalysis window: \n", analysis)
            else:
                print("No analysis generated for the current chunk.")

            # Calculate and display the progress of the summarization
            progress = (processed_chars / total_chars) * 100
            print(
                f"Processed {processed_chars} characters out of {total_chars} total in file: ({progress:.2f}%)")

        # Write the remaining summary paragraphs to the output file
        # write_paragraphs(out_f, previous_summary_paragraphs)
        while previous_analysis_blocks:
            out_f.write(previous_analysis_blocks.pop(0) + "\n\n")
            out_f.flush()
    print("Analysis complete!")

async def analyze_directory(input_dir_path, output_file_path, language):
    input_path = Path(input_dir_path)
    relevant_extensions = language_extensions.get(language.lower(), [])

    # Count the total number of relevant files
    total_files = sum(1 for file in input_path.rglob('*') if file.is_file() and file.suffix.lower() in relevant_extensions)
    print(f"Found {total_files} {language} files for analysis.")

    # Initialize a counter for processed files
    processed_files = 0

    # Iterate through each file in the input directory
    for file in input_path.rglob('*'):
        if file.is_file() and file.suffix.lower() in relevant_extensions:
            print(f"Analyzing file: {file}")
            await analyze_code(str(file), output_file_path, language)
            processed_files += 1
            progress = (processed_files / total_files) * 100
            print(f"\nProcessed {processed_files} out of {total_files} total files: ({progress:.2f}%)")

# Define command-line argument parser
parser = argparse.ArgumentParser(description="Code Analyzer")
parser.add_argument("input_dir_path", help="Path to the input directory")
parser.add_argument("output_path", help="Path to the output summary file")
parser.add_argument("language", help="Language of the code to analyze")

# Parse command-line arguments
args = parser.parse_args()

# Run the summarization process
if __name__ == "__main__":
    asyncio.run(analyze_directory(args.input_dir_path, args.output_path, language=args.language))