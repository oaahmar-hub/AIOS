import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/hassanka/Downloads/AIOS/KnowledgeBase/outputs/content_automation_map";
const finalPath = "/Users/hassanka/Downloads/AIOS/KnowledgeBase/AIOS_Content_Automation_Map.xlsx";
const outputPath = path.join(outputDir, "AIOS_Content_Automation_Map.xlsx");

const integrations = [
  {
    system: "Canva",
    connected: "YES",
    api: "YES",
    read: "YES",
    write: "YES",
    automation: "Generate/edit branded posts, stories, flyers, thumbnails, proposals, and listing visuals from AIOS scripts and property data.",
    useCases: "Instagram posts, LinkedIn cards, WhatsApp Status creatives, YouTube thumbnails, property flyers, developer launch assets.",
    timeSaved: "4-8 hrs/week",
    revenue: "High - faster listing promotion and more consistent lead-generation creatives.",
    readiness: 9,
    blocker: "Needs approved brand templates and asset folders for full autopilot."
  },
  {
    system: "Higgsfield AI",
    connected: "NO",
    api: "YES",
    read: "NO",
    write: "NO",
    automation: "Generate AI motion/video assets from scripts, images, characters, and property campaign concepts.",
    useCases: "Luxury property reels, Omar avatar/character videos, developer launch videos, lifestyle scenes, before/after renovation clips.",
    timeSaved: "5-10 hrs/week",
    revenue: "High - video output can multiply social reach and lead capture.",
    readiness: 5,
    blocker: "Needs API key/account connection and output-quality test."
  },
  {
    system: "Notion",
    connected: "YES",
    api: "YES",
    read: "YES",
    write: "YES",
    automation: "Store campaign briefs, content calendars, SOPs, approvals, creative ideas, and reusable marketing playbooks.",
    useCases: "Marketing calendar, campaign status, content approvals, idea vault, creative briefs, SOP hub.",
    timeSaved: "2-4 hrs/week",
    revenue: "Medium - improves organization and reduces repeated planning work.",
    readiness: 8,
    blocker: "No AIOS Notion workspace structure found yet; create content database when ready."
  },
  {
    system: "YouTube",
    connected: "NO",
    api: "YES",
    read: "NO",
    write: "NO",
    automation: "Upload videos, titles, descriptions, thumbnails, tags, and campaign metadata from AIOS-generated content.",
    useCases: "Property walkthroughs, market update videos, developer news, investment explainers, Shorts/Reels repurposing.",
    timeSaved: "2-5 hrs/week",
    revenue: "Medium-High - evergreen search and lead capture channel.",
    readiness: 6,
    blocker: "Needs OAuth/channel connection and approval before publishing."
  },
  {
    system: "LinkedIn",
    connected: "NO",
    api: "YES",
    read: "NO",
    write: "NO",
    automation: "Create/publish professional posts, market insights, case studies, and investment summaries.",
    useCases: "UAE market updates, investment thesis posts, developer news, corporate services content, Omar thought leadership.",
    timeSaved: "3-6 hrs/week",
    revenue: "High - investor and corporate-service lead generation.",
    readiness: 6,
    blocker: "Needs LinkedIn app/OAuth permissions and Omar approval flow for public posts."
  },
  {
    system: "Cloud Media Library",
    connected: "YES",
    api: "YES",
    read: "YES",
    write: "YES",
    automation: "Use Google Drive as the shared source for photos, videos, generated assets, documents, thumbnails, scripts, and campaign exports.",
    useCases: "Property asset folders, brand library, generated images/videos, campaign source files, approval packages, post archives.",
    timeSaved: "3-6 hrs/week",
    revenue: "High - prevents lost assets and speeds every listing/campaign.",
    readiness: 8,
    blocker: "Needs final folder taxonomy and naming rules."
  }
];

const workflow = [
  ["1", "Lead", "Inbound buyer/seller/investor request enters AIOS", "CRM lead + structured requirement", "Airtable / Entry Point", "Working except WhatsApp provider"],
  ["2", "Property Match", "AIOS queries Property_Master_Database", "Ranked matches / nearest alternatives", "Property_Master_Database", "Working"],
  ["3", "Script", "AIOS turns match into short premium sales script", "Caption, reel script, WhatsApp copy, LinkedIn angle", "OpenAI + Knowledge Vault", "Ready"],
  ["4", "Image", "Generate or design still assets", "Post, story, thumbnail, flyer", "Canva / image tools", "Canva ready; generation workflow next"],
  ["5", "Video", "Turn script/image into motion video", "Reel/Short/TikTok/YouTube draft", "Higgsfield AI", "Blocked until API connected"],
  ["6", "Post", "Publish or prepare platform-specific post", "LinkedIn/YouTube/Canva export", "LinkedIn / YouTube APIs", "Blocked until OAuth"],
  ["7", "Lead Capture", "Track inquiries from post/channel", "New lead / campaign source", "CRM + forms + inbox", "Partially ready"],
  ["8", "CRM", "Create/update lead and campaign source", "Lead record + task", "Airtable", "Working"],
  ["9", "Follow-Up", "Create task and draft response", "Follow-up task + message", "Airtable + AIOS router", "Working"]
];

