const pptxgen = require("pptxgenjs");
const pres = new pptxgen();

pres.layout = "LAYOUT_16x9";

// Shape type constants
const RECT = pres.shapes.RECTANGLE;
const RRECT = pres.shapes.ROUNDED_RECTANGLE;
const ELLIPSE = pres.shapes.OVAL;
const RARROW = pres.shapes.RIGHT_ARROW;
pres.author = "Agentic-TrailGPT Team";
pres.title = "Agentic-TrailGPT";

// --- Color Palette (Ocean/Medical) ---
const C = {
  dark:    "0B2545",  // deep navy
  primary: "13547A",  // ocean blue
  mid:     "1C7293",  // teal
  accent:  "02C39A",  // mint green
  light:   "EEF5F9",  // ice blue bg
  white:   "FFFFFF",
  text:    "1A1A2E",  // near black
  muted:   "5A6B7D",  // gray-blue
  warn:    "E8573A",  // coral for emphasis
};

// --- Helpers ---
function darkBg(slide) {
  slide.background = { fill: C.dark };
}
function lightBg(slide) {
  slide.background = { fill: C.white };
}
function addPageNum(slide, num, total, dark) {
  slide.addText(num + " / " + total, {
    x: 8.8, y: 5.15, w: 1.0, h: 0.35,
    fontSize: 9, color: dark ? "7A8FA6" : C.muted,
    align: "right", isTextBox: true, margin: 0,
  });
}

const TOTAL = 9;

// ============================================================
// SLIDE 1 — Title
// ============================================================
let s1 = pres.addSlide();
darkBg(s1);
addPageNum(s1, 1, TOTAL, true);

s1.addShape(RECT, {
  x: 0.6, y: 1.8, w: 0.06, h: 1.6, fill: { color: C.accent },
});

s1.addText("Agentic-TrailGPT", {
  x: 0.9, y: 1.7, w: 8.5, h: 0.8,
  fontSize: 42, fontFace: "Calibri", bold: true,
  color: C.white, isTextBox: true, margin: 0,
});

s1.addText("LLM-Powered Agents for Improved Clinical Trial Matching", {
  x: 0.9, y: 2.5, w: 7.5, h: 0.5,
  fontSize: 18, fontFace: "Calibri",
  color: C.accent, isTextBox: true, margin: 0,
});

s1.addText("Extending TrialGPT with Assertion, Clarification & Verification Agents", {
  x: 0.9, y: 3.15, w: 7.5, h: 0.4,
  fontSize: 13, fontFace: "Calibri",
  color: "7A8FA6", isTextBox: true, margin: 0,
});

s1.addShape(RECT, {
  x: 0.9, y: 4.1, w: 3.5, h: 0.02, fill: { color: "2A4A6B" },
});

s1.addText("Research Presentation  |  September 2026", {
  x: 0.9, y: 4.3, w: 5, h: 0.35,
  fontSize: 11, fontFace: "Calibri",
  color: "5A7A9A", isTextBox: true, margin: 0,
});


// ============================================================
// SLIDE 2 — Problem Statement
// ============================================================
let s2 = pres.addSlide();
lightBg(s2);
addPageNum(s2, 2, TOTAL, false);

s2.addText("Problem Statement", {
  x: 0.6, y: 0.4, w: 8, h: 0.7,
  fontSize: 36, fontFace: "Calibri", bold: true,
  color: C.dark, isTextBox: true, margin: 0,
});

// Left column: the problem
s2.addShape(RRECT, {
  x: 0.6, y: 1.35, w: 4.2, h: 3.6,
  fill: { color: C.light }, rectRadius: 0.1,
});

s2.addText("The Challenge", {
  x: 0.85, y: 1.5, w: 3.7, h: 0.4,
  fontSize: 18, fontFace: "Calibri", bold: true,
  color: C.primary, isTextBox: true, margin: 0,
});

