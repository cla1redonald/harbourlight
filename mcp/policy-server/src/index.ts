#!/usr/bin/env node
// stdio entry point. Logs go to stderr only: stdout belongs to the protocol.
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";

import { createServer } from "./server.js";

const server = createServer();
await server.connect(new StdioServerTransport());
console.error("harbourlight-policy MCP server running on stdio (read-only)");
