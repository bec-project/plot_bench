const $ = (id) => document.getElementById(id);
const enums = {
  view: ["waveform", "image", "both"],
  waveform_mode: ["replace", "append"],
  image_mode: ["scalar", "rgb"],
};
const fields = [
  ["view", "Plots"], ["hz", "Target rate (Hz)"], ["points", "Waveform points"],
  ["append_count", "Append count"], ["waveform_mode", "Waveform mode"],
  ["width", "Image width"], ["height", "Image height"], ["image_mode", "Image mode"],
  ["seed", "Data seed"],
];
const axes = [...fields.map(([key]) => key), "resolution"];
const timingFields = [
  ["warmup_seconds", "Warmup (seconds)"], ["measurement_seconds", "Measured (seconds)"],
  ["cooldown_seconds", "Cooldown (seconds)"], ["repetitions", "Repetitions"],
  ["order_seed", "Run order seed"],
];
let suite;
let options;
let previewTimer;
let revision = 0;
let validPlan = null;

function node(tag, text, attrs = {}) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  for (const [key, value] of Object.entries(attrs)) item.setAttribute(key, value);
  return item;
}

function button(label, action) {
  const item = node("button", label, { type: "button" });
  item.addEventListener("click", action);
  return item;
}

function error(message) {
  $("error").hidden = !message;
  $("error").textContent = message;
}

function numericValues(input, values) {
  const unsafe = values.some((value) => Math.abs(Number(value)) > Number.MAX_SAFE_INTEGER);
  input.setCustomValidity(unsafe
    ? `The editor supports numbers only between ${-Number.MAX_SAFE_INTEGER} and ${Number.MAX_SAFE_INTEGER} to avoid rounding. Use the CLI for larger integer seeds.`
    : "");
  return values.map((value) => {
    const number = Number(value);
    return value.trim() !== "" && Number.isFinite(number) && Math.abs(number) <= Number.MAX_SAFE_INTEGER
      ? number : value;
  });
}

function changed() {
  revision += 1;
  validPlan = null;
  $("export").disabled = true;
  $("export-status").textContent = "";
  $("raw").value = JSON.stringify(suite, null, 2);
  $("summary").textContent = "Validating matrix…";
  $("command").textContent = "";
  $("jobs").replaceChildren();
  $("preview-limit").textContent = "";
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => preview(revision), 250);
}

async function requestPreview(candidate, raw = false) {
  const response = await fetch("/api/preview", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ [raw ? "suite_json" : "suite"]: candidate, kind: $("kind").value }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || "The matrix could not be validated.");
  return result;
}

async function preview(expectedRevision) {
  try {
    const invalid = [...document.querySelectorAll("input")].find((input) => input.validity.customError);
    if (invalid) throw new Error(invalid.validationMessage);
    const plan = await requestPreview(suite);
    if (expectedRevision !== revision) return;
    validPlan = plan;
    error("");
    $("export").disabled = false;
    $("summary").textContent = `${plan.case_count.toLocaleString()} workloads · ${plan.run_count.toLocaleString()} runs · at least ${(plan.estimate.minimum_seconds / 60).toFixed(1)} minutes`;
    $("command").textContent = `./scripts/plotbench ${plan.kind} --suite my-suite.json --dry-run`;
    const rows = plan.jobs.slice(0, 250).map((job) => {
      const row = node("tr");
      for (const value of [job.run_id, job.scenario, job.frontend || "Receiver", job.backend,
        job.mode, job.repetition, `${job.config.hz} Hz`]) row.append(node("td", String(value)));
      return row;
    });
    $("jobs").replaceChildren(...rows);
    $("preview-limit").textContent = plan.jobs.length > 250
      ? `Showing the first 250 runs in the actual shuffled order. Use --dry-run --json for the complete ${plan.run_count.toLocaleString()}-run preview.`
      : "All planned runs are shown in the actual shuffled order.";
  } catch (failure) {
    if (expectedRevision !== revision) return;
    error(failure.message);
    $("summary").textContent = "Fix the fields above to preview or export this suite.";
  }
}

