/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, useRef } from "@odoo/owl";

class IcaMovieAction extends Component {
    setup() {
        this.nameRef = useRef('name');
        this.state = useState({
            partners: [],
            partner: { name: "", email: "", phone: "" },
            activeId: null,
            // paginacja
            currentPage: 1,
            pageSize: 10,
        });
        this.resModel = 'res.partner';
        this.orm = this.env.services.orm;
        onWillStart(async () => {
            await this.getAllPartners();
        });
    }

    // Pobranie wszystkich partnerów (opcjonalnie filtrowanych po nazwie)
    async getAllPartners(name = '') {
        const domain = name ? [['name', 'ilike', name]] : [];
        const ids = await this.orm.search(this.resModel, domain);
        const records = await this.orm.read(this.resModel, ids, ['name', 'email', 'phone']);
        this.state.partners = records.map(r => ({
            id: r.id, name: r.name, email: r.email, phone: r.phone
        }));
        this.state.currentPage = 1;
    }

    async searchPartners(e) {
        if (e.type === 'click' || e.keyCode === 13) {
            const name = this.nameRef.el.value.trim();
            await this.getAllPartners(name);
            this.nameRef.el.value = '';
        }
    }

    async savePartner() {
        if (this.state.activeId) {
            await this.orm.write(this.resModel, [this.state.activeId], this.state.partner);
            const idx = this.state.partners.findIndex(p => p.id === this.state.activeId);
            if (idx !== -1) this.state.partners[idx] = { id: this.state.activeId, ...this.state.partner };
            this.state.activeId = null;
        } else {
            const newIds = await this.orm.create(this.resModel, [this.state.partner]);
            this.state.partners.push({ id: newIds[0], ...this.state.partner });
        }
        this.state.partner = { name: "", email: "", phone: "" };
    }

    updatePartner(partner) {
        this.state.partner = { name: partner.name, email: partner.email, phone: partner.phone };
        this.state.activeId = partner.id;
    }

    async deletePartner(partner) {
        await this.orm.unlink(this.resModel, [partner.id]);
        this.state.partners = this.state.partners.filter(p => p.id !== partner.id);
        if (this.state.activeId === partner.id) {
            this.state.activeId = null;
            this.state.partner = { name: "", email: "", phone: "" };
        }
    }

    // Metody paginacji
    paginatedPartners() {
        const start = (this.state.currentPage - 1) * this.state.pageSize;
        return this.state.partners.slice(start, start + this.state.pageSize);
    }

    totalPages() {
        return Math.max(1, Math.ceil(this.state.partners.length / this.state.pageSize));
    }

    prevPage() {
        if (this.state.currentPage > 1) {
            this.state.currentPage--;
        }
    }

    nextPage() {
        if (this.state.currentPage < this.totalPages()) {
            this.state.currentPage++;
        }
    }

    goToPage(page) {
        if (page >= 1 && page <= this.totalPages()) {
            this.state.currentPage = page;
        }
    }
}

IcaMovieAction.template = "odoo17_sms_plugin.ContactsTable";
registry.category("public_components").add("odoo17_sms_plugin.ContactsTable", IcaMovieAction);
