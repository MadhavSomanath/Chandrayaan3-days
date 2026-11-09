// BM25 keyword search over the project's own corpus. The corpus is ~60 chunks, so this runs in
// well under a millisecond inside the Worker and needs no vector database or embedding API.
import corpus from "./corpus.json" with { type: "json" };

const STOP = new Set("a an and are as at be by did do does for from had has have how i in is it its of on or that the this to was were what when where which who why will with you your about can there their they".split(" "));
// visitors' words -> the corpus's words
const SYNONYMS = { aug: "august", sep: "september", sept: "september", moonquake: "seismometer", quake: "seismometer", earthquake: "seismometer", seismic: "seismometer", vibration: "shaking", hot: "temperature", heat: "temperature", cold: "temperature", composition: "element", chemistry: "element" };

export function tokens(text) {
  return (text.toLowerCase().match(/[a-zµ°0-9]+(?:[.-][a-z0-9]+)*/g) || [])
    .flatMap((w) => (w.includes("-") ? [w, ...w.split("-")] : [w])) // "rambha-lp" also matches "rambha"
    .map((w) => (w.length > 4 && /[^s]s$/.test(w) ? w.slice(0, -1) : w)) // crude plural folding: signals ~ signal
    .map((w) => SYNONYMS[w] || w.replace(/^0+(?=\d)/, "")) // "aug 06" ~ "6 august"
    .filter((w) => !STOP.has(w));
}

const K1 = 1.2, B = 0.75;
const docs = corpus.map((d) => {
  const toks = [...tokens(d.title), ...tokens(d.title), ...tokens(d.text)]; // titles count double
  const tf = new Map();
  for (const t of toks) tf.set(t, (tf.get(t) || 0) + 1);
  return { ...d, tf, len: toks.length };
});
const avgLen = docs.reduce((s, d) => s + d.len, 0) / docs.length;
const df = new Map();
for (const d of docs) for (const t of d.tf.keys()) df.set(t, (df.get(t) || 0) + 1);
const idf = (t) => Math.log(1 + (docs.length - (df.get(t) || 0) + 0.5) / ((df.get(t) || 0) + 0.5));

export function search(question, k = 6) {
  const q = [...new Set(tokens(question))];
  return docs
    .map((d) => ({
      d,
      score: q.reduce((s, t) => {
        const f = d.tf.get(t) || 0;
        return s + (f ? idf(t) * (f * (K1 + 1)) / (f + K1 * (1 - B + B * d.len / avgLen)) : 0);
      }, 0),
    }))
    .filter((x) => x.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, k)
    .map(({ d, score }) => ({ id: d.id, title: d.title, url: d.url, kind: d.kind, text: d.text, score }));
}
