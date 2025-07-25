from odoo import models, fields, api, _
from odoo.exceptions import UserError
import logging

_logger = logging.getLogger(__name__)


class SmsCampaign(models.Model):
    _name = 'sms.campaign'
    _description = 'SMS Campaign'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Campaign Name', required=True, tracking=True)
    message_ids = fields.One2many('sms.message', 'campaign_id', string='Messages')
    date_start = fields.Datetime(string='Start Date')
    date_end = fields.Datetime(string='End Date')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('running', 'Running'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    #single_message = fields.Boolean(string='Single Message')
    single_message = fields.Text(string = 'Treść wiadomości',required = True,help = 'Wiadomość, która zostanie wysłana do każdego odbiorcy')

    sender_number = fields.Selection(
        selection='_get_available_campaning_sender_numbers',
        string='Sender Number',
        required=True,
        default=lambda self: self._get_available_campaning_sender_numbers()
    )

    def _get_available_campaning_sender_numbers(self):
        """Zwraca listę dostępnych numerów nadawcy"""
        return [
            ('+48123456789', 'CLIP (POXBOX)'),
            ('+48987654321', 'Marketing (+48 600 100 100)'),
            ('+48111222333', 'Support (+48 600 200 200)')
        ]


    # Pola statystyczne

    pending_count = fields.Integer(
        string='Pending',
        compute='_compute_stats',
        store=True,
    )

    message_count = fields.Integer(
        string='Total Messages',
        compute='_compute_stats',
        store=True
    )
    sent_count = fields.Integer(
        string='Sent Messages',
        compute='_compute_stats',
        store=True
    )
    delivered_count = fields.Integer(
        string='Delivered',
        compute='_compute_stats',
        store=True
    )
    failed_count = fields.Integer(
        string='Failed',
        compute='_compute_stats',
        store=True
    )
    delivery_rate = fields.Float(
        string='Delivery Rate (%)',
        compute='_compute_stats',
        store=True,
        group_operator="avg"
    )
    scheduled_count = fields.Integer(
        string='Scheduled',
        compute='_compute_stats',
        store=True
    )

    @api.depends('message_ids', 'message_ids.state', 'message_ids.sms_gateway_response')
    def _compute_stats(self):
        for campaign in self:
            messages = campaign.message_ids
            # Ile w ogóle wiadomości
            campaign.message_count = len(messages)

            # Wysłane: stan 'sent' lub 'delivered'
            campaign.sent_count = len(
                messages.filtered(lambda m: m.state in ('sent', 'delivered'))
            )

            # Dostarczone: na podstawie sms_gateway_response
            def _is_delivered(m):
                if not m.sms_gateway_response:
                    return False
                txt = m.sms_gateway_response.lower()
                return 'zakończona sukcesem' in txt or 'potwierdziło wysyłkę' in txt

            campaign.delivered_count = len(
                messages.filtered(_is_delivered)
            )

            # Nieudane
            campaign.failed_count = len(
                messages.filtered(lambda m: m.state == 'failed')
            )

            # Zaplanowane
            campaign.scheduled_count = len(
                messages.filtered(lambda m: m.state == 'scheduled')
            )

            # % dostarczeń
            if campaign.message_count:
                campaign.delivery_rate = (
                    campaign.delivered_count / campaign.message_count * 100.0
                )
            else:
                campaign.delivery_rate = 0.0

    def action_start(self):
        """Uruchamia kampanię, wysyła wszystkie wiadomości i kończy kampanię."""
        now = fields.Datetime.now()
        for campaign in self:
            if campaign.state != 'draft':
                continue
            # 1) Zmiana stanu i data startu
            campaign.write({
                'state': 'running',
                'date_start': now,
            })
            # 2) Wysyłka SMS-ów
            to_send = campaign.message_ids.filtered(
                lambda m: m.state in ('draft', 'scheduled')
            )
            to_send.action_send_now()
            # 3) Jeżeli wszystkie są już wysłane/dostarczone, kończymy kampanię
            if campaign.message_ids and all(
                m.state in ('sent', 'delivered') for m in campaign.message_ids
            ):
                campaign.write({
                    'state': 'done',
                    'date_end': fields.Datetime.now(),
                })
                campaign.message_ids.retrieve_gateway_response()
        return True

    def action_stop(self):
        self.write({
            'state': 'done',
            'date_end': fields.Datetime.now()
        })

    def action_cancel(self):
        self.write({
            'state': 'cancelled',
            'date_end': fields.Datetime.now()
        })

    def action_retry_failed(self):
        failed_messages = self.message_ids.filtered(lambda m: m.state == 'failed')
        if failed_messages:
            failed_messages.action_send_now()
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _("Retry Started"),
                    'message': _("%d failed messages are being retried") % len(failed_messages),
                    'type': 'success',
                }
            }