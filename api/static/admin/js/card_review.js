document.addEventListener("DOMContentLoaded", function () {
  const panel = document.getElementById("card-review");
  if (!panel) {
    return;
  }

  const form = document.getElementById("word_form");
  const analyzeButton = panel.querySelector(".card-review__analyze");
  const statusEl = panel.querySelector(".card-review__status");
  const resultEl = panel.querySelector(".card-review__result");
  const analyzeUrl = panel.dataset.analyzeUrl;
  const configured = panel.dataset.configured === "true";
  const SAVE_FIRST = "Save changes first.";
  const NOT_CONFIGURED = "Analysis isn't configured.";
  const FIELD_LABELS = {
    chinese: "Traditional Chinese",
    simplified: "Simplified Chinese",
    pinyin: "Pinyin",
    english_basic: "English",
    hsk_level: "HSK level",
    example_sentence_traditional: "Example (traditional)",
    example_sentence_simplified: "Example (simplified)",
    example_sentence_pinyin: "Example (pinyin)",
    example_sentence_english: "Example (English)",
  };
  const DIRECTION_LABELS = {
    pinyin_to_en: "Pinyin to English",
    en_to_zh: "English to Chinese",
    zh_to_en: "Chinese to English",
  };
  const VERDICT_LABELS = {
    no_clear_issue: "No clear issue",
    issues_found: "Issues found",
    needs_human_review: "Needs human review",
  };

  let dirty = false;
  let initialSnapshot = "";

  function snapshotForm() {
    if (!form) {
      return "";
    }
    const data = new FormData(form);
    const parts = [];
    data.forEach(function (value, key) {
      if (key === "csrfmiddlewaretoken" || key.charAt(0) === "_") {
        return;
      }
      parts.push(key + "=" + value);
    });
    return parts.join("\n");
  }

  function setStatus(message, isError) {
    statusEl.hidden = !message;
    statusEl.textContent = message || "";
    statusEl.classList.toggle("is-error", Boolean(isError));
  }

  function csrfToken() {
    const input = form && form.querySelector("[name=csrfmiddlewaretoken]");
    return input ? input.value : "";
  }

  function updateAnalyzeEnabled() {
    if (!configured) {
      analyzeButton.disabled = true;
      setStatus(NOT_CONFIGURED, false);
      return;
    }
    if (dirty) {
      analyzeButton.disabled = true;
      setStatus(SAVE_FIRST, false);
      return;
    }
    analyzeButton.disabled = false;
    if (statusEl.textContent === SAVE_FIRST || statusEl.textContent === NOT_CONFIGURED) {
      setStatus("", false);
    }
  }

  function clearResult() {
    resultEl.hidden = true;
    resultEl.replaceChildren();
  }

  function text(tag, value, className) {
    const el = document.createElement(tag);
    if (className) {
      el.className = className;
    }
    el.textContent = value;
    return el;
  }

  function renderFindings(findings) {
    const heading = text("h3", "Findings");
    const list = document.createElement("ul");
    list.className = "card-review__findings";
    if (!findings.length) {
      const item = document.createElement("li");
      item.className = "card-review__finding";
      item.textContent = "None.";
      list.appendChild(item);
    } else {
      findings.forEach(function (finding) {
        const item = document.createElement("li");
        item.className = "card-review__finding";
        const directions = (finding.practice_directions || [])
          .map(function (direction) {
            return DIRECTION_LABELS[direction] || direction;
          })
          .join(", ");
        const body = finding.aspect + ": " + finding.explanation;
        item.textContent = directions ? body + " (" + directions + ")" : body;
        list.appendChild(item);
      });
    }
    resultEl.appendChild(heading);
    resultEl.appendChild(list);
  }

  function renderSuggestions(suggestions) {
    const heading = text("h3", "Suggestions");
    const list = document.createElement("ul");
    list.className = "card-review__suggestions";
    Object.keys(FIELD_LABELS).forEach(function (field) {
      const item = document.createElement("li");
      item.className = "card-review__suggestion";
      const label = text("strong", FIELD_LABELS[field]);
      const valueEl = document.createElement("span");
      valueEl.className = "card-review__suggestion-value";
      const value = suggestions[field];
      item.appendChild(label);
      if (value === null || value === undefined) {
        valueEl.textContent = "Keep current value";
        item.appendChild(valueEl);
      } else {
        valueEl.textContent = String(value);
        item.appendChild(valueEl);
        const copy = document.createElement("button");
        copy.type = "button";
        copy.className = "card-review__copy";
        copy.textContent = "Copy";
        copy.addEventListener("click", function () {
          if (!navigator.clipboard) {
            return;
          }
          navigator.clipboard.writeText(String(value)).then(function () {
            copy.textContent = "Copied";
            window.setTimeout(function () {
              copy.textContent = "Copy";
            }, 1200);
          });
        });
        item.appendChild(copy);
      }
      list.appendChild(item);
    });
    resultEl.appendChild(heading);
    resultEl.appendChild(list);
  }

  function renderResult(payload) {
    resultEl.replaceChildren();
    const verdict = VERDICT_LABELS[payload.verdict] || payload.verdict || "";
    resultEl.appendChild(text("h3", "Verdict"));
    resultEl.appendChild(text("p", verdict));
    renderFindings(payload.findings || []);
    renderSuggestions(payload.suggestions || {});
    resultEl.hidden = false;
  }

  function renderFailure(message) {
    resultEl.replaceChildren();
    resultEl.appendChild(text("p", message, "card-review__status is-error"));
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "card-review__retry";
    retry.textContent = "Try again";
    retry.addEventListener("click", runAnalyze);
    resultEl.appendChild(retry);
    resultEl.hidden = false;
  }

  function runAnalyze() {
    if (!configured || dirty) {
      updateAnalyzeEnabled();
      return;
    }
    analyzeButton.disabled = true;
    setStatus("Analyzing…", false);
    clearResult();
    fetch(analyzeUrl, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "X-CSRFToken": csrfToken(),
      },
      credentials: "same-origin",
    })
      .then(function (response) {
        return response.json().then(function (body) {
          return { ok: response.ok, body: body };
        });
      })
      .then(function (result) {
        if (!result.ok) {
          renderFailure(result.body.detail || "Analysis failed.");
          setStatus("", false);
          updateAnalyzeEnabled();
          return;
        }
        renderResult(result.body);
        setStatus("", false);
        updateAnalyzeEnabled();
      })
      .catch(function () {
        renderFailure("Analysis failed.");
        setStatus("", false);
        updateAnalyzeEnabled();
      });
  }

  if (form) {
    initialSnapshot = snapshotForm();
    form.addEventListener("input", function () {
      dirty = snapshotForm() !== initialSnapshot;
      updateAnalyzeEnabled();
    });
    form.addEventListener("change", function () {
      dirty = snapshotForm() !== initialSnapshot;
      updateAnalyzeEnabled();
    });
  }

  analyzeButton.addEventListener("click", runAnalyze);
  updateAnalyzeEnabled();
});
