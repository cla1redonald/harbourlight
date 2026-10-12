// The TypeScript checker must agree with evals/check_post.py on every labelled case
// and every seeded draft. Python is the reference implementation.
import { execFileSync } from "node:child_process";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { describe, it } from "node:test";
import assert from "node:assert/strict";

import { loadPolicy, checkPost } from "../src/policy.js";
import { REPO } from "./helpers.js";

const policy = loadPolicy(REPO);
const python = process.env.PYTHON ?? "python3";

function pythonCheck(files: string[]): Array<Record<string, unknown>> {
  const out = execFileSync(python, [join(REPO, "evals", "check_post.py"), "--json", ...files], { encoding: "utf-8" });
  return JSON.parse(out) as Array<Record<string, unknown>>;
}

describe("checker parity with Python", () => {
  const caseDir = join(REPO, "evals", "reviewer-cases");
  const postDir = join(REPO, "data-pristine", "posts");
  const tmpFiles: Array<{ name: string; text: string; path: string }> = [];
  for (const f of readdirSync(caseDir).filter((f) => f.endsWith(".json")).sort()) {
    const text = (JSON.parse(readFileSync(join(caseDir, f), "utf-8")) as { post: string }).post;
    tmpFiles.push({ name: f, text, path: "" });
  }
  for (const f of readdirSync(postDir).filter((f) => f.endsWith(".md")).sort()) {
    tmpFiles.push({ name: f, text: readFileSync(join(postDir, f), "utf-8"), path: join(postDir, f) });
  }

  it("matches on verdict, findings and fixes for every case and seeded post", async () => {
    const { mkdtempSync, writeFileSync } = await import("node:fs");
    const { tmpdir } = await import("node:os");
    const dir = mkdtempSync(join(tmpdir(), "parity-"));
    for (const item of tmpFiles) {
      if (!item.path) {
        item.path = join(dir, item.name.replace(/\.json$/, ".md"));
        writeFileSync(item.path, item.text, "utf-8");
      }
    }
    const expected = pythonCheck(tmpFiles.map((t) => t.path));
    assert.equal(expected.length, 29);
    tmpFiles.forEach((item, i) => {
      const py = expected[i]!;
      delete py.file;
      const ts = checkPost(policy, item.text) as unknown as Record<string, unknown>;
      delete ts.voice_version;
      assert.deepEqual(ts, py, item.name);
    });
  });
});
