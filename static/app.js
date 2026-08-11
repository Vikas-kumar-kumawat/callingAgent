const state = {
    customers: [],
    campaignRunning: false,
    toastTimer: null,
    pollInterval: null
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    bindEvents();
    loadCampaignStatus();
    loadCustomers();
    
    // Auto refresh data every 3 seconds for live call updates
    state.pollInterval = setInterval(() => {
        loadCustomers(true);
        loadCampaignStatus(true);
    }, 3000);
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
    elements.campaignStatus = document.getElementById("campaignStatus");
    elements.startCampaign = document.getElementById("startCampaignBtn");
    elements.stopCampaign = document.getElementById("stopCampaignBtn");
    elements.toast = document.getElementById("toast");
}

function bindEvents() {
    elements.form.addEventListener("submit", addCustomer);
    elements.search.addEventListener("input", renderCustomers);
    elements.filter.addEventListener("change", renderCustomers);
    elements.refresh.addEventListener("click", () => loadCustomers(false));
    elements.startCampaign.addEventListener("click", startCampaign);
    elements.stopCampaign.addEventListener("click", stopCampaign);

    elements.table.addEventListener("click", event => {
        const button = event.target.closest("[data-call-id]");
        if (button) {
            callCustomer(button.dataset.callId);
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
    if (!isSilent && elements.table.children.length === 1 && elements.table.children[0].innerText.includes("Loading")) {
        setTableMessage("Loading customers...");
    }

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
        setTableMessage("No customers found.");
        updateStats();
        return;
    }

    elements.table.innerHTML = customers.map(customer => {
        const status = normalizeStatus(customer.status);
        const feedback = customer.feedback ? escapeHtml(customer.feedback) : '<span class="muted">-</span>';
        const rating = renderRatingStars(customer.rating);
        const action = getActionMarkup(customer, status);

        return `
            <tr>
                <td>
                    <span class="customer-name">${escapeHtml(customer.name || "Customer")}</span>
                    <span class="customer-id">ID: ${escapeHtml(customer.id || "")}</span>
                </td>
                <td>${escapeHtml(customer.phone || "-")}</td>
                <td><span class="badge ${status}">${statusLabel(status)}</span></td>
                <td>${rating}</td>
                <td>${feedback}</td>
                <td>${action}</td>
            </tr>
        `;
    }).join("");
}

function renderRatingStars(rating) {
    const num = Number(rating);
    if (!num || isNaN(num)) return '<span class="muted">-</span>';
    const stars = '★'.repeat(Math.min(5, Math.max(1, Math.round(num)))) + '☆'.repeat(5 - Math.min(5, Math.max(1, Math.round(num))));
    return `<span style="color: #f59e0b; font-weight: bold;">${stars} (${num}/5)</span>`;
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
        return '<span class="badge calling">In Call...</span>';
    }
    if (status === "completed") {
        return '<span class="muted">Call Completed</span>';
    }

    const id = escapeHtml(customer.id || customer.phone);

    return `
        <button class="btn primary" type="button" data-call-id="${id}">
            Start Call
        </button>
    `;
}

function updateStats() {
    const total = state.customers.length;
    const completed = state.customers.filter(c => normalizeStatus(c.status) === "completed").length;
    const pending = state.customers.filter(c => {
        const s = normalizeStatus(c.status);
        return s === "pending" || s === "initiated" || s === "failed";
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
        showToast("Customer added successfully.");
    } catch (error) {
        showToast(error.message, true);
    } finally {
        setButtonLoading(elements.addButton, false, "Add Customer");
    }
}

async function callCustomer(customerId) {
    const customer = state.customers.find(item => String(item.id || item.phone) === String(customerId));
    const label = customer ? `${customer.name} (${customer.phone})` : "customer";

    if (!window.confirm(`Initiate AI feedback call to ${label}?`)) {
        return;
    }

    try {
        const result = await requestJson("/api/call", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ customer_id: customerId })
        });

        showToast(result.message || "Call initiated.");
        await loadCustomers();
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
        showToast("Auto campaign started.");
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

function updateCampaignStatus(running) {
    state.campaignRunning = running;
    elements.campaignStatus.innerText = running ? "Campaign Active" : "Stopped";
    elements.campaignStatus.className = `campaign-status ${running ? "running" : "stopped"}`;
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
    elements.toast.className = `toast visible${isError ? " error" : ""}`;
    state.toastTimer = window.setTimeout(() => {
        elements.toast.className = "toast";
    }, 3200);
}

function normalizeStatus(status) {
    const value = String(status || "pending").toLowerCase();
    return value.replace(/[^a-z0-9_-]/g, "") || "pending";
}

function statusLabel(status) {
    const labels = {
        pending: "Waiting",
        initiated: "Queued",
        calling: "Calling",
        completed: "Completed",
        failed: "Failed"
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