s2.addText([
  { text: "Clinical trials are critical for medical advancement, yet ", options: { fontSize: 13, color: C.text } },
  { text: "86% of trials fail to meet enrollment targets", options: { fontSize: 13, color: C.warn, bold: true } },
  { text: " on time.", options: { fontSize: 13, color: C.text } },
  { text: "\n\nTrialGPT (Nature, 2024) automates patient-trial matching with LLMs, but still produces errors in ", options: { fontSize: 13, color: C.text } },
  { text: "~13% of criterion-level decisions.", options: { fontSize: 13, color: C.warn, bold: true } },
], {
  x: 0.85, y: 1.95, w: 3.7, h: 2.8,
  fontFace: "Calibri", valign: "top",
  isTextBox: true, margin: 0, lineSpacingMultiple: 1.15,
});

// Right column: error categories
s2.addShape(RRECT, {
  x: 5.2, y: 1.35, w: 4.2, h: 3.6,
  fill: { color: C.light }, rectRadius: 0.1,
});

s2.addText("Baseline Error Categories", {
  x: 5.45, y: 1.5, w: 3.7, h: 0.4,
  fontSize: 18, fontFace: "Calibri", bold: true,
  color: C.primary, isTextBox: true, margin: 0,
});

const errors = [
  ["E1", "Wrong reasoning", "30.7%"],
  ["E2", "Medical knowledge gaps", "15.4%"],
  ["E3", "Label ambiguity", "26.9%"],
  ["E4", "Family history confusion", "~15%"],
];

errors.forEach((e, i) => {
  let yy = 2.05 + i * 0.7;
  s2.addShape(ELLIPSE, {
    x: 5.45, y: yy, w: 0.4, h: 0.4,
    fill: { color: C.primary },
  });
  s2.addText(e[0], {
    x: 5.45, y: yy, w: 0.4, h: 0.4,
    fontSize: 11, fontFace: "Calibri", bold: true,
    color: C.white, align: "center", valign: "middle",
    isTextBox: true, margin: 0,
  });
  s2.addText(e[1], {
    x: 6.0, y: yy, w: 2.4, h: 0.22,
    fontSize: 13, fontFace: "Calibri", bold: true,
    color: C.text, isTextBox: true, margin: 0,
  });
  s2.addText(e[2], {
    x: 6.0, y: yy + 0.22, w: 2.4, h: 0.18,
    fontSize: 11, fontFace: "Calibri",
    color: C.muted, isTextBox: true, margin: 0,
  });
});

s2.addText("Source: Jin et al., Nature Communications (2024)", {
  x: 5.2, y: 4.6, w: 4, h: 0.3,
  fontSize: 9, fontFace: "Calibri", italic: true,
  color: C.muted, isTextBox: true, margin: 0,
});


// ============================================================
// SLIDE 3 — Objectives Overview
// ============================================================
let s3 = pres.addSlide();
lightBg(s3);
addPageNum(s3, 3, TOTAL, false);

s3.addText("Our Solution: Three Novel Agents", {
  x: 0.6, y: 0.4, w: 8.5, h: 0.7,
  fontSize: 36, fontFace: "Calibri", bold: true,
  color: C.dark, isTextBox: true, margin: 0,
});

s3.addText("Post-processing agents that refine TrialGPT's criterion-level decisions", {
  x: 0.6, y: 1.05, w: 8, h: 0.35,
  fontSize: 14, fontFace: "Calibri",
  color: C.muted, isTextBox: true, margin: 0,
});

const agents = [
  {
    num: "1",
    title: "Assertion Agent",
    subtitle: "Evidence Usability Filter",
    desc: "Classifies every evidence sentence by subject (patient vs. family), polarity (affirmed vs. negated), and temporality. Filters out unusable evidence like family history cited as patient facts.",
    targets: "Targets: E4 errors",
    color: C.primary,
  },
  {
    num: "2",
    title: "Clarification Agent",
    subtitle: "Evidence-Gap Re-Search",
    desc: "When baseline says 'not enough information,' re-searches the same patient note with targeted queries to find overlooked evidence. Does not invent facts or access new data.",
    targets: "Targets: E1, E2 errors",
    color: C.mid,
  },
  {
    num: "3",
    title: "Verifier Agent",
    subtitle: "Entailment Check & Correction",
    desc: "Checks whether the chosen label is actually supported by the evidence and explanation. Corrects contradictions and flags uncertain decisions for human review.",
    targets: "Targets: E3 errors",
    color: "0E8C6E",
  },
];