function configFields(config, base = false) {
  const container = node("div", undefined, { class: "fields" });
  const configOptions = base ? [...fields, ["resolution", "Square resolution"]] : fields;
  for (const [key, labelText] of configOptions) {
    const label = node("label", labelText);
    let input;
    if (enums[key]) {
      input = node("select", undefined, { "aria-label": labelText });
      input.append(node("option", `Default (${options.config[key]})`, { value: "" }));
      for (const value of enums[key]) input.append(node("option", value, { value }));
    } else {
      input = node("input", undefined, {
        type: "number", step: key === "hz" ? "any" : "1",
        placeholder: String(options.config[key] ?? "Optional"), "aria-label": labelText,
      });
    }
    input.value = config[key] ?? "";
    input.addEventListener("input", () => {
      input.setCustomValidity("");
      if (input.validity.badInput) config[key] = input.value;
      else if (input.value === "") delete config[key];
      else config[key] = enums[key] ? input.value : numericValues(input, [input.value])[0];
      changed();
    });
    label.append(input);
    container.append(label);
  }
  return container;
}

function cardHeader(item, collection, index, labelText) {
  const heading = node("div", undefined, { class: "card-heading" });
  const label = node("label", labelText);
  const input = node("input", undefined, { type: "text", "aria-label": labelText });
  input.value = item.name;
  input.addEventListener("input", () => { item.name = input.value; changed(); });
  label.append(input);
  heading.append(label, button("Remove", () => {
    collection.splice(index, 1);
    renderWorkloads();
    changed();
  }));
  return heading;
}

function renderAxes(group, container) {
  container.replaceChildren();
  for (const [key, values] of Object.entries(group.matrix)) {
    const row = node("div", undefined, { class: "axis-row" });
    const keyLabel = node("label", "Vary field");
    const select = node("select", undefined, { "aria-label": "Matrix field" });
    for (const axis of axes) {
      const option = node("option", axis, { value: axis });
      option.disabled = axis !== key && Object.hasOwn(group.matrix, axis);
      select.append(option);
    }
    // An imported generation axis remains editable through the advanced JSON view.
    if (!axes.includes(key)) select.append(node("option", key, { value: key }));
    select.value = key;
    select.addEventListener("change", () => {
      group.matrix = Object.fromEntries(Object.entries(group.matrix).map(([axis, entries]) =>
        [axis === key ? select.value : axis, entries]));
      renderAxes(group, container);
      changed();
    });
    keyLabel.append(select);
    const valuesLabel = node("label", "Values (comma separated)");
    const input = node("input", undefined, { type: "text", "aria-label": `Matrix ${key} values` });
    input.value = values.join(", ");
    input.addEventListener("input", () => {
      input.setCustomValidity("");
      const entries = input.value.trim() === "" ? [] : input.value.split(",").map((value) => value.trim());
      group.matrix[key] = enums[key] ? entries : numericValues(input, entries);
      changed();
    });
    valuesLabel.append(input);
    row.append(keyLabel, valuesLabel, button("Remove axis", () => {
      delete group.matrix[key]; renderAxes(group, container); changed();
    }));
    container.append(row);
  }
  const nextAxis = axes.find((axis) => !Object.hasOwn(group.matrix, axis));
  const add = button("Add matrix axis", () => {
    group.matrix[nextAxis] = [options.config[nextAxis] ?? 512];
    renderAxes(group, container);
    changed();
  });
  add.disabled = !nextAxis;
  container.append(add);
}

function renderWorkloads() {
  $("cases").replaceChildren();
  (suite.cases || []).forEach((item, index) => {
    const card = node("article", undefined, { class: "card" });
    card.append(cardHeader(item, suite.cases, index, "Workload name"), configFields(item.config));
    $("cases").append(card);
  });
  $("groups").replaceChildren();
  (suite.case_groups || []).forEach((group, index) => {
    const card = node("article", undefined, { class: "card" });
    card.append(cardHeader(group, suite.case_groups, index, "Group name"));
    const base = node("details");
    const baseConfig = group.base || (group.base = {});
    base.append(node("summary", "Base workload fields"), configFields(baseConfig, true));
    const matrix = node("div", undefined, { class: "axes" });
    renderAxes(group, matrix);
    card.append(base, matrix);
    $("groups").append(card);
  });
}

