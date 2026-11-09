// Retrieval checks: run with `npm test`. Free; no API key needed.
import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { search } from "../src/retrieve.js";
import { EVAL } from "./questions.js";

test("each answerable question finds a document that contains its answer in the top 6", () => {
  const misses = [];
  for (const q of EVAL.filter((q) => q.expect)) {
    const hits = search(q.q);
    if (!hits.some((h) => q.expect.test(h.text))) misses.push(q.q);
  }
  assert.deepEqual(misses, []);
});

test("off-topic questions score below the answer threshold", () => {
  const MIN = Number(readFileSync(new URL("../src/index.js", import.meta.url), "utf8").match(/MIN_SCORE = (\d+(?:\.\d+)?)/)[1]);
  for (const q of EVAL.filter((q) => !q.expect && !q.llm)) {
    const top = search(q.q)[0]?.score ?? 0;
    assert.ok(top < MIN, `"${q.q}" scored ${top.toFixed(2)}, threshold ${MIN}`);
  }
});
