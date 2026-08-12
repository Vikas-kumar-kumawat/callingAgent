const state = {
    customers: [],
    campaignRunning: false,
    toastTimer: null,
    pollInterval: null,
    activeModalCustomerId: null
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    bindEvents();
    checkHealth();
    loadCampaignStatus();
    loadCustomers();

    // Auto-refresh every 2.5 seconds for live call & status updates
    state.pollInterval = setInterval(() => {
        loadCustomers(true);
        loadCampaignStatus(true);
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
    elements.campaignBadge = document.getElementById("campaignStatusBadge");
    elements.campaignLabel = document.getElementById("campaignStatusLabel");
    elements.startCampaign = document.getElementById("startCampaignBtn");
    elements.stopCampaign = document.getElementById("stopCampaignBtn");
    elements.toast = document.getElementById("toast");
    elements.ngrokText = document.getElementById("ngrokStatusText");

    // Modal elements
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

function bindEvents() {
    elements.form.addEventListener("submit", addCustomer);
    elements.search.addEventListener("input", renderCustomers);
    elements.filter.addEventListener("change", renderCustomers);
    elements.refresh.addEventListener("click", () => loadCustomers(false));
    if (elements.resetSeed) {
        elements.resetSeed.addEventListener("click", resetSampleData);
    }
    elements.startCampaign.addEventListener("click", startCampaign);
    elements.stopCampaign.addEventListener("click", stopCampaign);

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

async function checkHealth() {
    try {
        const data = await requestJson("/api/health");
        if (data.base_url) {
            elements.ngrokText.innerText = `Tunnel: ${data.base_url.replace('https://', '')}`;
        }
    } catch (e) {
        elements.ngrokText.innerText = "Local Flask Active";
    }
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

async function loadCampaignStatus(isSilent = false) {
    try {
        const result = await requestJson("/api/campaign");
        updateCampaignStatus(Boolean(result.running));
    } catch {
        if (!isSilent) updateCampaignStatus(false);
    }
}

function renderCustomers() {
    const customers = getVisibleCustomers();

    if (!customers.length) {
        setTableMessage("No customers found matching filter.");
        updateStats();
        return;
    }

    elements.table.innerHTML = customers.map(customer => {
        const status = normalizeStatus(customer.status);
        const rating = renderRatingStars(customer.rating);
        const sentiment = renderSentimentTag(customer.sentiment);
        const feedbackList = renderFeedbackList(customer.feedback);
        const actionMarkup = getActionMarkup(customer, status);

        return `
            <tr>
                <td>
                    <div class="customer-meta">
                        <span class="customer-name">${escapeHtml(customer.name || "Customer")}</span>
                        <span class="customer-id">ID: ${escapeHtml(customer.id || "")}</span>
                    </div>
                </td>
                <td><strong>${escapeHtml(customer.phone || "-")}</strong></td>
                <td><span class="badge ${status}">${statusLabel(status)}</span></td>
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
                        <button class="btn btn-secondary icon-only" data-action="inspect" data-id="${customer.id}" title="Inspect Live Transcript">
                            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
                        </button>
                    </div>
                </td>
            </tr>
        `;
    }).join("");
}

function renderRatingStars(rating) {
    const num = Number(rating);
    if (!num || isNaN(num)) return '<span class="text-muted" style="font-size: 0.8rem;">Pending</span>';
    const stars = '★'.repeat(Math.min(5, Math.max(1, Math.round(num))));
    return `<span class="rating-stars">${stars} (${num}/5)</span>`;
}

function renderSentimentTag(sentiment) {
    const s = String(sentiment || "Neutral").toLowerCase();
    return `<span class="sentiment-tag ${s}">${escapeHtml(sentiment || "Neutral")}</span>`;
}

function renderFeedbackList(feedback) {
    if (!feedback || !Array.isArray(feedback) || feedback.length === 0) {
        return '<span class="feedback-item text-muted">No feedback recorded yet</span>';
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
        return '<button class="btn btn-success" type="button" data-action="inspect" data-id="' + customer.id + '"><span class="pulse-dot"></span> In Call...</button>';
    }
    const id = escapeHtml(customer.id);
    return `<button class="btn btn-primary" type="button" data-action="call" data-id="${id}">Start Call</button>`;
}

function updateStats() {
    const total = state.customers.length;
    const completed = state.customers.filter(c => normalizeStatus(c.status) === "completed").length;
    const pending = state.customers.filter(c => {
        const s = normalizeStatus(c.status);
        return s === "pending" || s === "initiated";
    }).length;
    
    const ratings = state.customers
        .map(c => Number(c.rating))
        .filter(r => Number.isFinite(r) && r > 0);
        
    const average = ratings.length
        ? (ratings.reduce((sum, r) => sum + r, 0) / ratings.length).toFixed(1) + " / 5"
        : "-";

    document.getElementById("totalCustomers").innerText = total;
    document.getElementById("pendingCustomers").innerText = pending;
    document.getElementById("completedCustomers").innerText = completed;
    document.getElementById("averageRating").innerText = average;
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
        await loadCustomers();
        showToast("Customer queued successfully.");
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setButtonLoading(elements.addButton, false, "Add to Call Queue");
    }
}

async function callCustomer(customerId) {
    const customer = state.customers.find(item => String(item.id) === String(customerId));
    const label = customer ? `${customer.name} (${customer.phone})` : "customer";

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

async function startCampaign() {
    setButtonLoading(elements.startCampaign, true, "Starting...");
    try {
        const result = await requestJson("/api/campaign/start", { method: "POST" });
        updateCampaignStatus(Boolean(result.running));
        showToast("Autodialer campaign started.");
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setButtonLoading(elements.startCampaign, false, "Start Campaign");
    }
}

async function stopCampaign() {
    setButtonLoading(elements.stopCampaign, true, "Stopping...");
    try {
        const result = await requestJson("/api/campaign/stop", { method: "POST" });
        updateCampaignStatus(Boolean(result.running));
        showToast("Campaign stopped.");
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setButtonLoading(elements.stopCampaign, false, "Stop");
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

function updateCampaignStatus(running) {
    state.campaignRunning = running;
    elements.campaignLabel.innerText = running ? "Campaign Active" : "Stopped";
    elements.campaignBadge.className = `status-pill ${running ? "running" : "stopped"}`;
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

    elements.modalName.innerText = `${customer.name}'s Call Intelligence`;
    elements.modalPhone.innerText = customer.phone;
    elements.modalStatus.innerText = statusLabel(customer.status);
    
    const sent = customer.sentiment || "Neutral";
    elements.modalSentiment.innerText = sent;
    elements.modalSentiment.className = `sentiment-tag ${sent.toLowerCase()}`;

    const transcript = customer.transcript || [];
    if (!transcript.length) {
        elements.modalConversation.innerHTML = `<div class="transcript-empty">No spoken conversation recorded yet.<br>Click "Start AI Call Now" to initiate voice survey.</div>`;
        return;
    }

    elements.modalConversation.innerHTML = transcript.map(msg => {
        const isAI = msg.speaker === "ai";
        const label = isAI ? "Sarah (AI Agent)" : customer.name;
        return `
            <div class="chat-bubble ${isAI ? "ai" : "customer"}">
                <span class="speaker-name">${escapeHtml(label)}</span>
                ${escapeHtml(msg.text)}
            </div>
        `;
    }).join("");

    // Auto-scroll to bottom of conversation
    elements.modalConversation.scrollTop = elements.modalConversation.scrollHeight;
}

function setTableMessage(message) {
    elements.table.innerHTML = `
        <tr>
            <td colspan="6" class="state-cell">${escapeHtml(message)}</td>
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
