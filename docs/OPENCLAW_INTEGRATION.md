# OpenClaw Integration Guide for EverythingSearch

This guide is designed to help non-technical users quickly configure **OpenClaw** (or other similar AI agents) to leverage the powerful local file search capabilities of EverythingSearch. Once configured, your OpenClaw will be able to locate local documents and code on your computer using natural language.

## Step 1: Verify Your Environment

Before starting, please ensure that you have installed EverythingSearch and completed the initial indexing.
If you haven't installed it yet, please follow the [Installation Guide](INSTALL.md) first.

Verification: Open your Terminal and run the following command:
```bash
cd /path/to/your/EverythingSearch
python -m everythingsearch search "test" --json
```
If it outputs a block of text containing `"results"` (even if it's empty), you are ready to go!

## Step 2: Configure OpenClaw

Agent tools like OpenClaw typically allow you to customize their **System Prompt** or **Tools**. You simply need to copy the text below and paste it into OpenClaw's configuration area.

### Copy the following configuration:

```text
# Tool Configuration: EverythingSearch Local Retrieval
You now have the ability to intelligently search the user's local files via EverythingSearch.

## Command Syntax
`python -m everythingsearch search "<query>" --json`

## Parameter Requirements
- `<query>`: Must be wrapped in double quotes. Supports natural language (e.g., "Find the design docs I wrote last week").
- `--limit <number>`: (Optional) Limits the number of results returned (default is 10).
- `--json`: (Required) You must include this flag to ensure the output is machine-readable JSON.

## Your Workflow
1. When the user asks about local documents, code, notes, or project information, proactively execute this command.
2. Parse the JSON data output from the terminal to extract the `filepath` and `snippet`.
3. Answer the user based on the extracted information. If more context is needed, use your built-in file reading capabilities to read the corresponding `filepath`.
```

## Step 3: Try It Out

Once the configuration is saved, you can start asking OpenClaw directly in its chat interface!

**You can ask things like:**
- "Find documents on my computer related to 'product architecture evolution'."
- "Which file contains the implementation for our user login logic?"
- "Summarize all my local Nginx configuration files."

**What happens behind the scenes?**
When OpenClaw receives your request, it will 'think' and automatically run the `python -m everythingsearch search "query" --json` command in the background. It quickly retrieves all relevant snippets and summarizes the findings in plain language for you.

---

If it cannot find what you are looking for, double-check whether the EverythingSearch background index is up to date.
