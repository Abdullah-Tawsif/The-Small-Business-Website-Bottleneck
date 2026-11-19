
document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // =================================================
    // 1. DOM ELEMENTS
    // =================================================

    const form = document.getElementById("inquiry-form");

    if (!form) return;

    const el = {
        businessName: document.getElementById("business-name"),
        businessType: document.getElementById("business-type"),
        projectDescription: document.getElementById("project-description"),
        currentWebsite: document.getElementById("current-website"),

        goals: form.querySelectorAll('input[name="goals"]:checked'),

        timeline: document.getElementById("preferred-timeline"),
        budgetMin: document.getElementById("budget-min"),
        budgetMax: document.getElementById("budget-max"),

        pages: document.getElementById("required-pages"),
        features: document.getElementById("required-features"),

        chatMessages: document.getElementById("scoping-messages"),
        chatInput: document.getElementById("scoping-message"),
        sendButton: document.getElementById("send-scoping-message"),
        sessionInput: document.getElementById("ai-session-id"),
        scopingStatus: document.getElementById("scoping-status"),

        scopePlaceholder: document.getElementById("scope-placeholder"),
        scopeResults: document.getElementById("scope-results"),
        scopeSummary: document.getElementById("scope-summary"),

        scopePages: document.getElementById("scope-pages"),
        scopeFeatures: document.getElementById("scope-features"),

        questionsPanel: document.getElementById(
            "clarifying-questions-panel"
        ),
        questions: document.getElementById("clarifying-questions"),

        recommendation: document.getElementById(
            "package-recommendation"
        ),
        packageName: document.getElementById(
            "recommended-package-name"
        ),
        packageDescription: document.getElementById(
            "recommended-package-description"
        ),

        estimatedPrice: document.getElementById("estimated-price"),
        estimatedPriceNote: document.getElementById(
            "estimated-price-note"
        ),

        packageId: document.getElementById("selected-package-id"),
        currency: document.getElementById("currency"),

        contactName: document.getElementById("contact-name"),
        contactEmail: document.getElementById("contact-email"),
        contactPhone: document.getElementById("contact-phone"),

        submitButton: document.getElementById("submit-inquiry"),
        inquiryStatus: document.getElementById("inquiry-status"),

        progress: document.querySelectorAll(".progress-step")
    };


    // =================================================
    // 2. APPLICATION STATE
    // =================================================

    let sessionId = null;

    let packages = [];
    let selectedPackageId = null;
    let recommendedPackageId = null;

    let latestScopeSummary = "";

    let isScoping = false;
    let isSubmitting = false;

    let estimateTimer = null;
    let estimateRequestNumber = 0;
    let estimateController = null;

    let packageSelector = null;


    // =================================================
    // 3. GENERAL HELPERS
    // =================================================

    function setStatus(element, message, type = "") {
        if (!element) return;

        element.textContent = message;

        element.classList.remove(
            "is-error",
            "is-success"
        );

        if (type) {
            element.classList.add(`is-${type}`);
        }
    }


    function getValue(element) {
        return element ? element.value.trim() : "";
    }


    function getBudget(element) {
        const value = getValue(element);

        return value === "" ? null : Number(value);
    }


    function parseList(value) {
        const result = [];
        const seen = new Set();

        String(value || "")
            .split(/\r?\n/)
            .forEach(item => {
                const cleaned = item.trim();
                const key = cleaned.toLowerCase();

                if (cleaned && !seen.has(key)) {
                    result.push(cleaned);
                    seen.add(key);
                }
            });

        return result;
    }


    function getGoals() {
        return Array.from(
            form.querySelectorAll('input[name="goals"]:checked')
        ).map(input => input.value);
    }


    function formatCurrency(value, currency = "BDT") {
        const amount = Number(value);

        if (!Number.isFinite(amount)) {
            return "Price unavailable";
        }

        try {
            return new Intl.NumberFormat("en-BD", {
                style: "currency",
                currency,
                maximumFractionDigits: 0
            }).format(amount);
        } catch {
            return `${currency} ${amount.toLocaleString("en-BD")}`;
        }
    }


    function refreshIcons() {
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }


    function setProgress(currentStep) {
        el.progress.forEach((step, index) => {
            const active = index < currentStep;

            step.classList.toggle("active", active);
        });
    }


    function extractError(data, statusCode) {
        if (typeof data?.detail === "string") {
            return data.detail;
        }

        if (Array.isArray(data?.detail)) {
            return data.detail
                .map(error => error.msg || "Invalid input.")
                .join(" ");
        }

        if (typeof data?.message === "string") {
            return data.message;
        }

        return `Request failed (${statusCode}). Please try again.`;
    }


    async function apiRequest(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",
            ...options,
            headers: {
                Accept: "application/json",
                ...options.headers
            }
        });

        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            throw new Error(
                extractError(data, response.status)
            );
        }

        return data;
    }


    // =================================================
    // 4. CHAT MESSAGE DISPLAY
    // =================================================

    function addMessage(message, sender = "assistant") {
        if (!el.chatMessages) return;

        const wrapper = document.createElement("div");

        wrapper.className = `chat-message ${sender}`;

        const avatar = document.createElement("div");
        avatar.className = "chat-avatar";

        const icon = document.createElement("i");

        icon.setAttribute(
            "data-lucide",
            sender === "user" ? "user" : "sparkles"
        );

        avatar.appendChild(icon);

        const bubble = document.createElement("div");
        bubble.className = "chat-bubble";

        const paragraph = document.createElement("p");

        // Never insert AI or customer content through innerHTML.
        paragraph.textContent = message;

        bubble.appendChild(paragraph);

        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);

        el.chatMessages.appendChild(wrapper);

        el.chatMessages.scrollTop =
            el.chatMessages.scrollHeight;

        refreshIcons();
    }


    function setScopingLoading(loading) {
        isScoping = loading;

        el.sendButton.disabled = loading;
        el.chatInput.disabled = loading;

        el.sendButton.setAttribute(
            "aria-busy",
            String(loading)
        );
    }


    // =================================================
    // 5. SCOPING REQUEST PAYLOAD
    // =================================================

    function buildScopingPayload(message) {
        return {
            session_id: sessionId,

            message: message,

            business_name: getValue(el.businessName) || null,

            business_type: getValue(el.businessType) || null,

            project_description:
                getValue(el.projectDescription) || null,

            goals: getGoals(),

            current_website:
                getValue(el.currentWebsite) || null,

            required_pages: parseList(el.pages.value),

            required_features: parseList(el.features.value),

            preferred_timeline:
                getValue(el.timeline) || null,

            budget_min: getBudget(el.budgetMin),

            budget_max: getBudget(el.budgetMax)
        };
    }


    // =================================================
    // 6. DISPLAY GENERATED REQUIREMENTS
    // =================================================

    function renderRequirementList(container, items) {
        container.replaceChildren();

        if (!items.length) {
            const li = document.createElement("li");

            li.textContent = "No suggestions available.";

            container.appendChild(li);

            return;
        }

        items.forEach(item => {
            const li = document.createElement("li");

            const icon = document.createElement("i");

            icon.setAttribute(
                "data-lucide",
                "check-circle-2"
            );

            const text = document.createElement("span");

            text.textContent = item;

            li.appendChild(icon);
            li.appendChild(text);

            container.appendChild(li);
        });

        refreshIcons();
    }


    function renderQuestions(questions) {
        el.questions.replaceChildren();

        if (!questions.length) {
            el.questionsPanel.hidden = true;
            return;
        }

        el.questionsPanel.hidden = false;

        questions.forEach(question => {
            const li = document.createElement("li");

            li.textContent = question;

            el.questions.appendChild(li);
        });
    }


    function displayScope(data) {
        // Save session ID for all future AI requests.
        sessionId = data.session_id;

        el.sessionInput.value = sessionId;

        latestScopeSummary = data.scope_summary || "";

        el.scopeSummary.textContent = latestScopeSummary;

        const pages = Array.isArray(data.required_pages)
            ? data.required_pages
            : [];

        const features = Array.isArray(data.required_features)
            ? data.required_features
            : [];

        const questions = Array.isArray(data.clarifying_questions)
            ? data.clarifying_questions
            : [];

        // Populate editable requirement fields.
        el.pages.value = pages.join("\n");

        el.features.value = features.join("\n");

        // Populate visible suggested requirements.
        renderRequirementList(
            el.scopePages,
            pages
        );

        renderRequirementList(
            el.scopeFeatures,
            features
        );

        renderQuestions(questions);

        el.scopePlaceholder.hidden = true;
        el.scopeResults.hidden = false;

        // Update package recommendation.
        renderPackageRecommendation(
            data.recommended_package_id
        );

        addMessage(
            latestScopeSummary,
            "assistant"
        );

        if (questions.length) {
            addMessage(
                "I have a few questions that could help clarify your project:\n" +
                questions.map((q, index) => `${index + 1}. ${q}`).join("\n"),
                "assistant"
            );
        }

        setProgress(3);

        scheduleEstimate();

        refreshIcons();
    }


    // =================================================
    // 7. AI SCOPING API
    // =================================================

    async function sendScopingMessage() {
        if (isScoping) return;

        const message = getValue(el.chatInput);

        if (message.length < 3) {
            setStatus(
                el.scopingStatus,
                "Please enter at least 3 characters.",
                "error"
            );

            return;
        }

        addMessage(message, "user");

        setScopingLoading(true);

        setStatus(
            el.scopingStatus,
            "AI is reviewing your project requirements..."
        );

        setProgress(2);

        try {
            const payload = buildScopingPayload(message);

            const data = await apiRequest(
                "/api/scoping/",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                }
            );

            if (!data.session_id) {
                throw new Error(
                    "The scoping API did not return a session ID."
                );
            }

            displayScope(data);

            // Clear the message only after a successful response.
            el.chatInput.value = "";

            setStatus(
                el.scopingStatus,
                "Your project scope has been updated successfully.",
                "success"
            );

        } catch (error) {
            console.error("AI scoping failed:", error);

            addMessage(
                `Unable to process your message. ${error.message}`,
                "assistant"
            );

            setStatus(
                el.scopingStatus,
                error.message || "AI scoping service is unavailable.",
                "error"
            );

            // Restore the first-step indicator if scope generation failed.
            setProgress(1);

        } finally {
            setScopingLoading(false);

            el.chatInput.focus();
        }
    }


    el.sendButton.addEventListener(
        "click",
        sendScopingMessage
    );


    el.chatInput.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();

            sendScopingMessage();
        }
    });


    // =================================================
    // 8. LOAD AVAILABLE PACKAGES
    // =================================================

    async function loadPackages() {
        try {
            const data = await apiRequest(
                "/api/packages/",
                {
                    method: "GET"
                }
            );

            if (!Array.isArray(data)) {
                throw new Error(
                    "Unexpected package API response."
                );
            }

            packages = data.filter(
                item => item.is_active !== false
            );

            if (!packages.length) {
                console.warn("No active packages are available.");
            }

            return packages;

        } catch (error) {
            console.error("Package loading failed:", error);

            setStatus(
                el.scopingStatus,
                "Packages could not be loaded. You can still request a custom quotation.",
                "error"
            );

            packages = [];

            return [];
        }
    }


    // =================================================
    // 9. PACKAGE SELECTION
    // =================================================

    function createPackageSelector() {
        if (packageSelector) return;

        const wrapper = document.createElement("div");

        wrapper.className = "inquiry-field";

        wrapper.style.gridColumn = "1 / -1";
        wrapper.style.marginTop = "12px";

        const label = document.createElement("label");

        label.setAttribute(
            "for",
            "package-selector"
        );

        label.textContent = "Choose or change your package";

        packageSelector = document.createElement("select");

        packageSelector.id = "package-selector";

        const placeholder = document.createElement("option");

        placeholder.value = "";

        placeholder.textContent = "Select a package";

        packageSelector.appendChild(placeholder);

        packages.forEach(pkg => {
            const option = document.createElement("option");

            option.value = String(pkg.id);

            option.textContent =
                `${pkg.name} (${pkg.currency} ` +
                `${Number(pkg.min_price).toLocaleString("en-BD")} - ` +
                `${Number(pkg.max_price).toLocaleString("en-BD")})`;

            packageSelector.appendChild(option);
        });

        packageSelector.addEventListener(
            "change",
            () => {
                selectedPackageId = packageSelector.value
                    ? Number(packageSelector.value)
                    : null;

                el.packageId.value = selectedPackageId || "";

                updatePackageDetails();

                scheduleEstimate();
            }
        );

        wrapper.appendChild(label);
        wrapper.appendChild(packageSelector);

        // A full-width row below the recommendation card content.
        el.recommendation.appendChild(wrapper);
    }


    function renderPackageRecommendation(packageId) {
        el.recommendation.hidden = false;

        recommendedPackageId = packageId
            ? Number(packageId)
            : null;

        if (!packages.length) {
            el.packageName.textContent =
                "Custom project quotation";

            el.packageDescription.textContent =
                "Our team can review your requirements and prepare a custom quotation.";

            el.estimatedPrice.textContent =
                "Custom quote";

            el.estimatedPriceNote.textContent =
                "Package information is currently unavailable.";

            return;
        }

        createPackageSelector();

        const recommended = packages.find(
            pkg => Number(pkg.id) === recommendedPackageId
        );

        // Preserve a customer's previous selection when continuing the chat.
        const existingSelection = packages.find(
            pkg => Number(pkg.id) === Number(selectedPackageId)
        );

        const selected = existingSelection || recommended || packages[0];

        selectedPackageId = Number(selected.id);

        packageSelector.value = String(selectedPackageId);

        el.packageId.value = selectedPackageId;

        updatePackageDetails();
    }


    function updatePackageDetails() {
        const selected = packages.find(
            pkg => Number(pkg.id) === Number(selectedPackageId)
        );

        if (!selected) return;

        el.packageName.textContent = selected.name;

        el.packageDescription.textContent =
            selected.description || "Website development package.";

        el.currency.value = selected.currency || "BDT";

        const label = el.recommendation.querySelector(
            ".recommendation-label"
        );

        if (label) {
            label.textContent =
                Number(selected.id) === recommendedPackageId
                    ? "AI recommended package"
                    : "Selected package";
        }
    }


    // =================================================
    // 10. PRICE ESTIMATION
    // =================================================

    async function calculateEstimate() {
        if (!selectedPackageId || isSubmitting) return;

        const requestNumber = ++estimateRequestNumber;

        // Cancel outdated requests to avoid showing stale prices.
        if (estimateController) {
            estimateController.abort();
        }

        estimateController = new AbortController();

        el.estimatedPrice.textContent = "Calculating...";

        el.estimatedPriceNote.textContent =
            "Updating your estimate.";

        const payload = {
            package_id: Number(selectedPackageId),

            required_pages: parseList(el.pages.value),

            required_features: parseList(el.features.value)
        };

        try {
            const estimate = await apiRequest(
                "/api/packages/estimate",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload),
                    signal: estimateController.signal
                }
            );

            // Ignore old responses from previous selections.
            if (requestNumber !== estimateRequestNumber) return;

            const currency = estimate.currency || "BDT";

            const minimum = formatCurrency(
                estimate.estimated_min_price,
                currency
            );

            const maximum = formatCurrency(
                estimate.estimated_max_price,
                currency
            );

            el.estimatedPrice.textContent =
                `${minimum} – ${maximum}`;

            el.currency.value = currency;

            if (estimate.requires_manual_quote) {
                const unpriced = Array.isArray(
                    estimate.unpriced_features
                )
                    ? estimate.unpriced_features
                    : [];

                el.estimatedPriceNote.textContent =
                    unpriced.length
                        ? `Manual quotation required for: ${unpriced.join(", ")}`
                        : "Some features require a manual quotation.";
            } else {
                el.estimatedPriceNote.textContent =
                    `${estimate.total_pages} pages · ` +
                    `${estimate.package_name || "Selected package"}`;
            }

        } catch (error) {
            if (error.name === "AbortError") return;

            if (requestNumber !== estimateRequestNumber) return;

            console.error("Price estimation failed:", error);

            el.estimatedPrice.textContent = "Custom quotation";

            el.estimatedPriceNote.textContent =
                "We will review your requirements and prepare a quote.";
        }
    }


    function scheduleEstimate() {
        clearTimeout(estimateTimer);

        if (!selectedPackageId) return;

        estimateTimer = setTimeout(
            calculateEstimate,
            400
        );
    }


    // Recalculate when customer edits their requirements.
    el.pages.addEventListener("input", scheduleEstimate);

    el.features.addEventListener("input", scheduleEstimate);


    // =================================================
    // 11. LEAD VALIDATION
    // =================================================

    function validateInquiry() {
        if (!form.checkValidity()) {
            form.reportValidity();

            return false;
        }

        const minimum = getBudget(el.budgetMin);
        const maximum = getBudget(el.budgetMax);

        if (
            minimum !== null &&
            !Number.isFinite(minimum)
        ) {
            setStatus(
                el.inquiryStatus,
                "Please enter a valid minimum budget.",
                "error"
            );

            el.budgetMin.focus();

            return false;
        }

        if (
            maximum !== null &&
            !Number.isFinite(maximum)
        ) {
            setStatus(
                el.inquiryStatus,
                "Please enter a valid maximum budget.",
                "error"
            );

            el.budgetMax.focus();

            return false;
        }

        if (
            minimum !== null &&
            maximum !== null &&
            maximum < minimum
        ) {
            setStatus(
                el.inquiryStatus,
                "Maximum budget cannot be lower than minimum budget.",
                "error"
            );

            el.budgetMax.focus();

            return false;
        }

        return true;
    }


    // =================================================
    // 12. BUILD LEAD CREATE PAYLOAD
    // =================================================

    function buildLeadPayload() {
        const originalDescription = getValue(
            el.projectDescription
        );

        let description = originalDescription;

        // The existing LeadCreate schema does not accept
        // ai_scope_summary, so preserve it in the description.
        if (
            latestScopeSummary &&
            description.length < 5000
        ) {
            const suffix =
                "\n\nAI-generated project scope:\n" +
                latestScopeSummary;

            const availableCharacters = 5000 - description.length;

            description += suffix.slice(0, availableCharacters);
        }

        return {
            contact_name: getValue(el.contactName),

            business_name: getValue(el.businessName),

            email: getValue(el.contactEmail),

            phone: getValue(el.contactPhone) || null,

            business_type: getValue(el.businessType),

            project_description: description,

            required_pages: parseList(el.pages.value),

            required_features: parseList(el.features.value),

            preferred_timeline: getValue(el.timeline) || null,

            budget_min: getBudget(el.budgetMin),

            budget_max: getBudget(el.budgetMax),

            package_id: selectedPackageId || null,

            currency: el.currency.value || "BDT"
        };
    }


    // =================================================
    // 13. FINAL CUSTOMER LEAD SUBMISSION
    // =================================================

    async function submitInquiry(event) {
        event.preventDefault();

        // Block duplicate submissions.
        if (isSubmitting) return;

        if (!validateInquiry()) return;

        const payload = buildLeadPayload();

        isSubmitting = true;

        clearTimeout(estimateTimer);

        if (estimateController) {
            estimateController.abort();
        }

        el.submitButton.disabled = true;

        el.submitButton.setAttribute(
            "aria-busy",
            "true"
        );

        el.submitButton.textContent =
            "Submitting your inquiry...";

        setStatus(
            el.inquiryStatus,
            "Sending your project inquiry..."
        );

        setProgress(4);

        try {
            const result = await apiRequest(
                "/api/leads/",
                {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                }
            );

            const reference = result.id
                ? ` Reference: #${result.id}.`
                : "";

            setStatus(
                el.inquiryStatus,
                "Your project inquiry was submitted successfully!" +
                reference +
                " Our team will review your requirements and contact you.",
                "success"
            );

            el.submitButton.textContent =
                "Inquiry submitted successfully";

            // Disable all controls after confirmed submission.
            form.querySelectorAll(
                "input, textarea, select, button"
            ).forEach(control => {
                control.disabled = true;
            });

            addMessage(
                "Thank you! Your inquiry has been received. " +
                "Our team will review your project and get in touch.",
                "assistant"
            );

            setProgress(4);

        } catch (error) {
            console.error("Lead submission failed:", error);

            setStatus(
                el.inquiryStatus,
                error.message ||
                "We couldn't submit your inquiry. Please try again.",
                "error"
            );

            // Restore the button so the customer can retry.
            el.submitButton.disabled = false;

            el.submitButton.removeAttribute("aria-busy");

            el.submitButton.textContent =
                "Submit project inquiry";

            setProgress(3);

        } finally {
            isSubmitting = false;
        }
    }


    form.addEventListener(
        "submit",
        submitInquiry
    );


    // =================================================
    // 14. INITIALIZE
    // =================================================

    async function initialize() {
        setProgress(1);

        setStatus(
            el.scopingStatus,
            "Loading available website packages..."
        );

        await loadPackages();

        setStatus(
            el.scopingStatus,
            "Tell us about your business and start your AI discovery conversation.",
            "success"
        );
    }


    initialize();

});