const roadmap = [
  ["1", "Cloud Media Library", "Create AIOS media folder taxonomy and naming rules", "Immediate", "Low", "Fastest foundation for all content automation"],
  ["2", "Canva", "Create 5 HSH real estate templates: listing, market update, investor, developer launch, YouTube thumbnail", "Immediate", "Low", "Turns property matches into visual assets quickly"],
  ["3", "Notion", "Create campaign/content calendar database and approval board", "Immediate", "Low", "Organizes content operations without waiting for social APIs"],
  ["4", "Higgsfield AI", "Connect API key and run one property reel generation test", "Next", "Medium", "Unlocks high-impact video automation"],
  ["5", "LinkedIn", "Connect OAuth/app permissions and create draft-only posting flow", "Next", "Medium", "Revenue channel for investors/corporate clients"],
  ["6", "YouTube", "Connect OAuth/channel and create upload-as-draft flow", "Next", "Medium", "Enables long-form and Shorts distribution"],
  ["7", "CRM Attribution", "Add campaign/source tracking from post to lead", "Next", "Medium", "Closes the marketing-to-revenue loop"]
];

const sources = [
  ["Canva Connect APIs", "https://www.canva.dev/docs/connect/", "Canva REST APIs can create/sync assets, designs, comments, and workflow integrations."],
  ["Canva Apps SDK", "https://www.canva.dev/docs/apps/", "Canva supports apps plus Connect APIs for workflow integration."],
  ["Higgsfield Cloud", "https://cloud.higgsfield.ai/", "Higgsfield cloud account/API entry point requires sign-in."],
  ["Higgsfield Python SDK", "https://github.com/higgsfield-ai/higgsfield-client", "Official Python SDK exists for Higgsfield API."],
  ["YouTube videos.insert", "https://developers.google.com/youtube/v3/docs/videos/insert", "YouTube Data API supports uploading videos with videos.insert."],
  ["YouTube upload guide", "https://developers.google.com/youtube/v3/guides/uploading_a_video", "Official guide explains upload flow."],
  ["LinkedIn Posts API", "https://learn.microsoft.com/en-us/linkedin/marketing/community-management/shares/posts-api?view=li-lms-2026-06", "Current LinkedIn Posts API creates/retrieves organic and sponsored posts."],
  ["LinkedIn Marketing APIs", "https://developer.linkedin.com/product-catalog/marketing", "LinkedIn Marketing APIs support marketing workflow integrations."],
  ["Notion API overview", "https://developers.notion.com/guides/get-started/overview", "Notion REST API can read, create, and update workspace content based on permissions."],
  ["Google Drive files.create", "https://developers.google.com/workspace/drive/api/reference/rest/v3/files/create", "Drive API supports file creation and media upload types."],
  ["Google Drive search", "https://developers.google.com/workspace/drive/api/guides/search-files", "Drive API supports file/folder search through files.list queries."]
];

const workbook = Workbook.create();
const summary = workbook.worksheets.add("Summary");
const map = workbook.worksheets.add("Integration Map");
const flow = workbook.worksheets.add("Workflow");
const ready = workbook.worksheets.add("Readiness");
const sourceSheet = workbook.worksheets.add("Sources");

for (const sheet of [summary, map, flow, ready, sourceSheet]) sheet.showGridLines = false;

function header(range) {
  range.format.fill = { color: "#DCEAF7" };
  range.format.font = { bold: true, color: "#102A43" };
  range.format.wrapText = true;
  range.format.borders = { preset: "bottom", style: "thin", color: "#8AA4B8" };
}

function title(sheet, text, range = "A1:J1") {
  sheet.getRange(range).merge();
  sheet.getRange("A1").values = [[text]];
  sheet.getRange(range).format.font = { bold: true, size: 18, color: "#102A43" };
  sheet.getRange(range).format.fill = { color: "#FFFFFF" };
}

title(summary, "AIOS Content & Automation Map", "A1:H1");
summary.getRange("A3:B8").values = [
  ["Connected systems", null],
  ["API-available systems", null],
  ["Read-ready systems", null],
  ["Write-ready systems", null],
  ["Highest readiness", null],
  ["Main blocker", "Higgsfield, YouTube, and LinkedIn need external account/API/OAuth connection before live automation."]
];
summary.getRange("B3").formulas = [["=COUNTIF('Integration Map'!B2:B7,\"YES\")"]];
summary.getRange("B4").formulas = [["=COUNTIF('Integration Map'!C2:C7,\"YES\")"]];
summary.getRange("B5").formulas = [["=COUNTIF('Integration Map'!D2:D7,\"YES\")"]];
summary.getRange("B6").formulas = [["=COUNTIF('Integration Map'!E2:E7,\"YES\")"]];
summary.getRange("B7").formulas = [["=MAX('Integration Map'!J2:J7)"]];
summary.getRange("A3:B8").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
summary.getRange("A3:A8").format.font = { bold: true, color: "#102A43" };
summary.getRange("B8").format.wrapText = true;

