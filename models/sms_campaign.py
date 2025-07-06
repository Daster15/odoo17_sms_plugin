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

    @api.depends('message_ids', 'message_ids.state')
    def _compute_stats(self):
        for campaign in self:
            messages = campaign.message_ids
            campaign.message_count = len(messages)
            campaign.sent_count = len(messages.filtered(lambda m: m.state in ['sent', 'delivered']))
            campaign.delivered_count = len(messages.filtered(lambda m: m.state == 'delivered'))
            campaign.failed_count = len(messages.filtered(lambda m: m.state == 'failed'))
            campaign.scheduled_count = len(messages.filtered(lambda m: m.state == 'scheduled'))

            if campaign.message_count > 0:
                campaign.delivery_rate = (campaign.delivered_count / campaign.message_count) * 100
            else:
                campaign.delivery_rate = 0.0

    def action_start(self):
        for campaign in self:
            if not campaign.message_ids:
                raise UserError(_("Cannot start an empty campaign - add messages first"))

            campaign.write({
                'state': 'running',
                'date_start': fields.Datetime.now()
            })
            # Automatyczne wysłanie wiadomości w stanie draft
            campaign.message_ids.filtered(
                lambda m: m.state == 'draft'
            ).action_send_now()

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