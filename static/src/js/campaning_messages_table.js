/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart } from "@odoo/owl";

class CampaignMessagesAction extends Component {
    static props = { campaign_id: [Number, String] };
    static template = "odoo17_sms_plugin.CampaignMessagesTable";

    setup() {
        this.orm = this.env.services.orm;
        this.resModel = "sms.message";

        // campaignId: props -> URL
        const fromProps = this.props?.campaign_id ?? null;
        const m = window.location.pathname.match(/\/my\/sms_campaigns\/(\d+)/);
        const fromUrl = m ? Number(m[1]) : null;
        this.campaignId = Number(fromProps ?? fromUrl ?? 0) || null;

        // Pole w modelu odpowiedzialne za numer telefonu (wykrywane dynamicznie)
        this.phoneField = null;

        this.state = useState({
            rows: [],
            currentPage: 1,
            pageSize: 10,
            search: "",
            sortBy: "partner_name",
            sortDir: "asc",
            editing: { id: null, body: "", phone: "" },
            campaignClosed: false,
        });

        onWillStart(async () => {
            await this.loadCampaignClosedFlag();
            await this.loadPhoneField();
            await this.fetchAll();
        });
    }

    // ===== Helpers =====
    _closedStates = () => ["done", "running", "finished", "cancel", "cancelled", "closed", "sent", "inactive"];

    loadCampaignClosedFlag = async () => {
        if (!this.campaignId) {
            this.state.campaignClosed = false;
            return;
        }
        const candidates = [
            { model: "sms.campaign", fields: ["state"] },
        ];
        const closedSet = new Set(this._closedStates());
        for (const c of candidates) {
            try {
                const [rec] = await this.orm.read(c.model, [this.campaignId], c.fields);
                if (!rec) continue;
                const st = String(rec.state || rec.stage || rec.status || "").toLowerCase();
                this.state.campaignClosed = !!rec.is_closed || rec.active === false || closedSet.has(st);
                return;
            } catch (_) {
                // model może nie istnieć – próbuj następny
            }
        }
        this.state.campaignClosed = false;
    };

    loadPhoneField = async () => {
        // Spróbuj wykryć istniejące pole w sms.message, które może trzymać numer telefonu
        try {
            const fields = await this.orm.call(this.resModel, "fields_get", [[], ["string", "type"]]);
            const candidates = [
                "recipient_number",
                "to_number",
                "number",
                "phone_to",
                "phone",
                "mobile",
                "partner_phone",
                "partner_mobile",
            ];
            for (const k of candidates) {
                if (k in fields && ["char", "text"].includes(fields[k].type)) {
                    this.phoneField = k;
                    return;
                }
            }
            this.phoneField = null;
        } catch (_) {
            this.phoneField = null;
        }
    };

    ensureEditable = () => {
        if (this.state.campaignClosed) {
            this.env.services?.notification?.add?.(
                "Kampania jest zakończona. Edycja i usuwanie są wyłączone.",
                { type: "warning" }
            );
            return false;
        }
        return true;
    };

    // ===== RPC =====
    fetchAll = async () => {
        const domain = [["campaign_id", "=", this.campaignId]];
        const ids = await this.orm.search(this.resModel, domain);
        if (!ids.length) {
            this.state.rows = [];
            this.state.currentPage = 1;
            return;
        }
        const readFields = [
            "body",
            "partner_id",
            "sms_gateway_response",
            "sms_gateway_response_human",
        ];
        if (this.phoneField) readFields.push(this.phoneField);

        const records = await this.orm.read(this.resModel, ids, readFields);
        this.state.rows = records.map((r) => ({
            id: r.id,
            partner_name: r.partner_id ? r.partner_id[1] : "",
            message_body: r.body || "",
            response: r.sms_gateway_response_human || r.sms_gateway_response || "",
            phone: this.phoneField ? (r[this.phoneField] || "") : "", // dla modala
        }));
        this.state.currentPage = 1;
    };