agents.forEach((a, i) => {
  let xOff = 0.6 + i * 3.1;

  s3.addShape(RRECT, {
    x: xOff, y: 1.65, w: 2.85, h: 3.4,
    fill: { color: C.white },
    shadow: { type: "outer", blur: 6, offset: 2, angle: 135, color: "000000", opacity: 0.12 },
    rectRadius: 0.1,
  });

  // Number circle
  s3.addShape(ELLIPSE, {
    x: xOff + 0.15, y: 1.85, w: 0.45, h: 0.45,
    fill: { color: a.color },
  });
  s3.addText(a.num, {
    x: xOff + 0.15, y: 1.85, w: 0.45, h: 0.45,
    fontSize: 18, fontFace: "Calibri", bold: true,
    color: C.white, align: "center", valign: "middle",
    isTextBox: true, margin: 0,
  });

  s3.addText(a.title, {
    x: xOff + 0.15, y: 2.45, w: 2.55, h: 0.35,
    fontSize: 16, fontFace: "Calibri", bold: true,
    color: C.dark, isTextBox: true, margin: 0,
  });

  s3.addText(a.subtitle, {
    x: xOff + 0.15, y: 2.78, w: 2.55, h: 0.25,
    fontSize: 11, fontFace: "Calibri", italic: true,
    color: a.color, isTextBox: true, margin: 0,
  });

  s3.addText(a.desc, {
    x: xOff + 0.15, y: 3.15, w: 2.55, h: 1.4,
    fontSize: 11, fontFace: "Calibri",
    color: C.text, isTextBox: true, margin: 0,
    lineSpacingMultiple: 1.15, valign: "top",
  });

  s3.addText(a.targets, {
    x: xOff + 0.15, y: 4.6, w: 2.55, h: 0.25,
    fontSize: 10, fontFace: "Calibri", bold: true,
    color: a.color, isTextBox: true, margin: 0,
  });
});


// ============================================================
// SLIDE 4 — Assertion Agent Detail
// ============================================================
let s4 = pres.addSlide();
lightBg(s4);
addPageNum(s4, 4, TOTAL, false);

s4.addText("Assertion Agent — How It Works", {
  x: 0.6, y: 0.4, w: 8.5, h: 0.7,
  fontSize: 32, fontFace: "Calibri", bold: true,
  color: C.dark, isTextBox: true, margin: 0,
});

// Left: classification dimensions
s4.addShape(RRECT, {
  x: 0.6, y: 1.3, w: 4.2, h: 2.0,
  fill: { color: C.light }, rectRadius: 0.1,
});
s4.addText("Three Classification Dimensions", {
  x: 0.85, y: 1.4, w: 3.7, h: 0.35,
  fontSize: 15, fontFace: "Calibri", bold: true,
  color: C.primary, isTextBox: true, margin: 0,
});

const dims = [
  ["Subject:", "patient | family | other | unclear"],
  ["Polarity:", "affirmed | negated | hypothetical"],
  ["Temporality:", "current | historical | future"],
];
dims.forEach((d, i) => {
  let yy = 1.85 + i * 0.45;
  s4.addText(d[0], {
    x: 0.85, y: yy, w: 1.1, h: 0.3,
    fontSize: 12, fontFace: "Calibri", bold: true,
    color: C.text, isTextBox: true, margin: 0,
  });
  s4.addText(d[1], {
    x: 1.95, y: yy, w: 2.6, h: 0.3,
    fontSize: 11, fontFace: "Courier New",
    color: C.muted, isTextBox: true, margin: 0,
  });
});