summary.getRange("D3:H3").values = [["Goal Flow", "Status", "Owner System", "Next Action", "Business Result"]];
header(summary.getRange("D3:H3"));
summary.getRange("D4:H12").values = workflow.map((row) => [row[1], row[5], row[4], row[3], row[2]]);
summary.getRange("D4:H12").format.wrapText = true;
summary.getRange("D3:H12").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };

map.getRange("A1:K1").values = [[
  "System",
  "CONNECTED",
  "API AVAILABLE",
  "READ",
  "WRITE",
  "AUTOMATION POTENTIAL",
  "REAL ESTATE USE CASES",
  "TIME SAVED",
  "REVENUE IMPACT",
  "READINESS SCORE",
  "BLOCKER / NOTE"
]];
header(map.getRange("A1:K1"));
map.getRangeByIndexes(1, 0, integrations.length, 11).values = integrations.map((i) => [
  i.system, i.connected, i.api, i.read, i.write, i.automation, i.useCases, i.timeSaved, i.revenue, i.readiness, i.blocker
]);
map.getRange("F2:K7").format.wrapText = true;
map.getRange("A1:K7").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
map.getRange("J2:J7").format.numberFormat = Array.from({ length: 6 }, () => ["0"]);
map.freezePanes.freezeRows(1);

flow.getRange("A1:F1").values = [["Step", "Stage", "AIOS Action", "Output", "System", "Status"]];
header(flow.getRange("A1:F1"));
flow.getRangeByIndexes(1, 0, workflow.length, 6).values = workflow;
flow.getRange("C2:F10").format.wrapText = true;
flow.getRange("A1:F10").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
flow.freezePanes.freezeRows(1);

ready.getRange("A1:G1").values = [["Rank", "System", "Next Activation", "Timing", "Risk", "Why It Matters", "Status"]];
header(ready.getRange("A1:G1"));
ready.getRangeByIndexes(1, 0, roadmap.length, 7).values = roadmap.map((r) => [...r, r[4] === "Low" ? "Ready" : "Needs connection"]);
ready.getRange("C2:G8").format.wrapText = true;
ready.getRange("A1:G8").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
ready.freezePanes.freezeRows(1);

sourceSheet.getRange("A1:C1").values = [["Source", "URL", "Use"]];
header(sourceSheet.getRange("A1:C1"));
sourceSheet.getRangeByIndexes(1, 0, sources.length, 3).values = sources;
sourceSheet.getRange("B2:C12").format.wrapText = true;
sourceSheet.getRange("A1:C12").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
sourceSheet.freezePanes.freezeRows(1);

for (const sheet of [summary, map, flow, ready, sourceSheet]) {
  sheet.getUsedRange().format.autofitColumns();
  sheet.getUsedRange().format.autofitRows();
}

summary.getRange("A:A").format.columnWidth = 24;
summary.getRange("B:B").format.columnWidth = 62;
summary.getRange("D:H").format.columnWidth = 26;
map.getRange("A:A").format.columnWidth = 20;
map.getRange("F:G").format.columnWidth = 58;
map.getRange("H:H").format.columnWidth = 16;
map.getRange("I:I").format.columnWidth = 44;
map.getRange("J:J").format.columnWidth = 16;
map.getRange("K:K").format.columnWidth = 46;
map.getRange("A2:K7").format.rowHeight = 92;
flow.getRange("C:F").format.columnWidth = 38;
ready.getRange("C:G").format.columnWidth = 38;
sourceSheet.getRange("B:B").format.columnWidth = 72;
sourceSheet.getRange("C:C").format.columnWidth = 58;

await fs.mkdir(outputDir, { recursive: true });
for (const [sheetName, range] of [["Summary", "A1:H12"], ["Integration Map", "A1:K7"], ["Workflow", "A1:F10"], ["Readiness", "A1:G8"]]) {
  const preview = await workbook.render({ sheetName, range, scale: 1, format: "png" });
  await fs.writeFile(path.join(outputDir, `${sheetName.replaceAll(" ", "_")}_preview.png`), new Uint8Array(await preview.arrayBuffer()));
}

const inspect = await workbook.inspect({
  kind: "table",
  sheetId: "Integration Map",
  range: "A1:K7",
  include: "values,formulas",
  tableMaxRows: 7,
  tableMaxCols: 11,
  maxChars: 10000
});
console.log(inspect.ndjson);

const errors = await workbook.inspect({
  kind: "match",
  searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A",
  options: { useRegex: true, maxResults: 300 },
  summary: "final formula error scan"
});
console.log(errors.ndjson);

const output = await SpreadsheetFile.exportXlsx(workbook);
await output.save(outputPath);
await fs.copyFile(outputPath, finalPath);
console.log(JSON.stringify({ outputPath, finalPath }));
