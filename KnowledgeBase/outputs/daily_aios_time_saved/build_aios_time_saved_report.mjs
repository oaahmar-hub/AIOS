import fs from "node:fs/promises";
import path from "node:path";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "/Users/hassanka/Downloads/AIOS/KnowledgeBase/outputs/daily_aios_time_saved";
const finalPath = "/Users/hassanka/Downloads/AIOS/KnowledgeBase/AIOS_Time_Saved_Report.xlsx";
const outputPath = path.join(outputDir, "AIOS_Time_Saved_Report.xlsx");

const rows = [
  {
    task: "Property search",
    current: "Search WhatsApp sheets, Drive files, old chats, and ask data contacts manually. Compare area, project, budget, unit type, and availability one by one.",
    aios: "Ask AIOS for area/project/budget criteria. AIOS queries Property_Master_Database, applies aliases, returns ranked matches and nearest alternatives.",
    automation: "Fully automate from inbound lead: parse requirement, query inventory, rank options, create shortlist, log result, and draft client reply.",
    occurrences: 18,
    manualMins: 12,
    assistedMins: 3,
    autoPotential: "High",
    dependency: "Property_Master_Database",
    status: "Working"
  },
  {
    task: "Lead follow-up",
    current: "Read WhatsApp or email, remember context, decide next step, create task manually, and follow up later from memory.",
    aios: "AIOS creates/updates CRM lead, creates follow-up task, links requirement, and suggests property/action next step.",
    automation: "Auto-create CRM, task, lead score, follow-up time, and draft message after every qualified inbound lead.",
    occurrences: 25,
    manualMins: 8,
    assistedMins: 2,
    autoPotential: "High",
    dependency: "Airtable CRM + tasks",
    status: "Working"
  },
  {
    task: "Document retrieval",
    current: "Search Drive, Downloads, WhatsApp, and folders manually for contracts, title deeds, NOC files, approval packages, or company documents.",
    aios: "Ask for the document by client/project/process. AIOS searches Drive and local indexes, then returns the closest document names/links.",
    automation: "Auto-link documents to client/property/deal records and surface required files during task workflows.",
    occurrences: 12,
    manualMins: 20,
    assistedMins: 4,
    autoPotential: "High",
    dependency: "Google Drive + local Knowledge Vault",
    status: "Working"
  },
  {
    task: "NOC preparation",
    current: "Check developer/Nakheel/DLD requirements, collect document list, prepare package, and verify what is missing manually.",
    aios: "AIOS retrieves NOC process, requirements, risk notes, and related historical cases/checklists.",
    automation: "Generate NOC checklist, missing-doc tracker, client message, and submission pack draft from deal/property data.",
    occurrences: 5,
    manualMins: 45,
    assistedMins: 15,
    autoPotential: "Medium",
    dependency: "Operations Brain + case library",
    status: "Working"
  },
  {
    task: "Transfer preparation",
    current: "Confirm parties, fees, required documents, DLD/Oqood steps, payment method, timelines, and title deed/NOC readiness manually.",
    aios: "AIOS answers transfer process questions and returns fee/document/timeline checklists from Operations Brain.",
    automation: "Auto-generate transfer checklist, fee estimate, document request, and status tracker for each deal.",
    occurrences: 4,
    manualMins: 60,
    assistedMins: 20,
    autoPotential: "Medium",
    dependency: "Operations Brain + CRM deal data",
    status: "Working"
  },
  {
    task: "Valuation coordination",
    current: "Collect property details, compare market data, contact parties, create valuation task, and track response manually.",
    aios: "AIOS creates valuation task, links lead/property, and pulls market/property context for the request.",
    automation: "Auto-create valuation request from lead message, attach comparable inventory, assign task, and remind until complete.",
    occurrences: 6,
    manualMins: 25,
    assistedMins: 8,
    autoPotential: "High",
    dependency: "Airtable + Property_Master_Database",
    status: "Working"
  },
  {
    task: "Email review",
    current: "Open Gmail, scan unread messages, identify urgent business emails, separate admin noise from revenue/operation items.",
    aios: "AIOS searches recent Gmail and extracts important messages needing attention.",
    automation: "Daily CEO briefing: categorize, summarize, rank urgency, create tasks, and draft replies for review.",
    occurrences: 7,
    manualMins: 20,
    assistedMins: 6,
    autoPotential: "High",
    dependency: "Gmail + Airtable tasks",
    status: "Working"
  },
  {
    task: "Client qualification",
    current: "Ask budget, area, bedroom, purpose, finance/cash, timeline, nationality/documents, then remember all context manually.",
    aios: "AIOS uses a qualification checklist and stores structured requirement fields into CRM.",
    automation: "Auto-detect missing qualification fields from WhatsApp/email and ask short premium follow-up questions.",
    occurrences: 15,
    manualMins: 10,
    assistedMins: 3,
    autoPotential: "High",
    dependency: "CRM + WhatsApp provider once restored",
    status: "Partially Working"
  },
  {
    task: "Visa processing",
    current: "Check ICP/GDRFA requirements, documents, fees, timelines, client eligibility, and next steps manually.",
    aios: "AIOS retrieves ICP/GDRFA knowledge from Operations Brain and builds document/checklist answers.",
    automation: "Auto-generate visa checklist and task plan from client/company profile once structured intake exists.",
    occurrences: 3,
    manualMins: 50,
    assistedMins: 18,
    autoPotential: "Medium",
    dependency: "Operations Brain + client profile",
    status: "Working"
  },
  {
    task: "Mortgage support",
    current: "Review mortgage registration/release/transfer requirements, bank coordination items, and document needs manually.",
    aios: "AIOS retrieves mortgage processes and document requirements from local operations corpus.",
    automation: "Auto-create mortgage checklist, bank follow-up tasks, document tracker, and client-facing summary.",
    occurrences: 4,
    manualMins: 40,
    assistedMins: 12,
    autoPotential: "Medium",
    dependency: "Operations Brain + deal records",
    status: "Working"
  }
];