// Right: example
s4.addShape(RRECT, {
  x: 5.2, y: 1.3, w: 4.2, h: 2.0,
  fill: { color: C.light }, rectRadius: 0.1,
});
s4.addText("Example", {
  x: 5.45, y: 1.4, w: 3.7, h: 0.35,
  fontSize: 15, fontFace: "Calibri", bold: true,
  color: C.primary, isTextBox: true, margin: 0,
});
s4.addText([
  { text: 'Criterion: "Must NOT have diabetes"\n', options: { fontSize: 11, bold: true, color: C.text } },
  { text: '[1] Father has type 2 diabetes\n', options: { fontSize: 11, color: C.warn } },
  { text: '     subject=family  DROPPED\n', options: { fontSize: 10, color: C.warn, italic: true } },
  { text: '[2] No history of diabetes in patient\n', options: { fontSize: 11, color: "0E8C6E" } },
  { text: '     subject=patient, negated  KEPT', options: { fontSize: 10, color: "0E8C6E", italic: true } },
], {
  x: 5.45, y: 1.8, w: 3.7, h: 1.4,
  fontFace: "Calibri", valign: "top",
  isTextBox: true, margin: 0, lineSpacingMultiple: 1.1,
});

// Bottom: Clarification + Verifier brief
s4.addShape(RRECT, {
  x: 0.6, y: 3.55, w: 4.2, h: 1.5,
  fill: { color: C.light }, rectRadius: 0.1,
});
s4.addText("Clarification Agent", {
  x: 0.85, y: 3.65, w: 3.7, h: 0.3,
  fontSize: 15, fontFace: "Calibri", bold: true,
  color: C.mid, isTextBox: true, margin: 0,
});
s4.addText("When baseline labels 'not enough info,' builds targeted queries and re-searches the patient note. Finds overlooked evidence without inventing new data.", {
  x: 0.85, y: 3.98, w: 3.7, h: 0.9,
  fontSize: 11.5, fontFace: "Calibri",
  color: C.text, isTextBox: true, margin: 0, lineSpacingMultiple: 1.15,
});

s4.addShape(RRECT, {
  x: 5.2, y: 3.55, w: 4.2, h: 1.5,
  fill: { color: C.light }, rectRadius: 0.1,
});
s4.addText("Verifier Agent", {
  x: 5.45, y: 3.65, w: 3.7, h: 0.3,
  fontSize: 15, fontFace: "Calibri", bold: true,
  color: "0E8C6E", isTextBox: true, margin: 0,
});
s4.addText("Checks if the label is actually supported by the evidence. Issues verdicts: verified, unsupported, contradicted, or uncertain. Corrects labels when evidence disagrees.", {
  x: 5.45, y: 3.98, w: 3.7, h: 0.9,
  fontSize: 11.5, fontFace: "Calibri",
  color: C.text, isTextBox: true, margin: 0, lineSpacingMultiple: 1.15,
});


// ============================================================
// SLIDE 5 — Architecture
// ============================================================
let s5 = pres.addSlide();
lightBg(s5);
addPageNum(s5, 5, TOTAL, false);

s5.addText("System Architecture", {
  x: 0.6, y: 0.4, w: 8.5, h: 0.7,
  fontSize: 36, fontFace: "Calibri", bold: true,
  color: C.dark, isTextBox: true, margin: 0,
});

// Pipeline boxes
const pipeline = [
  { label: "Patient\nRecord", color: C.muted, y: 0.3, tag: "Input" },
  { label: "Trial\nRetrieval", color: "6B7D8E", y: 0.3, tag: "Baseline" },
  { label: "Criterion\nMatching", color: "6B7D8E", y: 0.3, tag: "Baseline" },
  { label: "Assertion\nAgent", color: C.primary, y: 0.3, tag: "NEW" },
  { label: "Clarification\nAgent", color: C.mid, y: 0.3, tag: "NEW" },
  { label: "Verifier\nAgent", color: "0E8C6E", y: 0.3, tag: "NEW" },
  { label: "Aggregation\n& Ranking", color: "6B7D8E", y: 0.3, tag: "Baseline" },
  { label: "Ranked\nTrials", color: C.accent, y: 0.3, tag: "Output" },
];

