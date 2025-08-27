/** @odoo-module **/
import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, useRef, onMounted } from "@odoo/owl";

class CampaignMessagesAction extends Component {

    static props = { campaign_id: [Number, String] };

    setup() {
        console.log("propsaaaaaaaaaaaaaaaa:", this.props);         // { campaign_id: 123 }
        this.campaignId = this.props.campaign_id;  // używaj dalej w RPC itd.
        console.log('=== PROPS ANALYSIS ===');
        //console.log('Wszystkie props:', Number(this.el.parentElement.dataset.campaignId));
        console.log(this.ala);

        this.nameRef = useRef('body');
        this.state = useState({
            partners: [],
            partner: { body: "", sms_gateway_response_human: "", sender_number: "" },
            activeId: null,
            // paginacja
            currentPage: 1,
            pageSize: 10,
        });
       // this.campaignId = 1;
        this.resModel = 'sms.message';
        this.orm = this.env.services.orm;
       // onMounted(() => {
      // 1) Normalnie z props (docelowo to ma działać)
      let fromProps = this.props?.campaign_id ?? null;
      // 2) Awaryjnie z wrappera data-*
      const wrapper = this.el?.closest("#cmp-wrapper");
      let fromDataset = wrapper?.dataset?.campaignId ?? null;
      // 3) Ostatecznie z URL (np. /my/sms_campaigns/123)
      let fromUrl = null;
      const m = window.location.pathname.match(/\/my\/sms_campaigns\/(\d+)/);
      if (m) fromUrl = m[1];
      // Priorytet: props -> data-* -> URL
      this.campaignId = Number(fromProps ?? fromDataset ?? fromUrl ?? 0) || null;
      console.log("props:", this.props);               // powinno pokazać {campaign_id: ...}
      console.log("resolved campaignId:", this.campaignId);
   // });


        onWillStart(async () => {
            await this.getAllMessages();
        });
    }

    // Pobranie wszystkich wiadomości dla kampanii
    async getAllMessages(body = '') {
        // Dodaj filtr campaign_id do domeny
        const domain = [
            ['campaign_id', '=', this.campaignId],
            ...(body ? [['partner_id', 'ilike', body]] : [])
        ];

        const ids = await this.orm.search(this.resModel, domain);
        const records = await this.orm.read(this.resModel, ids, [
            'body',
            'partner_id',
            'sms_gateway_response',
            'sms_gateway_response_human',
            'sender_number',
            'campaign_id' // Dodajemy campaign_id dla pewności
        ]);

        this.state.partners = records.map(r => ({
            id: r.id,
            body: r.partner_id[1],
            email: r.sms_gateway_response_human,
            sms_gateway_response_human: r.sms_gateway_response_human,
            campaign_id: r.campaign_id,
            message_body: r.body
        }));
        this.state.currentPage = 1;
    }

    async searchMessages(e) {
        if (e.type === 'click' || e.keyCode === 13) {
            const body = this.nameRef.el.value.trim();
            await this.getAllMessages(body);
            this.nameRef.el.value = '';
        }
    }

    // Metody paginacji
    paginatedMessages() {
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

CampaignMessagesAction.template = "odoo17_sms_plugin.CampaignMessagesTable";
registry.category("public_components").add("odoo17_sms_plugin.CampaignMessagesTable", CampaignMessagesAction);