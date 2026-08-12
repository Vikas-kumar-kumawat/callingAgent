const state = {
    customers: [],
    voices: [],
    activeVoiceId: null,
    toastTimer: null,
    pollInterval: null,
    activeModalCustomerId: null,
    activeDetailCustomerId: null
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
    cacheElements();
    initTheme();
    initAuth();
    bindEvents();
});

function cacheElements() {
    // Auth Elements
    elements.loginOverlay = document.getElementById("loginOverlay");
    elements.loginForm = document.getElementById("loginForm");
    elements.adminUsername = document.getElementById("adminUsername");
    elements.adminPassword = document.getElementById("adminPassword");
    elements.loginErrorMsg = document.getElementById("loginErrorMsg");
    elements.dashboardApp = document.getElementById("dashboardApp");
    elements.logoutBtn = document.getElementById("logoutBtn");

    // Voice Selector Elements
    elements.voiceSelect = document.getElementById("voiceSelect");
    elements.playVoiceDemoBtn = document.getElementById("playVoiceDemoBtn");

    // Dashboard Elements
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

    // Detailed Feedback Modal Page
    elements.detailModal = document.getElementById("feedbackDetailModal");
    elements.closeDetailModal = document.getElementById("closeDetailModalBtn");
    elements.closeDetailFooter = document.getElementById("closeDetailFooterBtn");
    elements.detailName = document.getElementById("detailCustomerName");
    elements.detailPhone = document.getElementById("detailCustomerPhone");
    elements.detailRating = document.getElementById("detailCustomerRating");
    elements.detailSentiment = document.getElementById("detailCustomerSentiment");
    elements.detailStatus = document.getElementById("detailCustomerStatus");
    elements.detailQuotes = document.getElementById("detailFeedbackQuotes");
    elements.detailConversation = document.getElementById("detailConversation");
    elements.detailCallBtn = document.getElementById("detailCallBtn");
    elements.detailClearBtn = document.getElementById("detailClearFeedbackBtn");

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

function initAuth() {
    const isAuthenticated = localStorage.getItem("adminAuth") === "true";

    if (isAuthenticated) {
        unlockDashboard();
    } else {
        lockDashboard();
    }
}

function unlockDashboard() {
    if (elements.loginOverlay) elements.loginOverlay.classList.add("hidden");
    if (elements.dashboardApp) elements.dashboardApp.classList.remove("hidden-auth");
    
    loadVoices();
    loadCustomers();

    if (!state.pollInterval) {
        state.pollInterval = setInterval(() => {
            loadCustomers(true);
            if (state.activeModalCustomerId) {
                updateModalTranscript(state.activeModalCustomerId);
            }
            if (state.activeDetailCustomerId) {
                updateDetailModal(state.activeDetailCustomerId);
            }
        }, 2500);
    }
}

function lockDashboard() {
    if (elements.loginOverlay) elements.loginOverlay.classList.remove("hidden");
    if (elements.dashboardApp) elements.dashboardApp.classList.add("hidden-auth");
    
    if (state.pollInterval) {
        clearInterval(state.pollInterval);
        state.pollInterval = null;
    }
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

async function loadVoices() {
    try {
        const res = await requestJson("/api/voices");
        if (res && res.voices) {
            state.voices = res.voices;
            state.activeVoiceId = res.active_voice;
            renderVoiceDropdown();
        }
    } catch (err) {
        console.warn("Failed to load voices:", err);
    }
}

function renderVoiceDropdown() {
    if (!elements.voiceSelect || !state.voices.length) return;

    elements.voiceSelect.innerHTML = state.voices.map(voice => {
        const icon = voice.gender === "Female" ? "👩 " : "👨 ";
        return `
            <option value="${voice.id}" ${voice.id === state.activeVoiceId ? "selected" : ""}>
                ${icon} ${escapeHtml(voice.name)}
            </option>
        `;
    }).join("");
}

async function changeActiveVoice(voiceId) {
    try {
        const res = await requestJson("/api/voices", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ voice_id: voiceId })
        });
        if (res && res.success) {
            state.activeVoiceId = res.active_voice;
            showToast(`Voice set to: ${res.voice_info ? res.voice_info.name : voiceId}`);
            playVoiceDemoAudio(voiceId);
        }
    } catch (err) {
        showToast(err.message, true);
    }
}