const boxW = 1.0;
const boxH = 0.75;
const gap = 0.15;
const startX = 0.5;
const boxY = 2.8;

pipeline.forEach((p, i) => {
  let xx = startX + i * (boxW + gap);

  s5.addShape(RRECT, {
    x: xx, y: boxY, w: boxW, h: boxH,
    fill: { color: p.color }, rectRadius: 0.08,
  });
  s5.addText(p.label, {
    x: xx, y: boxY, w: boxW, h: boxH,
    fontSize: 9.5, fontFace: "Calibri", bold: true,
    color: C.white, align: "center", valign: "middle",
    isTextBox: true, margin: 0,
  });

  // Tag above
  let tagColor = p.tag === "NEW" ? C.warn : C.muted;
  s5.addText(p.tag, {
    x: xx, y: boxY - 0.3, w: boxW, h: 0.25,
    fontSize: 8, fontFace: "Calibri", bold: true,
    color: tagColor, align: "center",
    isTextBox: true, margin: 0,
  });

  // Arrow between boxes
  if (i < pipeline.length - 1) {
    let arrowX = xx + boxW;
    s5.addShape(RARROW, {
      x: arrowX, y: boxY + boxH / 2 - 0.08, w: gap, h: 0.16,
      fill: { color: "B0BEC5" },
    });
  }
});

// Bracket around the 3 new agents
s5.addShape(RECT, {
  x: startX + 3 * (boxW + gap), y: boxY + boxH + 0.1,
  w: 3 * boxW + 2 * gap, h: 0.03,
  fill: { color: C.primary },
});
s5.addText("Our Contribution: Agent Enhancement Layer", {
  x: startX + 3 * (boxW + gap), y: boxY + boxH + 0.15,
  w: 3 * boxW + 2 * gap, h: 0.3,
  fontSize: 10, fontFace: "Calibri", bold: true,
  color: C.primary, align: "center",
  isTextBox: true, margin: 0,
});

// Data flow description
s5.addShape(RRECT, {
  x: 0.6, y: 4.0, w: 8.8, h: 1.0,
  fill: { color: C.light }, rectRadius: 0.08,
});
s5.addText([
  { text: "Data Flow: ", options: { fontSize: 12, bold: true, color: C.primary } },
  { text: "Patient note + retrieved trials ", options: { fontSize: 12, color: C.text } },
  { text: "\u2192", options: { fontSize: 12, color: C.muted } },
  { text: " per-criterion LLM judgments ", options: { fontSize: 12, color: C.text } },
  { text: "\u2192", options: { fontSize: 12, color: C.muted } },
  { text: " assertion filtering \u2192 gap re-search \u2192 verification ", options: { fontSize: 12, color: C.primary, bold: true } },
  { text: "\u2192", options: { fontSize: 12, color: C.muted } },
  { text: " corrected labels + audit trail \u2192 trial ranking", options: { fontSize: 12, color: C.text } },
], {
  x: 0.8, y: 4.1, w: 8.4, h: 0.8,
  fontFace: "Calibri", valign: "middle",
  isTextBox: true, margin: 0, lineSpacingMultiple: 1.2,
});


// ============================================================
// SLIDE 6 — Results
// ============================================================
let s6 = pres.addSlide();
lightBg(s6);
addPageNum(s6, 6, TOTAL, false);

s6.addText("Experimental Results", {
  x: 0.6, y: 0.4, w: 8.5, h: 0.7,
  fontSize: 36, fontFace: "Calibri", bold: true,
  color: C.dark, isTextBox: true, margin: 0,
});

s6.addText("SIGIR 2016 benchmark  |  4 patients  |  1,663 criterion decisions  |  Qwen 27B model", {
  x: 0.6, y: 1.0, w: 8.5, h: 0.35,
  fontSize: 12, fontFace: "Calibri",
  color: C.muted, isTextBox: true, margin: 0,
});

