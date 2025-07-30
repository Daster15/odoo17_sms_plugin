/** @odoo-module **/
import publicWidget from '@web/legacy/js/public/public_widget';

publicWidget.registry.SmsCharCount = publicWidget.Widget.extend({
    selector: 'form.row.g-3',  // lub inny wrapper Twojego formularza
    events: {
        'input textarea[name="single_message"]': '_onInput',
    },
    start() {
        this._super(...arguments);
        this.$charCount = this.$el.find('.sms_char_count');
        this._updateCount();
    },
    _onInput() { this._updateCount(); },
    _updateCount() {
        const txt = this.$el.find('textarea[name="single_message"]').val() || '';
        this.$charCount.text(`${txt.length} znaków`);
    },
});
