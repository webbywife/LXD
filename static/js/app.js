/**
 * MATATAG AI Lesson Plan Generator - Frontend Logic
 */

document.addEventListener("DOMContentLoaded", function () {
    // Element references
    const subjectSelect = document.getElementById("subject-select");
    const gradeSelect = document.getElementById("grade-select");
    const quarterSelect = document.getElementById("quarter-select");
    const btnLoadComps = document.getElementById("btn-load-competencies");
    const compsContainer = document.getElementById("competencies-container");
    const compsList = document.getElementById("competencies-list");
    const compCount = document.getElementById("comp-count");
    const btnSelectAll = document.getElementById("btn-select-all");
    const btnDeselectAll = document.getElementById("btn-deselect-all");
    const btnGenerate = document.getElementById("btn-generate");
    const useAiCheckbox = document.getElementById("use-ai");
    const aiOptions = document.getElementById("ai-options");
    const outputPlaceholder = document.getElementById("output-placeholder");
    const outputLoading = document.getElementById("output-loading");
    const outputContent = document.getElementById("output-content");
    const btnCopy = document.getElementById("btn-copy");
    const btnPrint = document.getElementById("btn-print");
    const btnDownload = document.getElementById("btn-download");

    let selectedCompetencies = new Set();
    let curriculumContext = null;

    // === Subject Change ===
    subjectSelect.addEventListener("change", function () {
        const subjectId = this.value;
        gradeSelect.innerHTML = '<option value="">-- Select Grade --</option>';
        gradeSelect.disabled = true;
        quarterSelect.innerHTML = '<option value="">-- Select Quarter --</option>';
        quarterSelect.disabled = true;
        btnLoadComps.disabled = true;
        compsContainer.style.display = "none";
        selectedCompetencies.clear();
        updateGenerateButton();

        if (!subjectId) return;

        fetch(`/api/grades/${subjectId}`)
            .then((r) => r.json())
            .then((grades) => {
                grades.forEach((g) => {
                    const opt = document.createElement("option");
                    opt.value = g;
                    opt.textContent = g.startsWith("Grade") || g.startsWith("K") ? g : `Grade ${g}`;
                    gradeSelect.appendChild(opt);
                });
                gradeSelect.disabled = false;
            });

        // Load curriculum context (skills, approaches, etc.)
        fetch(`/api/curriculum-context/${subjectId}`)
            .then((r) => r.json())
            .then((ctx) => {
                curriculumContext = ctx;
                populateSkillsCheckboxes(ctx.skills);
            });
    });

    // === Grade Change ===
    gradeSelect.addEventListener("change", function () {
        const subjectId = subjectSelect.value;
        const grade = this.value;
        quarterSelect.innerHTML = '<option value="">-- Select Quarter --</option>';
        quarterSelect.disabled = true;
        btnLoadComps.disabled = true;

        if (!grade) return;

        fetch(`/api/quarters/${subjectId}/${grade}`)
            .then((r) => r.json())
            .then((quarters) => {
                if (quarters.length === 0) {
                    // No quarters, allow loading all competencies for this grade
                    btnLoadComps.disabled = false;
                    return;
                }
                quarters.forEach((q) => {
                    const opt = document.createElement("option");
                    opt.value = q;
                    opt.textContent = q;
                    quarterSelect.appendChild(opt);
                });
                quarterSelect.disabled = false;
            });
    });

    // === Quarter Change ===
    quarterSelect.addEventListener("change", function () {
        btnLoadComps.disabled = !this.value;
    });

    // === Load Competencies ===
    btnLoadComps.addEventListener("click", function () {
        const subjectId = subjectSelect.value;
        const grade = gradeSelect.value;
        const quarter = quarterSelect.value;

        if (!subjectId || !grade) return;

        let url = `/api/competencies/${subjectId}?grade=${encodeURIComponent(grade)}`;
        if (quarter) url += `&quarter=${encodeURIComponent(quarter)}`;

        this.disabled = true;
        this.textContent = "Loading...";

        fetch(url)
            .then((r) => r.json())
            .then((comps) => {
                renderCompetencies(comps);
                compsContainer.style.display = "block";
                btnLoadComps.disabled = false;
                btnLoadComps.textContent = "Load Learning Competencies";
            })
            .catch(() => {
                btnLoadComps.disabled = false;
                btnLoadComps.textContent = "Load Learning Competencies";
            });
    });

    // === Render Competencies ===
    function renderCompetencies(comps) {
        compsList.innerHTML = "";
        selectedCompetencies.clear();

        if (comps.length === 0) {
            compsList.innerHTML = '<p class="help-text" style="padding:12px;">No competencies found for this selection.</p>';
            compCount.textContent = "0";
            updateGenerateButton();
            return;
        }

        compCount.textContent = comps.length;

        comps.forEach((c) => {
            const div = document.createElement("div");
            div.className = "comp-item";
            div.dataset.id = c.id;

            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = c.id;

            const info = document.createElement("div");
            info.className = "comp-info";

            const idSpan = document.createElement("span");
            idSpan.className = "comp-id";
            idSpan.textContent = c.lc_id || `LC-${c.id}`;

            const textSpan = document.createElement("span");
            textSpan.className = "comp-text";
            textSpan.textContent = c.learning_competency;

            const metaSpan = document.createElement("span");
            metaSpan.className = "comp-meta";
            const metaParts = [];
            if (c.domain) metaParts.push(c.domain);
            if (c.blooms_level) metaParts.push(`Bloom's: ${c.blooms_level}`);
            if (c.competency_type) metaParts.push(c.competency_type);
            metaSpan.textContent = metaParts.join(" | ");

            info.appendChild(idSpan);
            info.appendChild(textSpan);
            if (metaParts.length > 0) info.appendChild(metaSpan);

            div.appendChild(cb);
            div.appendChild(info);

            // Click handler
            div.addEventListener("click", function (e) {
                if (e.target !== cb) cb.checked = !cb.checked;
                if (cb.checked) {
                    selectedCompetencies.add(c.id);
                    div.classList.add("selected");
                } else {
                    selectedCompetencies.delete(c.id);
                    div.classList.remove("selected");
                }
                updateGenerateButton();
            });

            compsList.appendChild(div);
        });

        updateGenerateButton();
    }

    // === Select / Deselect All ===
    btnSelectAll.addEventListener("click", function () {
        compsList.querySelectorAll(".comp-item").forEach((item) => {
            const cb = item.querySelector("input[type='checkbox']");
            cb.checked = true;
            item.classList.add("selected");
            selectedCompetencies.add(parseInt(item.dataset.id));
        });
        updateGenerateButton();
    });

    btnDeselectAll.addEventListener("click", function () {
        compsList.querySelectorAll(".comp-item").forEach((item) => {
            const cb = item.querySelector("input[type='checkbox']");
            cb.checked = false;
            item.classList.remove("selected");
        });
        selectedCompetencies.clear();
        updateGenerateButton();
    });

    // === Update Generate Button State ===
    function updateGenerateButton() {
        btnGenerate.disabled = selectedCompetencies.size === 0;
    }

    // === Populate 21st Century Skills Checkboxes ===
    function populateSkillsCheckboxes(skills) {
        const container = document.getElementById("skills-checkboxes");
        container.innerHTML = "";

        if (!skills || skills.length === 0) {
            container.innerHTML = '<p class="help-text">No skills data available for this subject.</p>';
            return;
        }

        skills.forEach((s) => {
            const label = document.createElement("label");
            label.className = "checkbox-label";
            const cb = document.createElement("input");
            cb.type = "checkbox";
            cb.value = s.skill_name;
            cb.className = "skill-checkbox";
            label.appendChild(cb);
            label.appendChild(document.createTextNode(" " + s.skill_name));
            container.appendChild(label);
        });
    }

    // === Template Section Expand/Collapse ===
    document.querySelectorAll(".btn-expand").forEach((btn) => {
        btn.addEventListener("click", function (e) {
            e.stopPropagation();
            const section = this.dataset.section;
            const options = document.getElementById(`options-${section}`);
            if (options.style.display === "none") {
                options.style.display = "block";
                this.classList.add("expanded");
            } else {
                options.style.display = "none";
                this.classList.remove("expanded");
            }
        });
    });

    // Make section headers clickable too
    document.querySelectorAll(".section-header").forEach((header) => {
        header.addEventListener("click", function (e) {
            if (e.target.classList.contains("toggle-slider") ||
                e.target.type === "checkbox" ||
                e.target.closest(".toggle-switch")) return;
            const btn = this.querySelector(".btn-expand");
            if (btn) btn.click();
        });
    });

    // === AI Toggle ===
    useAiCheckbox.addEventListener("change", function () {
        aiOptions.style.display = this.checked ? "block" : "none";
    });

    // === Build Template Config ===
    function buildTemplateConfig() {
        const config = {};

        // Title Info
        config.title_info = {
            enabled: document.querySelector('.section-toggle[data-section="title_info"]').checked,
            customizable_fields: {
                custom_title: document.getElementById("custom-title")?.value || "",
                time_allotment: document.getElementById("time-allotment")?.value || "60 minutes",
            },
        };

        // 21st Century Skills
        const focusSkills = [];
        document.querySelectorAll(".skill-checkbox:checked").forEach((cb) => {
            focusSkills.push(cb.value);
        });
        config.twenty_first_century_skills = {
            enabled: document.querySelector('.section-toggle[data-section="twenty_first_century_skills"]').checked,
            customizable_fields: { focus_skills: focusSkills },
        };

        // Learning Objectives
        const customObjText = document.getElementById("custom-objectives")?.value || "";
        const customObjectives = customObjText.split("\n").map((s) => s.trim()).filter((s) => s);
        config.learning_objectives = {
            enabled: document.querySelector('.section-toggle[data-section="learning_objectives"]').checked,
            customizable_fields: {
                num_objectives: parseInt(document.getElementById("num-objectives")?.value || "3"),
                custom_objectives: customObjectives,
            },
        };

        // Materials
        const customMatsText = document.getElementById("custom-materials")?.value || "";
        const customMaterials = customMatsText.split("\n").map((s) => s.trim()).filter((s) => s);
        config.materials_technology = {
            enabled: document.querySelector('.section-toggle[data-section="materials_technology"]').checked,
            customizable_fields: {
                include_digital_tools: document.getElementById("include-digital")?.checked !== false,
                include_traditional: document.getElementById("include-traditional")?.checked !== false,
                custom_materials: customMaterials,
            },
        };

        // Prior Knowledge
        const customPrereqText = document.getElementById("custom-prerequisites")?.value || "";
        const customPrereqs = customPrereqText.split("\n").map((s) => s.trim()).filter((s) => s);
        config.prior_knowledge = {
            enabled: document.querySelector('.section-toggle[data-section="prior_knowledge"]').checked,
            customizable_fields: { custom_prerequisites: customPrereqs },
        };

        // Lesson Procedure
        config.lesson_procedure = {
            enabled: document.querySelector('.section-toggle[data-section="lesson_procedure"]').checked,
            customizable_fields: {
                model: document.getElementById("procedure-model")?.value || "5e",
                include_timing: document.getElementById("include-timing")?.checked !== false,
                custom_activities: {},
            },
        };

        // Differentiation
        const customDiffText = document.getElementById("custom-diff-strategies")?.value || "";
        const customDiff = customDiffText.split("\n").map((s) => s.trim()).filter((s) => s);
        config.differentiation = {
            enabled: document.querySelector('.section-toggle[data-section="differentiation"]').checked,
            customizable_fields: {
                include_struggling: document.getElementById("diff-struggling")?.checked !== false,
                include_advanced: document.getElementById("diff-advanced")?.checked !== false,
                include_ell: document.getElementById("diff-ell")?.checked !== false,
                custom_strategies: customDiff,
            },
        };

        // Assessment
        const customAssessText = document.getElementById("custom-assessments")?.value || "";
        const customAssess = customAssessText.split("\n").map((s) => s.trim()).filter((s) => s);
        config.assessment = {
            enabled: document.querySelector('.section-toggle[data-section="assessment"]').checked,
            customizable_fields: {
                include_formative: document.getElementById("assess-formative")?.checked !== false,
                include_summative: document.getElementById("assess-summative")?.checked !== false,
                custom_assessments: customAssess,
            },
        };

        // Reflection
        const customRefText = document.getElementById("custom-reflection")?.value || "";
        const customRef = customRefText.split("\n").map((s) => s.trim()).filter((s) => s);
        config.reflection = {
            enabled: document.querySelector('.section-toggle[data-section="reflection"]').checked,
            customizable_fields: {
                num_prompts: parseInt(document.getElementById("num-reflections")?.value || "3"),
                custom_prompts: customRef,
            },
        };

        return config;
    }

    // === Generate Lesson Plan ===
    btnGenerate.addEventListener("click", function () {
        if (selectedCompetencies.size === 0) return;

        const subjectId = subjectSelect.value;
        const templateConfig = buildTemplateConfig();
        const useAi = useAiCheckbox.checked;
        const apiKey = document.getElementById("api-key")?.value || "";
        const aiProvider = document.getElementById("ai-provider")?.value || "anthropic";

        // Show loading
        outputPlaceholder.style.display = "none";
        outputContent.style.display = "none";
        outputLoading.style.display = "block";
        btnGenerate.disabled = true;
        btnGenerate.textContent = "Generating...";

        const payload = {
            subject_id: subjectId,
            competency_ids: Array.from(selectedCompetencies),
            template_config: templateConfig,
            use_ai: useAi,
            api_key: apiKey,
            ai_provider: aiProvider,
        };

        fetch("/api/generate", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        })
            .then((r) => r.json())
            .then((data) => {
                outputLoading.style.display = "none";
                btnGenerate.disabled = false;
                btnGenerate.textContent = "Generate Lesson Plan";

                if (data.error) {
                    outputContent.innerHTML = `<div style="padding:20px;color:var(--danger);"><strong>Error:</strong> ${data.error}</div>`;
                    outputContent.style.display = "block";
                    return;
                }

                // Render markdown to HTML
                const html = markdownToHtml(data.content);
                outputContent.innerHTML = html;
                outputContent.style.display = "block";

                // Show action buttons
                btnCopy.style.display = "inline-flex";
                btnPrint.style.display = "inline-flex";
                btnDownload.style.display = "inline-flex";

                // Store raw content for copy/download
                outputContent.dataset.raw = data.content;
            })
            .catch((err) => {
                outputLoading.style.display = "none";
                btnGenerate.disabled = false;
                btnGenerate.textContent = "Generate Lesson Plan";
                outputContent.innerHTML = `<div style="padding:20px;color:var(--danger);"><strong>Error:</strong> ${err.message}</div>`;
                outputContent.style.display = "block";
            });
    });

    // === Simple Markdown to HTML Converter ===
    function markdownToHtml(md) {
        if (!md) return "";
        let html = md;

        // Escape HTML
        html = html.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

        // Headers
        html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
        html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
        html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");

        // Bold and italic
        html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
        html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
        html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");

        // Tables
        html = html.replace(/^\|(.+)\|$/gm, function (match) {
            const cells = match.split("|").filter((c) => c.trim());
            if (cells.every((c) => /^[\s-]+$/.test(c))) {
                return "<!-- table separator -->";
            }
            const tds = cells.map((c) => `<td>${c.trim()}</td>`).join("");
            return `<tr>${tds}</tr>`;
        });
        html = html.replace(
            /((<tr>.*<\/tr>\n?)+)/g,
            "<table>$1</table>"
        );
        html = html.replace(/<!-- table separator -->\n?/g, "");

        // Unordered lists
        html = html.replace(/^(\s*)[-*] (.+)$/gm, function (match, indent, text) {
            return `<li>${text}</li>`;
        });
        html = html.replace(/((<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");

        // Ordered lists
        html = html.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");

        // Paragraphs (lines that aren't already wrapped in tags)
        html = html.replace(/^(?!<[a-z])((?!<).+)$/gm, "<p>$1</p>");

        // Clean up empty paragraphs
        html = html.replace(/<p>\s*<\/p>/g, "");

        // Line breaks
        html = html.replace(/\n{2,}/g, "\n");

        return html;
    }

    // === Copy Button ===
    btnCopy.addEventListener("click", function () {
        const raw = outputContent.dataset.raw || outputContent.textContent;
        navigator.clipboard.writeText(raw).then(() => {
            const orig = this.textContent;
            this.textContent = "Copied!";
            setTimeout(() => (this.textContent = orig), 2000);
        });
    });

    // === Print Button ===
    btnPrint.addEventListener("click", function () {
        window.print();
    });

    // === Download Button ===
    btnDownload.addEventListener("click", function () {
        const raw = outputContent.dataset.raw || outputContent.textContent;
        const subject = subjectSelect.options[subjectSelect.selectedIndex]?.text || "lesson";
        const grade = gradeSelect.value || "";
        const quarter = quarterSelect.value || "";
        const filename = `Lesson_Plan_${subject}_${grade}_${quarter}.md`
            .replace(/\s+/g, "_")
            .replace(/[^a-zA-Z0-9_.-]/g, "");

        const blob = new Blob([raw], { type: "text/markdown" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        a.click();
        URL.revokeObjectURL(url);
    });
});