// Big stat callouts
const stats = [
  { num: "26", label: "Corrections\nMade", color: C.primary },
  { num: "14", label: "Clarification\nTriggered", color: C.mid },
  { num: "3", label: "Contradictions\nCaught", color: C.warn },
  { num: "10", label: "Unsupported\nLabels Fixed", color: "0E8C6E" },
];

stats.forEach((st, i) => {
  let xx = 0.6 + i * 2.3;
  s6.addShape(RRECT, {
    x: xx, y: 1.55, w: 2.05, h: 1.3,
    fill: { color: C.white },
    shadow: { type: "outer", blur: 5, offset: 2, angle: 135, color: "000000", opacity: 0.1 },
    rectRadius: 0.08,
  });
  s6.addText(st.num, {
    x: xx, y: 1.6, w: 2.05, h: 0.7,
    fontSize: 44, fontFace: "Calibri", bold: true,
    color: st.color, align: "center", valign: "middle",
    isTextBox: true, margin: 0,
  });
  s6.addText(st.label, {
    x: xx, y: 2.35, w: 2.05, h: 0.45,
    fontSize: 11, fontFace: "Calibri",
    color: C.muted, align: "center", valign: "top",
    isTextBox: true, margin: 0,
  });
});

// Sample correction example
s6.addShape(RRECT, {
  x: 0.6, y: 3.1, w: 8.8, h: 2.0,
  fill: { color: C.light }, rectRadius: 0.1,
});

s6.addText("Example Correction", {
  x: 0.85, y: 3.2, w: 3, h: 0.35,
  fontSize: 16, fontFace: "Calibri", bold: true,
  color: C.primary, isTextBox: true, margin: 0,
});

s6.addText([
  { text: 'Criterion: ', options: { fontSize: 12, bold: true, color: C.text } },
  { text: '"Severe hepatic insufficiency" (exclusion)\n', options: { fontSize: 12, color: C.text } },
  { text: 'Baseline: ', options: { fontSize: 12, bold: true, color: C.warn } },
  { text: '"not excluded" \u2014 assumed absence = safe\n', options: { fontSize: 12, color: C.warn } },
  { text: 'Verifier: ', options: { fontSize: 12, bold: true, color: "0E8C6E" } },
  { text: 'Unsupported \u2014 absence of mention \u2260 evidence of absence\n', options: { fontSize: 12, color: "0E8C6E" } },
  { text: 'Corrected: ', options: { fontSize: 12, bold: true, color: C.primary } },
  { text: '"not enough information" \u2014 requires lab confirmation', options: { fontSize: 12, color: C.primary } },
], {
  x: 0.85, y: 3.55, w: 8.3, h: 1.4,
  fontFace: "Calibri", valign: "top",
  isTextBox: true, margin: 0, lineSpacingMultiple: 1.3,
});


// ============================================================
// SLIDE 7 — Key Findings
// ============================================================
let s7 = pres.addSlide();
lightBg(s7);
addPageNum(s7, 7, TOTAL, false);

s7.addText("Key Findings", {
  x: 0.6, y: 0.4, w: 8.5, h: 0.7,
  fontSize: 36, fontFace: "Calibri", bold: true,
  color: C.dark, isTextBox: true, margin: 0,
});

const findings = [
  {
    title: "Absence \u2260 Evidence",
    body: "Most corrections (19/26) changed 'not excluded' to 'not enough information.' The baseline incorrectly treats missing info in a patient note as evidence the condition is absent.",
    icon: "!",
  },
  {
    title: "Clarification Recovers Evidence",
    body: "The Clarification Agent triggered 14 times and successfully found overlooked evidence in the patient note, enabling more informed decisions.",
    icon: "\u2714",
  },
  {
    title: "Verifier Catches Real Errors",
    body: "3 direct contradictions caught: e.g., baseline using cardiac evaluation to judge antidepressant intolerance. The verifier correctly identified irrelevant reasoning.",
    icon: "\u26A0",
  },
];

