/** @odoo-module **/
import { registry } from '@web/core/registry';
import { X2ManyField } from '@web/views/fields/x2many/x2many_field';
import { useService } from '@web/core/utils/hooks';
import { _t } from '@web/core/l10n/translation';

export class ConversationPreviewWidget extends X2ManyField {
    static template = 'ConversationPreviewWidget';

    setup() {
        super.setup();
        this.time = useService('time');
        const opts = this.nodeOptions || {};
        this.displayFields = opts.display_fields || ['body'];
        this.displayLimit = parseInt(opts.display_limit, 10) || 3;
        this.maxChars = parseInt(opts.max_chars, 10) || 50;
        this.dateField = opts.date_field || 'date';
        this.directionField = opts.direction_field || 'direction';
    }

    get records() {
        return this.props.value.records || [];
    }
    get sortedRecords() {
        return this.records.slice().sort((a, b) => {
            const aD = new Date(a.data[this.dateField]   || a.data.create_date);
            const bD = new Date(b.data[this.dateField]   || b.data.create_date);
            return bD - aD;
        });
    }
    get toDisplay() {
        return this.sortedRecords.slice(0, this.displayLimit);
    }
    get moreCount() {
        return Math.max(0, this.records.length - this.displayLimit);
    }

    formatTime(rec) {
        const d = rec.data[this.dateField];
        return d ? this.time.formatDate(d, 'time') : '';
    }
    getIconClass(rec) {
        return rec.data[this.directionField] === 'in'
            ? 'fa fa-arrow-left text-success'
            : 'fa fa-arrow-right text-primary';
    }
    getText(rec) {
        const txt = this.displayFields
            .map(f => rec.data[f] || '')
            .join(' ')
            .trim();
        return txt.length > this.maxChars
            ? txt.substring(0, this.maxChars) + '...'
            : txt;
    }
}

registry.category('fields').add('conversation_preview', ConversationPreviewWidget);