    // ===== Search =====
    onSearchInput = (ev) => {
        this.state.search = ev.target.value || "";
        this.state.currentPage = 1;
    };

    // ===== Sort =====
    onHeaderClick = (ev) => {
        const col = ev.currentTarget.dataset.col; // z data-col w <th>
        if (!col) return;
        if (this.state.sortBy === col) {
            this.state.sortDir = this.state.sortDir === "asc" ? "desc" : "asc";
        } else {
            this.state.sortBy = col;
            this.state.sortDir = "asc";
        }
        this.state.currentPage = 1;
    };

    sortIndicator = (col) => {
        if (this.state.sortBy !== col) return "";
        return this.state.sortDir === "asc" ? "▲" : "▼";
    };

    // ===== Data pipeline =====
    filteredRows = () => {
        const q = (this.state.search || "").trim().toLowerCase();
        if (!q) return this.state.rows;
        const keys = ["partner_name", "message_body", "response", "phone"];
        return this.state.rows.filter((r) =>
            keys.some((k) => (r[k] || "").toString().toLowerCase().includes(q))
        );
    };

    sortedRows = () => {
        const list = [...this.filteredRows()];
        const { sortBy, sortDir } = this.state;
        return list.sort((a, b) => {
            const va = (a[sortBy] ?? "").toString().toLowerCase();
            const vb = (b[sortBy] ?? "").toString().toLowerCase();
            if (va < vb) return sortDir === "asc" ? -1 : 1;
            if (va > vb) return sortDir === "asc" ? 1 : -1;
            return 0;
        });
    };

    paginatedRows = () => {
        const list = this.sortedRows();
        const start = (this.state.currentPage - 1) * this.state.pageSize;
        return list.slice(start, start + this.state.pageSize);
    };

    totalPages = () => Math.max(1, Math.ceil(this.filteredRows().length / this.state.pageSize));

    pageNumbers = () => {
        const n = this.totalPages();
        const arr = [];
        for (let i = 1; i <= n; i++) arr.push(i);
        return arr;
    };

    // ===== Pagination =====
    onPrevPage = () => {
        if (this.state.currentPage > 1) this.state.currentPage--;
    };
    onNextPage = () => {
        if (this.state.currentPage < this.totalPages()) this.state.currentPage++;
    };
    onGoToPage = (ev) => {
        const page = Number(ev.currentTarget.dataset.page);
        if (page >= 1 && page <= this.totalPages()) this.state.currentPage = page;
    };

    // ===== CRUD (arrow functions, żeby nie gubić this) =====
    updateMessage = (row) => {
        if (!this.ensureEditable()) return;
        this.state.editing = {
            id: row.id,
            body: row.message_body || "",
            phone: row.phone || "",
        };
    };

    saveMessage = async () => {
        if (!this.ensureEditable()) return;
        const e = this.state.editing;
        if (!e || !e.id) return;

        const vals = { body: e.body };
        if (this.phoneField) vals[this.phoneField] = (e.phone || "").trim();

        await this.orm.write(this.resModel, [e.id], vals);

        const i = this.state.rows.findIndex((r) => r.id === e.id);
        if (i !== -1) {
            this.state.rows[i] = {
                ...this.state.rows[i],
                message_body: e.body,
                ...(this.phoneField ? { phone: (e.phone || "").trim() } : {}),
            };
        }

        this.state.editing = { id: null, body: "", phone: "" };
        document.querySelector('#exampleModal [data-bs-dismiss="modal"]')?.click();
    };

    deleteMessage = async (row) => {
        if (!this.ensureEditable()) return;

        await this.orm.unlink(this.resModel, [row.id]);
        this.state.rows = this.state.rows.filter((r) => r.id !== row.id);

        const tp = this.totalPages();
        if (this.state.currentPage > tp) this.state.currentPage = tp;

        if (this.state.editing?.id === row.id) {
            this.state.editing = { id: null, body: "", phone: "" };
        }
    };
}

registry.category("public_components").add(
    "odoo17_sms_plugin.CampaignMessagesTable",
    CampaignMessagesAction
);