findings.forEach((f, i) => {
  let yy = 1.3 + i * 1.35;

  s7.addShape(RRECT, {
    x: 0.6, y: yy, w: 8.8, h: 1.1,
    fill: { color: C.white },
    shadow: { type: "outer", blur: 4, offset: 2, angle: 135, color: "000000", opacity: 0.08 },
    rectRadius: 0.08,
  });

  s7.addShape(ELLIPSE, {
    x: 0.85, y: yy + 0.25, w: 0.5, h: 0.5,
    fill: { color: i === 0 ? C.warn : i === 1 ? C.mid : "E8A73A" },
  });
  s7.addText(f.icon, {
    x: 0.85, y: yy + 0.25, w: 0.5, h: 0.5,
    fontSize: 18, fontFace: "Calibri", bold: true,
    color: C.white, align: "center", valign: "middle",
    isTextBox: true, margin: 0,
  });

  s7.addText(f.title, {
    x: 1.6, y: yy + 0.1, w: 7.5, h: 0.35,
    fontSize: 16, fontFace: "Calibri", bold: true,
    color: C.dark, isTextBox: true, margin: 0,
  });

  s7.addText(f.body, {
    x: 1.6, y: yy + 0.45, w: 7.5, h: 0.55,
    fontSize: 12, fontFace: "Calibri",
    color: C.text, isTextBox: true, margin: 0,
    lineSpacingMultiple: 1.15,
  });
});


// ============================================================
// SLIDE 8 — Individual Contributions
// ============================================================
let s8 = pres.addSlide();
lightBg(s8);
addPageNum(s8, 8, TOTAL, false);

s8.addText("Individual Contributions", {
  x: 0.6, y: 0.4, w: 8.5, h: 0.7,
  fontSize: 36, fontFace: "Calibri", bold: true,
  color: C.dark, isTextBox: true, margin: 0,
});

const members = [
  {
    name: "Team Member 1",
    role: "Assertion Agent & Data Pipeline",
    tasks: [
      "Designed and implemented the Assertion Agent",
      "Built evidence classification (subject, polarity, temporality)",
      "Created data preprocessing and sentence parsing pipeline",
      "Handled patient note segmentation and indexing",
    ],
  },
  {
    name: "Team Member 2",
    role: "Clarification Agent & Integration",
    tasks: [
      "Designed and implemented the Clarification Agent",
      "Built targeted query generation for evidence re-search",
      "Integrated all three agents into the orchestration pipeline",
      "Managed API integration with Groq/LLM backend",
    ],
  },
  {
    name: "Team Member 3",
    role: "Verifier Agent & Evaluation",
    tasks: [
      "Designed and implemented the Verifier Agent",
      "Built entailment checking and label correction logic",
      "Conducted experimental evaluation on SIGIR benchmark",
      "Created comparison framework and result analysis",
    ],
  },
];