function renderSetup() {
  for (const key of ["name", "display_context"]) $(key).value = suite[key] ?? "";
  $("selections").replaceChildren();
  const probe = $("kind").value === "probe";
  for (const [key, labelText, defaults] of [
    ["frontends", "Frontends", options.frontends], ["backends", "Source backends", [options.default_backend]],
    ["modes", "Delivery modes", options.modes],
  ]) {
    const fieldset = node("fieldset");
    fieldset.append(node("legend", labelText));
    fieldset.disabled = probe && key !== "backends";
    for (const value of options[key]) {
      const label = node("label");
      const input = node("input", undefined, { type: "checkbox", value });
      const selectedValues = suite[key] ?? defaults;
      input.checked = Array.isArray(selectedValues) && selectedValues.includes(value);
      input.addEventListener("change", () => {
        const selected = new Set(suite[key] ?? defaults);
        if (input.checked) selected.add(value); else selected.delete(value);
        suite[key] = [...selected];
        changed();
      });
      label.append(input, document.createTextNode(value));
      fieldset.append(label);
    }
    $("selections").append(fieldset);
  }
  $("timings").replaceChildren();
  const defaults = { warmup_seconds: probe ? 2 : 5, measurement_seconds: probe ? 10 : 30,
    cooldown_seconds: probe ? 0.5 : 1, repetitions: 3, order_seed: 42 };
  for (const [key, labelText] of timingFields) {
    const label = node("label", labelText);
    const input = node("input", undefined, { type: "number", placeholder: String(defaults[key]),
      step: key.endsWith("seconds") ? "any" : "1", "aria-label": labelText });
    input.value = suite[key] ?? "";
    input.addEventListener("input", () => {
      input.setCustomValidity("");
      if (input.validity.badInput) suite[key] = input.value;
      else if (input.value === "") delete suite[key]; else suite[key] = numericValues(input, [input.value])[0];
      changed();
    });
    label.append(input);
    $("timings").append(label);
  }
}

async function replaceSuite(text) {
  revision += 1;
  const expectedRevision = revision;
  clearTimeout(previewTimer);
  validPlan = null;
  $("export").disabled = true;
  error("");
  $("summary").textContent = "Validating imported JSON…";
  $("export-status").textContent = "";
  $("command").textContent = "";
  $("jobs").replaceChildren();
  $("preview-limit").textContent = "";
  try {
    // Python validates the original number tokens before JavaScript can round them.
    const plan = await requestPreview(text, true);
    if (expectedRevision !== revision) return;
    suite = plan.suite;
    renderSetup();
    renderWorkloads();
    changed();
  } catch (failure) {
    if (expectedRevision !== revision) return;
    error(failure.message);
    $("summary").textContent = "JSON was not applied. Fix it in the advanced editor and apply again.";
    $("advanced").open = true;
    $("raw").value = text;
  }
}

function uniqueName(prefix) {
  const names = new Set([...(suite.cases || []), ...(suite.case_groups || [])].map((item) => item.name));
  let number = 1;
  while (names.has(`${prefix}-${number}`)) number += 1;
  return `${prefix}-${number}`;
}

for (const key of ["name", "display_context"]) $(key).addEventListener("input", () => {
  if ($(key).value === "") delete suite[key]; else suite[key] = $(key).value;
  changed();
});
$("kind").addEventListener("change", () => { renderSetup(); changed(); });
$("add-case").addEventListener("click", () => {
  (suite.cases ||= []).push({ name: uniqueName("workload"), config: {} });
  renderWorkloads(); changed();
});
$("add-group").addEventListener("click", () => {
  (suite.case_groups ||= []).push({ name: uniqueName("group"), base: { view: "waveform" }, matrix: { hz: [30, 60] } });
  renderWorkloads(); changed();
});
$("apply-json").addEventListener("click", () => replaceSuite($("raw").value));
$("raw").addEventListener("input", () => {
  revision += 1;
  clearTimeout(previewTimer);
  validPlan = null;
  $("export").disabled = true;
  $("summary").textContent = "JSON draft changed. Apply JSON to validate and update the form.";
  $("command").textContent = "";
  $("jobs").replaceChildren();
  $("preview-limit").textContent = "";
});
$("import").addEventListener("change", async (event) => {
  const file = event.target.files[0];
  if (!file) return;
  if (file.size > 1024 * 1024) { error("Suite JSON must be at most 1 MiB."); return; }
  await replaceSuite(await file.text());
  event.target.value = "";
});
$("export").addEventListener("click", () => {
  if (!validPlan) return;
  const blob = new Blob([JSON.stringify(validPlan.suite, null, 2) + "\n"], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = node("a", undefined, { href: url, download: "my-suite.json" });
  document.body.append(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
  $("export-status").textContent = "Suite exported. Preview its CLI command before measuring.";
});

try {
  const response = await fetch("/api/initial");
  if (!response.ok) throw new Error("The matrix editor could not load its initial suite.");
  options = await response.json();
  suite = options.suite;
  renderSetup(); renderWorkloads(); changed();
} catch (failure) {
  error(`${failure.message} Restart the matrix editor and reload this page.`);
}