function playVoiceDemoAudio(voiceId) {
    const vId = voiceId || state.activeVoiceId;
    const voiceInfo = state.voices.find(v => v.id === vId) || state.voices[0];
    
    if (elements.playVoiceDemoBtn) {
        elements.playVoiceDemoBtn.innerText = "🔊 Playing...";
    }

    const audioUrl = `/api/demo-audio?voice_id=${encodeURIComponent(vId)}&t=${Date.now()}`;
    const audio = new Audio(audioUrl);
    
    audio.play().then(() => {
        audio.onended = () => {
            if (elements.playVoiceDemoBtn) elements.playVoiceDemoBtn.innerText = "🔊 Demo";
        };
        audio.onerror = () => {
            fallbackSpeechSynthesis(voiceInfo);
        };
    }).catch(err => {
        console.warn("Audio play error, falling back to Web Speech:", err);
        fallbackSpeechSynthesis(voiceInfo);
    });
}

function fallbackSpeechSynthesis(voiceInfo) {
    if ('speechSynthesis' in window) {
        window.speechSynthesis.cancel();
        const textToSpeak = voiceInfo ? voiceInfo.sample_text : "Hello! I am your AI Voice Assistant.";
        const utterance = new SpeechSynthesisUtterance(textToSpeak);
        
        if (voiceInfo && voiceInfo.gender === "Male") {
            utterance.pitch = 0.92;
            utterance.rate = 0.95;
        } else {
            utterance.pitch = 1.1;
            utterance.rate = 1.0;
        }

        if (elements.playVoiceDemoBtn) {
            elements.playVoiceDemoBtn.innerText = "🔊 Playing...";
            utterance.onend = () => { if (elements.playVoiceDemoBtn) elements.playVoiceDemoBtn.innerText = "🔊 Demo"; };
            utterance.onerror = () => { if (elements.playVoiceDemoBtn) elements.playVoiceDemoBtn.innerText = "🔊 Demo"; };
        }
        window.speechSynthesis.speak(utterance);
    } else {
        if (elements.playVoiceDemoBtn) elements.playVoiceDemoBtn.innerText = "🔊 Demo";
    }
}