members.forEach((m, i) => {
  let xx = 0.6 + i * 3.1;
  let cardColor = i === 0 ? C.primary : i === 1 ? C.mid : "0E8C6E";

  s8.addShape(RRECT, {
    x: xx, y: 1.3, w: 2.85, h: 3.7,
    fill: { color: C.white },
    shadow: { type: "outer", blur: 5, offset: 2, angle: 135, color: "000000", opacity: 0.1 },
    rectRadius: 0.1,
  });

  // Name circle
  s8.addShape(ELLIPSE, {
    x: xx + 0.95, y: 1.5, w: 0.95, h: 0.95,
    fill: { color: cardColor },
  });
  let initials = m.name.split(" ").map(w => w[0]).join("").substring(0, 2);
  s8.addText(initials, {
    x: xx + 0.95, y: 1.5, w: 0.95, h: 0.95,
    fontSize: 24, fontFace: "Calibri", bold: true,
    color: C.white, align: "center", valign: "middle",
    isTextBox: true, margin: 0,
  });

  s8.addText(m.name, {
    x: xx + 0.15, y: 2.55, w: 2.55, h: 0.3,
    fontSize: 15, fontFace: "Calibri", bold: true,
    color: C.dark, align: "center",
    isTextBox: true, margin: 0,
  });

  s8.addText(m.role, {
    x: xx + 0.15, y: 2.85, w: 2.55, h: 0.25,
    fontSize: 10, fontFace: "Calibri", italic: true,
    color: cardColor, align: "center",
    isTextBox: true, margin: 0,
  });

  // Tasks as bullets
  let taskText = m.tasks.map((t, ti) => ({
    text: t,
    options: {
      fontSize: 10.5, fontFace: "Calibri", color: C.text,
      bullet: true, breakLine: ti < m.tasks.length - 1,
      paraSpaceAfter: 4,
    },
  }));
  s8.addText(taskText, {
    x: xx + 0.15, y: 3.25, w: 2.55, h: 1.65,
    valign: "top", isTextBox: true, margin: [0, 0, 0, 4],
    lineSpacingMultiple: 1.1,
  });
});

s8.addText("* Replace 'Team Member 1/2/3' with actual names", {
  x: 0.6, y: 5.1, w: 6, h: 0.3,
  fontSize: 9, fontFace: "Calibri", italic: true,
  color: C.muted, isTextBox: true, margin: 0,
});


// ============================================================
// SLIDE 9 — Conclusion / Thank You
// ============================================================
let s9 = pres.addSlide();
darkBg(s9);
addPageNum(s9, 9, TOTAL, true);

s9.addShape(RECT, {
  x: 0.6, y: 1.6, w: 0.06, h: 1.2, fill: { color: C.accent },
});

s9.addText("Conclusion & Future Work", {
  x: 0.9, y: 1.5, w: 8, h: 0.7,
  fontSize: 36, fontFace: "Calibri", bold: true,
  color: C.white, isTextBox: true, margin: 0,
});

s9.addText([
  { text: "Agentic-TrailGPT demonstrates that targeted post-processing agents\ncan catch and correct real errors in LLM-based clinical trial matching.", options: { fontSize: 15, color: C.accent } },
], {
  x: 0.9, y: 2.3, w: 8, h: 0.7,
  fontFace: "Calibri", isTextBox: true, margin: 0, lineSpacingMultiple: 1.2,
});

s9.addText("Future Directions", {
  x: 0.9, y: 3.3, w: 5, h: 0.4,
  fontSize: 18, fontFace: "Calibri", bold: true,
  color: C.white, isTextBox: true, margin: 0,
});

const future = [
  "Full-scale evaluation on TREC 2021/2022 datasets",
  "Ablation studies for each agent's individual impact",
  "Integration with clinical trial registries for real-world deployment",
  "Fine-tuning on domain-specific medical LLMs",
];

s9.addText(
  future.map((f, i) => ({
    text: f,
    options: {
      fontSize: 13, fontFace: "Calibri", color: "B0C4DE",
      bullet: true, breakLine: i < future.length - 1,
      paraSpaceAfter: 6,
    },
  })),
  {
    x: 0.9, y: 3.75, w: 7.5, h: 1.5,
    valign: "top", isTextBox: true, margin: [0, 0, 0, 4],
  }
);

s9.addText("Thank You", {
  x: 6.5, y: 4.8, w: 3, h: 0.5,
  fontSize: 20, fontFace: "Calibri", bold: true,
  color: C.accent, align: "right",
  isTextBox: true, margin: 0,
});


// ============================================================
// WRITE FILE
// ============================================================
const outPath = "C:\\Users\\udayr\\Downloads\\llm project_trailgpt\\Agentic-TrailGPT\\Agentic_TrailGPT_Presentation.pptx";
pres.writeFile({ fileName: outPath }).then(() => {
  console.log("Saved: " + outPath);
}).catch(err => {
  console.error("Error:", err);
});
