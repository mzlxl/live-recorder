// 选项面板跟随触发按钮，弹框内的面板也留在同一模态层。
const choices = new Map();
const choiceList = document.createElement("div");
choiceList.id = "choice-list";
choiceList.className = "choice-list";
choiceList.setAttribute("role", "listbox");
let choiceOwner = null;
let currentOption = 0;
let searchPrefix = "",
  lastTyped = 0;

function setChoices(button, entries, value) {
  const items = entries.map(([key, label]) => ({ value: String(key), label: String(label) }));
  const selected = items.find((item) => item.value === String(value)) || items[0];
  const previousValue = button.value;
  button.value = selected?.value ?? "";
  button.textContent = selected?.label ?? "";
  button.setAttribute("role", "combobox");
  button.setAttribute("aria-haspopup", "listbox");
  button.setAttribute("aria-expanded", String(choiceOwner === button));
  const previous = choices.get(button);
  choices.set(button, items);
  if (
    choiceOwner === button &&
    (previousValue !== button.value || JSON.stringify(items) !== JSON.stringify(previous))
  )
    drawOptions();
}

function positionChoice() {
  if (!choiceOwner) return;
  const rect = choiceOwner.getBoundingClientRect();
  const modal = choiceOwner.closest("dialog");
  if (!rect.width || rect.bottom < 0 || rect.top >= innerHeight || (modal && !modal.open)) {
    closeChoice();
    return;
  }
  const below = innerHeight - rect.bottom - 10;
  const above = rect.top - 10;
  const up = below < Math.min(choiceList.scrollHeight + 2, 256) && above > below;
  const width = Math.min(
    innerWidth - 16,
    Math.max(choiceOwner.closest(".clock-field") ? 210 : 150, rect.width),
  );
  Object.assign(choiceList.style, {
    width: width + "px",
    left: Math.max(8, Math.min(rect.left, innerWidth - width - 8)) + "px",
    maxHeight: Math.min(256, Math.max(40, up ? above : below)) + "px",
    top: up ? "auto" : rect.bottom + 5 + "px",
    bottom: up ? innerHeight - rect.top + 5 + "px" : "auto",
  });
}

function markOption(index) {
  const options = choiceList.children;
  if (!options.length) return;
  options[currentOption]?.classList.remove("pointed");
  currentOption = Math.max(0, Math.min(index, options.length - 1));
  const active = options[currentOption];
  active.classList.add("pointed");
  choiceOwner.setAttribute("aria-activedescendant", active.id);
  const y = active.offsetTop;
  if (y < choiceList.scrollTop) choiceList.scrollTop = y - 4;
  else if (y + active.offsetHeight > choiceList.scrollTop + choiceList.clientHeight)
    choiceList.scrollTop = y + active.offsetHeight - choiceList.clientHeight + 4;
}

function drawOptions() {
  const items = choices.get(choiceOwner);
  choiceList.replaceChildren(
    ...items.map((item, index) => {
      const el = document.createElement("div");
      el.setAttribute("role", "option");
      el.setAttribute("aria-selected", String(item.value === choiceOwner.value));
      el.id = "choice-option-" + index;
      el.dataset.index = index;
      el.textContent =
        choiceList.classList.contains("clock-options") && !item.value ? "不限" : item.label;
      return el;
    }),
  );
  positionChoice();
  if (choiceOwner) markOption(items.findIndex((item) => item.value === choiceOwner.value));
}

function openChoice(button) {
  closeChoice();
  if (!choices.get(button)?.length) return;
  choiceOwner = button;
  choiceList.classList.toggle("clock-options", Boolean(button.closest(".clock-field")));
  if (choiceList.classList.contains("clock-options")) {
    const unit = button.getAttribute("aria-label");
    choiceList.dataset.heading = unit + (unit.endsWith("小时") ? " · 00–23" : " · 00–59");
  }
  searchPrefix = "";
  button.focus({ preventScroll: true });
  (button.closest("dialog") || document.body).append(choiceList);
  choiceList.setAttribute(
    "aria-label",
    button.getAttribute("aria-label") || button.labels?.[0]?.textContent || "选项",
  );
  button.setAttribute("aria-controls", choiceList.id);
  button.setAttribute("aria-expanded", "true");
  drawOptions();
}

function closeChoice() {
  if (!choiceOwner) return;
  choiceOwner.setAttribute("aria-expanded", "false");
  choiceOwner.removeAttribute("aria-controls");
  choiceOwner.removeAttribute("aria-activedescendant");
  choiceList.remove();
  choiceOwner = null;
}

function choose(index) {
  const button = choiceOwner;
  const item = choices.get(button)[index];
  closeChoice();
  button.value = item.value;
  button.textContent = item.label;
  button.focus({ preventScroll: true });
  button.dispatchEvent(new Event("change", { bubbles: true }));
}

// 点击选项时让焦点留在组合框，触屏仍然可以滚动列表。
choiceList.addEventListener("mousedown", (event) => {
  if (event.target.closest("[role=option]")) event.preventDefault();
});
document.addEventListener("click", (event) => {
  const option = event.target.closest("#choice-list [role=option]");
  if (option && choiceOwner) return choose(Number(option.dataset.index));
  const button = event.target.closest(".choice");
  if (button && button !== choiceOwner) openChoice(button);
  else closeChoice();
});
document.addEventListener("pointerdown", (event) => {
  if (choiceOwner && !choiceList.contains(event.target) && !choiceOwner.contains(event.target))
    closeChoice();
});
document.addEventListener("focusin", (event) => {
  if (choiceOwner && event.target !== choiceOwner && !choiceList.contains(event.target))
    closeChoice();
});
document.addEventListener("close", closeChoice, true);
document.addEventListener(
  "scroll",
  (event) => {
    if (choiceOwner && event.target !== choiceList) positionChoice();
  },
  true,
);
window.addEventListener("resize", positionChoice);
document.addEventListener("keydown", (event) => {
  const button = event.target.closest(".choice");
  if (!button) return;
  const key = event.key;
  if (key === "Tab") return closeChoice();
  if (key === "Escape" && choiceOwner) {
    event.preventDefault();
    closeChoice();
    return;
  }
  if (choiceOwner && (key === "Enter" || key === " ")) {
    event.preventDefault();
    return choose(currentOption);
  }
  const grid = Boolean(button.closest(".clock-field"));
  const arrows = grid
    ? { ArrowLeft: -1, ArrowRight: 1, ArrowDown: 4, ArrowUp: -4 }
    : { ArrowDown: 1, ArrowUp: -1 };
  const step = { ...arrows, Home: -Infinity, End: Infinity }[key];
  const typed =
    key.length === 1 && /\S/.test(key) && !event.ctrlKey && !event.metaKey && !event.altKey;
  if (step === undefined && !typed) return;
  event.preventDefault();
  if (!choiceOwner) openChoice(button);
  if (!choiceOwner) return;
  if (!typed) return markOption(currentOption + step);
  searchPrefix = (Date.now() - lastTyped > 800 ? "" : searchPrefix) + key.toLowerCase();
  lastTyped = Date.now();
  const ix = choices
    .get(button)
    .findIndex(
      (item) =>
        item.label.toLowerCase().startsWith(searchPrefix) || item.value.startsWith(searchPrefix),
    );
  if (ix >= 0) markOption(ix);
});
