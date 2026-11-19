
document.addEventListener("DOMContentLoaded", () => {
    "use strict";

    // ================================================
    // 1. DOM ELEMENTS
    // ================================================

    const form = document.getElementById("inquiry-form");

    if (!form) return;

    const elements = {
        businessName: document.getElementById("business-name"),
        businessType: document.getElementById("business-type"),
        projectDescription: document.getElementById("project-description"),
        currentWebsite: document.getElementById("current-website"),

        preferredTimeline: document.getElementById("preferred-timeline"),
        budgetMin: document.getElementById("budget-min"),
        budgetMax: document.getElementById("budget-max"),

        requiredPages: document.getElementById("required-pages"),
        requiredFeatures: document.getElementById("required-features"),

        chatMessages: document.getElementById("scoping-messages"),
        chatInput: document.getElementById("scoping-message"),
        sendButton: document.getElementById("send-scoping-message"),
        sessionId: document.getElementById("ai-session-id"),
        scopingStatus: document.getElementById("scoping-status"),

        scopePlaceholder: document.getElementById("scope-placeholder"),
        scopeResults: document.getElementById("scope-results"),
        scopeSummary: document.getElementById("scope-summary"),

        scopePages: document.getElementById("scope-pages"),
        scopeFeatures: document.getElementById("scope-features"),

        questionsPanel: document.getElementById(
            "clarifying-questions-panel"
        ),
        clarifyingQuestions: document.getElementById(
            "clarifying-questions"
        ),

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
        inquiryStatus: document.getElementById("inquiry-status")
    };


    // ================================================
    // 2. APPLICATION STATE
    // ================================================

    let sessionId = null;

    let packages = [];

    let latestScopeSummary = "";

    let selectedPackageId = null;

    let isScoping = false;
    let isSubmitting = false;

    let estimateTimer = null;
    let estimateRequestNumber = 0;

    let packageSelector = null;


    // ================================================
    // 3. GENERAL HELPERS
    // ================================================

    function showStatus(element, message, type = "") {
        if (!element) return;

        element.textContent = message;

        element.classList.remove("is-error", "is-success");

        if (type) {
            element.classList.add(`is-${type}`);
        }
    }


    async function parseResponse(response) {
        const data = await response.json().catch(() => ({}));

        if (!response.ok) {
            let message = `Request failed (${response.status}).`;

            if (typeof data.detail === "string") {
                message = data.detail;
            } else if (Array.isArray(data.detail)) {
                message = data.detail
                    .map(item => item.msg || "Invalid input.")
                    .join(" ");
            } else if (typeof data.message === "string") {
                message = data.message;
            }

            throw new Error(message);
        }

        return data;
    }


    async function apiRequest(url, options = {}) {
        const response = await fetch(url, {
            credentials: "same-origin",

            ...options,

            headers: {
                Accept: "application/json",
                ...(options.headers || {})
            }
        });

        return parseResponse(response);
    }


    function getJSONHeaders() {
        return {
            "Content-Type": "application/json"
        };
    }


    function getValue(element) {
        return element ? element.value.trim() : "";
    }


    function getBudget(element) {
        const value = getValue(element);

        return value === "" ? null : Number(value);
    }


    function getSelectedGoals() {
        return Array.from(
            form.querySelectorAll('input[name="goals"]:checked')
        ).map(input => input.value);
    }


    function parseList(value) {
        const result = [];
        const seen = new Set();

        value.split(/\r?\n/).forEach(item => {
            const cleaned = item.trim();
            const key = cleaned.toLowerCase();

            if (cleaned && !seen.has(key)) {
                result.push(cleaned);
                seen.add(key);
            }
        });

        return result;
    }


    function formatCurrency(amount, currency = "BDT") {
        const value = Number(amount);

        if (!Number.isFinite(value)) {
            return "Price unavailable";
        }

        try {
            return new Intl.NumberFormat("en-BD", {
                style: "currency",
                currency: currency,
                maximumFractionDigits: 0
            }).format(value);
        } catch {
            return `${currency} ${value.toLocaleString("en-BD")}`;
        }
    }


    function renderIcons() {
        if (window.lucide) {
            window.lucide.createIcons();
        }
    }


    // ================================================
    // 4. CHAT INTERFACE
    // ================================================

    function addChatMessage(message, sender = "assistant") {
        if (!elements.chatMessages) return;

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

        // Use textContent to prevent HTML injection.
        paragraph.textContent = message;

        bubble.appendChild(paragraph);

        wrapper.appendChild(avatar);
        wrapper.appendChild(bubble);

        elements.chatMessages.appendChild(wrapper);

        elements.chatMessages.scrollTop =
            elements.chatMessages.scrollHeight;

        renderIcons();
    }


    function setScopingLoading(loading) {
        isScoping = loading;

        if (elements.sendButton) {
            elements.sendButton.disabled = loading;
        }

        if (elements.chatInput) {
            elements.chatInput.disabled = loading;
        }

        if (elements.sendButton) {
            elements.sendButton.setAttribute(
                "aria-busy",
                String(loading)
            );
        }
    }


    // ================================================
    // 5. COLLECT SCOPING INFORMATION
    // ================================================

    function getScopingPayload(message) {
        return {
            session_id: sessionId,

            message: message,

            business_name: getValue(elements.businessName) || null,

            business_type: getValue(elements.businessType) || null,

            project_description:
                getValue(elements.projectDescription) || null,

            goals: getSelectedGoals(),

            current_website:
                getValue(elements.currentWebsite) || null,

            required_pages: parseList(
                getValue(elements.requiredPages)
            ),

            required_features: parseList(
                getValue(elements.requiredFeatures)
            ),

            preferred_timeline:
                getValue(elements.preferredTimeline) || null,

            budget_min: getBudget(elements.budgetMin),

            budget_max: getBudget(elements.budgetMax)
        };
    }


    // ================================================
    // 6. DISPLAY GENERATED REQUIREMENTS
    // ================================================

    function renderScopeList(container, items) {
        if (!container) return;

        container.replaceChildren();

        items.forEach(item => {
            const li = document.createElement("li");

            const icon = document.createElement("i");

            icon.setAttribute("data-lucide", "check-circle-2");

            const text = document.createElement("span");

            text.textContent = item;

            li.appendChild(icon);
            li.appendChild(text);

            container.appendChild(li);
        });

        if (!items.length) {
            const li = document.createElement("li");

            li.textContent = "No suggestions available yet.";

            container.appendChild(li);
        }
    }


    function renderQuestions(questions) {
        elements.clarifyingQuestions.replaceChildren();

        if (!questions.length) {
            elements.questionsPanel.hidden = true;
            return;
        }

        elements.questionsPanel.hidden = false;

        questions.forEach(question => {
            const li = document.createElement("li");

            li.textContent = question;

            elements.clarifyingQuestions.appendChild(li);
        });
    }


    function displayScope(data) {
        sessionId = data.session_id;

        elements.sessionId.value = sessionId;

        latestScopeSummary = data.scope_summary || "";

        elements.scopeSummary.textContent = latestScopeSummary;

        // Allow the customer to edit the AI suggestions.
        elements.requiredPages.value = (
            data.required_pages || []
        ).join("\n");

        elements.requiredFeatures.value = (
            data.required_features || []
        ).join("\n");

        renderScopeList(
            elements.scopePages,
            data.required_pages || []
        );

        renderScopeList(
            elements.scopeFeatures,
            data.required_features || []
        );

        renderQuestions(
            data.clarifying_questions || []
        );

        elements.scopePlaceholder.hidden = true;
        elements.scopeResults.hidden = false;

        // Display the AI response in the conversation.
        addChatMessage(latestScopeSummary, "assistant");

        if (data.clarifying_questions?.length) {
            addChatMessage(
                "A few things we'd like to clarify: " +
                data.clarifying_questions.join(" "),
                "assistant"
            );
        }

        renderIcons();

        // Select the AI-recommended package when available.
        renderPackageRecommendation(
            data.recommended_package_id
        );

        highlightProgress(2);

        scheduleEstimate();
    }


    // ================================================
    // 7. AI SCOPING API
    // ================================================

    async function sendScopingMessage() {
        if (isScoping) return;

        const message = getValue(elements.chatInput);

        if (message.length < 3) {
            showStatus(
                elements.scopingStatus,
                "Please enter at least 3 characters.",
                "error"
            );

            return;
        }

        addChatMessage(message, "user");

        elements.chatInput.value = "";

        setScopingLoading(true);

        showStatus(
            elements.scopingStatus,
            "Our AI assistant is reviewing your requirements..."
        );

        try {
            const payload = getScopingPayload(message);

            const data = await apiRequest(
                "/api/scoping/",
                {
                    method: "POST",
                    headers: getJSONHeaders(),
                    body: JSON.stringify(payload)
                }
            );

            if (!data.session_id) {
                throw new Error(
                    "The scoping service did not return a session ID."
                );
            }

            displayScope(data);

            showStatus(
                elements.scopingStatus,
                "Your project scope has been updated.",
                "success"
            );

        } catch (error) {
            console.error("AI scoping error:", error);

            addChatMessage(
                "Sorry, we couldn't process that message. " +
                error.message +
                " Please try again.",
                "assistant"
            );

            showStatus(
                elements.scopingStatus,
                error.message || "Unable to contact the AI service.",
                "error"
            );

        } finally {
            setScopingLoading(false);

            elements.chatInput.focus();
        }
    }


    elements.sendButton.addEventListener(
        "click",
        sendScopingMessage
    );


    elements.chatInput.addEventListener("keydown", event => {
        if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();

            sendScopingMessage();
        }
    });


    // ================================================
    // 8. FETCH AVAILABLE PACKAGES
    // ================================================

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
                    "The package API returned an unexpected response."
                );
            }

            packages = data.filter(
                item => item.is_active !== false
            );

            if (!packages.length) {
                console.warn("No active website packages are available.");
            }

            return packages;

        } catch (error) {
            console.error("Package loading error:", error);

            showStatus(
                elements.inquiryStatus,
                "Available packages could not be loaded. " +
                "You can still submit an inquiry without selecting a package.",
                "error"
            );

            return [];
        }
    }


    // ================================================
    // 9. PACKAGE SELECTOR
    // ================================================

    function createPackageSelector() {
        if (packageSelector) return;

        const wrapper = document.createElement("div");

        wrapper.id = "package-selector-wrap";

        wrapper.className = "inquiry-field";

        wrapper.style.marginTop = "17px";

        const label = document.createElement("label");

        label.textContent = "Choose or change your package";

        label.htmlFor = "package-selector";

        packageSelector = document.createElement("select");

        packageSelector.id = "package-selector";

        packageSelector.name = "package_selection";

        const placeholder = document.createElement("option");

        placeholder.value = "";

        placeholder.textContent = "Select a package";

        packageSelector.appendChild(placeholder);

        packages.forEach(pkg => {
            const option = document.createElement("option");

            option.value = String(pkg.id);

            option.textContent =
                `${pkg.name} — ${pkg.currency} ` +
                `${Number(pkg.min_price).toLocaleString("en-BD")}–` +
                `${Number(pkg.max_price).toLocaleString("en-BD")}`;

            packageSelector.appendChild(option);
        });

        packageSelector.addEventListener("change", () => {
            selectedPackageId = packageSelector.value
                ? Number(packageSelector.value)
                : null;

            elements.packageId.value = selectedPackageId || "";

            updatePackageDetails();

            scheduleEstimate();
        });

        wrapper.appendChild(label);
        wrapper.appendChild(packageSelector);

        elements.recommendation.insertAdjacentElement(
            "afterend",
            wrapper
        );
    }


    function renderPackageRecommendation(recommendedId) {
        elements.recommendation.hidden = false;

        if (!packages.length) {
            elements.packageName.textContent =
                "Packages currently unavailable";

            elements.packageDescription.textContent =
                "You can still submit your project inquiry for a custom quote.";

            elements.estimatedPrice.textContent =
                "Custom quotation";

            return;
        }

        createPackageSelector();

        const recommended = packages.find(
            pkg => Number(pkg.id) === Number(recommendedId)
        );

        const selected = recommended || packages[0];

        selectedPackageId = Number(selected.id);

        elements.packageId.value = selectedPackageId;

        packageSelector.value = String(selectedPackageId);

        updatePackageDetails();
    }


    function updatePackageDetails() {
        const selected = packages.find(
            pkg => Number(pkg.id) === Number(selectedPackageId)
        );

        if (!selected) {
            elements.packageName.textContent = "Choose a package";

            elements.packageDescription.textContent =
                "Select a package to calculate your project estimate.";

            return;
        }

        elements.packageName.textContent = selected.name;

        elements.packageDescription.textContent =
            selected.description;

        elements.currency.value = selected.currency || "BDT";
    }


    // ================================================
    // 10. PROJECT PRICE ESTIMATION
    // ================================================

    async function calculateEstimate() {
        if (!selectedPackageId) return;

        const requestNumber = ++estimateRequestNumber;

        elements.estimatedPrice.textContent =
            "Calculating...";

        elements.estimatedPriceNote.textContent =
            "Updating your project estimate.";

        const payload = {
            package_id: selectedPackageId,

            required_pages: parseList(
                getValue(elements.requiredPages)
            ),

            required_features: parseList(
                getValue(elements.requiredFeatures)
            )
        };

        try {
            const estimate = await apiRequest(
                "/api/packages/estimate",
                {
                    method: "POST",
                    headers: getJSONHeaders(),
                    body: JSON.stringify(payload)
                }
            );

            // Ignore old results if a newer request has been made.
            if (requestNumber !== estimateRequestNumber) {
                return;
            }

            const currency = estimate.currency || "BDT";

            const minimum = formatCurrency(
                estimate.estimated_min_price,
                currency
            );

            const maximum = formatCurrency(
                estimate.estimated_max_price,
                currency
            );

            elements.estimatedPrice.textContent =
                `${minimum} – ${maximum}`;

            elements.currency.value = currency;

            if (estimate.requires_manual_quote) {
                elements.estimatedPriceNote.textContent =
                    "Some requested features require a manual quotation.";
            } else {
                elements.estimatedPriceNote.textContent =
                    `${estimate.total_pages} pages · ` +
                    `${estimate.package_name || "Selected package"}`;
            }

        } catch (error) {
            if (requestNumber !== estimateRequestNumber) {
                return;
            }

            console.error("Price estimation error:", error);

            elements.estimatedPrice.textContent =
                "Custom quotation";

            elements.estimatedPriceNote.textContent =
                "We will review your requirements and prepare a quote.";
        }
    }


    function scheduleEstimate() {
        clearTimeout(estimateTimer);

        if (!selectedPackageId) return;

        estimateTimer = setTimeout(
            calculateEstimate,
            350
        );
    }


    // Recalculate estimates after manual edits.
    elements.requiredPages.addEventListener(
        "input",
        scheduleEstimate
    );

    elements.requiredFeatures.addEventListener(
        "input",
        scheduleEstimate
    );


    // ================================================
    // 11. PROGRESS INDICATOR
    // ================================================

    function highlightProgress(stepNumber) {
        const steps = document.querySelectorAll(
            ".progress-step"
        );

        steps.forEach((step, index) => {
            step.classList.toggle(
                "active",
                index + 1 === stepNumber
            );
        });
    }


    // ================================================
    // 12. FORM VALIDATION
    // ================================================

    function validateInquiry() {
        if (!form.checkValidity()) {
            form.reportValidity();

            return false;
        }

        const minimum = getBudget(elements.budgetMin);

        const maximum = getBudget(elements.budgetMax);

        if (
            minimum !== null &&
            maximum !== null &&
            maximum < minimum
        ) {
            showStatus(
                elements.inquiryStatus,
                "Maximum budget cannot be lower than minimum budget.",
                "error"
            );

            elements.budgetMax.focus();

            return false;
        }

        if (
            minimum !== null &&
            !Number.isFinite(minimum)
        ) {
            showStatus(
                elements.inquiryStatus,
                "Please enter a valid minimum budget.",
                "error"
            );

            return false;
        }

        if (
            maximum !== null &&
            !Number.isFinite(maximum)
        ) {
            showStatus(
                elements.inquiryStatus,
                "Please enter a valid maximum budget.",
                "error"
            );

            return false;
        }

        if (
            getValue(elements.projectDescription).length < 10
        ) {
            showStatus(
                elements.inquiryStatus,
                "Please provide at least 10 characters describing your project.",
                "error"
            );

            elements.projectDescription.focus();

            return false;
        }

        return true;
    }


    // ================================================
    // 13. BUILD LEAD REQUEST
    // ================================================

    function getLeadPayload() {
        let description = getValue(
            elements.projectDescription
        );

        // Preserve the useful AI summary in the lead description.
        // The current LeadCreate schema does not expose ai_scope_summary.
        if (latestScopeSummary) {
            description +=
                "\n\nAI-generated project scope:\n" +
                latestScopeSummary;
        }

        // Do not exceed the backend LeadCreate limit.
        description = description.slice(0, 5000);

        return {
            contact_name: getValue(elements.contactName),

            business_name: getValue(elements.businessName),

            email: getValue(elements.contactEmail),

            phone: getValue(elements.contactPhone) || null,

            business_type: getValue(elements.businessType),

            project_description: description,

            required_pages: parseList(
                getValue(elements.requiredPages)
            ),

            required_features: parseList(
                getValue(elements.requiredFeatures)
            ),

            preferred_timeline:
                getValue(elements.preferredTimeline) || null,

            budget_min: getBudget(elements.budgetMin),

            budget_max: getBudget(elements.budgetMax),

            package_id: selectedPackageId || null,

            currency: elements.currency.value || "BDT"
        };
    }


    // ================================================
    // 14. FINAL LEAD SUBMISSION
    // ================================================

    async function submitInquiry(event) {
        event.preventDefault();

        if (isSubmitting) return;

        if (!validateInquiry()) return;

        const payload = getLeadPayload();

        isSubmitting = true;

        elements.submitButton.disabled = true;

        elements.submitButton.setAttribute(
            "aria-busy",
            "true"
        );

        elements.submitButton.textContent =
            "Submitting your inquiry...";

        showStatus(
            elements.inquiryStatus,
            "Sending your project inquiry..."
        );

        highlightProgress(4);

        try {
            const result = await apiRequest(
                "/api/leads/",
                {
                    method: "POST",
                    headers: getJSONHeaders(),
                    body: JSON.stringify(payload)
                }
            );

            const leadId = result.id;

            showStatus(
                elements.inquiryStatus,
                leadId
                    ? `Your inquiry was submitted successfully! Reference number: #${leadId}`
                    : "Your project inquiry was submitted successfully!",
                "success"
            );

            elements.submitButton.textContent =
                "Inquiry submitted successfully";

            // Prevent duplicate inquiries.
            elements.submitButton.disabled = true;

            // Disable every input after confirmed submission.
            form.querySelectorAll(
                "input, textarea, select, button"
            ).forEach(element => {
                element.disabled = true;
            });

            addChatMessage(
                "Thank you! Your project inquiry has been received. " +
                "Our team will review your requirements and contact you.",
                "assistant"
            );

            highlightProgress(4);

        } catch (error) {
            console.error("Inquiry submission error:", error);

            showStatus(
                elements.inquiryStatus,
                error.message ||
                "Unable to submit your inquiry. Please try again.",
                "error"
            );

            // Allow the customer to retry.
            elements.submitButton.disabled = false;

            elements.submitButton.textContent =
                "Submit project inquiry";

        } finally {
            if (!elements.submitButton.disabled) {
                elements.submitButton.removeAttribute("aria-busy");
            }

            isSubmitting = false;
        }
    }


    form.addEventListener(
        "submit",
        submitInquiry
    );


    // ================================================
    // 15. INITIALIZE APPLICATION
    // ================================================

    async function initialize() {
        showStatus(
            elements.scopingStatus,
            "Loading available packages..."
        );

        await loadPackages();

        showStatus(
            elements.scopingStatus,
            "Tell us about your project to begin AI discovery.",
            "success"
        );

        // The customer can still start a conversation even
        // when the packages endpoint is temporarily unavailable.
    }


    initialize();

});