function bindEvents() {
    // Voice Selection Event
    if (elements.voiceSelect) {
        elements.voiceSelect.addEventListener("change", (e) => {
            changeActiveVoice(e.target.value);
        });
    }

    if (elements.playVoiceDemoBtn) {
        elements.playVoiceDemoBtn.addEventListener("click", () => {
            playVoiceDemoAudio();
        });
    }

    // Login Form Submit
    if (elements.loginForm) {
        elements.loginForm.addEventListener("submit", (e) => {
            e.preventDefault();
            const user = elements.adminUsername.value.trim();
            const pass = elements.adminPassword.value.trim();

            if (user.toUpperCase() === "VIKAS" && pass === "7014") {
                localStorage.setItem("adminAuth", "true");
                elements.loginErrorMsg.classList.add("hidden");
                unlockDashboard();
                showToast("Welcome Admin VIKAS! Access granted.");
            } else {
                elements.loginErrorMsg.classList.remove("hidden");
            }
        });
    }

    // Logout Action
    if (elements.logoutBtn) {
        elements.logoutBtn.addEventListener("click", () => {
            localStorage.removeItem("adminAuth");
            lockDashboard();
            showToast("Portal locked. Logged out successfully.");
        });
    }

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

    // Table action listener
    elements.table.addEventListener("click", event => {
        // Priority 1: Clear feedback button
        const deleteFeedbackBtn = event.target.closest("[data-action='delete-feedback']");
        if (deleteFeedbackBtn) {
            event.stopPropagation();
            deleteFeedback(deleteFeedbackBtn.dataset.id);
            return;
        }

        // Priority 2: Start call button
        const callBtn = event.target.closest("[data-action='call']");
        if (callBtn) {
            event.stopPropagation();
            callCustomer(callBtn.dataset.id);
            return;
        }

        // Priority 3: Delete customer task button
        const deleteCustomerBtn = event.target.closest("[data-action='delete-customer']");
        if (deleteCustomerBtn) {
            event.stopPropagation();
            deleteCustomer(deleteCustomerBtn.dataset.id);
            return;
        }

        // Priority 4: Quick transcript button
        const inspectBtn = event.target.closest("[data-action='inspect']");
        if (inspectBtn) {
            event.stopPropagation();
            openTranscriptModal(inspectBtn.dataset.id);
            return;
        }

        // Priority 5: Click anywhere on row / feedback box / customer name -> Open Details Page!
        const row = event.target.closest("tr[data-customer-id]");
        if (row) {
            openDetailModal(row.dataset.customerId);
        }
    });

    // Transcript Modal controls
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

    // Detailed Feedback Modal controls
    elements.closeDetailModal.addEventListener("click", closeDetailModal);
    elements.closeDetailFooter.addEventListener("click", closeDetailModal);
    elements.detailModal.addEventListener("click", (e) => {
        if (e.target === elements.detailModal) closeDetailModal();
    });

    elements.detailCallBtn.addEventListener("click", () => {
        if (state.activeDetailCustomerId) {
            callCustomer(state.activeDetailCustomerId);
        }
    });

    elements.detailClearBtn.addEventListener("click", () => {
        if (state.activeDetailCustomerId) {
            deleteFeedback(state.activeDetailCustomerId);
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
        return;
    }

    elements.table.innerHTML = customers.map(customer => {
        const status = normalizeStatus(customer.status);
        const statusPill = getStatusPillMarkup(status);
        const rating = renderRatingStars(customer.rating);
        const sentiment = renderSentimentTag(customer.sentiment);
        const feedbackList = renderFeedbackList(customer, customer.feedback);
        const actionMarkup = getActionMarkup(customer, status);

        return `
            <tr data-customer-id="${customer.id}" class="clickable-row" title="Click to view full customer feedback details">
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
                    <div class="feedback-box clickable-feedback-box">
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
                        <button class="btn btn-danger btn-sm icon-only" data-action="delete-customer" data-id="${customer.id}" title="Delete Customer Task">
                            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"></polyline><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path></svg>
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

function renderFeedbackList(customer, feedback) {
    if (!feedback || !Array.isArray(feedback) || feedback.length === 0) {
        return `
            <div class="feedback-content-wrap">
                <span class="feedback-item text-muted">No feedback recorded yet (Click to inspect)</span>
            </div>
        `;
    }
    const quotes = feedback.map(item => `<div class="feedback-item">"${escapeHtml(item)}"</div>`).join("");
    return `
        <div class="feedback-content-wrap">
            ${quotes}
            <div class="feedback-footer-row">
                <span class="inspect-hint">View Details ↗</span>
                <button class="clear-feedback-btn" data-action="delete-feedback" data-id="${customer.id}" title="Clear Feedback History">
                    Clear ✕
                </button>
            </div>
        </div>
    `;
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

function normalizePhone(phone) {
    if (!phone) return "";
    let cleaned = phone.replace(/[^\d+]/g, "").trim();
    if (!cleaned) return "";
    if (cleaned.startsWith("+")) return cleaned;
    if (cleaned.startsWith("00")) return "+" + cleaned.slice(2);
    if (cleaned.startsWith("0") && cleaned.length === 11) cleaned = cleaned.slice(1);
    if (cleaned.length === 10) return "+91" + cleaned;
    if (cleaned.length === 12 && cleaned.startsWith("91")) return "+" + cleaned;
    return "+" + cleaned;
}

async function addCustomer(event) {
    event.preventDefault();
    const name = elements.name.value.trim();
    const rawPhone = elements.phone.value.trim();

    if (!name || !rawPhone) {
        showToast("Enter customer name and phone number.", true);
        return;
    }

    const phone = normalizePhone(rawPhone);

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

async function deleteCustomer(customerId) {
    const customer = state.customers.find(item => String(item.id) === String(customerId));
    const name = customer ? customer.name : "customer";

    if (!confirm(`Are you sure you want to delete ${name}?`)) return;

    try {
        await requestJson(`/api/customers/${customerId}`, { method: "DELETE" });
        showToast(`Deleted ${name} successfully.`);
        if (state.activeDetailCustomerId === customerId) closeDetailModal();
        await loadCustomers();
    } catch (error) {
        showToast(error.message, true);
    }
}

async function deleteFeedback(customerId) {
    const customer = state.customers.find(item => String(item.id) === String(customerId));
    const name = customer ? customer.name : "customer";

    if (!confirm(`Clear feedback history for ${name}?`)) return;

    try {
        await requestJson(`/api/customers/${customerId}/feedback`, { method: "DELETE" });
        showToast(`Cleared feedback for ${name}.`);
        await loadCustomers();
        if (state.activeDetailCustomerId === customerId) {
            updateDetailModal(customerId);
        }
    } catch (error) {
        showToast(error.message, true);
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

// Ultra-Clean Detailed Feedback Modal Inspector Page
function openDetailModal(customerId) {
    state.activeDetailCustomerId = customerId;
    elements.detailModal.classList.add("active");
    updateDetailModal(customerId);
}

function closeDetailModal() {
    state.activeDetailCustomerId = null;
    elements.detailModal.classList.remove("active");
}

function updateDetailModal(customerId) {
    const customer = state.customers.find(c => String(c.id) === String(customerId));
    if (!customer) return;

    elements.detailName.innerText = customer.name || "Customer";
    elements.detailPhone.innerText = customer.phone || "";
    elements.detailRating.innerHTML = renderRatingStars(customer.rating);
    
    const sent = customer.sentiment || "Neutral";
    elements.detailSentiment.innerText = sent;
    elements.detailSentiment.className = `sentiment-tag ${sent.toLowerCase()}`;

    const status = normalizeStatus(customer.status);
    elements.detailStatus.innerText = statusLabel(status);
    elements.detailStatus.className = `status-pill ${status}`;

    // Render clean spoken feedback quotes
    const quotes = customer.feedback || [];
    if (!quotes.length) {
        elements.detailQuotes.innerHTML = `<div class="clean-quote-item text-muted">No spoken feedback recorded yet.</div>`;
    } else {
        elements.detailQuotes.innerHTML = quotes.map(q => `
            <div class="clean-quote-item">
                💬 "${escapeHtml(q)}"
            </div>
        `).join("");
    }

    // Render clean full call conversation dialogue
    const transcript = customer.transcript || [];
    if (!transcript.length) {
        elements.detailConversation.innerHTML = `<div class="transcript-empty">No call transcript recorded yet.<br>Click "Start New Call" to initiate voice survey.</div>`;
    } else {
        elements.detailConversation.innerHTML = transcript.map(msg => {
            const isAI = msg.speaker === "ai";
            const label = isAI ? "AI Voice Agent" : customer.name;
            return `
                <div class="chat-bubble ${isAI ? "ai" : "customer"}">
                    <span class="speaker-name">${escapeHtml(label)}</span>
                    ${escapeHtml(msg.text)}
                </div>
            `;
        }).join("");
        elements.detailConversation.scrollTop = elements.detailConversation.scrollHeight;
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
