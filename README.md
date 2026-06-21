# Multi-Agent MCP Orchestrator

An enterprise-grade, autonomous AI orchestration system built with LangGraph, utilizing the Model Context Protocol (MCP) to seamlessly connect LLMs to local environments, vector databases, and cloud APIs.

## Architectural Highlights

### 1. The Supervisor Routing (LangGraph)
* Transitioned from a monolithic tool-calling agent to a distributed `MultiServerMCPClient` architecture.
* Implemented strict system prompt injection to control agent behavior dynamically (e.g., forcing Google Sheets defaults) without polluting user queries.
* Handled state routing via `GraphState` to allow seamless multi-step tool chaining across completely isolated MCP servers.

### 2. Self-Healing RAG Vault (`ragsystem.py`)
* Built a custom Pinecone Hybrid Search vector database with LlamaParse for structural markdown extraction.
* **Wipe-and-Replace Mechanism:** Implemented pre-ingestion metadata filtering (`index.delete(filter={"source": filepath})`). This prevents vector duplication when re-ingesting updated source files, maintaining a pristine context window.

### 3. Custom Google Workspace Server (`workspace_custom.py`)
* Bypassed limited community MCP packages to build a raw Python MCP server interacting directly with Google Docs and Sheets REST APIs.
* **Capabilities:** * `create_sheet` & `write_sheet`: Matrix-based (2D array) row appending using Google's `USER_ENTERED` parsing.
  * `create_doc` & `append_doc`: Dynamic EOF index calculation to securely inject text into heavily nested Google Docs JSON trees.