const roadmapRows = [
  ["1", "Lead follow-up", "Auto CRM + task + property shortlist from inbound lead", "Immediate", "High", "Requires WhatsApp provider for full inbound autopilot"],
  ["2", "Property search", "One command returns ranked matches and near-misses", "Immediate", "High", "Already works through Property_Master_Database"],
  ["3", "Document retrieval", "Drive/local search by project/client/process", "Immediate", "High", "Already works for Nakheel examples"],
  ["4", "Email review", "Daily important email extraction and task creation", "Immediate", "High", "Gmail read access works"],
  ["5", "CEO briefing", "Daily calendar, Gmail, tasks, leads, risks", "Immediate", "High", "Calendar can be empty; still valid"],
  ["6", "NOC preparation", "Developer/DLD checklist + missing document tracker", "This week", "Medium", "Needs developer-specific templates expanded"],
  ["7", "Transfer preparation", "Transfer checklist + fee/doc timeline output", "This week", "Medium", "Operations Brain already has DLD sources"],
  ["8", "Valuation coordination", "Create valuation task and attach comps", "This week", "High", "Airtable task creation proven"],
  ["9", "Client qualification", "Detect missing lead fields and draft questions", "After WhatsApp fix", "High", "Inbound channel remains provider-blocked"],
  ["10", "Mortgage support", "Mortgage checklist and bank-task tracker", "Next", "Medium", "Knowledge exists, workflow templates next"]
];

function styleTitle(range) {
  range.format.fill = { color: "#FFFFFF" };
  range.format.font = { color: "#102A43", bold: true, size: 18 };
  range.format.wrapText = true;
}

function styleHeader(range) {
  range.format.fill = { color: "#D9E8F5" };
  range.format.font = { bold: true, color: "#102A43" };
  range.format.wrapText = true;
  range.format.borders = { preset: "bottom", style: "thin", color: "#8AA4B8" };
}

function styleSummary(range, fill = "#F4F8FB") {
  range.format.fill = { color: fill };
  range.format.borders = { preset: "outside", style: "thin", color: "#B8C7D3" };
  range.format.font = { bold: true, color: "#102A43" };
}

const workbook = Workbook.create();
const dashboard = workbook.worksheets.add("Dashboard");
const taskSheet = workbook.worksheets.add("Weekly Tasks");
const roadmap = workbook.worksheets.add("Automation Roadmap");

