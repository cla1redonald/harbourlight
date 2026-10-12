// The Harbourlight policy MCP server: read-only tools over the rules a post is judged by.
//
// Any MCP client can consult it, not only this pipeline: a writer agent checking a
// product line before it drafts, an approver's assistant, a CMS plug-in. Five tools,
// no resources, no prompts, no writes, and every input is a strict schema.

import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { checkClaim, checkPost, loadPolicy, voiceRules, type Policy } from "./policy.js";

export const MAX_TEXT = 20_000;
const READ_ONLY = { readOnlyHint: true, destructiveHint: false, idempotentHint: true, openWorldHint: false } as const;

const text = z.string().min(1).max(MAX_TEXT);
const noArgs = z.object({}).strict();

const finding = z.object({
  rule: z.string(),
  severity: z.enum(["fail", "flag"]),
  quote: z.string(),
  why: z.string(),
});

function reply<T extends Record<string, unknown>>(data: T) {
  return { content: [{ type: "text" as const, text: JSON.stringify(data, null, 2) }], structuredContent: data };
}

export function createServer(policy: Policy = loadPolicy()): McpServer {
  const server = new McpServer(
    { name: "harbourlight-policy", version: "0.1.0" },
    {
      capabilities: { tools: {} },
      instructions:
        "Harbourlight Mutual's content policy, read-only. Use check_post on a whole draft and check_claim " +
        "on a single product sentence before writing it. A PASS here is the deterministic checker only: " +
        "a draft still needs the independent compliance reviewer and a named human approver.",
    },
  );

  server.registerTool(
    "list_approved_claims",
    {
      title: "List approved product claims",
      description: "The five products and the one approved line for each. A post may use at most one, word for word.",
      inputSchema: noArgs,
      outputSchema: z.object({
        voice_version: z.number(),
        claims: z.array(z.object({ product: z.string(), short_name: z.string(), claim: z.string(),
          signpost: z.boolean() })),
      }),
      annotations: READ_ONLY,
    },
    async () => reply({
      voice_version: policy.rules.voice_version,
      claims: policy.rules.products.map((p) => ({ product: p.name, short_name: p.aliases[0] ?? p.name,
        claim: p.claim, signpost: p.signpost })),
    }),
  );

  server.registerTool(
    "check_claim",
    {
      title: "Check one product claim",
      description: "Whether the text is exactly one of the approved product lines. Returns the matching claim, or none.",
      inputSchema: z.object({ text }).strict(),
      outputSchema: z.object({
        approved: z.boolean(),
        claim: z.string().nullable(),
        product: z.string().nullable(),
        names_product: z.string().nullable(),
        reason: z.string(),
      }),
      annotations: READ_ONLY,
    },
    async ({ text: input }) => reply({ ...checkClaim(policy, input) }),
  );

  server.registerTool(
    "check_post",
    {
      title: "Run the deterministic checker on a post",
      description:
        "Runs the deterministic checker rules (H1 to H7, S1 to S5) on a whole post, including its Sources block. " +
        "Returns the verdict, every finding with its rule id and exact quote, and what would change a FAIL.",
      inputSchema: z.object({ text }).strict(),
      outputSchema: z.object({
        verdict: z.enum(["PASS", "FLAG", "FAIL"]),
        needs_human: z.boolean(),
        word_count: z.number(),
        rules: z.array(z.string()),
        findings: z.array(finding),
        what_would_change: z.array(z.string()),
        voice_version: z.number(),
      }),
      annotations: READ_ONLY,
    },
    async ({ text: input }) => reply({ ...checkPost(policy, input) }),
  );

  server.registerTool(
    "get_checklist",
    {
      title: "Get the compliance checklist",
      description: "The compliance checklist the reviewer applies: verdicts, hard rules H1 to H7, soft rules S1 to S5.",
      inputSchema: noArgs,
      outputSchema: z.object({ voice_version: z.number(), checklist: z.string() }),
      annotations: READ_ONLY,
    },
    async () => reply({ voice_version: policy.rules.voice_version, checklist: policy.checklist }),
  );

  server.registerTool(
    "get_voice_rules",
    {
      title: "Get the brand voice rules",
      description: "The brand voice guide and its machine-checkable parts: length, banned words, spelling.",
      inputSchema: noArgs,
      outputSchema: z.object({
        voice_version: z.number(),
        guide: z.string(),
        word_count: z.object({ min: z.number(), max: z.number() }),
        banned_filler_words: z.array(z.string()),
        hype_phrases: z.array(z.string()),
        american_spellings: z.record(z.string(), z.string()),
        punctuation: z.object({ exclamation_marks: z.boolean(), em_dashes: z.boolean() }),
      }),
      annotations: READ_ONLY,
    },
    async () => reply({ ...voiceRules(policy) }),
  );

  return server;
}
