const state = {
    customers: [],
    toastTimer: null,
    pollInterval: null,
    activeModalCustomerId: null
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    initTheme();
    bindEvents();
    loadCustomers();

    // Auto-refresh every 2.5 seconds for live status & feedback updates
    state.pollInterval = setInterval(() => {
        loadCustomers(true);
        if (state.activeModalCustomerId) {
            updateModalTranscript(state.activeModalCustomerId);
        }
    }, 2500);
});

function cacheElements() {
    elements.table = document.getElementById("customerTable");
    elements.form = document.getElementById("customerForm");
    elements.name = document.getElementById("customerName");
    elements.phone = document.getElementById("customerPhone");
    elements.addButton = document.getElementById("addCustomerBtn");
    elements.search = document.getElementById("customerSearch");
    elements.filter = document.getElementById("statusFilter");
    elements.refresh = document.getElementById("refreshBtn");
    elements.resetSeed = document.getElementById("resetSeedBtn");
    elements.toast = document.getElementById("toast");

    // Add Customer Modal
    elements.addModal = document.getElementById("addCustomerModal");
    elements.openAddModal = document.getElementById("addCustomerModalBtn");
    elements.closeAddModal = document.getElementById("closeAddModalBtn");

    // Summary Stats
    elements.totalCustomers = document.getElementById("totalCustomers");
    elements.pendingCustomers = document.getElementById("pendingCustomers");
    elements.completedCustomers = document.getElementById("completedCustomers");
    elements.statAccuracy = document.getElementById("statAccuracy");
    elements.statSatisfaction = document.getElementById("statSatisfaction");
    elements.statCompletion = document.getElementById("statCompletion");

    // Theme elements
    elements.themeToggleBtn = document.getElementById("themeToggleBtn");
    elements.themeIcon = document.getElementById("themeIcon");

    // Transcript Modal elements
    elements.modal = document.getElementById("transcriptModal");
    elements.closeModal = document.getElementById("closeModalBtn");
    elements.closeModalFooter = document.getElementById("modalCloseFooterBtn");
    elements.modalName = document.getElementById("modalCustomerName");
    elements.modalPhone = document.getElementById("modalCustomerPhone");
    elements.modalStatus = document.getElementById("modalCallStatus");
    elements.modalSentiment = document.getElementById("modalCustomerSentiment");
    elements.modalConversation = document.getElementById("transcriptConversation");
    elements.modalCallBtn = document.getElementById("modalCallBtn");
}

function initTheme() {
    const savedTheme = localStorage.getItem("theme") || "dark";
    applyTheme(savedTheme);

    if (elements.themeToggleBtn) {
        elements.themeToggleBtn.addEventListener("click", () => {
            const currentTheme = document.documentElement.getAttribute("data-theme") || "dark";
            const newTheme = currentTheme === "dark" ? "light" : "dark";
            applyTheme(newTheme);
            localStorage.setItem("theme", newTheme);
        });
    }
}

function applyTheme(theme) {
    document.documentElement.setAttribute("data-theme", theme);
    if (elements.themeIcon) {
        elements.themeIcon.innerText = theme === "light" ? "🌙" : "☀️";
    }
}

function bindEvents() {
    elements.form.addEventListener("submit", addCustomer);
    elements.search.addEventListener("input", renderCustomers);
    elements.filter.addEventListener("change", renderCustomers);
    if (elements.refresh) {
        elements.refresh.addEventListener("click", () => loadCustomers(false));
    }
    if (elements.resetSeed) {
        elements.resetSeed.addEventListener("click", resetSampleData);
    }

    // Modal Add Customer Controls
    if (elements.openAddModal) {
        elements.openAddModal.addEventListener("click", () => {
            elements.addModal.classList.add("active");
        });
    }
    if (elements.closeAddModal) {
        elements.closeAddModal.addEventListener("click", () => {
            elements.addModal.classList.remove("active");
        });
    }
    if (elements.addModal) {
        elements.addModal.addEventListener("click", (e) => {
            if (e.target === elements.addModal) elements.addModal.classList.remove("active");
        });
    }

    // Table click listener for call buttons & transcript inspector
    elements.table.addEventListener("click", event => {
        const callBtn = event.target.closest("[data-action='call']");
        if (callBtn) {
            callCustomer(callBtn.dataset.id);
            return;
        }

        const inspectBtn = event.target.closest("[data-action='inspect']");
        if (inspectBtn) {
            openTranscriptModal(inspectBtn.dataset.id);
        }
    });

    // Modal controls
    elements.closeModal.addEventListener("click", closeModal);
    elements.closeModalFooter.addEventListener("click", closeModal);
    elements.modal.addEventListener("click", (e) => {
        if (e.target === elements.modal) closeModal();
    });

    elements.modalCallBtn.addEventListener("click", () => {
        if (state.activeModalCustomerId) {
            callCustomer(state.activeModalCustomerId);
        }
    });
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, options);
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(data.error || "Request failed.");
    }
    return data;
}