for (const sheet of [dashboard, taskSheet, roadmap]) {
  sheet.showGridLines = false;
}

dashboard.getRange("A1:H1").merge();
dashboard.getRange("A1").values = [["AIOS Time Saved Report"]];
styleTitle(dashboard.getRange("A1:H1"));
dashboard.getRange("A1").format.fill = { color: "#FFFFFF" };
dashboard.getRange("A1").format.font = { color: "#102A43", bold: true, size: 18 };
dashboard.getRange("A1:H1").format.rowHeight = 28;
dashboard.getRange("A2:H2").merge();
dashboard.getRange("A2").values = [["Purpose: reduce Omar's weekly workload using the AIOS assets already proven live: Property Database, Airtable CRM, Gmail, Calendar, Drive, Operations Brain, and Knowledge Vault."]];
dashboard.getRange("A2:H2").format.wrapText = true;

dashboard.getRange("A4:B4").merge();
dashboard.getRange("D4:E4").merge();
dashboard.getRange("G4:H4").merge();
dashboard.getRange("A4").values = [["Manual Hours / Week"]];
dashboard.getRange("D4").values = [["AIOS-Assisted Hours / Week"]];
dashboard.getRange("G4").values = [["Hours Saved / Week"]];
styleSummary(dashboard.getRange("A4:B5"), "#FFF7E6");
styleSummary(dashboard.getRange("D4:E5"), "#EAF7F1");
styleSummary(dashboard.getRange("G4:H5"), "#EAF2FF");
dashboard.getRange("A5").formulas = [["=SUM('Weekly Tasks'!E2:E11)/60"]];
dashboard.getRange("D5").formulas = [["=SUM('Weekly Tasks'!F2:F11)/60"]];
dashboard.getRange("G5").formulas = [["=SUM('Weekly Tasks'!G2:G11)/60"]];
dashboard.getRange("A5").format.numberFormat = [["0.0"]];
dashboard.getRange("D5").format.numberFormat = [["0.0"]];
dashboard.getRange("G5").format.numberFormat = [["0.0"]];
dashboard.getRange("A7:H7").merge();
dashboard.getRange("A7").values = [["Highest-impact weekly tasks"]];
styleHeader(dashboard.getRange("A7:H7"));
dashboard.getRange("A8:D8").values = [["Task", "Manual min/wk", "AIOS min/wk", "Saved min/wk"]];
styleHeader(dashboard.getRange("A8:D8"));
dashboard.getRange("A9:A18").formulas = rows.map((_, idx) => [`='Weekly Tasks'!A${idx + 2}`]);
dashboard.getRange("B9:B18").formulas = rows.map((_, idx) => [`='Weekly Tasks'!E${idx + 2}`]);
dashboard.getRange("C9:C18").formulas = rows.map((_, idx) => [`='Weekly Tasks'!F${idx + 2}`]);
dashboard.getRange("D9:D18").formulas = rows.map((_, idx) => [`='Weekly Tasks'!G${idx + 2}`]);
dashboard.getRange("A8:D18").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
dashboard.getRange("B9:D18").format.numberFormat = [["0"], ["0"], ["0"], ["0"], ["0"], ["0"], ["0"], ["0"], ["0"], ["0"]];
dashboard.getRange("F8:H8").values = [["Metric", "Result", "Meaning"]];
styleHeader(dashboard.getRange("F8:H8"));
dashboard.getRange("F9:H13").values = [
  ["Tasks covered", null, "Top repeated weekly Omar workflows"],
  ["Weekly hours saved", null, "Weekly time AIOS can remove now"],
  ["Monthly hours saved", null, "Weekly saved hours x 4.33"],
  ["Automation-ready tasks", null, "Tasks marked High automation potential"],
  ["WhatsApp-dependent tasks", null, "Needs provider restored for full autopilot"]
];
dashboard.getRange("G9").formulas = [["=COUNTA('Weekly Tasks'!A2:A11)"]];
dashboard.getRange("G10").formulas = [["=G5"]];
dashboard.getRange("G11").formulas = [["=G10*4.33"]];
dashboard.getRange("G12").formulas = [["=COUNTIF('Weekly Tasks'!H2:H11,\"High\")"]];
dashboard.getRange("G13").formulas = [["=COUNTIF('Weekly Tasks'!I2:I11,\"CRM + WhatsApp provider once restored\")"]];
dashboard.getRange("F8:H13").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
dashboard.getRange("G10:G11").format.numberFormat = [["0.0"], ["0.0"]];

