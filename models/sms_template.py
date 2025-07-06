from odoo import models, fields

class SmsTemplate(models.Model):
    _name = 'sms.template'
    _description = 'SMS Template'

    name = fields.Char(string='Template Name', required=True)
    model_id = fields.Many2one('ir.model', string='Applies to')
    body = fields.Text(string='Message Content', required=True)
    lang = fields.Char(string='Language')
    active = fields.Boolean(default=True)
    default = fields.Boolean(string='Default Template')
