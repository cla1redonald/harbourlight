import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const here = dirname(fileURLToPath(import.meta.url));
export const PACKAGE = resolve(here, "..", "..");
export const REPO = resolve(PACKAGE, "..", "..");
export const ENTRY = resolve(PACKAGE, "dist", "src", "index.js");

export async function connect(): Promise<Client> {
  const transport = new StdioClientTransport({ command: process.execPath, args: [ENTRY], stderr: "ignore" });
  const client = new Client({ name: "policy-server-test", version: "0.0.0" });
  await client.connect(transport);
  return client;
}

export function json(result: unknown): Record<string, unknown> {
  const r = result as { structuredContent?: Record<string, unknown> };
  if (!r.structuredContent) throw new Error("no structuredContent in " + JSON.stringify(result));
  return r.structuredContent;
}