const headers = [
  "Task",
  "Current Manual Process",
  "AIOS-Assisted Process",
  "Full Automation Potential",
  "Manual Minutes / Week",
  "AIOS Minutes / Week",
  "Minutes Saved / Week",
  "Automation Potential",
  "Dependency",
  "Status"
];
taskSheet.getRange("A1:J1").values = [headers];
styleHeader(taskSheet.getRange("A1:J1"));
taskSheet.getRangeByIndexes(1, 0, rows.length, 10).values = rows.map((r) => [
  r.task,
  r.current,
  r.aios,
  r.automation,
  r.occurrences * r.manualMins,
  r.occurrences * r.assistedMins,
  null,
  r.autoPotential,
  r.dependency,
  r.status
]);
taskSheet.getRange("G2:G11").formulas = rows.map((_, idx) => [`=E${idx + 2}-F${idx + 2}`]);
taskSheet.getRange("A1:J11").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
taskSheet.getRange("B2:D11").format.wrapText = true;
taskSheet.getRange("E2:G11").format.numberFormat = Array.from({ length: 10 }, () => ["0", "0", "0"]);
taskSheet.getRange("H2:H11").dataValidation = { rule: { type: "list", values: ["High", "Medium", "Low"] } };
taskSheet.getRange("J2:J11").dataValidation = { rule: { type: "list", values: ["Working", "Partially Working", "Blocked"] } };
taskSheet.freezePanes.freezeRows(1);

roadmap.getRange("A1:F1").values = [["Rank", "Task", "Next AIOS Action", "When", "Business Value", "Note"]];
styleHeader(roadmap.getRange("A1:F1"));
roadmap.getRangeByIndexes(1, 0, roadmapRows.length, 6).values = roadmapRows;
roadmap.getRange("C2:F11").format.wrapText = true;
roadmap.getRange("A1:F11").format.borders = { preset: "insideHorizontal", style: "thin", color: "#D8E0E6" };
roadmap.freezePanes.freezeRows(1);

dashboard.getRange("A:H").format.autofitColumns();
taskSheet.getRange("A:J").format.autofitColumns();
roadmap.getRange("A:F").format.autofitColumns();
dashboard.getRange("A:A").format.columnWidth = 28;
dashboard.getRange("B:D").format.columnWidth = 18;
dashboard.getRange("F:F").format.columnWidth = 26;
dashboard.getRange("G:G").format.columnWidth = 16;
dashboard.getRange("H:H").format.columnWidth = 48;
taskSheet.getRange("A:A").format.columnWidth = 24;
taskSheet.getRange("B:D").format.columnWidth = 42;
taskSheet.getRange("I:I").format.columnWidth = 34;
roadmap.getRange("C:C").format.columnWidth = 44;
roadmap.getRange("F:F").format.columnWidth = 44;
taskSheet.getRange("A1:J11").format.autofitRows();
roadmap.getRange("A1:F11").format.autofitRows();

await fs.mkdir(outputDir, { recursive: true });

const dashboardPreview = await workbook.render({ sheetName: "Dashboard", range: "A1:H18", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "dashboard_preview.png"), new Uint8Array(await dashboardPreview.arrayBuffer()));
const tasksPreview = await workbook.render({ sheetName: "Weekly Tasks", range: "A1:J11", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "weekly_tasks_preview.png"), new Uint8Array(await tasksPreview.arrayBuffer()));
const roadmapPreview = await workbook.render({ sheetName: "Automation Roadmap", range: "A1:F11", scale: 1, format: "png" });
await fs.writeFile(path.join(outputDir, "roadmap_preview.png"), new Uint8Array(await roadmapPreview.arrayBuffer()));

const dashboardInspect = await workbook.inspect({
  kind: "table",
  sheetId: "Dashboard",
  range: "A1:H18",
  include: "values,formulas",
  tableMaxRows: 18,
  tableMaxCols: 8,
  maxChars: 8000
});
console.log(dashboardInspect.ndjson);

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