async function loadCustomers(isSilent = false) {
    try {
        const customers = await requestJson("/api/customers");
        state.customers = Array.isArray(customers) ? customers : [];
        renderCustomers();
        updateStats();
    } catch (error) {
        if (!isSilent) {
            setTableMessage(error.message);
            showToast(error.message, true);
        }
    }
}

function renderCustomers() {
    const customers = getVisibleCustomers();

    if (!customers.length) {
        setTableMessage("No agent tasks found matching filter.");
        updateStats();
        return;
    }

    elements.table.innerHTML = customers.map(customer => {
        const status = normalizeStatus(customer.status);
        const statusPill = getStatusPillMarkup(status);
        const rating = renderRatingStars(customer.rating);
        const sentiment = renderSentimentTag(customer.sentiment);
        const feedbackList = renderFeedbackList(customer.feedback);
        const actionMarkup = getActionMarkup(customer, status);

        return `
            <tr>
                <td>
                    <div class="customer-meta">
                        <span class="customer-name">Survey: ${escapeHtml(customer.name || "Customer")}</span>
                        <span class="customer-id">Task ID: ${escapeHtml(customer.id || "")}</span>
                    </div>
                </td>
                <td><strong>${escapeHtml(customer.phone || "-")}</strong></td>
                <td>${statusPill}</td>
                <td>${rating}</td>
                <td>
                    <div class="feedback-box">
                        ${sentiment}
                        ${feedbackList}
                    </div>
                </td>
                <td>
                    <div class="actions-cell">
                        ${actionMarkup}
                        <button class="btn btn-secondary btn-sm icon-only" data-action="inspect" data-id="${customer.id}" title="Inspect Spoken Conversation">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

function getStatusPillMarkup(status) {
    if (status === "calling") {
        return '<span class="status-pill calling"><span class="pulse-dot"></span> In progress</span>';
    } else if (status === "completed") {
        return '<span class="status-pill completed">✓ Completed</span>';
    } else if (status === "failed") {
        return '<span class="status-pill failed">Failed</span>';
    } else {
        return '<span class="status-pill pending">⏳ Waiting</span>';
    }
}

function renderRatingStars(rating) {
    const num = Number(rating);
    if (!num || isNaN(num)) return '<span class="text-muted" style="font-size: 0.8rem;">Pending Rating</span>';
    const stars = '★'.repeat(Math.min(5, Math.max(1, Math.round(num))));
    return `<span class="rating-stars">${stars} (${num}/5)</span>`;
}

function renderSentimentTag(sentiment) {
    const s = String(sentiment || "Neutral").toLowerCase();
    return `<span class="sentiment-tag ${s}">${escapeHtml(sentiment || "Neutral")}</span>`;
}

function renderFeedbackList(feedback) {
    if (!feedback || !Array.isArray(feedback) || feedback.length === 0) {
        return '<span class="feedback-item text-muted">No spoken feedback recorded yet</span>';
    }
    return feedback.map(item => `<div class="feedback-item">"${escapeHtml(item)}"</div>`).join("");
}

function getVisibleCustomers() {
    const search = elements.search.value.trim().toLowerCase();
    const filter = elements.filter.value;

    return state.customers.filter(customer => {
        const status = normalizeStatus(customer.status);
        const matchesStatus = filter === "all" || status === filter;
        const searchable = `${customer.name || ""} ${customer.phone || ""}`.toLowerCase();
        const matchesSearch = !search || searchable.includes(search);
        return matchesStatus && matchesSearch;
    });
}

function getActionMarkup(customer, status) {
    if (status === "calling") {
        return '';
    }
    const id = escapeHtml(customer.id);
    return `<button class="btn btn-primary btn-sm" type="button" data-action="call" data-id="${id}">Start Call</button>`;
}

function updateStats() {
    const total = state.customers.length;
    const completed = state.customers.filter(c => normalizeStatus(c.status) === "completed").length;
    const pending = state.customers.filter(c => {
        const s = normalizeStatus(c.status);
        return s === "pending" || s === "initiated" || s === "calling";
    }).length;

    if (elements.totalCustomers) elements.totalCustomers.innerText = total;
    if (elements.pendingCustomers) elements.pendingCustomers.innerText = pending;
    if (elements.completedCustomers) elements.completedCustomers.innerText = completed;

    const satisfactionRate = total > 0 ? Math.round((completed / total) * 100) : 96;
    if (elements.statSatisfaction) elements.statSatisfaction.innerText = `${satisfactionRate}%`;
    if (elements.statCompletion) elements.statCompletion.innerText = `${total > 0 ? Math.round((completed / total) * 100) : 91}%`;
}

async function addCustomer(event) {
    event.preventDefault();
    const name = elements.name.value.trim();
    const phone = elements.phone.value.trim();

    if (!name || !phone) {
        showToast("Enter customer name and phone number.", true);
        return;
    }

    setButtonLoading(elements.addButton, true, "Adding...");

    try {
        await requestJson("/api/customers", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, phone })
        });

        elements.form.reset();
        if (elements.addModal) elements.addModal.classList.remove("active");
        await loadCustomers();
        showToast("Agent task queued successfully.");
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setButtonLoading(elements.addButton, false, "Queue Agent Task");
    }
}

async function callCustomer(customerId) {
    try {
        const result = await requestJson("/api/call", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ customer_id: customerId })
        });

        showToast(result.message || "Call initiated successfully.");
        await loadCustomers();
        openTranscriptModal(customerId);
    } catch (error) {
        showToast(error.message, true);
        await loadCustomers();
    }
}

async function resetSampleData() {
    try {
        await requestJson("/api/seed", { method: "POST" });
        showToast("Sample data reset successfully.");
        await loadCustomers();
    } catch (err) {
        showToast("Failed to reset sample data.", true);
    }
}

// Modal Transcript Inspector
function openTranscriptModal(customerId) {
    state.activeModalCustomerId = customerId;
    elements.modal.classList.add("active");
    updateModalTranscript(customerId);
}

function closeModal() {
    state.activeModalCustomerId = null;
    elements.modal.classList.remove("active");
}

function updateModalTranscript(customerId) {
    const customer = state.customers.find(c => String(c.id) === String(customerId));
    if (!customer) return;

    elements.modalName.innerText = `${customer.name}'s Feedback Transcript`;
    elements.modalPhone.innerText = customer.phone;
    elements.modalStatus.innerText = statusLabel(customer.status);
    
    const sent = customer.sentiment || "Neutral";
    elements.modalSentiment.innerText = sent;
    elements.modalSentiment.className = `sentiment-tag ${sent.toLowerCase()}`;

    const transcript = customer.transcript || [];
    if (!transcript.length) {
        elements.modalConversation.innerHTML = `<div class="transcript-empty">No spoken conversation recorded yet.<br>Click "Start Call Now" to initiate voice survey.</div>`;
        return;
    }

    elements.modalConversation.innerHTML = transcript.map(msg => {
        const isAI = msg.speaker === "ai";
        const label = isAI ? "Voice AI Agent" : customer.name;
        return `
            <div class="chat-bubble ${isAI ? "ai" : "customer"}">
                <span class="speaker-name">${escapeHtml(label)}</span>
                ${escapeHtml(msg.text)}
            </div>
        `;
    }).join("");

    elements.modalConversation.scrollTop = elements.modalConversation.scrollHeight;
}

function setTableMessage(message) {
    elements.table.innerHTML = `
        <tr>
            <td colspan="6" class="empty-cell">${escapeHtml(message)}</td>
        </tr>
    `;
}

function setButtonLoading(button, loading, label) {
    button.disabled = loading;
    button.innerText = label;
}

function showToast(message, isError = false) {
    window.clearTimeout(state.toastTimer);
    elements.toast.innerText = message;
    elements.toast.className = `toast-notification active${isError ? " error" : ""}`;
    state.toastTimer = window.setTimeout(() => {
        elements.toast.className = "toast-notification";
    }, 3500);
}

function normalizeStatus(status) {
    const value = String(status || "pending").toLowerCase();
    return value.replace(/[^a-z0-9_-]/g, "") || "pending";
}

function statusLabel(status) {
    const labels = {
        pending: "Waiting Queue",
        initiated: "Dialing...",
        calling: "Active Call",
        completed: "Completed",
        failed: "Call Failed"
    };
    return labels[status] || status;
}

function escapeHtml(value) {
    return String(value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}
