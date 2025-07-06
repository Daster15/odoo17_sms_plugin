from odoo import models, fields, api
import logging
import requests

_logger = logging.getLogger(__name__)

class SmsMessage(models.Model):
    _name = 'sms.message'
    _description = 'SMS Message'

    template_id = fields.Many2one('sms.template', string='Template', help='Select SMS template')
    body = fields.Text(string='Message', required=True)
    char_count = fields.Integer(string='Chars', compute='_compute_char_count', store=True)
    partner_id = fields.Many2one('res.partner', string='Customer', index=True)
    group_ids = fields.Many2many('res.partner', string='Customer Groups')
    campaign_id = fields.Many2one('sms.campaign', string='Campaign', index=True)
    date_scheduled = fields.Datetime(string='Scheduled Date', index=True)
    state = fields.Selection([
        ('draft', 'Oczekujące'),
        ('scheduled', 'Zaplanowane'),
        ('sent', 'Wysłane'),
        ('delivered', 'Dostarczone'),
        ('failed', 'Nieudane')
    ], default='draft', index=True)
    message_type = fields.Selection(
        [('sms', 'SMS'), ('notification', 'Notification')],
        string='Message Type',
        default='sms'
    )

    external_id = fields.Char(string='External SMS ID', help='ID from SMS provider')

    sender_number = fields.Selection(
        selection='_get_available_sender_numbers',
        string='Sender Number',
        required=True,
        default=lambda self: self._get_default_sender_number()
    )

    def _get_available_sender_numbers(self):
        """Zwraca listę dostępnych numerów nadawcy"""
        return [
            ('+48123456789', 'CLIP (POXBOX)'),
            ('+48987654321', 'Marketing (+48 600 100 100)'),
            ('+48111222333', 'Support (+48 600 200 200)')
        ]

    def _get_default_sender_number(self):
        """Zwraca domyślny numer nadawcy"""
        numbers = self._get_available_sender_numbers()
        return numbers[0][0] if numbers else False

    # Hardcoded API credentials and URL
    API_USERNAME = 'user'
    API_PASSWORD = 'pass'
    API_URL = 'https://api.example.com'

    @api.depends('body')
    def _compute_char_count(self):
        for rec in self:
            rec.char_count = len(rec.body or '')

    @api.onchange('template_id')
    def _onchange_template(self):
        if self.template_id:
            self.body = self.template_id.body

    @api.model
    def _call_api(self, method, payload):
        endpoint = f"{self.API_URL.rstrip('/')}/smsapi/{method}"
        try:
            resp = requests.post(endpoint, json=payload, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _logger.error('%s error: %s', method, e)
            return False

    def action_send_now(self):
        for msg in self.filtered(lambda m: m.state in ('draft','scheduled')):
            messages = []
            if msg.partner_id and msg.partner_id.phone:
                messages.append({'destination_number': msg.partner_id.phone, 'text': msg.body})
            if msg.group_ids:
                for num in msg.group_ids.mapped('phone'):
                    messages.append({'destination_number': num, 'text': msg.body})
            payload = {
                'username': self.API_USERNAME,
                'password': self.API_PASSWORD,
                'messages': messages,
                'sch_date': msg.date_scheduled and msg.date_scheduled.strftime('%Y-%m-%d %H:%M:%S'),
                'test': '0'
            }
            result = self._call_api('send_multi_sms', payload)
            if result and result.get('msg_details'):
                detail = result['msg_details'][0]
                msg.external_id = detail.get('smsid')
                msg.state = 'sent'
            else:
                msg.state = 'failed'

    def action_schedule(self):
        for msg in self:
            if msg.state == 'draft':
                msg.state = 'scheduled'

    @api.model
    def send_sms_batch(self):
        to_send = self.search([
            ('state', '=', 'scheduled'),
            ('date_scheduled', '<=', fields.Datetime.now())
        ])
        to_send.action_send_now()

    @api.model
    def poll_delivery_status(self):
        to_check = self.search([('external_id', '!=', False), ('state', '=', 'sent')])
        for msg in to_check:
            payload = {
                'username': self.API_USERNAME,
                'password': self.API_PASSWORD,
                'criteria': [{'smsid': msg.external_id}]
            }
            result = self._call_api('query_sent_messages', payload)
            if result and result.get('messages'):
                info = result['messages'][0]
                status = info.get('status', '')
                if status == 'wysyłka zakończona sukcesem':
                    msg.state = 'delivered'
                elif 'błąd' in status:
                    msg.state = 'failed'
