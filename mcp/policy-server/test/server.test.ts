// The policy server over a real stdio transport, as any MCP client would see it.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { after, before, describe, it } from "node:test";
import assert from "node:assert/strict";

import type { Client } from "@modelcontextprotocol/sdk/client/index.js";

import { connect, json, PACKAGE, REPO } from "./helpers.js";

const caseText = (id: string): string =>
  (JSON.parse(readFileSync(join(REPO, "evals", "reviewer-cases", `${id}.json`), "utf-8")) as { post: string }).post;

describe("policy server over stdio", () => {
  let client: Client;
  before(async () => { client = await connect(); });
  after(async () => { await client.close(); });

  it("lists exactly the five read-only tools and nothing else", async () => {
    const { tools } = await client.listTools();
    assert.deepEqual(tools.map((t) => t.name).sort(),
      ["check_claim", "check_post", "get_checklist", "get_voice_rules", "list_approved_claims"]);
    for (const tool of tools) {
      assert.equal(tool.annotations?.readOnlyHint, true, tool.name);
      assert.equal(tool.annotations?.destructiveHint, false, tool.name);
      assert.ok(tool.outputSchema, `${tool.name} has an output schema`);
    }
    const caps = client.getServerCapabilities() ?? {};
    assert.equal(caps.resources, undefined, "no resources");
    assert.equal(caps.prompts, undefined, "no prompts");
  });

  it("lists the approved claims from rules.json", async () => {
    const out = json(await client.callTool({ name: "list_approved_claims", arguments: {} }));
    const rules = JSON.parse(readFileSync(join(REPO, "references", "rules.json"), "utf-8"));
    const claims = out.claims as Array<{ claim: string; signpost: boolean }>;
    assert.deepEqual(claims.map((c) => c.claim), rules.products.map((p: { claim: string }) => p.claim));
    assert.equal(claims.filter((c) => c.signpost).length, 1);
  });

  it("check_claim accepts an approved line and names the product", async () => {
    const out = json(await client.callTool({ name: "check_claim", arguments: {
      text: "the FixedFive Remortgage fixes your monthly payment for five years" } }));
    assert.equal(out.approved, true);
    assert.equal(out.product, "FixedFive Remortgage");
    assert.match(String(out.claim), /^The FixedFive Remortgage/);
  });

  it("check_claim rejects a reworded claim and says which product it names", async () => {
    const out = json(await client.callTool({ name: "check_claim", arguments: {
      text: "FixedFive is the cheapest way to fix for five years." } }));
    assert.equal(out.approved, false);
    assert.equal(out.claim, null);
    assert.equal(out.names_product, "FixedFive Remortgage");
    const none = json(await client.callTool({ name: "check_claim", arguments: { text: "Rates fell this week." } }));
    assert.equal(none.names_product, null);
  });

  it("check_post fails a post with no sources and quotes the evidence", async () => {
    const out = json(await client.callTool({ name: "check_post", arguments: { text: caseText("H1a") } }));
    assert.equal(out.verdict, "FAIL");
    const findings = out.findings as Array<{ rule: string; quote: string }>;
    assert.ok(findings.some((f) => f.rule === "H1" && f.quote === "(no sources block)"));
    assert.ok((out.what_would_change as string[]).length > 0);
  });

  it("check_post passes a clean post", async () => {
    const out = json(await client.callTool({ name: "check_post", arguments: { text: caseText("C01") } }));
    assert.equal(out.verdict, "PASS");
    assert.deepEqual(out.findings, []);
  });

  it("serves the checklist and the voice rules", async () => {
    const checklist = json(await client.callTool({ name: "get_checklist", arguments: {} }));
    assert.match(String(checklist.checklist), /## Hard rules \(fail\)/);
    const voice = json(await client.callTool({ name: "get_voice_rules", arguments: {} }));
    assert.match(String(voice.guide), /sensible neighbour/);
    assert.deepEqual(voice.word_count, { min: 120, max: 220 });
  });

  it("rejects unknown arguments, empty text and oversized text", async () => {
    const bad = [
      { name: "check_claim", arguments: { text: "x", path: "/etc/passwd" } },
      { name: "check_post", arguments: { text: "" } },
      { name: "check_post", arguments: { text: "x".repeat(20_001) } },
      { name: "get_checklist", arguments: { file: "references/rules.json" } },
    ];
    for (const call of bad) {
      const result = await client.callTool(call) as { isError?: boolean };
      assert.equal(result.isError, true, JSON.stringify(call).slice(0, 80));
    }
  });

  it("refuses a tool that does not exist", async () => {
    const result = await client.callTool({ name: "write_rules", arguments: {} }).catch((e: Error) => e);
    const isError = result instanceof Error || (result as { isError?: boolean }).isError === true;
    assert.ok(isError);
  });
});

describe("the source never writes", () => {
  it("has no file-writing or process-spawning calls", () => {
    const banned = /\b(writeFile|appendFile|mkdir|rmSync|rm\(|unlink|rename|createWriteStream|copyFile|child_process|execSync|spawn)\b/;
    for (const file of readdirSync(join(PACKAGE, "src"))) {
      const source = readFileSync(join(PACKAGE, "src", file), "utf-8");
      assert.doesNotMatch(source, banned, file);
    }
  });
});
