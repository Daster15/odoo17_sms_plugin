from odoo import models, fields, api
from datetime import datetime
from odoo.tools import format_datetime


class SmsConversation(models.Model):
    _name = 'sms.conversation'
    _description = 'SMS Conversation'
    _order = 'last_message_date desc'


    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True)
    phone_number = fields.Char(string='Phone Number', related='partner_id.phone', store=True)
    message_ids = fields.One2many('sms.conversation.line', 'conversation_id', string='Messages')
    message_count = fields.Integer(string='Message Count', compute='_compute_message_count', store=True)
    last_message_date = fields.Datetime(string='Last Message', compute='_compute_last_message', store=True)
    state = fields.Selection([
        ('active', 'Active'),
        ('closed', 'Closed'),
        ('spam', 'Spam')
    ], string='Status', default='active')
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)
    message_preview = fields.Text(
        string='Preview',
        compute='_compute_message_preview',
        store=True,
    )

    @api.depends('message_ids.body', 'message_ids.date', 'message_ids.create_date', 'message_ids.direction')
    def _compute_message_preview(self):
        for conv in self:
            # pobierz maks. 3 najnowsze wiadomości
            msgs = conv.message_ids.sorted(
                key=lambda m: m.date or m.create_date,
                reverse=True
            )[:10]
            lines = []
            for m in msgs:
                arrow = '←' if m.direction == 'in' else '→'
                dt = m.date or m.create_date
                time_str = format_datetime(self.env, dt, dt_format='HH:mm') if dt else ''
                body = (m.body or '').strip()
                if len(body) > 50:
                    body = body[:47] + '...'
                lines.append(f"{arrow}{time_str} {body}")
            conv.message_preview = "\n".join(lines)

    @api.depends('message_ids')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    @api.depends('message_ids.date')
    def _compute_last_message(self):
        for rec in self:
            rec.last_message_date = rec.message_ids and max(rec.message_ids.mapped('date')) or False

    def action_new_message(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'New Message to {self.partner_id.name}',
            'res_model': 'sms.conversation.line',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_conversation_id': self.id,
                'default_partner_id': self.partner_id.id,
                'default_direction': 'out',
            }
        }


class SmsConversationLine(models.Model):
    _name = 'sms.conversation.line'
    _description = 'SMS Conversation Line'
    _order = 'date asc'

    conversation_id = fields.Many2one('sms.conversation', string='Conversation', ondelete='cascade')
    partner_id = fields.Many2one('res.partner', string='Partner', related='conversation_id.partner_id', store=True)
    body = fields.Text(string='Message', required=True)
    date = fields.Datetime(string='Date', default=fields.Datetime.now, index=True)
    direction = fields.Selection([
        ('in', 'Incoming'),
        ('out', 'Outgoing')
    ], string='Direction', required=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('failed', 'Failed')
    ], string='Status', default='draft')
    external_id = fields.Char(string='External ID', help='Message ID from provider')
    user_id = fields.Many2one('res.users', string='Agent', default=lambda self: self.env.user)



    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        # Automatically mark outgoing messages as sent
        for rec in records:
            if rec.direction == 'out' and rec.status == 'draft':
                rec.status = 'sent'
        return records